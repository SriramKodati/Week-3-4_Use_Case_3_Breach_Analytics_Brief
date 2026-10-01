"""
Orchestrator, Exception Investigator, Entity-Resolution Adjudicator, and
QA Auditor - real implementations for all four agents.
"""
import shutil
import random
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.db.models import Run, Document, RunTrace, IdentityLink, Extraction, Person, ReviewDecision
from app.core.config import settings
from app.services.extraction.tier1_tier2 import TIER_PROVIDERS, _repair_brackets, PROVIDER_RATE_PER_1K_TOKENS


class Orchestrator:
    """Runs once per batch. Real, enforced budget checking - this is
    what the forced-failure demo exercises live, not a logged warning."""

    def plan_run(self, db: Session, run: Run) -> dict:
        documents = db.query(Document).filter(Document.run_id == run.id).all()
        by_format = {}
        for d in documents:
            by_format.setdefault(d.format or "unknown", []).append(d)

        priority_order = ["pdf", "docx", "txt", "html", "csv", "xlsx", "eml", "image"]
        ordered_ids = []
        for fmt in priority_order:
            ordered_ids.extend([d.id for d in by_format.get(fmt, [])])
        for fmt, docs in by_format.items():
            if fmt not in priority_order:
                ordered_ids.extend([d.id for d in docs])

        quarantine_count = sum(1 for d in documents if d.status == "quarantined")
        quarantine_rate = quarantine_count / len(documents) if documents else 0.0

        db.add(RunTrace(run_id=run.id, agent_or_component="orchestrator", tool_call_name="plan_run",
                         input_summary=f"{len(documents)} documents",
                         output_summary=f"quarantine_rate={quarantine_rate:.2f}"))
        db.commit()

        return {
            "document_order": ordered_ids,
            "quarantine_rate": quarantine_rate,
            "high_quarantine_warning": quarantine_rate > 0.3,
        }

    def check_budget(self, db: Session, run: Run) -> bool:
        over_token = run.tokens_used_total >= run.token_budget
        over_spend = run.spend_total_usd >= run.spend_budget_usd

        db.add(RunTrace(run_id=run.id, agent_or_component="orchestrator", tool_call_name="check_budget",
                         input_summary=f"tokens={run.tokens_used_total}/{run.token_budget}, spend=${run.spend_total_usd:.4f}/${run.spend_budget_usd}",
                         output_summary="OK" if not (over_token or over_spend) else "BUDGET_EXCEEDED"))

        if over_token or over_spend:
            run.status = "budget_exceeded"
            run.completed_at = datetime.utcnow()
            db.commit()
            return False

        db.commit()
        return True


class ExceptionInvestigator:
    RECOVERABLE_REASONS = {"wrong_extension_actually_pdf", "low_confidence_ocr"}

    def investigate(self, db: Session, document: Document, file_path: str, run: Run) -> dict:
        reason = document.quarantine_reason or ""
        base_reason = reason.split(":")[0]

        db.add(RunTrace(run_id=run.id, agent_or_component="exception_investigator",
                         tool_call_name="investigate",
                         input_summary=f"{document.filename}: {reason}"))

        if base_reason not in self.RECOVERABLE_REASONS:
            diagnosis = self._diagnose_unrecoverable(base_reason)
            db.add(RunTrace(run_id=run.id, agent_or_component="exception_investigator",
                             tool_call_name="investigate", output_summary=f"escalated: {diagnosis}"))
            document.status = "escalated"
            db.commit()
            return {"result": "escalated", "diagnosis": diagnosis}

        if base_reason == "wrong_extension_actually_pdf":
            return self._recover_wrong_extension(db, document, file_path, run)

        if base_reason == "low_confidence_ocr":
            return self._retry_ocr_with_preprocessing(db, document, file_path, run)

    def _diagnose_unrecoverable(self, reason: str) -> str:
        diagnoses = {
            "password_protected": "File requires a password not available to this pipeline. Needs the source's credential holder.",
            "corrupt_file": "File structure is genuinely damaged, not a format-detection error. No automated recovery possible.",
            "zero_byte": "File contains no data - likely a failed export or transfer on the source side, not a parsing issue.",
        }
        return diagnoses.get(reason, f"Unrecognized quarantine reason '{reason}' - needs manual review.")

    def _recover_wrong_extension(self, db: Session, document: Document, file_path: str, run: Run) -> dict:
        from app.services.pipeline import process_document

        src = Path(file_path)
        fixed_path = src.with_suffix(".recovered.pdf")
        shutil.copy(src, fixed_path)

        document.status = "queued"
        document.quarantine_reason = None
        db.commit()

        result = process_document(db, document, str(fixed_path))

        db.add(RunTrace(run_id=run.id, agent_or_component="exception_investigator",
                         tool_call_name="investigate",
                         output_summary=f"resolved: reprocessed as PDF -> {result.get('status')}"))
        db.commit()
        return {"result": "resolved", "new_status": document.status}

    def _retry_ocr_with_preprocessing(self, db: Session, document: Document, file_path: str, run: Run) -> dict:
        from PIL import Image
        import pytesseract

        img = Image.open(file_path)
        upscaled = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)

        data = pytesseract.image_to_data(upscaled, output_type=pytesseract.Output.DICT)
        confidences = [
            data["conf"][i] / 100.0 for i, word in enumerate(data["text"])
            if word.strip() and isinstance(data["conf"][i], (int, float)) and data["conf"][i] >= 0
        ]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        db.add(RunTrace(run_id=run.id, agent_or_component="exception_investigator",
                         tool_call_name="investigate",
                         output_summary=f"upscale retry: confidence {avg_conf:.2f} (threshold 0.55)"))

        if avg_conf >= 0.55:
            from app.services.pipeline import process_document
            document.status = "queued"
            document.quarantine_reason = None
            db.commit()
            result = process_document(db, document, file_path)
            db.commit()
            return {"result": "resolved", "new_status": document.status, "recovered_confidence": avg_conf}

        document.status = "escalated"
        db.commit()
        return {"result": "escalated",
                "diagnosis": f"Upscale retry still only reached {avg_conf:.2f} confidence - image quality is genuinely too poor for reliable OCR, not a fixable preprocessing issue."}


