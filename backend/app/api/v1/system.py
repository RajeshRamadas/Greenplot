from fastapi import APIRouter

from app.core.deps import DB, Perm
from app.models.base import utcnow
from app.schemas.operations import SyncIn, SyncOut
from app.services import jobs
from app.services import sync as sync_svc

router = APIRouter(tags=["system"])


@router.post("/sync", response_model=SyncOut)
def sync(body: SyncIn, db: DB, actor: Perm("sync.use")):
    """Replay operations queued offline by the guard/staff PWA. Safe to retry."""
    results = sync_svc.process(db, actor, body.operations, body.device_id)
    return SyncOut(results=results, server_time=utcnow())


@router.post("/jobs/run")
def run_jobs(db: DB, actor: Perm("settings.manage")):
    """Run background jobs now (schedules, reminders, SOS escalation, retention)."""
    return jobs.run_all(db)
