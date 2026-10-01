"""
Renders actual files in each required format. Each function takes a list
of text lines/paragraphs to embed (already containing planted PII from
content_snippets.py) and produces a real file of that format.
"""
import csv
import random
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet

from docx import Document as DocxDocument
import openpyxl
from PIL import Image, ImageDraw, ImageFont

styles = getSampleStyleSheet()


def render_pdf(path: Path, title: str, paragraphs: list[str]):
    doc = SimpleDocTemplate(str(path), pagesize=letter,
                             topMargin=0.8*inch, bottomMargin=0.8*inch,
                             leftMargin=0.9*inch, rightMargin=0.9*inch)
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for p in paragraphs:
        story.append(Paragraph(p.replace("\n", "<br/>"), styles["Normal"]))
        story.append(Spacer(1, 10))
    doc.build(story)


def render_docx(path: Path, title: str, paragraphs: list[str]):
    doc = DocxDocument()
    doc.add_heading(title, level=1)
    for p in paragraphs:
        for line in p.split("\n"):
            doc.add_paragraph(line)
    doc.save(str(path))


def render_xlsx_bulk(path: Path, people: list[dict], columns: list[str]):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Export"
    ws.append(columns)
    for person in people:
        ws.append([person.get(c, "") for c in columns])
    wb.save(str(path))


def render_csv_bulk(path: Path, people: list[dict], columns: list[str]):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for person in people:
            writer.writerow([person.get(c, "") for c in columns])


def render_html(path: Path, title: str, paragraphs: list[str]):
    body = "".join(f"<p>{p}</p>\n" for p in paragraphs)
    path.write_text(f"<!doctype html><html><head><title>{title}</title></head>"
                     f"<body><h1>{title}</h1>\n{body}</body></html>")


def render_txt(path: Path, title: str, paragraphs: list[str]):
    path.write_text(title + "\n\n" + "\n\n".join(paragraphs))


def render_png_screenshot(path: Path, title: str, lines: list[str]):
    """Simulates a screenshot of a form/confirmation page — plain text
    rendered to an image, no embedded text layer, so it genuinely
    requires OCR."""
    width, height = 800, 100 + 30 * (len(lines) + 2)
    img = Image.new("RGB", (width, height), color=(250, 250, 248))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except Exception:
        font = ImageFont.load_default()
        font_bold = font

    draw.text((30, 20), title, font=font_bold, fill=(20, 20, 20))
    y = 60
    for line in lines:
        draw.text((30, y), line, font=font, fill=(30, 30, 30))
        y += 28
    img.save(path)
