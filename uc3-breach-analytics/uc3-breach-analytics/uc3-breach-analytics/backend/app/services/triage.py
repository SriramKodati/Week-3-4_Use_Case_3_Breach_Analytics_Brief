"""
Ingestion & Triage — the first deterministic pipeline stage. Classifies
every file by format and parseability, and quarantines problem files
WITH A REASON rather than dropping or crashing on them (brief Section 2).

Verified against the real corpus's problem_files/ during development —
see backend/scripts/verify_triage.py.
"""
from pathlib import Path

import pdfplumber
import pikepdf

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".eml", ".html", ".htm", ".txt", ".png", ".jpg", ".jpeg"}


class TriageResult:
    def __init__(self, action: str, format: str = None, reason: str = None):
        self.action = action  # "process" | "quarantine"
        self.format = format
        self.reason = reason


def _looks_like_pdf(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(5) == b"%PDF-"
    except Exception:
        return False


def _pdf_is_password_protected(path: Path) -> bool:
    try:
        pikepdf.open(path)
        return False
    except pikepdf.PasswordError:
        return True
    except Exception:
        return False  # a different failure — let corrupt-file detection catch it


def _pdf_is_readable(path: Path) -> bool:
    try:
        with pdfplumber.open(path) as pdf:
            _ = len(pdf.pages)
        return True
    except Exception:
        return False


def triage_file(path: Path) -> TriageResult:
    if not path.exists() or path.stat().st_size == 0:
        return TriageResult("quarantine", reason="zero_byte")

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return TriageResult("quarantine", reason=f"unsupported_extension:{ext}")

    # Wrong-extension check: does the byte signature match a known format
    # regardless of what the filename claims?
    if ext != ".pdf" and _looks_like_pdf(path):
        return TriageResult("quarantine", reason="wrong_extension_actually_pdf")

    if ext == ".pdf":
        if _pdf_is_password_protected(path):
            return TriageResult("quarantine", reason="password_protected")
        if not _pdf_is_readable(path):
            return TriageResult("quarantine", reason="corrupt_file")
        return TriageResult("process", format="pdf")

    if ext in (".png", ".jpg", ".jpeg"):
        # Images are OCR'd like scanned PDFs, not quarantined outright —
        # quarantining every image would wrongly catch legitimate
        # screenshots along with the deliberate photo-of-a-spreadsheet
        # problem files. The real signal (low OCR confidence on a table-
        # like layout) is only knowable AFTER running OCR, so that check
        # belongs in the parsing stage, not here — see parsing/ocr.py's
        # LOW_CONFIDENCE_QUARANTINE_THRESHOLD.
        return TriageResult("process", format="image")

    if ext in (".docx", ".xlsx", ".csv", ".eml", ".html", ".htm", ".txt"):
        return TriageResult("process", format=ext.lstrip("."))

    return TriageResult("quarantine", reason="unhandled_case")
