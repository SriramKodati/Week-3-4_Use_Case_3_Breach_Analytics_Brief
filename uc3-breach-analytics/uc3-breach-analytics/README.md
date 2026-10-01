# UC3 — Breach Analytics Platform (Capstone, Weeks 3-4)

## Status: Week 4 Monday scope

This is the project scaffold plus **working, verified code** for exactly
Monday's build-plan scope: ingestion/triage, parsing, and Tier 0/1/2
extraction. Entity resolution and all four agents are **not yet
implemented** — see "What's actually implemented" below. Nothing is
faked as complete; not-yet-built endpoints return HTTP 501 with a clear
message rather than a fake empty result.

## What's actually implemented and verified (not just written)

- **Triage**: tested against all 538 real corpus files. 0 false
  quarantines across 521 legitimate documents; 16/17 real problem files
  correctly quarantined with the right reason (the 17th — photographed
  spreadsheets — is deferred by design to the OCR-confidence check in
  parsing, not caught at triage).
- **Parsing**: all 7 formats (PDF digital/scanned, DOCX, XLSX, CSV, EML
  with attachments, HTML, TXT, PNG) have working parsers.
- **Tier 0 deterministic detection**: regex + Luhn-validated card
  checking. Verified 20/20 on a real sample against the ground-truth
  manifest.
- **Two real bugs found and fixed during this build, in the corpus
  generator itself, not the pipeline code**:
  1. The prose templates never actually embedded the SSN value in
     document text, even though the manifest claimed every primary
     document planted one. Fixed, and reverified against 20 real
     documents.
  2. The "photographed spreadsheet" problem file was rendered too
     cleanly — Tesseract read it at 91% confidence, defeating the whole
     point of the edge case. Fixed with real degradation (blur, rotation,
     contrast, noise); now correctly triggers the low-confidence-OCR
     quarantine path.

## What's NOT implemented yet (Tuesday-Wednesday, per the build plan)

- Deterministic entity matching (name+DOB+SSN+address)
- All four agents: Orchestrator, Exception Investigator, Entity-Resolution
  Adjudicator, QA Auditor — stubbed in `app/agents/agents.py` with clear
  interfaces, each raising `NotImplementedError` on purpose
- Review queue, exposure table, run traces, export — API endpoints exist
  and return 501, not fake data

## Setup

```bash
cd backend
uv venv --python 3.12
.venv\Scripts\Activate.ps1
uv pip install --only-binary :all: -r requirements.txt
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8003
```

You'll also need Tesseract and Poppler installed (same as Week 2) for
OCR and scanned-PDF handling.

Frontend:
```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

## Trying the implemented pipeline

Upload files directly from `data/corpus/` — try a mix:
- `data/corpus/pdf_digital/pdf_case_0001.pdf` (should extract cleanly)
- `data/corpus/problem_files/protected_0.pdf` (should quarantine: password_protected)
- `data/corpus/problem_files/sheet_photo_0.png` (should quarantine: low_confidence_ocr)
- `data/corpus/pdf_scanned/scan_0000.pdf` (should OCR and extract)

Check `GET /api/v1/documents` to see status, and
`GET /api/v1/documents/{id}/extractions` to see what Tier 0/1/2 found.

## Project structure

```
backend/app/
  services/
    triage.py                 verified against all 538 corpus files
    parsing/parser.py          all 7 formats
    extraction/
      tier0_detectors.py       regex + Luhn, verified
      tier1_tier2.py           LLM extraction, local/DeepSeek/Claude swap
    pipeline.py                orchestrates Monday's scope only
  agents/agents.py             4 stubs, NotImplementedError by design
  db/models.py                 matches the 8-entity ERD exactly
data/
  corpus/                      538 documents, 7 formats (regenerated with fixes)
  manifest/                    ground truth — individuals, variants, collisions,
                                document_manifest, negatives, quarantine_expected
docs/                          problem statement, design doc, diagrams, deck
```
