"""
Full-corpus live test. Same ingestion pattern as run_accuracy_batch.py
(reuses the existing Run row, creates a Document per file, calls
process_document directly) but with the sampling caps removed --
processes every name_and_ssn (primary) and name_variant (variant) row in
document_manifest.csv, plus every row in negatives.csv and
quarantine_expected.csv.

Resumable: if full_results.json already exists, filenames already
recorded in it are skipped, so an interrupted run can just be re-launched
with the same command. Progress is saved to disk every 10 documents, not
just at the end, so a Ctrl+C or crash partway through loses at most a
handful of documents' worth of work.

Run from backend/:
    python run_full_corpus.py
"""
import csv
import json
import time
from pathlib import Path

from app.db.base import SessionLocal
from app.db.models import Run, Document
from app.services.pipeline import process_document
from app.services.exposure.flags import compute_flags_for_run

RESULTS_PATH = Path("full_results.json")
SAVE_EVERY = 10

db = SessionLocal()
run = db.query(Run).first()
run.status = "running"
db.commit()

corpus_root = Path("../data/corpus")
manifest_root = Path("../data/manifest")

file_index = {p.name: p for p in corpus_root.rglob("*") if p.is_file()}


def load_csv(name):
    with open(manifest_root / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


doc_manifest = load_csv("document_manifest.csv")
negatives = load_csv("negatives.csv")
quarantine_expected = load_csv("quarantine_expected.csv")

primaries = {}
for row in doc_manifest:
    if row["category"] == "name_and_ssn" and row["person_id"] not in primaries:
        primaries[row["person_id"]] = row
primary_all = list(primaries.values())

variant_all = [r for r in doc_manifest if r["category"] == "name_variant" and r["person_id"] in primaries]

negative_all = negatives
quarantine_all = quarantine_expected

batch = (
    [(r["filename"], "primary", r["person_id"]) for r in primary_all]
    + [(r["filename"], "variant", r["person_id"]) for r in variant_all]
    + [(r["filename"], "negative", None) for r in negative_all]
    + [(r["filename"], "quarantine_expected", r.get("reason")) for r in quarantine_all]
)

print(f"Full corpus batch: {len(primary_all)} primary, {len(variant_all)} variant, "
      f"{len(negative_all)} negative, {len(quarantine_all)} quarantine_expected "
      f"= {len(batch)} total documents")

# --- resume support ---
already_done = set()
results = []
if RESULTS_PATH.exists():
    prev = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    results = prev.get("results", [])
    already_done = {r[0] for r in results}
    print(f"Resuming: {len(already_done)} documents already recorded in {RESULTS_PATH}, skipping those.")

tokens_before = run.tokens_used_total
spend_before = run.spend_total_usd
start = time.time()

processed_this_run = 0
skipped_missing = []

for i, (filename, kind, meta) in enumerate(batch, 1):
    if filename in already_done:
        continue
    path = file_index.get(filename)
    if path is None:
        print(f"SKIP (not found in corpus): {filename}")
        skipped_missing.append(filename)
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

    print(f"[{i}/{len(batch)}] [{kind}] {filename} -> {status} ({elapsed:.1f}s)")
    results.append((filename, kind, meta, document.id, status))
    processed_this_run += 1

    if processed_this_run % SAVE_EVERY == 0:
        db.refresh(run)
        RESULTS_PATH.write_text(json.dumps({
            "results": results,
            "tokens_used_so_far": run.tokens_used_total - tokens_before,
            "spend_used_so_far": run.spend_total_usd - spend_before,
            "elapsed_so_far": time.time() - start,
            "primary_sample": [(r["filename"], r["person_id"]) for r in primary_all],
            "variant_sample": [(r["filename"], r["person_id"], r["planted_value"]) for r in variant_all],
            "negative_sample": [(r["filename"], r["negative_type"]) for r in negative_all],
            "quarantine_sample": [(r["filename"], r["reason"]) for r in quarantine_all],
        }, indent=2), encoding="utf-8")
        print(f"  ...saved progress ({len(results)}/{len(batch)} total recorded)")

elapsed_total = time.time() - start
db.refresh(run)
tokens_used = run.tokens_used_total - tokens_before
spend_used = run.spend_total_usd - spend_before

flags_written = compute_flags_for_run(db, run.id)

print(f"\n=== Full corpus run complete: {processed_this_run} newly processed this session, "
      f"{len(results)} total recorded, {elapsed_total:.1f}s this session ===")
print(f"Tokens used this session: {tokens_used}, spend: ${spend_used:.4f}")
print(f"Flags computed/updated: {flags_written}")
if skipped_missing:
    print(f"Filenames referenced in manifest but not found in corpus ({len(skipped_missing)}): {skipped_missing[:20]}"
          + (" ..." if len(skipped_missing) > 20 else ""))

RESULTS_PATH.write_text(json.dumps({
    "results": results,
    "tokens_used_so_far": tokens_used,
    "spend_used_so_far": spend_used,
    "elapsed_so_far": elapsed_total,
    "primary_sample": [(r["filename"], r["person_id"]) for r in primary_all],
    "variant_sample": [(r["filename"], r["person_id"], r["planted_value"]) for r in variant_all],
    "negative_sample": [(r["filename"], r["negative_type"]) for r in negative_all],
    "quarantine_sample": [(r["filename"], r["reason"]) for r in quarantine_all],
}, indent=2), encoding="utf-8")
print("Saved full_results.json")

db.close()
