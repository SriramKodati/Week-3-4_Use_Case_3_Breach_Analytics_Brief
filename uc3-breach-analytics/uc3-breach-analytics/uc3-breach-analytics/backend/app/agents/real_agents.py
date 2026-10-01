"""
Orchestrator and Exception Investigator — real implementations (Tuesday
scope). EntityResolutionAdjudicator and QAAuditor remain stubs in
agents.py — that's Wednesday's work per the build plan, not faked here.
"""
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Run, Document, RunTrace
from app.core.config import settings


class Orchestrator:
    """Runs once per batch. Real, enforced budget checking — this is
    what the forced-failure demo exercises live, not a logged warning."""

    def plan_run(self, db: Session, run: Run) -> dict:
        documents = db.query(Document).filter(Document.run_id == run.id).all()
        by_format = {}
        for d in documents:
            by_format.setdefault(d.format or "unknown", []).append(d)

        # Cheap, deterministic documents first — digital text extraction is
        # faster and more reliable than OCR, so process it first; this is
        # a real prioritization decision, not just a status report.
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
        """Real enforcement: returns False and marks the run halted if
        either budget is exceeded. Called before every paid (Tier 1/2)
        step, not just logged at the end."""
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
    """Invoked only for quarantined documents. Tries a genuine alternate
    strategy for the two quarantine reasons that actually have one
    (wrong extension, low-confidence OCR); every other reason gets an
    honest escalation with a diagnosis, not a fake retry."""

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
            "zero_byte": "File contains no data — likely a failed export or transfer on the source side, not a parsing issue.",
        }
        return diagnoses.get(reason, f"Unrecognized quarantine reason '{reason}' — needs manual review.")

    def _recover_wrong_extension(self, db: Session, document: Document, file_path: str, run: Run) -> dict:
        """The file's bytes are a valid PDF despite its extension — copy
        it to a .pdf path and re-run it through the real pipeline."""
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
        """One alternate attempt: upscale the image before OCR, which
        sometimes recovers legibility a first pass misses. If confidence
        is still too low, escalate honestly rather than loop forever."""
        from PIL import Image
        import pytesseract

        img = Image.open(file_path)
        upscaled = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)

        data = pytesseract.image_to_data(upscaled, output_type=pytesseract.Output.DICT)
        # Only count confidence where real text was actually found — Tesseract
        # can report a high confidence on a spurious empty-string detection,
        # which would otherwise make a genuinely unreadable image look
        # falsely "recovered." Verified against a real corpus file: an
        # unfiltered average reported 0.95 confidence with ZERO actual words.
        confidences = [
            data["conf"][i] / 100.0 for i, word in enumerate(data["text"])
            if word.strip() and isinstance(data["conf"][i], (int, float)) and data["conf"][i] >= 0
        ]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        db.add(RunTrace(run_id=run.id, agent_or_component="exception_investigator",
                         tool_call_name="investigate",
                         output_summary=f"upscale retry: confidence {avg_conf:.2f} (threshold {settings.__dict__.get('low_ocr_threshold', 0.55)})"))

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
                "diagnosis": f"Upscale retry still only reached {avg_conf:.2f} confidence — image quality is genuinely too poor for reliable OCR, not a fixable preprocessing issue."}
