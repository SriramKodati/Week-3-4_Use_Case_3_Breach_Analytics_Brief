"""
Main corpus builder. Assigns people to documents across all required
formats, plants every Section 3.2 edge case, and writes the ground-truth
manifest that scores extraction/entity-resolution accuracy later.
"""
import csv
import random
from pathlib import Path

from doc_builders import (render_pdf, render_docx, render_xlsx_bulk,
                            render_csv_bulk, render_html, render_txt, render_png_screenshot)
from email_builder import render_eml
from problem_files import (make_password_protected_pdf, make_corrupt_pdf,
                             make_zero_byte_file, make_wrong_extension_file, make_image_of_spreadsheet)
import content_snippets as snip

BASE = Path(__file__).parent.parent
CORPUS = BASE / "corpus"
MANIFEST_DIR = BASE / "manifest"
RNG = random.Random(99)

EMPLOYEE_NAMES = ["Alex Rivera", "Jordan Blake", "Casey Nguyen", "Morgan Ellis"]


def load_people():
    with open(MANIFEST_DIR / "individuals.csv") as f:
        return list(csv.DictReader(f))


def load_variants():
    with open(MANIFEST_DIR / "name_variants.csv") as f:
        return list(csv.DictReader(f))


def load_collisions():
    with open(MANIFEST_DIR / "name_collisions.csv") as f:
        return list(csv.DictReader(f))


manifest_rows = []      # (filename, format, person_id, category, planted_value)
negative_rows = []      # (filename, format, negative_type, text)
quarantine_rows = []    # (filename, reason)


def log_plant(filename, fmt, person_id, category, value):
    manifest_rows.append({"filename": filename, "format": fmt, "person_id": person_id,
                           "category": category, "planted_value": value})


def log_negative(filename, fmt, ntype, text):
    negative_rows.append({"filename": filename, "format": fmt, "negative_type": ntype, "text": text})


def category_lines_for(person):
    """Returns list of (category, line_text, value) for every category this person has."""
    out = [("name_and_ssn", snip.prose_paragraph(person), person["ssn"])]
    if person["has_driver_license"] == "True":
        out.append(("driver_license", snip.driver_license_note_line(person), person["driver_license"]))
    if person["has_passport"] == "True":
        out.append(("passport", snip.passport_note_line(person), person["passport"]))
    if person["has_financial"] == "True":
        out.append(("financial_account", snip.financial_note_line(person), person["card_number"]))
    if person["has_medical"] == "True":
        out.append(("medical", snip.medical_note_line(person), person["medical_note"]))
    if person["has_login"] == "True":
        out.append(("login_credential", snip.login_note_line(person), person["login_credential"]))
    out.append(("phone", person["phone"], person["phone"]))
    out.append(("email", person["email"], person["email"]))
    out.append(("address", person["address"], person["address"]))
    return out


