"""
Computes exposure Flags from resolved Persons and their linked
extractions. A Flag is one (person, category) pair marked exposed —
the basic unit the exposure table and QAAuditor both operate on.
Nothing populated this before now; entity resolution only wrote
IdentityLink rows, one per raw extraction, with no per-person,
per-category rollup.
"""
from sqlalchemy.orm import Session

from app.db.models import Person, IdentityLink, Extraction, Flag, Document


def compute_flags_for_person(db: Session, person: Person) -> list[Flag]:
    links = db.query(IdentityLink).filter(IdentityLink.person_id == person.id).all()
    by_category: dict[str, list[tuple[IdentityLink, Extraction]]] = {}
    for link in links:
        extraction = db.query(Extraction).get(link.extraction_id)
        by_category.setdefault(extraction.category, []).append((link, extraction))

    flags = []
    for category, pairs in by_category.items():
        confidences = [link.link_confidence * extraction.confidence for link, extraction in pairs]
        avg_confidence = sum(confidences) / len(confidences)
        # Evidence that went through ambiguous adjudication needs a human
        # sign-off before it counts as a confirmed exposure, per the
        # design doc's human-approval requirement.
        needs_review = any(link.link_method == "deterministic_ambiguous_pending_agent" for link, _ in pairs)

        existing = db.query(Flag).filter(Flag.person_id == person.id, Flag.category == category).first()
        if existing:
            existing.is_exposed = True
            existing.confidence = avg_confidence
            existing.evidence_count = len(pairs)
            existing.review_status = "needs_review" if needs_review else "auto_confirmed"
            flags.append(existing)
        else:
            flag = Flag(person_id=person.id, category=category, is_exposed=True,
                         confidence=avg_confidence, evidence_count=len(pairs),
                         review_status="needs_review" if needs_review else "auto_confirmed")
            db.add(flag)
            flags.append(flag)

    db.commit()
    return flags


def compute_flags_for_run(db: Session, run_id: str) -> int:
    """Recomputes flags for every person touched by documents in this run.
    Returns the number of flags written/updated."""
    person_ids = (
        db.query(IdentityLink.person_id)
        .join(Extraction, IdentityLink.extraction_id == Extraction.id)
        .join(Document, Extraction.document_id == Document.id)
        .filter(Document.run_id == run_id)
        .distinct()
        .all()
    )
    count = 0
    for (person_id,) in person_ids:
        person = db.query(Person).get(person_id)
        flags = compute_flags_for_person(db, person)
        count += len(flags)
    return count