class AdjudicationResult(BaseModel):
    decision: str  # "merge" | "split" | "escalate"
    explanation: str
    confidence: float = 0.5


ADJUDICATION_PROMPT = """You are reviewing an identity match that a deterministic matcher scored \
in the ambiguous range - not confident enough to auto-link, not weak enough to dismiss.

NEW EVIDENCE (from the document just processed):
- category of this specific value: {category}
- value: {value}
- other values extracted from the SAME document: {doc_signals}

CANDIDATE EXISTING PERSON this might be the same as:
- name on file: {person_name}
- date of birth on file: {person_dob}
- other values already linked to this person: {person_signals}
- the deterministic matcher's similarity score: {match_score:.2f} (0=no similarity, 1=identical)

Decide:
- "merge" if this is almost certainly the same real person (e.g. a nickname/initials variant \
with strong corroborating detail like a matching address).
- "split" if this is more likely a DIFFERENT real person who happens to share a similar name \
or partial detail, and should NOT be linked.
- "escalate" if you genuinely cannot tell from the evidence given - do not guess.

Return ONLY this JSON object, compact single line, no other text:
{{"decision": "merge" or "split" or "escalate", "explanation": "one or two sentences citing the specific evidence", "confidence": number 0 to 1}}"""


class EntityResolutionAdjudicator:
    """Invoked only when the deterministic matcher's similarity score lands
    in the ambiguous band. Reasons over both records' evidence using the
    escalation-tier model and returns an explained decision - this is
    recorded as a RECOMMENDATION (ReviewDecision rows) and does NOT
    auto-apply a merge; a human still approves before it's final.

    Called once per (document, candidate person) MATCH, not once per
    extraction."""

    def adjudicate_group(self, db: Session, identity_links: list[IdentityLink], run: Run) -> dict:
        anchor = identity_links[0]
        extraction = db.query(Extraction).get(anchor.extraction_id)
        person = db.query(Person).get(anchor.person_id)

        doc_signals = {
            e.category: e.raw_value
            for e in db.query(Extraction).filter(Extraction.document_id == extraction.document_id).all()
        }
        linked_extraction_ids = {l.extraction_id for l in identity_links}
        person_signals = {
            l.extraction.category: l.extraction.raw_value
            for l in db.query(IdentityLink)
            .filter(IdentityLink.person_id == person.id, ~IdentityLink.extraction_id.in_(linked_extraction_ids))
            .all()
        }

        prompt = ADJUDICATION_PROMPT.format(
            category="multiple (see below)",
            value=doc_signals,
            doc_signals=doc_signals,
            person_name=person.best_known_name,
            person_dob=person.dob,
            person_signals=person_signals,
            match_score=anchor.link_confidence,
        )

        provider_name = settings.tier2_provider  # agents always run on the escalation tier
        fn = TIER_PROVIDERS.get(provider_name)
        result, raw_error = None, None
        total_tokens = 0
        for attempt in range(3):
            raw, tokens = fn(prompt if attempt == 0 else prompt + "\n\nReturn corrected, compact single-line JSON only.")
            total_tokens += tokens
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            try:
                data = json.loads(cleaned)
            except json.JSONDecodeError:
                try:
                    data = json.loads(_repair_brackets(cleaned))
                except json.JSONDecodeError as e:
                    raw_error = f"invalid JSON: {e}"
                    continue
            try:
                result = AdjudicationResult(**data)
                break
            except ValidationError as e:
                raw_error = f"schema validation failed: {e}"
                continue

        cost = total_tokens / 1000 * PROVIDER_RATE_PER_1K_TOKENS.get(provider_name, 0.0)
        run.tokens_used_total += total_tokens
        run.spend_total_usd += cost

        db.add(RunTrace(run_id=run.id, agent_or_component="entity_resolution_adjudicator",
                         tool_call_name="adjudicate_group",
                         input_summary=f"doc={extraction.document_id} ({len(identity_links)} linked extractions) vs person={person.best_known_name}",
                         output_summary=(f"{result.decision}: {result.explanation}" if result else f"FAILED: {raw_error}")))
        db.commit()

        if result is None:
            for link in identity_links:
                db.add(ReviewDecision(identity_link_id=link.id, decision_type="agent_failed",
                                       original_value=str(person.id), corrected_value=raw_error,
                                       reviewer="entity_resolution_adjudicator_agent", decided_at=datetime.utcnow()))
            db.commit()
            return {"decision": "escalate", "target_person_id": None,
                    "explanation": f"Adjudicator could not produce a valid decision: {raw_error}", "confidence": 0.0}

        for link in identity_links:
            db.add(ReviewDecision(identity_link_id=link.id, decision_type=f"agent_{result.decision}",
                                   original_value=str(person.id), corrected_value=result.explanation,
                                   reviewer="entity_resolution_adjudicator_agent", decided_at=datetime.utcnow()))
        db.commit()

        return {
            "decision": result.decision,
            "target_person_id": person.id if result.decision == "merge" else None,
            "explanation": result.explanation,
            "confidence": result.confidence,
            "extractions_covered": len(identity_links),
        }


