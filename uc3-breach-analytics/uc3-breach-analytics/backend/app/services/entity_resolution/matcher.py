"""
Deterministic entity resolution (Design Doc Section 6: this stays in the
pipeline because it has a clear, fixed-threshold answer for the confident
majority of cases — only the ambiguous middle band needs the Wednesday
Adjudicator agent).

SCOPE NOTE: this matcher assumes one document carries one person's
signals, which holds for primary documents, collisions, variants,
attachments, and confirmations — but NOT for bulk spreadsheets (15-30
people per file). Multi-person documents are detected and explicitly
skipped here rather than silently mismatched; row-aware extraction for
spreadsheets is real follow-up work, not solved today.
"""
import difflib
from datetime import date

from sqlalchemy.orm import Session

from app.db.models import Document, Extraction, Person, IdentityLink
from app.core.config import settings


def _name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _get_document_signals(document: Document) -> dict | None:
    """Returns {category: Extraction} using the first occurrence of each
    category, OR None if this document has multiple distinct values for
    an identity-bearing category (a multi-person document)."""
    by_category: dict[str, list[Extraction]] = {}
    for e in document.extractions:
        by_category.setdefault(e.category, []).append(e)

    identity_categories = ["ssn", "name", "dob"]
    for cat in identity_categories:
        values = {e.raw_value for e in by_category.get(cat, [])}
        if len(values) > 1:
            return None  # multi-person document — skip, see module docstring

    return {cat: exts[0] for cat, exts in by_category.items() if exts}


def _score_match(signals: dict, person: Person, person_address: str | None) -> float:
    score = 0.0
    weight_total = 0.0

    if "name" in signals:
        sim = _name_similarity(signals["name"].raw_value, person.best_known_name)
        score += sim * 0.5
        weight_total += 0.5

    if "dob" in signals and person.dob is not None:
        try:
            doc_dob = date.fromisoformat(signals["dob"].raw_value)
            score += (1.0 if doc_dob == person.dob else 0.0) * 0.3
        except ValueError:
            pass
        weight_total += 0.3

    if "address" in signals and person_address:
        sim = _name_similarity(signals["address"].raw_value, person_address)
        score += sim * 0.2
        weight_total += 0.2

    return score / weight_total if weight_total > 0 else 0.0


def resolve_document(db: Session, document: Document) -> dict:
    signals = _get_document_signals(document)
    if signals is None:
        return {"result": "skipped_multi_person"}
    if "name" not in signals and "ssn" not in signals:
        return {"result": "insufficient_signal"}

    # 1. Exact SSN match — authoritative when present (Design Doc: SSN is
    # the strongest single signal, and correctly keeps collision pairs
    # separate since they have different SSNs by construction).
    if "ssn" in signals:
        existing_link = (
            db.query(IdentityLink)
            .join(Extraction, IdentityLink.extraction_id == Extraction.id)
            .filter(Extraction.category == "ssn", Extraction.raw_value == signals["ssn"].raw_value)
            .first()
        )
        if existing_link:
            _apply_link(db, document, signals, existing_link.person, confidence=1.0, method="deterministic_ssn")
            return {"result": "matched", "person_id": existing_link.person_id, "confidence": 1.0}

    # 2. Fuzzy name + DOB + address against existing persons
    best_person, best_score, best_address = None, 0.0, None
    if "name" in signals:
        for person in db.query(Person).all():
            addr_link = (
                db.query(IdentityLink)
                .join(Extraction, IdentityLink.extraction_id == Extraction.id)
                .filter(IdentityLink.person_id == person.id, Extraction.category == "address")
                .first()
            )
            person_address = addr_link.extraction.raw_value if addr_link else None
            score = _score_match(signals, person, person_address)
            if score > best_score:
                best_person, best_score, best_address = person, score, person_address

    if best_person and best_score >= settings.entity_match_confident_threshold:
        _apply_link(db, document, signals, best_person, confidence=best_score, method="deterministic_fuzzy")
        return {"result": "matched", "person_id": best_person.id, "confidence": best_score}

    if best_person and best_score >= settings.entity_match_ambiguous_floor:
        # Parked for the Adjudicator agent (Wednesday) — not applied yet.
        _apply_link(db, document, signals, best_person, confidence=best_score,
                     method="deterministic_ambiguous_pending_agent")
        return {"result": "ambiguous", "candidate_person_id": best_person.id, "confidence": best_score}

    # 3. No match at all — new person
    dob_val = None
    if "dob" in signals:
        try:
            dob_val = date.fromisoformat(signals["dob"].raw_value)
        except ValueError:
            pass
    new_person = Person(best_known_name=signals["name"].raw_value if "name" in signals else signals["ssn"].raw_value,
                         dob=dob_val)
    db.add(new_person)
    db.flush()
    _apply_link(db, document, signals, new_person, confidence=1.0, method="deterministic_new")
    return {"result": "new_person", "person_id": new_person.id}


def _apply_link(db: Session, document: Document, signals: dict, person: Person, confidence: float, method: str):
    for extraction in document.extractions:
        existing = db.query(IdentityLink).filter(IdentityLink.extraction_id == extraction.id).first()
        if existing:
            continue
        db.add(IdentityLink(extraction_id=extraction.id, person_id=person.id,
                             link_confidence=confidence, link_method=method))
    db.commit()
