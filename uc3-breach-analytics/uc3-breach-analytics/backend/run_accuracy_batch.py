import csv, time
from pathlib import Path
from app.db.base import SessionLocal
from app.db.models import Run, Document, Extraction, IdentityLink, Person
from app.services.pipeline import process_document
from app.services.exposure.flags import compute_flags_for_run

db = SessionLocal()
run = db.query(Run).first()
run.status = "running"
db.commit()

corpus_root = Path("../data/corpus")
manifest_root = Path("../data/manifest")

# Index every corpus file by filename for quick lookup regardless of subfolder
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
primary_sample = list(primaries.values())[:8]

variant_sample = [r for r in doc_manifest if r["category"] == "name_variant"
                   and r["person_id"] in primaries][:6]

negative_sample = negatives[:4]
quarantine_sample = quarantine_expected[:5]

batch = (
    [(r["filename"], "primary", r["person_id"]) for r in primary_sample] +
    [(r["filename"], "variant", r["person_id"]) for r in variant_sample] +
    [(r["filename"], "negative", None) for r in negative_sample] +
    [(r["filename"], "quarantine_expected", r.get("reason")) for r in quarantine_sample]
)

tokens_before = run.tokens_used_total
spend_before = run.spend_total_usd
start = time.time()

results = []
for filename, kind, meta in batch:
    path = file_index.get(filename)
    if path is None:
        print(f"SKIP (not found in corpus): {filename}")
        continue
    document = Document(run_id=run.id, filename=filename, format="unknown", status="queued")
    db.add(document)
    db.commit()
    t0 = time.time()
    result = process_document(db, document, str(path))
    elapsed = time.time() - t0
    print(f"[{kind}] {filename} -> {result.get('status')} ({elapsed:.1f}s)")
    results.append((filename, kind, meta, document.id, result.get("status")))

elapsed_total = time.time() - start
db.refresh(run)
tokens_used = run.tokens_used_total - tokens_before
spend_used = run.spend_total_usd - spend_before

flags_written = compute_flags_for_run(db, run.id)

print(f"\n=== Batch complete: {len(results)} documents, {elapsed_total:.1f}s total ===")
print(f"Tokens used this batch: {tokens_used}, spend: ${spend_used:.4f}")
print(f"Flags computed/updated: {flags_written}")

import json
with open("batch_results.json", "w") as f:
    json.dump({
        "results": results,
        "tokens_used": tokens_used,
        "spend_used": spend_used,
        "elapsed_total": elapsed_total,
        "primary_sample": [(r["filename"], r["person_id"]) for r in primary_sample],
        "variant_sample": [(r["filename"], r["person_id"], r["planted_value"]) for r in variant_sample],
        "negative_sample": [(r["filename"], r["negative_type"]) for r in negative_sample],
        "quarantine_sample": [(r["filename"], r["reason"]) for r in quarantine_sample],
    }, f, indent=2)
print("Saved batch_results.json")
