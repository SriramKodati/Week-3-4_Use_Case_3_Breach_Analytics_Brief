# UC3 Breach Analytics — Synthetic Corpus + Ground Truth Manifest

Weeks 3-4 capstone. 538 documents, 171 synthetic individuals, 7 formats.
Fully reproducible — every generator script is seeded (people_gen.py:
seed 2026, build_corpus.py: seed 99, content_snippets.py: seed 7).

**No real personal data anywhere in this corpus.** Every name, SSN,
address, phone, email, and identifier is fabricated. SSNs use the
900-999 area-number range (reserved by SSA as never-issuable). Card
numbers use the 4111-prefix test-BIN pattern with a genuine Luhn check
digit. Area code 555 (reserved for fiction) is used for all phone
numbers.

## Corpus composition (538 files, 7 formats)

| Folder | Count | Format(s) |
|---|---|---|
| pdf_digital | 82 | .pdf (real text layer) |
| pdf_scanned | 80 | .pdf (image-only, verified 0 extractable chars) |
| docx | 58 | .docx |
| emails | 52 | .eml (some with real .pdf attachments) |
| spreadsheets | 7 | .xlsx / .csv (bulk exports, 15-30 people each) |
| other | 242 | .html / .txt / .png (confirmation pages, logs, screenshots) |
| problem_files | 17 | password-protected PDF, corrupt PDF, zero-byte, wrong-extension, image-of-spreadsheet |

## Population (171 people — exceeds the 150+ requirement)

`manifest/individuals.csv` — 155 unique people + 16 people across 8
deliberate name-collision pairs. Each person has a randomized subset of:
SSN (always), phone, email, address (always), driver's license (~55%),
passport (~25%), financial/card (~45%), medical note (~30%), login
credential (~35%) — uneven coverage on purpose, so per-category
recall/precision numbers are meaningful rather than trivially 100%.

## Every Section 3.2 edge case, and where it lives

- **Same person, different names** (`manifest/name_variants.csv`, 57
  rows across 30 people): nicknames, initials, misspellings, name-order
  variants — each planted in a *different* document than the canonical
  name, with DOB/address included so resolution has real evidence to
  link on.
- **Shared name, different people** (`manifest/name_collisions.csv`, 8
  pairs / 16 people): identical display name, distinct DOB/SSN/address,
  each in `corpus/pdf_digital/collision_XXXa.pdf` / `...b.pdf`. Manifest
  explicitly marks `should_merge=False`.
- **Partial identifiers** (12 people, tagged `ssn_only_partial` /
  `name_only_partial` in the manifest): SSN with no name nearby in one
  document, matching name with no SSN in a separate document.
- **Multi-person documents**: `corpus/spreadsheets/bulk_export_*` — 7
  files, 15-30 people each.
- **False-positive traps** (`manifest/negatives.csv`, 58 rows): order
  numbers shaped like SSNs, internal employee email signatures, fictional
  "test" records, literal template placeholders (`XXX-XX-XXXX`). These
  should NOT be flagged — this is what makes precision measurable, not
  just recall.
- **Problem files** (`manifest/quarantine_expected.csv`, 17 files):
  password-protected (verified genuinely unopenable without credentials),
  corrupt, zero-byte, wrong-extension, and a photographed spreadsheet
  (genuinely unreliable to OCR, which is the point).

## Manifest files (the answer key)

- `individuals.csv` — every person's true attribute values
- `name_variants.csv` — variant text + type, linked to person_id
- `name_collisions.csv` — the 8 shared-name traps, with the correct answer
- `document_manifest.csv` — 1,776 rows: every (filename, person_id,
  category, planted_value) — this is what an accuracy report scores
  extraction against
- `negatives.csv` — every false-positive trap, for precision scoring
- `quarantine_expected.csv` — every problem file and its expected
  quarantine reason, for triage scoring

## Regenerating

```bash
cd generator
python3 people_gen.py      # writes individuals/variants/collisions CSVs
python3 build_corpus.py    # builds all 538 documents + remaining manifests
```

Both scripts are seeded — rerunning produces an identical corpus.
