from app.db.base import SessionLocal
from app.db.models import Run
from app.services.exposure.flags import compute_flags_for_run
from app.agents.real_agents import QAAuditor

db = SessionLocal()
run = db.query(Run).first()

count = compute_flags_for_run(db, run.id)
print(f"Computed/updated {count} flags")

auditor = QAAuditor()
result = auditor.audit_sample(db, run, sample_size=10)
print(result)
