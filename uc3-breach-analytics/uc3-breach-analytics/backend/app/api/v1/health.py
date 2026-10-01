from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health():
    return {
        "status": "ok",
        "tier1_provider": settings.tier1_provider,
        "tier2_provider": settings.tier2_provider,
        "implemented_stages": ["triage", "parsing", "tier0_detection", "tier1_tier2_extraction"],
        "not_yet_implemented": ["entity_resolution", "orchestrator", "exception_investigator",
                                  "adjudicator", "qa_auditor", "review_queue_ui", "export"],
    }
