"""
Full per-category ground-truth comparison against full_results.json.

Unlike the earlier run_accuracy_report.py (which only checked the single
name_and_ssn/name_variant planted value per document), this groups
document_manifest.csv by filename -- since it's one row per PLANTED FIELD,
not one row per document -- and checks recall for every planted field
(ssn, phone, email, address, driver_license, financial_account, medical,
passport, login_credential, and their _scanned variants) against that
document's actual Extraction rows. Reports recall broken down by category.

Also keeps the entity-linking (variant -> same Person as primary),
false-positive (negative sample), and quarantine-reason checks from
before, now against the full processed set.

Run from backend/:
    python run_full_accuracy_report.py
"""
import csv
import json
from collections import defaultdict, Counter
from pathlib import Path

from app.db.base import SessionLocal
from app.db.models import Document, Extraction, IdentityLink, Flag

BASE = Path(__file__).parent
manifest_root = Path("../data/manifest")


def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    batch = json.loads((BASE / "full_results.json").read_text(encoding="utf-8"))
    results = batch["results"]  # [filename, kind, meta, document_id, status]

    doc_manifest = load_csv(manifest_root / "document_manifest.csv")

    by_filename = defaultdict(list)
    for row in doc_manifest:
        by_filename[row["filename"]].append(row)

    primary_filenames = {}
    variant_filenames = {}
    for filename, rows in by_filename.items():
        categories = {r["category"] for r in rows}
        person_id = rows[0]["person_id"]
        if categories & {"name_and_ssn", "name_and_ssn_scanned"}:
            primary_filenames[filename] = person_id
        elif "name_variant" in categories:
            variant_filenames[filename] = person_id

    doc_id_by_filename = {}
    status_by_filename = {}
    kind_by_filename = {}
    for filename, kind, meta, document_id, status in results:
        doc_id_by_filename[filename] = document_id
        status_by_filename[filename] = status
        kind_by_filename[filename] = kind

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

    category_totals = Counter()
    category_hits = Counter()
    misses = []

    for filename, rows in by_filename.items():
        if filename not in doc_id_by_filename:
            continue
        document_id = doc_id_by_filename[filename]
        vals = raw_values_for(document_id)
        for row in rows:
            category = row["category"]
            planted = row.get("planted_value", "")
            if not planted:
                continue
            category_totals[category] += 1
            found = any(planted in v or v in planted for v in vals)
            if found:
                category_hits[category] += 1
            else:
                misses.append({"filename": filename, "category": category, "planted_value": planted})

    primary_person_map = {}
    for filename, manifest_pid in primary_filenames.items():
        document_id = doc_id_by_filename.get(filename)
        if document_id is None:
            continue
        pid = person_id_for(document_id)
        if pid:
            primary_person_map[manifest_pid] = pid

    linking_checked = 0
    linking_correct = 0
    linking_mismatches = []
    for filename, manifest_pid in variant_filenames.items():
        document_id = doc_id_by_filename.get(filename)
        if document_id is None:
            continue
        linking_checked += 1
        actual_pid = person_id_for(document_id)
        expected_pid = primary_person_map.get(manifest_pid)
        if actual_pid is not None and expected_pid is not None and actual_pid == expected_pid:
            linking_correct += 1
        else:
            linking_mismatches.append({
                "filename": filename,
                "manifest_person_id": manifest_pid,
                "status": status_by_filename.get(filename),
                "actual_person_id": actual_pid,
                "expected_person_id": expected_pid,
            })

    negative_filenames = [f for f, k in kind_by_filename.items() if k == "negative"]
    fp_checked = len(negative_filenames)
    fp_flagged = []
    for filename in negative_filenames:
        document_id = doc_id_by_filename[filename]
        pid = person_id_for(document_id)
        if pid:
            flags = db.query(Flag).filter(Flag.person_id == pid, Flag.is_exposed == True).all()
            if flags:
                fp_flagged.append(filename)

    negatives_csv = load_csv(manifest_root / "negatives.csv")
    neg_type_by_filename = {}
    for r in negatives_csv:
        neg_type_by_filename.setdefault(r["filename"], r.get("negative_type"))
    fp_by_type = Counter(neg_type_by_filename.get(f) for f in fp_flagged)
    all_neg_types = Counter(neg_type_by_filename.get(f) for f in negative_filenames)

    quarantine_csv = load_csv(manifest_root / "quarantine_expected.csv")
    q_checked = 0
    q_correct = 0
    q_mismatches = []
    for row in quarantine_csv:
        filename = row["filename"]
        document_id = doc_id_by_filename.get(filename)
        if document_id is None:
            continue
        q_checked += 1
        doc = db.get(Document, document_id)
        actual_reason = doc.quarantine_reason if doc else None
        expected_reason = row.get("reason")
        ok = bool(
            actual_reason and expected_reason
            and (expected_reason.lower() in actual_reason.lower() or actual_reason.lower() in expected_reason.lower())
        )
        if ok:
            q_correct += 1
        else:
            q_mismatches.append({"filename": filename, "expected": expected_reason, "actual": actual_reason})

    db.close()

    total_checked = sum(category_totals.values())
    total_hit = sum(category_hits.values())

    print("=" * 70)
    print("FULL-CORPUS GROUND-TRUTH ACCURACY REPORT")
    print("=" * 70)

    print(f"\n(a) Overall PII field extraction recall: {total_hit}/{total_checked} "
          f"({total_hit/total_checked*100:.1f}%)")
    print("    By category:")
    for cat in sorted(category_totals, key=lambda c: -category_totals[c]):
        h, t = category_hits[cat], category_totals[cat]
        print(f"      {cat:32s} {h:4d}/{t:4d}  ({h/t*100:5.1f}%)")
    print(f"    ({len(misses)} total misses; showing up to 20)")
    for m in misses[:20]:
        print(f"      MISS: {m}")

    print(f"\n(b) Entity-linking (variant -> same Person as primary): "
          f"{linking_correct}/{linking_checked} ({linking_correct/linking_checked*100:.1f}%)")
    print(f"    ({len(linking_mismatches)} mismatches; showing up to 15)")
    for m in linking_mismatches[:15]:
        print(f"      MISMATCH: {m}")

    print(f"\n(c) False positives on negative sample: {len(fp_flagged)}/{fp_checked} flagged (want 0)")
    print(f"    By negative_type -- flagged: {dict(fp_by_type)}")
    print(f"    By negative_type -- total in sample: {dict(all_neg_types)}")

    print(f"\n(d) Quarantine reason correctness: {q_correct}/{q_checked} "
          f"({q_correct/q_checked*100:.1f}%)" if q_checked else "\n(d) no quarantine data")
    for m in q_mismatches:
        print(f"      MISMATCH: {m}")

    out = {
        "extraction_recall": {
            "total_checked": total_checked,
            "total_hit": total_hit,
            "by_category": {c: {"hit": category_hits[c], "total": category_totals[c]} for c in category_totals},
            "misses": misses,
        },
        "entity_linking": {
            "checked": linking_checked,
            "correct": linking_correct,
            "mismatches": linking_mismatches,
        },
        "false_positives": {
            "checked": fp_checked,
            "flagged": fp_flagged,
            "flagged_by_type": dict(fp_by_type),
            "all_by_type": dict(all_neg_types),
        },
        "quarantine_accuracy": {
            "checked": q_checked,
            "correct": q_correct,
            "mismatches": q_mismatches,
        },
    }
    (BASE / "full_accuracy_report.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("\nSaved full_accuracy_report.json")


if __name__ == "__main__":
    main()
