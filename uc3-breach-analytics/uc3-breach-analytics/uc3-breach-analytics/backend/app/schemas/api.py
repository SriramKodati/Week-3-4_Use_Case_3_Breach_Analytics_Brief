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
