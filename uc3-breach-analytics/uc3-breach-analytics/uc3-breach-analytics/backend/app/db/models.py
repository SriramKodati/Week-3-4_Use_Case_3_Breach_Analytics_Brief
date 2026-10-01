"""
SQLAlchemy models matching the ERD in the Solution Design Document
(Figure 2) exactly: RUN, DOCUMENT, EXTRACTION, PERSON, IDENTITY_LINK,
FLAG, REVIEW_DECISION, RUN_TRACE.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.db.base import Base


def gen_uuid():
    return str(uuid.uuid4())


class Run(Base):
    __tablename__ = "runs"

    id = Column(String, primary_key=True, default=gen_uuid)
    status = Column(String, default="running")  # running|completed|budget_exceeded|failed
    token_budget = Column(Integer, nullable=False)
    spend_budget_usd = Column(Float, nullable=False)
    tokens_used_total = Column(Integer, default=0)
    spend_total_usd = Column(Float, default=0.0)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    documents = relationship("Document", back_populates="run")
    traces = relationship("RunTrace", back_populates="run", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=gen_uuid)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    filename = Column(String, nullable=False)
    format = Column(String, nullable=False)
    status = Column(String, default="queued")  # queued|processing|parsed|quarantined|escalated|failed
    quarantine_reason = Column(String, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)

    run = relationship("Run", back_populates="documents")
    extractions = relationship("Extraction", back_populates="document", cascade="all, delete-orphan")


class Extraction(Base):
    """Generic — one row per detected element. category + extraction_tier
    together power both per-category accuracy and per-tier cost reporting
    from this single table (Design Doc Section 4)."""
    __tablename__ = "extractions"

    id = Column(String, primary_key=True, default=gen_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    category = Column(String, nullable=False)  # ssn|dob|phone|email|name|financial_account|...
    raw_value = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    extraction_tier = Column(Integer, nullable=False)  # 0, 1, or 2
    source_passage = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="extractions")
    identity_link = relationship("IdentityLink", back_populates="extraction", uselist=False)


class Person(Base):
    __tablename__ = "persons"

    id = Column(String, primary_key=True, default=gen_uuid)
    best_known_name = Column(String, nullable=False)
    dob = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    identity_links = relationship("IdentityLink", back_populates="person")
    flags = relationship("Flag", back_populates="person", cascade="all, delete-orphan")


class IdentityLink(Base):
    __tablename__ = "identity_links"

    id = Column(String, primary_key=True, default=gen_uuid)
    extraction_id = Column(String, ForeignKey("extractions.id"), nullable=False, unique=True)
    person_id = Column(String, ForeignKey("persons.id"), nullable=False)
    link_confidence = Column(Float, nullable=False)
    link_method = Column(String, nullable=False)  # deterministic|adjudicator|human
    created_at = Column(DateTime, default=datetime.utcnow)

    extraction = relationship("Extraction", back_populates="identity_link")
    person = relationship("Person", back_populates="identity_links")
    review_decisions = relationship("ReviewDecision", back_populates="identity_link")


class Flag(Base):
    """The fast, UI-facing view: one row per (person, category). Evidence
    traces through IDENTITY_LINK -> EXTRACTION -> DOCUMENT, not duplicated
    here."""
    __tablename__ = "flags"

    id = Column(String, primary_key=True, default=gen_uuid)
    person_id = Column(String, ForeignKey("persons.id"), nullable=False)
    category = Column(String, nullable=False)
    is_exposed = Column(Boolean, default=True)
    confidence = Column(Float, nullable=False)
    evidence_count = Column(Integer, default=0)
    review_status = Column(String, default="auto_accepted")  # auto_accepted|needs_review|human_reviewed

    person = relationship("Person", back_populates="flags")
    review_decisions = relationship("ReviewDecision", back_populates="flag")


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id = Column(String, primary_key=True, default=gen_uuid)
    identity_link_id = Column(String, ForeignKey("identity_links.id"), nullable=True)
    flag_id = Column(String, ForeignKey("flags.id"), nullable=True)
    decision_type = Column(String, nullable=False)  # correct|merge|split|escalate|approve
    original_value = Column(String, nullable=True)
    corrected_value = Column(String, nullable=True)
    reviewer = Column(String, nullable=False)
    decided_at = Column(DateTime, default=datetime.utcnow)

    identity_link = relationship("IdentityLink", back_populates="review_decisions")
    flag = relationship("Flag", back_populates="review_decisions")


class RunTrace(Base):
    """Every tool/model call, from any pipeline stage or agent — the
    record that makes the whole system auditable (Design Doc Section 2)."""
    __tablename__ = "run_traces"

    id = Column(String, primary_key=True, default=gen_uuid)
    run_id = Column(String, ForeignKey("runs.id"), nullable=False)
    agent_or_component = Column(String, nullable=False)
    tool_call_name = Column(String, nullable=False)
    input_summary = Column(Text, nullable=True)
    output_summary = Column(Text, nullable=True)
    tokens_used = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("Run", back_populates="traces")
