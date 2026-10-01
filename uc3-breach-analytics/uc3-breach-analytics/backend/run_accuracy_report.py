"""
Ground-truth comparison for the UC3 accuracy batch (run_accuracy_batch.py).

Uses the document_id values already recorded in batch_results.json (not
filename lookups) so it can't be confused by the fact that "primary" and
"negative" samples happen to share filenames like eml_case_0002.eml across
different corpus folders -- they're different Document rows.

Run from backend/:
    python run_accuracy_report.py
"""
import csv
import json
from pathlib import Path

from app.db.base import SessionLocal
from app.db.models import Document, Extraction, IdentityLink, Person, Flag

BASE = Path(__file__).parent


def find_manifest():
    for p in BASE.rglob("document_manifest.csv"):
        return p
    for p in BASE.parent.rglob("document_manifest.csv"):
        return p
    raise SystemExit("Could not find document_manifest.csv anywhere under backend/ or its parent.")


def load_manifest(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    by_filename = {}
    for row in rows:
        by_filename.setdefault(row["filename"], row)
    return by_filename


def main():
    results_path = BASE / "full_results.json"
    batch = json.loads(results_path.read_text(encoding="utf-8"))
    manifest_by_filename = load_manifest(find_manifest())

    db = SessionLocal()

    def raw_values_for(document_id):
        exs = db.query(Extraction).filter(Extraction.document_id == document_id).all()
        return [e.raw_value for e in exs if e.raw_value]

    def person_id_for(document_id):
        exs = db.query(Extraction).filter(Extraction.document_id == document_id).all()
        ex_ids = [e.id for e in exs]
        if not ex_ids:
            return None
        links = db.query(IdentityLink).filter(IdentityLink.extraction_id.in_(ex_ids)).all()
        pids = {l.person_id for l in links}
        return next(iter(pids)) if len(pids) == 1 else None

    rows = batch["results"]

    report = {
        "extraction_recall": {"checked": 0, "found": 0, "misses": []},
        "entity_linking": {"checked": 0, "correct": 0, "mismatches": []},
        "false_positives": {"checked": 0, "flagged": 0, "flagged_docs": []},
        "quarantine_accuracy": {"checked": 0, "correct": 0, "mismatches": []},
    }

    primary_person_map = {}
    for filename, category, manifest_pid, document_id, status in rows:
        if category != "primary":
            continue
        manifest_row = manifest_by_filename.get(filename)
        report["extraction_recall"]["checked"] += 1
        if manifest_row and manifest_row.get("planted_value"):
            planted = manifest_row["planted_value"]
            vals = raw_values_for(document_id)
            found = any(planted in v or v in planted for v in vals)
            if found:
                report["extraction_recall"]["found"] += 1
            else:
                report["extraction_recall"]["misses"].append(
                    {"filename": filename, "category": "primary", "planted_value": planted, "extracted_values": vals}
                )
        else:
            report["extraction_recall"]["misses"].append(
                {"filename": filename, "category": "primary", "reason": "no manifest row / no planted_value"}
            )

        actual_pid = person_id_for(document_id)
        if actual_pid:
            primary_person_map[manifest_pid] = actual_pid

    for filename, category, manifest_pid, document_id, status in rows:
        if category != "variant":
            continue
        manifest_row = manifest_by_filename.get(filename)
        report["extraction_recall"]["checked"] += 1
        if manifest_row and manifest_row.get("planted_value"):
            planted = manifest_row["planted_value"]
            vals = raw_values_for(document_id)
            found = any(planted in v or v in planted for v in vals)
            if found:
                report["extraction_recall"]["found"] += 1
            else:
                report["extraction_recall"]["misses"].append(
                    {"filename": filename, "category": "variant", "planted_value": planted, "extracted_values": vals}
                )
        else:
            report["extraction_recall"]["misses"].append(
                {"filename": filename, "category": "variant", "reason": "no manifest row / no planted_value"}
            )

        report["entity_linking"]["checked"] += 1
        actual_pid = person_id_for(document_id)
        expected_pid = primary_person_map.get(manifest_pid)
        if actual_pid is not None and expected_pid is not None and actual_pid == expected_pid:
            report["entity_linking"]["correct"] += 1
        else:
            report["entity_linking"]["mismatches"].append(
                {
                    "filename": filename,
                    "manifest_person_id": manifest_pid,
                    "status": status,
                    "actual_person_id": actual_pid,
                    "expected_person_id (from primary doc)": expected_pid,
                }
            )

    for filename, category, tag, document_id, status in rows:
        if category != "negative":
            continue
        report["false_positives"]["checked"] += 1
        pid = person_id_for(document_id)
        flagged = False
        if pid:
            flags = db.query(Flag).filter(Flag.person_id == pid, Flag.is_exposed == True).all()
            flagged = len(flags) > 0
        if flagged:
            report["false_positives"]["flagged"] += 1
            report["false_positives"]["flagged_docs"].append(
                {"filename": filename, "negative_type": tag, "status": status, "person_id": pid}
            )

    for filename, category, expected_reason, document_id, status in rows:
        if category != "quarantine_expected":
            continue
        report["quarantine_accuracy"]["checked"] += 1
        doc = db.get(Document, document_id)
        actual_reason = doc.quarantine_reason if doc else None
        actual_status = doc.status if doc else None
        ok = bool(
            actual_reason
            and expected_reason
            and (expected_reason.lower() in actual_reason.lower() or actual_reason.lower() in expected_reason.lower())
        )
        if ok:
            report["quarantine_accuracy"]["correct"] += 1
        else:
            report["quarantine_accuracy"]["mismatches"].append(
                {
                    "filename": filename,
                    "expected_reason": expected_reason,
                    "actual_reason": actual_reason,
                    "actual_status": actual_status,
                }
            )

    db.close()

    er, el, fp, qa = (
        report["extraction_recall"],
        report["entity_linking"],
        report["false_positives"],
        report["quarantine_accuracy"],
    )

    def pct(n, d):
        return f"{(n / d * 100 if d else 0):.1f}%"

    print("=" * 60)
    print("GROUND-TRUTH ACCURACY REPORT")
    print("=" * 60)

    print(f"\n(a) PII extraction recall: {er['found']}/{er['checked']} ({pct(er['found'], er['checked'])})")
    for m in er["misses"]:
        print(f"    MISS: {m}")

    print(
        f"\n(b) Entity-resolution linking correctness (variant -> same Person as its primary doc): "
        f"{el['correct']}/{el['checked']} ({pct(el['correct'], el['checked'])})"
    )
    for m in el["mismatches"]:
        print(f"    MISMATCH: {m}")

    print(f"\n(c) False positives on negative sample: {fp['flagged']}/{fp['checked']} flagged (want 0)")
    for d in fp["flagged_docs"]:
        print(f"    FALSE POSITIVE: {d}")

    print(
        f"\n(d) Quarantine reason correctness: {qa['correct']}/{qa['checked']} ({pct(qa['correct'], qa['checked'])})"
    )
    for m in qa["mismatches"]:
        print(f"    MISMATCH: {m}")

    out_path = BASE / "accuracy_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()