class QAAuditor:
    """Runs after a batch completes. Independently re-derives what it can
    from stored evidence and reports a measured accuracy estimate - not
    the system grading its own homework. Tier 0 evidence kept its source
    passage and can be re-checked; Tier 1/2 evidence never had its source
    text persisted, so those flags are reported as unverifiable rather
    than silently counted as correct."""

    def audit_sample(self, db: Session, run: Run, sample_size: int = 10) -> dict:
        from app.db.models import Flag, Document
        from app.services.extraction.tier0_detectors import detect_tier0

        flags = (
            db.query(Flag)
            .join(IdentityLink, IdentityLink.person_id == Flag.person_id)
            .join(Extraction, IdentityLink.extraction_id == Extraction.id)
            .join(Document, Extraction.document_id == Document.id)
            .filter(Document.run_id == run.id)
            .distinct()
            .all()
        )
        sample = random.sample(flags, min(sample_size, len(flags)))

        verified_match = verified_mismatch = unverifiable = 0
        details = []

        for flag in sample:
            links = (
                db.query(IdentityLink)
                .join(Extraction, IdentityLink.extraction_id == Extraction.id)
                .filter(IdentityLink.person_id == flag.person_id, Extraction.category == flag.category)
                .all()
            )
            outcome = "unverifiable"
            for link in links:
                extraction = db.query(Extraction).get(link.extraction_id)
                if extraction.extraction_tier == 0 and extraction.source_passage:
                    rederived = detect_tier0(extraction.source_passage)
                    match = any(hit["category"] == extraction.category and hit["raw_value"] == extraction.raw_value
                                for hit in rederived)
                    outcome = "match" if match else "mismatch"
                    break

            if outcome == "match":
                verified_match += 1
            elif outcome == "mismatch":
                verified_mismatch += 1
            else:
                unverifiable += 1

            details.append({"person_id": flag.person_id, "category": flag.category, "outcome": outcome})

        checkable = verified_match + verified_mismatch
        accuracy_on_checkable = verified_match / checkable if checkable else None

        db.add(RunTrace(run_id=run.id, agent_or_component="qa_auditor", tool_call_name="audit_sample",
                         input_summary=f"sampled {len(sample)} of {len(flags)} flags",
                         output_summary=f"match={verified_match} mismatch={verified_mismatch} unverifiable={unverifiable}"))
        db.commit()

        return {
            "sample_size": len(sample),
            "total_flags": len(flags),
            "verified_match": verified_match,
            "verified_mismatch": verified_mismatch,
            "unverifiable_no_source_passage": unverifiable,
            "accuracy_on_independently_checkable_subset": accuracy_on_checkable,
            "coverage": checkable / len(sample) if sample else 0.0,
            "details": details,
        }