def build_primary_documents(people, partial_id_person_ids):
    """One primary document per person, round-robined across digital PDF,
    DOCX, and email formats. People in partial_id_person_ids get their
    SSN and name split across two separate documents instead."""
    counters = {"pdf": 0, "docx": 0, "eml": 0}

    for i, person in enumerate(people):
        fmt = ["pdf", "docx", "eml"][i % 3]
        counters[fmt] += 1
        pid = person["person_id"]

        if pid in partial_id_person_ids:
            # Document A: SSN only, no name nearby
            fname_a = f"{fmt}_case_{counters[fmt]:04d}a.{fmt if fmt!='eml' else 'eml'}"
            ssn_line = snip.partial_identifier_ssn_only(person)
            # Document B: name only, no SSN
            fname_b = f"{fmt}_case_{counters[fmt]:04d}b.{fmt if fmt!='eml' else 'eml'}"
            name_line = snip.partial_identifier_name_only(person)

            _write_single_doc(fmt, fname_a, "Case Reference", [ssn_line])
            _write_single_doc(fmt, fname_b, "Case Follow-up", [name_line])
            log_plant(fname_a, fmt, pid, "ssn_only_partial", person["ssn"])
            log_plant(fname_b, fmt, pid, "name_only_partial", person["canonical_name"])
            continue

        lines = [line for _, line, _ in category_lines_for(person)]
        fname = f"{fmt}_case_{counters[fmt]:04d}.{fmt if fmt!='eml' else 'eml'}"

        # Occasionally inject a false-positive trap into the same doc
        extra_negative = None
        roll = RNG.random()
        if roll < 0.08:
            fake_order = f"{RNG.randint(100,999)}-{RNG.randint(10,99)}-{RNG.randint(1000,9999)}"
            extra_negative = ("order_number_lookalike", snip.FALSE_POSITIVE_ORDER_NOTE.format(fake_ssn_shaped=fake_order))
        elif roll < 0.14:
            extra_negative = ("template_placeholder", snip.TEMPLATE_PLACEHOLDER_LINE)
        elif roll < 0.18:
            extra_negative = ("test_record", snip.TEST_RECORD_LINE)

        if extra_negative:
            lines.append(extra_negative[1])

        if fmt == "eml" and RNG.random() < 0.3:
            # attach a small standalone PDF carrying the same person's info
            attach_name = f"attach_{counters[fmt]:04d}.pdf"
            render_pdf(CORPUS / "pdf_digital" / attach_name, "Attachment", [snip.prose_paragraph(person)])
            log_plant(f"{fname}::{attach_name}", "pdf_attachment", pid, "name_and_ssn", person["ssn"])

        _write_single_doc(fmt, fname, "Case Notes", lines, person=person)

        for category, _, value in category_lines_for(person):
            log_plant(fname, fmt, pid, category, value)
        if extra_negative:
            log_negative(fname, fmt, extra_negative[0], extra_negative[1])


def _write_single_doc(fmt, fname, title, lines, person=None):
    if fmt == "pdf":
        render_pdf(CORPUS / "pdf_digital" / fname, title, lines)
    elif fmt == "docx":
        render_docx(CORPUS / "docx" / fname, title, lines)
    elif fmt == "eml":
        employee = RNG.choice(EMPLOYEE_NAMES)
        sender = f"{employee.split()[0].lower()}@datafactz-client.example"
        body = lines + [snip.employee_signature_negative(employee, "555-100-2000", sender)]
        render_eml(CORPUS / "emails" / fname, sender,
                   person["email"] if person else "case@client.example", title, body)
        if person is None or RNG.random() < 0.5:
            log_negative(fname, "eml", "employee_signature", employee)


def build_variant_documents(people_by_id, variants):
    """Plants each canonical name+SSN once (already done in primary docs)
    and each variant text in a SEPARATE document, with enough matching
    detail (DOB or address) for resolution to actually link them."""
    for i, v in enumerate(variants):
        person = people_by_id[v["person_id"]]
        fname = f"variant_note_{i:04d}.txt"
        line = (f"Follow-up note regarding {v['variant_text']} "
                f"(DOB on file: {person['dob']}). Reference address: {person['address']}.")
        render_txt(CORPUS / "other" / fname, "Follow-up Note", [line])
        log_plant(fname, "txt", v["person_id"], "name_variant", v["variant_text"])


def build_collision_documents(people_by_id, collisions):
    """Each person in a collision pair gets a dedicated document under
    the SAME display name but with their own distinguishing details —
    this is the trap: naive matching would merge them."""
    for i, c in enumerate(collisions):
        for label, pid in [("a", c["person_id_a"]), ("b", c["person_id_b"])]:
            person = people_by_id[pid]
            fname = f"collision_{i:03d}{label}.pdf"
            lines = [snip.prose_paragraph(person)]
            render_pdf(CORPUS / "pdf_digital" / fname, "Case File", lines)
            log_plant(fname, "pdf", pid, "name_and_ssn", person["ssn"])


