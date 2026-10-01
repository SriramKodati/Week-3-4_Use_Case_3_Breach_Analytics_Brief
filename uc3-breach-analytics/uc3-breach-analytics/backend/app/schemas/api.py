from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RunOut(BaseModel):
    id: str
    status: str
    token_budget: int
    spend_budget_usd: float
    tokens_used_total: int
    spend_total_usd: float
    started_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentOut(BaseModel):
    id: str
    filename: str
    format: str
    status: str
    quarantine_reason: Optional[str] = None
    uploaded_at: datetime
    processed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExtractionOut(BaseModel):
    category: str
    raw_value: str
    confidence: float
    extraction_tier: int

    class Config:
        from_attributes = True


class PersonOut(BaseModel):
    id: str
    best_known_name: str
    dob: Optional[str] = None

    class Config:
        from_attributes = True


class ReviewDecisionIn(BaseModel):
    decision_type: str
    corrected_value: Optional[str] = None
    reviewer: str = "reviewer"

class FlagOut(BaseModel):
    id: str
    category: str
    is_exposed: bool
    confidence: float
    evidence_count: int
    review_status: str

    class Config:
        from_attributes = True


class EvidenceOut(BaseModel):
    document_filename: str
    category: str
    raw_value: str
    extraction_tier: int
    link_confidence: float
    link_method: str


class PersonDetailOut(BaseModel):
    id: str
    best_known_name: str
    dob: Optional[str] = None
    flags: list[FlagOut]
    evidence: list[EvidenceOut]


class ReviewQueueItemOut(BaseModel):
    identity_link_id: str
    person_id: str
    person_name: str
    category: str
    raw_value: str
    match_confidence: float
    agent_decision: Optional[str] = None
    agent_explanation: Optional[str] = None
    agent_confidence: Optional[float] = None


class TraceOut(BaseModel):
    agent_or_component: str
    tool_call_name: str
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
