"""
Orchestrates Monday's scope exactly, per the Week 4 Build Plan: triage,
parsing, Tier 0/1/2 extraction. Deliberately stops before entity
resolution (Tuesday) — a document leaves this pipeline in status
"extracted", ready for the next stage, not further.
"""
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Document, Extraction
from app.services.triage import triage_file
from app.services.parsing.parser import parse_document
from app.services.extraction.tier0_detectors import detect_tier0
from app.services.extraction.tier1_tier2 import extract_tier
from app.core.config import settings


def process_document(db: Session, document: Document, file_path: str):
    path = Path(file_path)

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

    # Tier 0: free, deterministic
    tier0_hits = detect_tier0(parsed.text)
    for hit in tier0_hits:
        db.add(Extraction(document_id=document.id, category=hit["category"],
                           raw_value=hit["raw_value"], confidence=hit["confidence"],
                           extraction_tier=0, source_passage=hit["source_passage"]))

    # Tier 1: cheap model, for categories Tier 0 can't catch deterministically
    tier1_result, tier1_error = extract_tier(parsed.text, tier=1)
    if tier1_result is not None:
        _log_tier1_fields(db, document.id, tier1_result, tier=1)

        # Fixed-threshold escalation (deterministic — not an agent decision)
        if tier1_result.self_assessed_confidence < settings.tier1_escalation_threshold:
            tier2_result, tier2_error = extract_tier(parsed.text, tier=2)
            if tier2_result is not None:
                _log_tier1_fields(db, document.id, tier2_result, tier=2)

    document.status = "extracted"
    document.processed_at = datetime.utcnow()
    db.commit()

    # Entity resolution — deterministic pass (Design Doc Section 6).
    # Multi-person documents (bulk spreadsheets) are detected and skipped
    # by the matcher itself, not handled here.
    from app.services.entity_resolution.matcher import resolve_document
    match_result = resolve_document(db, document)
    if match_result["result"] in ("matched", "new_person"):
        document.status = "resolved"
        db.commit()
    elif match_result["result"] == "ambiguous":
        document.status = "needs_adjudication"
        db.commit()

    return {"status": document.status, "tier0_count": len(tier0_hits), "match": match_result}


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
        if value:
            db.add(Extraction(document_id=document_id, category=category, raw_value=value,
                               confidence=result.self_assessed_confidence, extraction_tier=tier,
                               source_passage=None))
    db.commit()
