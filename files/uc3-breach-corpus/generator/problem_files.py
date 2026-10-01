"""
Section 3.2 'Problem files' — deliberately broken inputs that a robust
ingestion/triage layer must quarantine WITH A REASON, not silently drop
or crash on.
"""
import random
from pathlib import Path

import pikepdf
from reportlab.pdfgen import canvas


def make_password_protected_pdf(path: Path):
    tmp = path.with_suffix(".tmp.pdf")
    c = canvas.Canvas(str(tmp))
    c.drawString(100, 700, "This PDF is password protected.")
    c.save()

    pdf = pikepdf.open(tmp)
    pdf.save(path, encryption=pikepdf.Encryption(owner="ownerpass123", user="userpass123"))
    tmp.unlink()


def make_corrupt_pdf(path: Path):
    # Valid PDF header, then garbage — enough to fool a naive extension
    # check but fail real parsing.
    path.write_bytes(b"%PDF-1.4\n" + bytes(random.Random(1).randbytes(200)))


def make_zero_byte_file(path: Path):
    path.write_bytes(b"")


def make_wrong_extension_file(path: Path, real_content: bytes, wrong_ext: str):
    # e.g. a real PDF's bytes saved with a .docx extension
    path_with_wrong_ext = path.with_suffix(wrong_ext)
    path_with_wrong_ext.write_bytes(real_content)
    return path_with_wrong_ext


def make_image_of_spreadsheet(path: Path):
    """A spreadsheet that exists only as a photo of a printed page — text
    is genuinely unextractable without OCR, and OCR on a table photo is
    itself unreliable, which is exactly the point of this edge case."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (900, 500), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except Exception:
        font = ImageFont.load_default()

    rows = [
        ["Name", "SSN", "Phone"],
        ["Sample Person One", "912-34-5678", "555-201-3344"],
        ["Sample Person Two", "913-45-6789", "555-202-4455"],
    ]
    y = 30
    for row in rows:
        draw.text((30, y), "   |   ".join(row), font=font, fill=(0, 0, 0))
        y += 40
    img.save(path)
