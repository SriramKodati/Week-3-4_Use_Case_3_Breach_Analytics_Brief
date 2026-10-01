"""
Two-configuration cost/accuracy comparison for Section 10's outstanding
commitment: current tiering (tier1_escalation_threshold=0.7) vs. a more
aggressive escalation threshold (0.9), on the SAME sample of documents,
each under its own fresh Run row so tokens/cost are cleanly attributable.

Sample: every distinct filename in document_manifest.csv carrying one of
the categories the full-corpus run found weakest --
financial_account_scanned, name_and_ssn_scanned, driver_license_scanned,
passport_scanned, name_variant, name_only_partial -- capped at 60 files so
both passes finish in reasonable time. This is a targeted comparison, not
a full-corpus one; the report should say so explicitly.

Run from backend/:
    python run_two_config_comparison.py
"""
import csv
import json
import time
from pathlib import Path

from app.db.base import SessionLocal
from app.db.models import Run, Document, Extraction, IdentityLink
from app.services.pipeline import process_document
from app.core.config import settings

CAP = 60
RESULTS_PATH = Path("two_config_results.json")

corpus_root = Path("../data/corpus")
manifest_root = Path("../data/manifest")

file_index = {p.name: p for p in corpus_root.rglob("*") if p.is_file()}


def load_csv(name):
    with open(manifest_root / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


doc_manifest = load_csv("document_manifest.csv")

WEAK_CATEGORIES = {
    "financial_account_scanned", "name_and_ssn_scanned", "driver_license_scanned",
    "passport_scanned", "name_variant", "name_only_partial",
}

by_filename = {}
for row in doc_manifest:
    by_filename.setdefault(row["filename"], []).append(row)

sample_filenames = [f for f, rows in by_filename.items() if any(r["category"] in WEAK_CATEGORIES for r in rows)]
sample_filenames = sample_filenames[:CAP]
print(f"Sample: {len(sample_filenames)} documents (categories: {WEAK_CATEGORIES})")

sample_rows = {f: by_filename[f] for f in sample_filenames}


def run_config(label: str, threshold: float):
    print(f"\n=== Running config '{label}' (tier1_escalation_threshold={threshold}) ===")
    settings.tier1_escalation_threshold = threshold

    db = SessionLocal()
    run = Run(status="running", token_budget=500_000, spend_budget_usd=20.0)
    db.add(run)
    db.commit()

    start = time.time()
    results = []
    for i, filename in enumerate(sample_filenames, 1):
        path = file_index.get(filename)
        if path is None:
            print(f"  SKIP (not found): {filename}")
            continue
        document = Document(run_id=run.id, filename=filename, format="unknown", status="queued")
        db.add(document)
        db.commit()
        t0 = time.time()
        try:
            result = process_document(db, document, str(path))
            status = result.get("status")
        except Exception as e:
            db.rollback()
            status = f"error: {e}"
        elapsed = time.time() - t0
        results.append((filename, document.id, status))
        if i % 10 == 0:
            print(f"  [{i}/{len(sample_filenames)}] ... ({elapsed:.1f}s last doc)")

    db.refresh(run)
    elapsed_total = time.time() - start

    total_checked = 0
    total_hit = 0
    for filename, document_id, status in results:
        exs = db.query(Extraction).filter(Extraction.document_id == document_id).all()
        vals = [e.raw_value for e in exs if e.raw_value]
        for row in sample_rows[filename]:
            planted = row.get("planted_value", "")
            if not planted:
                continue
            total_checked += 1
            if any(planted in v or v in planted for v in vals):
                total_hit += 1

    print(f"  Config '{label}': {len(results)} docs, {elapsed_total:.1f}s, "
          f"tokens={run.tokens_used_total}, spend=${run.spend_total_usd:.4f}, "
          f"recall={total_hit}/{total_checked} ({total_hit/total_checked*100:.1f}%)")

    db.close()
    return {
        "label": label,
        "threshold": threshold,
        "run_id": run.id,
        "documents": len(results),
        "elapsed_seconds": elapsed_total,
        "tokens_used": run.tokens_used_total,
        "spend_usd": run.spend_total_usd,
        "recall_checked": total_checked,
        "recall_hit": total_hit,
        "results": results,
    }


config_a = run_config("current (0.7)", 0.7)
config_b = run_config("aggressive (0.9)", 0.9)

print("\n" + "=" * 70)
print("TWO-CONFIGURATION COMPARISON SUMMARY")
print("=" * 70)
for c in (config_a, config_b):
    tok_per_doc = c["tokens_used"] / c["documents"] if c["documents"] else 0
    print(f"{c['label']:20s} docs={c['documents']:3d}  tokens={c['tokens_used']:7d}  "
          f"tok/doc={tok_per_doc:6.1f}  recall={c['recall_hit']}/{c['recall_checked']} "
          f"({c['recall_hit']/c['recall_checked']*100:.1f}%)  time={c['elapsed_seconds']:.1f}s")

token_delta = config_b["tokens_used"] - config_a["tokens_used"]
recall_delta = (config_b["recall_hit"] / config_b["recall_checked"]) - (config_a["recall_hit"] / config_a["recall_checked"])
print(f"\nToken delta (B - A): {token_delta:+d} ({token_delta / config_a['tokens_used'] * 100:+.1f}% vs config A)")
print(f"Recall delta (B - A): {recall_delta*100:+.1f} percentage points")

RESULTS_PATH.write_text(json.dumps({"config_a": config_a, "config_b": config_b}, indent=2, default=str), encoding="utf-8")
print(f"\nSaved {RESULTS_PATH}")
