"""initial schema — runs, documents, extractions, persons, identity_links, flags, review_decisions, run_traces

Revision ID: 0001
Revises:
Create Date: 2026-09-16

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "runs",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("status", sa.String, default="running"),
        sa.Column("token_budget", sa.Integer, nullable=False),
        sa.Column("spend_budget_usd", sa.Float, nullable=False),
        sa.Column("tokens_used_total", sa.Integer, default=0),
        sa.Column("spend_total_usd", sa.Float, default=0.0),
        sa.Column("started_at", sa.DateTime),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("filename", sa.String, nullable=False),
        sa.Column("format", sa.String, nullable=False),
        sa.Column("status", sa.String, default="queued"),
        sa.Column("quarantine_reason", sa.String, nullable=True),
        sa.Column("uploaded_at", sa.DateTime),
        sa.Column("processed_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "extractions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("document_id", sa.String, sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("raw_value", sa.String, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("extraction_tier", sa.Integer, nullable=False),
        sa.Column("source_passage", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime),
    )

    op.create_table(
        "persons",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("best_known_name", sa.String, nullable=False),
        sa.Column("dob", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )

    op.create_table(
        "identity_links",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("extraction_id", sa.String, sa.ForeignKey("extractions.id"), nullable=False, unique=True),
        sa.Column("person_id", sa.String, sa.ForeignKey("persons.id"), nullable=False),
        sa.Column("link_confidence", sa.Float, nullable=False),
        sa.Column("link_method", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime),
    )

    op.create_table(
        "flags",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("person_id", sa.String, sa.ForeignKey("persons.id"), nullable=False),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("is_exposed", sa.Boolean, default=True),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("evidence_count", sa.Integer, default=0),
        sa.Column("review_status", sa.String, default="auto_accepted"),
    )

    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("identity_link_id", sa.String, sa.ForeignKey("identity_links.id"), nullable=True),
        sa.Column("flag_id", sa.String, sa.ForeignKey("flags.id"), nullable=True),
        sa.Column("decision_type", sa.String, nullable=False),
        sa.Column("original_value", sa.String, nullable=True),
        sa.Column("corrected_value", sa.String, nullable=True),
        sa.Column("reviewer", sa.String, nullable=False),
        sa.Column("decided_at", sa.DateTime),
    )

    op.create_table(
        "run_traces",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("run_id", sa.String, sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("agent_or_component", sa.String, nullable=False),
        sa.Column("tool_call_name", sa.String, nullable=False),
        sa.Column("input_summary", sa.Text, nullable=True),
        sa.Column("output_summary", sa.Text, nullable=True),
        sa.Column("tokens_used", sa.Integer, default=0),
        sa.Column("latency_ms", sa.Integer, default=0),
        sa.Column("cost_usd", sa.Float, default=0.0),
        sa.Column("created_at", sa.DateTime),
    )


def downgrade():
    op.drop_table("run_traces")
    op.drop_table("review_decisions")
    op.drop_table("flags")
    op.drop_table("identity_links")
    op.drop_table("persons")
    op.drop_table("extractions")
    op.drop_table("documents")
    op.drop_table("runs")
