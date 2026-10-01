"""
Document upload + status. Creates a Run on first upload if none is
active. Per Design Doc Section 5.
"""
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.api.v1.deps import require_api_key
from app.db.base import get_db, SessionLocal
from app.db.models import Document, Run
from app.schemas.api import DocumentOut, ExtractionOut, RunOut
from app.services.pipeline import process_document
from app.core.config import settings

router = APIRouter(dependencies=[Depends(require_api_key)])

Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


def _process_in_background(document_id: str, file_path: str):
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if document:
            process_document(db, document, file_path)
    finally:
        db.close()


def _get_or_create_active_run(db: Session) -> Run:
    run = db.query(Run).filter(Run.status == "running").order_by(Run.started_at.desc()).first()
    if run is None:
        run = Run(status="running", token_budget=settings.run_token_budget,
                   spend_budget_usd=settings.run_spend_budget_usd)
        db.add(run)
        db.commit()
    return run


@router.post("/documents", response_model=list[DocumentOut])
async def upload_documents(background_tasks: BackgroundTasks,
                            files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    run = _get_or_create_active_run(db)
    created = []
    for file in files:
        dest = Path(settings.upload_dir) / file.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        document = Document(run_id=run.id, filename=file.filename, format="unknown", status="queued")
        db.add(document)
        db.commit()
        created.append(document)
        background_tasks.add_task(_process_in_background, document.id, str(dest))

    return created


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return db.query(Document).order_by(Document.uploaded_at.desc()).all()


@router.get("/documents/{document_id}/extractions", response_model=list[ExtractionOut])
def get_extractions(document_id: str, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(404, "document not found")
    return document.extractions


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run
