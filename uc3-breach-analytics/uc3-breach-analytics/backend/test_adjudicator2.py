from itertools import groupby
from app.db.base import SessionLocal
from app.db.models import Run, IdentityLink, Extraction
from app.agents.real_agents import EntityResolutionAdjudicator

db = SessionLocal()
run = db.query(Run).first()

pending = db.query(IdentityLink).filter(
    IdentityLink.link_method == "deterministic_ambiguous_pending_agent"
).all()

groups = {}
for link in pending:
    extraction = db.query(Extraction).get(link.extraction_id)
    key = (extraction.document_id, link.person_id)
    groups.setdefault(key, []).append(link)

print(f"Found {len(pending)} pending link(s) grouped into {len(groups)} match(es)")

agent = EntityResolutionAdjudicator()
for key, links in groups.items():
    result = agent.adjudicate_group(db, links, run)
    print(result)
