from app.db.base import SessionLocal
from app.db.models import Run, IdentityLink
from app.agents.real_agents import EntityResolutionAdjudicator

db = SessionLocal()
run = db.query(Run).first()

pending = db.query(IdentityLink).filter(
    IdentityLink.link_method == "deterministic_ambiguous_pending_agent"
).all()

print(f"Found {len(pending)} pending ambiguous link(s)")

agent = EntityResolutionAdjudicator()
for link in pending:
    result = agent.adjudicate(db, link, run)
    print(result)
