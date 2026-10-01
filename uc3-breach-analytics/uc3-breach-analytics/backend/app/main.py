from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.base import Base, engine
from app.api.v1 import health, documents, exposure

Base.metadata.create_all(bind=engine)  # local dev convenience; Alembic owns real migrations

app = FastAPI(title="DataFactZ UC3 — Breach Analytics Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(exposure.router, prefix="/api/v1")