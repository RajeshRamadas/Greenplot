import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Counter
from app.models.base import utcnow

PREFIX = {
    "MNT": "GP-MNT",
    "CMP": "GP-CMP",
    "INS": "GP-INS",
    "INC": "GP-INC",
    "INV": "GP-INV",
    "RCT": "GP-RCT",
    "TKT": "GP-TKT",
}

# Ticket numbers use six digits (GP-TKT-2026-000001, ticketing requirements §6).
WIDTH = {"TKT": 6}


def next_number(db: Session, tenant_id: uuid.UUID, kind: str) -> str:
    """Allocate the next human-readable record number, e.g. GP-MNT-2026-00418."""
    year = utcnow().year
    stmt = select(Counter).where(Counter.tenant_id == tenant_id, Counter.kind == kind, Counter.year == year)
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    counter = db.scalar(stmt)
    if counter is None:
        counter = Counter(tenant_id=tenant_id, kind=kind, year=year, value=0)
        db.add(counter)
    counter.value += 1
    db.flush()
    return f"{PREFIX[kind]}-{year}-{counter.value:0{WIDTH.get(kind, 5)}d}"
