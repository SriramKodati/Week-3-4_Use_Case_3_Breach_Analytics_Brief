"""
Real implementations of the endpoints that not_yet_implemented.py used to
stub out with 501s: person/exposure listing, the human review queue for
agent-flagged ambiguous matches, run traces, and export.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import require_api_key
from app.db.base import get_db
from app.db.models import Person, Flag, IdentityLink, Extraction, Document, ReviewDecision, RunTrace
from app.schemas.api import PersonOut, PersonDetailOut, FlagOut, EvidenceOut, ReviewQueueItemOut, ReviewDecisionIn, TraceOut

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/persons", response_model=list[PersonOut])
def list_persons(db: Session = Depends(get_db)):
    return db.query(Person).all()


@router.get("/persons/{person_id}", response_model=PersonDetailOut)
def get_person(person_id: str, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if person is None:
        raise HTTPException(404, "person not found")

    flags = db.query(Flag).filter(Flag.person_id == person_id).all()

    links = db.query(IdentityLink).filter(IdentityLink.person_id == person_id).all()
    evidence = []
    for link in links:
        extraction = db.get(Extraction, link.extraction_id)
        document = db.get(Document, extraction.document_id)
        evidence.append(EvidenceOut(
            document_filename=document.filename,
            category=extraction.category,
            raw_value=extraction.raw_value,
            extraction_tier=extraction.extraction_tier,
            link_confidence=link.link_confidence,
            link_method=link.link_method,
        ))

    return PersonDetailOut(id=person.id, best_known_name=person.best_known_name,
                            dob=str(person.dob) if person.dob else None,
                            flags=flags, evidence=evidence)


@router.get("/review/queue", response_model=list[ReviewQueueItemOut])
def review_queue(db: Session = Depends(get_db)):
    pending_links = (
        db.query(IdentityLink)
        .filter(IdentityLink.link_method == "deterministic_ambiguous_pending_agent")
        .all()
    )

    items = []
    for link in pending_links:
        decisions = db.query(ReviewDecision).filter(ReviewDecision.identity_link_id == link.id).all()
        already_decided_by_human = any(d.reviewer != "entity_resolution_adjudicator_agent" for d in decisions)
        if already_decided_by_human:
            continue

        agent_decision = next((d for d in decisions if d.reviewer == "entity_resolution_adjudicator_agent"), None)

        extraction = db.get(Extraction, link.extraction_id)
        person = db.get(Person, link.person_id)

        items.append(ReviewQueueItemOut(
            identity_link_id=link.id,
            person_id=person.id,
            person_name=person.best_known_name,
            category=extraction.category,
            raw_value=extraction.raw_value,
            match_confidence=link.link_confidence,
            agent_decision=agent_decision.decision_type.replace("agent_", "") if agent_decision else None,
            agent_explanation=agent_decision.corrected_value if agent_decision else None,
        ))
    return items


@router.post("/review/{item_id}/decide")
def review_decide(item_id: str, decision: ReviewDecisionIn, db: Session = Depends(get_db)):
    link = db.get(IdentityLink, item_id)
    if link is None:
        raise HTTPException(404, "review item not found")

    if decision.decision_type not in ("confirmed_merge", "confirmed_split"):
        raise HTTPException(400, "decision_type must be 'confirmed_merge' or 'confirmed_split'")

    db.add(ReviewDecision(identity_link_id=link.id, decision_type=decision.decision_type,
                           original_value=link.person_id, corrected_value=decision.corrected_value,
                           reviewer=decision.reviewer))

    if decision.decision_type == "confirmed_merge":
        link.link_method = "human_confirmed_merge"
    else:
        extraction = db.get(Extraction, link.extraction_id)
        new_person = Person(best_known_name=extraction.raw_value if extraction.category == "name" else "unknown (split by reviewer)")
        db.add(new_person)
        db.flush()
        link.person_id = new_person.id
        link.link_method = "human_confirmed_split"

    db.commit()

    from app.services.exposure.flags import compute_flags_for_person
    compute_flags_for_person(db, db.get(Person, link.person_id))

    return {"status": "recorded", "decision_type": decision.decision_type}


@router.get("/traces/{run_id}", response_model=list[TraceOut])
def get_traces(run_id: str, db: Session = Depends(get_db)):
    return db.query(RunTrace).filter(RunTrace.run_id == run_id).order_by(RunTrace.created_at).all()


@router.get("/export")
def export(db: Session = Depends(get_db)):
    persons = db.query(Person).all()
    out = []
    for person in persons:
        flags = db.query(Flag).filter(Flag.person_id == person.id, Flag.is_exposed == True).all()
        confirmed_flags = [f for f in flags if f.review_status != "needs_review"]
        if not confirmed_flags:
            continue
        out.append({
            "person_id": person.id,
            "name": person.best_known_name,
            "dob": str(person.dob) if person.dob else None,
            "exposed_categories": [
                {"category": f.category, "confidence": f.confidence, "evidence_count": f.evidence_count}
                for f in confirmed_flags
            ],
        })
    return out