def build_bulk_spreadsheets(people, n_sheets=7, min_people=15, max_people=30):
    """The 'one spreadsheet exposes many people at once' edge case."""
    columns = ["canonical_name", "ssn", "phone", "email", "address"]
    pool = people.copy()
    RNG.shuffle(pool)
    idx = 0
    for i in range(n_sheets):
        n = RNG.randint(min_people, max_people)
        batch = pool[idx: idx + n]
        idx += n
        if not batch:
            break
        fmt = "xlsx" if i % 2 == 0 else "csv"
        fname = f"bulk_export_{i:02d}.{fmt}"
        if fmt == "xlsx":
            render_xlsx_bulk(CORPUS / "spreadsheets" / fname, batch, columns)
        else:
            render_csv_bulk(CORPUS / "spreadsheets" / fname, batch, columns)
        for person in batch:
            log_plant(fname, fmt, person["person_id"], "bulk_export_row", person["ssn"])


def build_other_formats(people, n_html=15, n_png=15):
    for i in range(n_html):
        person = RNG.choice(people)
        fname = f"confirmation_{i:03d}.html"
        render_html(CORPUS / "other" / fname, "Confirmation",
                    [snip.prose_paragraph(person)])
        log_plant(fname, "html", person["person_id"], "name_and_ssn", person["ssn"])

    for i in range(n_png):
        person = RNG.choice(people)
        fname = f"screenshot_{i:03d}.png"
        lines = [f"Name: {person['canonical_name']}", f"SSN: {person['ssn']}",
                 f"Phone: {person['phone']}"]
        render_png_screenshot(CORPUS / "other" / fname, "Form Submission Confirmation", lines)
        log_plant(fname, "png", person["person_id"], "name_and_ssn", person["ssn"])


def build_scanned_pdfs(n=80):
    """Rasterizes existing digital PDFs into image-only scanned versions,
    reusing the Week 2 degradation technique (skew/noise/contrast)."""
    import subprocess
    from PIL import Image, ImageEnhance
    import numpy as np
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import letter

    digital_pdfs = sorted((CORPUS / "pdf_digital").glob("*.pdf"))
    chosen = RNG.sample(digital_pdfs, min(n, len(digital_pdfs)))

    for i, src in enumerate(chosen):
        out_path = CORPUS / "pdf_scanned" / f"scan_{i:04d}.pdf"
        tmp_prefix = f"/tmp/scan3_{i}"
        subprocess.run(["pdftoppm", "-jpeg", "-r", "150", str(src), tmp_prefix], check=True, capture_output=True)
        page = Path(f"{tmp_prefix}-1.jpg")
        if not page.exists():
            continue
        img = Image.open(page).convert("RGB")
        angle = RNG.uniform(-3, 3)
        img = img.rotate(angle, expand=True, fillcolor=(255, 255, 255))
        img = ImageEnhance.Contrast(img).enhance(RNG.uniform(0.85, 0.95))
        arr = np.array(img).astype("int16")
        noise = np.random.randint(-8, 8, arr.shape, dtype="int16")
        img = Image.fromarray((arr + noise).clip(0, 255).astype("uint8"))

        tmp_img = f"{tmp_prefix}_final.jpg"
        img.save(tmp_img, quality=85)

        c = rl_canvas.Canvas(str(out_path), pagesize=letter)
        page_w, page_h = letter
        iw, ih = img.size
        scale = min(page_w / iw, page_h / ih)
        c.drawImage(tmp_img, 0, page_h - ih * scale, width=iw * scale, height=ih * scale)
        c.save()

        page.unlink(missing_ok=True)
        Path(tmp_img).unlink(missing_ok=True)

        # carry over the manifest rows for the source doc's person_id(s)
        src_rows = [r for r in manifest_rows if r["filename"] == src.name]
        for r in src_rows:
            log_plant(out_path.name, "pdf_scanned", r["person_id"], r["category"] + "_scanned", r["planted_value"])


