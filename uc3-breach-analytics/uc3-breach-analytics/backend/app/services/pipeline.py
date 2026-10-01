"""
Orchestrates ingestion through entity resolution: triage, parsing,
Tier 0/1/2 extraction (with real, enforced budget checking before each
paid step), and deterministic entity resolution.
"""
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Document, Extraction, Run
from app.services.triage import triage_file
from app.services.parsing.parser import parse_document
from app.services.extraction.tier0_detectors import detect_tier0
from app.services.extraction.tier1_tier2 import extract_tier
from app.core.config import settings

_NULL_LIKE = {"null", "none", "n/a", "na", ""}


def process_document(db: Session, document: Document, file_path: str):
    path = Path(file_path)
    run = db.get(Run, document.run_id) if document.run_id else None

    triage_result = triage_file(path)
    if triage_result.action == "quarantine":
        document.status = "quarantined"
        document.quarantine_reason = triage_result.reason
        document.processed_at = datetime.utcnow()
        db.commit()
        return {"status": "quarantined", "reason": triage_result.reason}

    document.status = "processing"
    document.format = triage_result.format
    db.commit()

    try:
        parsed = parse_document(path, triage_result.format)
    except Exception as e:
        document.status = "quarantined"
        document.quarantine_reason = f"parse_error:{e}"
        document.processed_at = datetime.utcnow()
        db.commit()
        return {"status": "quarantined", "reason": document.quarantine_reason}

    if parsed.quarantine_reason:
        document.status = "quarantined"
        document.quarantine_reason = parsed.quarantine_reason
        document.processed_at = datetime.utcnow()
        db.commit()
        return {"status": "quarantined", "reason": parsed.quarantine_reason}

    # Tier 0: free, deterministic - no budget check needed, costs nothing
    tier0_hits = detect_tier0(parsed.text)
    for hit in tier0_hits:
        db.add(Extraction(document_id=document.id, category=hit["category"],
                           raw_value=hit["raw_value"], confidence=hit["confidence"],
                           extraction_tier=0, source_passage=hit["source_passage"]))
    db.commit()

    # Tier 1: cheap model - a real, enforced budget check before spending
    if run is not None and not _check_budget_and_record(db, run):
        document.status = "budget_exceeded"
        document.processed_at = datetime.utcnow()
        db.commit()
        return {"status": "budget_exceeded", "tier0_count": len(tier0_hits)}

    tier1_result, tier1_error, tier1_tokens, tier1_cost = extract_tier(parsed.text, tier=1)
    if run is not None:
        run.tokens_used_total += tier1_tokens
        run.spend_total_usd += tier1_cost
        db.commit()

    if tier1_result is not None:
        _log_tier1_fields(db, document.id, tier1_result, tier=1)

        # Fixed-threshold escalation (deterministic - not an agent decision)
        if tier1_result.self_assessed_confidence < settings.tier1_escalation_threshold:
            if run is not None and not _check_budget_and_record(db, run):
                document.status = "budget_exceeded"
                document.processed_at = datetime.utcnow()
                db.commit()
                return {"status": "budget_exceeded", "tier0_count": len(tier0_hits)}

            tier2_result, tier2_error, tier2_tokens, tier2_cost = extract_tier(parsed.text, tier=2)
            if run is not None:
                run.tokens_used_total += tier2_tokens
                run.spend_total_usd += tier2_cost
                db.commit()
            if tier2_result is not None:
                _log_tier1_fields(db, document.id, tier2_result, tier=2)

    document.status = "extracted"
    document.processed_at = datetime.utcnow()
    db.commit()

    # Entity resolution - deterministic pass (Design Doc Section 6).
    from app.services.entity_resolution.matcher import resolve_document
    match_result = resolve_document(db, document)
    if match_result["result"] in ("matched", "new_person"):
        document.status = "resolved"
        db.commit()
    elif match_result["result"] == "ambiguous":
        document.status = "needs_adjudication"
        db.commit()
    elif match_result["result"] == "skipped_multi_person":
        document.status = "multi_person_skipped"
        db.commit()
    elif match_result["result"] == "insufficient_signal":
        document.status = "resolution_insufficient_signal"
        db.commit()

    return {"status": document.status, "tier0_count": len(tier0_hits), "match": match_result}


def _check_budget_and_record(db: Session, run: Run) -> bool:
    """Real enforcement, called right before a paid step. Uses the
    Orchestrator's check so there's one source of truth for the budget
    decision, not a second copy of the same comparison."""
    from app.agents.real_agents import Orchestrator
    return Orchestrator().check_budget(db, run)


def _log_tier1_fields(db: Session, document_id: str, result, tier: int):
    fields = [
        ("name", result.person_name),
        ("address", result.address),
        ("driver_license", result.driver_license),
        ("passport", result.passport),
        ("medical", result.medical_note),
        ("login_credential", result.login_credential),
    ]
    for category, value in fields:
        if value and str(value).strip().lower() not in _NULL_LIKE:
            db.add(Extraction(document_id=document_id, category=category, raw_value=value,
                               confidence=result.self_assessed_confidence, extraction_tier=tier,
                               source_passage=None))
    db.commit()
