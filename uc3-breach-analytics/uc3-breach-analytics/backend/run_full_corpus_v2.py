"""
Full-corpus live test, v2 -- extends the first pass (which only processed
name_and_ssn / name_variant filenames) to cover EVERY distinct filename in
document_manifest.csv, since that CSV is one row per PLANTED FIELD, not one
row per document: a single filename can have separate rows for its
name_and_ssn, phone, email, address, driver_license, financial_account,
medical, passport, and login_credential fields (plus _scanned variants),
and there are ~300 filenames whose only manifest rows are a single-field
category that the first pass never touched at all.

Resumable against the SAME full_results.json the first pass wrote -- any
filename already recorded there is skipped, so this only processes the
newly-identified documents.

Run from backend/:
    python run_full_corpus_v2.py
"""
import csv
import json
import time
from collections import defaultdict
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

by_filename = defaultdict(list)
for row in doc_manifest:
    by_filename[row["filename"]].append(row)

primary_filenames = {}
variant_filenames = {}
other_filenames = {}

for filename, rows in by_filename.items():
    categories = {r["category"] for r in rows}
    person_id = rows[0]["person_id"]
    if categories & {"name_and_ssn", "name_and_ssn_scanned"}:
        primary_filenames[filename] = person_id
    elif "name_variant" in categories:
        variant_filenames[filename] = person_id
    else:
        other_filenames[filename] = person_id

batch = (
    [(f, "primary", pid) for f, pid in primary_filenames.items()]
    + [(f, "variant", pid) for f, pid in variant_filenames.items()]
    + [(f, "other_category", pid) for f, pid in other_filenames.items()]
    + [(r["filename"], "negative", None) for r in negatives]
    + [(r["filename"], "quarantine_expected", r.get("reason")) for r in quarantine_expected]
)

print(f"Full manifest batch: {len(primary_filenames)} primary, {len(variant_filenames)} variant, "
      f"{len(other_filenames)} other_category, {len(negatives)} negative, "
      f"{len(quarantine_expected)} quarantine_expected = {len(batch)} total document entries")

already_done = set()
results = []
if RESULTS_PATH.exists():
    prev = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    results = prev.get("results", [])
    already_done = {r[0] for r in results}
    print(f"Resuming: {len(already_done)} filenames already recorded, skipping those.")

to_process = [(f, k, m) for f, k, m in batch if f not in already_done]
print(f"Newly to process this session: {len(to_process)}")

tokens_before = run.tokens_used_total
spend_before = run.spend_total_usd
start = time.time()

processed_this_run = 0
skipped_missing = []

for i, (filename, kind, meta) in enumerate(to_process, 1):
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

    print(f"[{i}/{len(to_process)}] [{kind}] {filename} -> {status} ({elapsed:.1f}s)")
    results.append((filename, kind, meta, document.id, status))
    processed_this_run += 1

    if processed_this_run % SAVE_EVERY == 0:
        db.refresh(run)
        RESULTS_PATH.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
        print(f"  ...saved progress ({len(results)} total recorded)")

elapsed_total = time.time() - start
db.refresh(run)
tokens_used = run.tokens_used_total - tokens_before
spend_used = run.spend_total_usd - spend_before

flags_written = compute_flags_for_run(db, run.id)

print(f"\n=== v2 run complete: {processed_this_run} newly processed this session, "
      f"{len(results)} total recorded, {elapsed_total:.1f}s this session ===")
print(f"Tokens used this session: {tokens_used}, spend: ${spend_used:.4f}")
print(f"Flags computed/updated: {flags_written}")
if skipped_missing:
    print(f"Filenames referenced in manifest but not found in corpus ({len(skipped_missing)}): "
          f"{skipped_missing[:20]}" + (" ..." if len(skipped_missing) > 20 else ""))

RESULTS_PATH.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
print("Saved full_results.json")

db.close()