def build_problem_files(n_each=4):
    for i in range(n_each):
        make_password_protected_pdf(CORPUS / "problem_files" / f"protected_{i}.pdf")
        quarantine_rows.append({"filename": f"protected_{i}.pdf", "reason": "password_protected"})

        make_corrupt_pdf(CORPUS / "problem_files" / f"corrupt_{i}.pdf")
        quarantine_rows.append({"filename": f"corrupt_{i}.pdf", "reason": "corrupt_file"})

        make_zero_byte_file(CORPUS / "problem_files" / f"empty_{i}.pdf")
        quarantine_rows.append({"filename": f"empty_{i}.pdf", "reason": "zero_byte"})

        make_image_of_spreadsheet(CORPUS / "problem_files" / f"sheet_photo_{i}.png")
        quarantine_rows.append({"filename": f"sheet_photo_{i}.png", "reason": "image_of_spreadsheet_unreliable_ocr"})

    # wrong-extension: take a real PDF's bytes, save as .docx
    real_pdf = next((CORPUS / "pdf_digital").glob("*.pdf"))
    wrong = make_wrong_extension_file(CORPUS / "problem_files" / "mislabeled", real_pdf.read_bytes(), ".docx")
    quarantine_rows.append({"filename": wrong.name, "reason": "wrong_extension_actually_pdf"})


def build_secondary_mentions(people, collision_ids):
    """Every primary person also gets a short secondary document (a
    lighter confirmation/log mention) — realistic, since real breach
    dumps repeat the same person's contact info across many files, and
    gives entity resolution more same-person-multiple-docs cases to link."""
    eligible = [p for p in people if p["person_id"] not in collision_ids]
    for i, person in enumerate(eligible):
        fmt = ["html", "txt", "png"][i % 3]
        fname = f"secondary_{i:04d}.{fmt}"
        line = f"{person['canonical_name']} — contact on file: {person['phone']} / {person['email']}"

        if fmt == "html":
            render_html(CORPUS / "other" / fname, "Contact Log", [line])
        elif fmt == "txt":
            render_txt(CORPUS / "other" / fname, "Contact Log", [line])
        else:
            render_png_screenshot(CORPUS / "other" / fname, "Contact Log",
                                   [f"Name: {person['canonical_name']}", f"Phone: {person['phone']}", f"Email: {person['email']}"])

        log_plant(fname, fmt, person["person_id"], "phone", person["phone"])
        log_plant(fname, fmt, person["person_id"], "email", person["email"])


def main():
    people = load_people()
    people_by_id = {p["person_id"]: p for p in people}
    variants = load_variants()
    collisions = load_collisions()

    collision_ids = set()
    for c in collisions:
        collision_ids.add(c["person_id_a"])
        collision_ids.add(c["person_id_b"])

    # People used for the partial-identifier edge case (not variants/collisions)
    remaining = [p for p in people if p["person_id"] not in collision_ids]
    partial_id_people = RNG.sample(remaining, 12)
    partial_id_ids = {p["person_id"] for p in partial_id_people}

    primary_people = [p for p in people if p["person_id"] not in collision_ids]

    print("Building primary documents...")
    build_primary_documents(primary_people, partial_id_ids)

    print("Building name-variant documents...")
    build_variant_documents(people_by_id, variants)

    print("Building collision documents...")
    build_collision_documents(people_by_id, collisions)

    print("Building bulk spreadsheets...")
    build_bulk_spreadsheets(people)

    print("Building HTML/PNG documents...")
    build_other_formats(people)

    print("Building secondary mention documents...")
    build_secondary_mentions(people, collision_ids)

    print("Building scanned PDFs...")
    build_scanned_pdfs(n=80)

    print("Building problem files...")
    build_problem_files(n_each=4)

    # Write manifests
    with open(MANIFEST_DIR / "document_manifest.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "format", "person_id", "category", "planted_value"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    with open(MANIFEST_DIR / "negatives.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "format", "negative_type", "text"])
        writer.writeheader()
        writer.writerows(negative_rows)

    with open(MANIFEST_DIR / "quarantine_expected.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "reason"])
        writer.writeheader()
        writer.writerows(quarantine_rows)

    total_files = sum(1 for _ in CORPUS.rglob("*") if _.is_file())
    print(f"\nDone. Total files in corpus: {total_files}")
    print(f"Manifest rows (planted elements): {len(manifest_rows)}")
    print(f"Negative traps: {len(negative_rows)}")
    print(f"Quarantine-expected problem files: {len(quarantine_rows)}")


if __name__ == "__main__":
    main()
