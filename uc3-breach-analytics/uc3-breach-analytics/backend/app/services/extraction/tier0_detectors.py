"""
Tier 0: deterministic detectors. Free, no LLM call — regex for
structured formats, Luhn checksum validation for card numbers (brief
Section 2's explicit example). Runs on every document's parsed text
before any LLM extraction happens.
"""
import re

SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
PHONE_PATTERN = re.compile(r"\b\d{3}-\d{3}-\d{4}\b")
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
CARD_PATTERN = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{4}\b")
# ISO dates (YYYY-MM-DD) near the words "DOB" or "date of birth" — a
# genuinely safe deterministic signal for THIS corpus's consistent date
# format, not a general-purpose date extractor (a bare ISO date elsewhere
# in a document, e.g. an invoice date, would be a false positive — the
# nearby keyword requirement is what keeps this precise).
DOB_PATTERN = re.compile(
    r"(?:DOB|date of birth)\D{0,15}(\d{4}-\d{2}-\d{2})", re.IGNORECASE
)


def luhn_valid(card_digits: str) -> bool:
    digits = [int(d) for d in card_digits if d.isdigit()]
    if len(digits) < 12:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def detect_tier0(text: str) -> list[dict]:
    """Returns a list of {category, raw_value, confidence, source_passage}.
    Confidence is 1.0 for every Tier 0 hit — these are deterministic
    format/checksum matches, not model guesses, so a constant high
    confidence here is honest, unlike an LLM self-report (see Section 6.2's
    argument about why a constant confidence is normally a red flag)."""
    results = []

    for m in SSN_PATTERN.finditer(text):
        results.append({"category": "ssn", "raw_value": m.group(),
                         "confidence": 1.0, "source_passage": _context(text, m)})

    for m in PHONE_PATTERN.finditer(text):
        results.append({"category": "phone", "raw_value": m.group(),
                         "confidence": 1.0, "source_passage": _context(text, m)})

    for m in EMAIL_PATTERN.finditer(text):
        results.append({"category": "email", "raw_value": m.group(),
                         "confidence": 1.0, "source_passage": _context(text, m)})

    for m in DOB_PATTERN.finditer(text):
        results.append({"category": "dob", "raw_value": m.group(1),
                         "confidence": 1.0, "source_passage": _context(text, m)})

    for m in CARD_PATTERN.finditer(text):
        if luhn_valid(m.group()):
            results.append({"category": "financial_account", "raw_value": m.group(),
                             "confidence": 1.0, "source_passage": _context(text, m)})
        # A card-shaped number that FAILS Luhn is not flagged at all — most
        # likely a different kind of ID number, not a real card. This is
        # exactly what keeps precision high on the false-positive traps.

    return results


def _context(text: str, match, window: int = 60) -> str:
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    return text[start:end].strip()
