"""Unauthenticated endpoints used by the public website (requirements §32)."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.v1._util import Limit, Offset, paginate
from app.core.deps import DB, Perm, client_ip
from app.core.ratelimit import limiter
from app.models import DemoRequest
from app.schemas.common import Page, Stamped

router = APIRouter(tags=["public"])


class DemoIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=8, max_length=30, pattern=r"^[0-9+\-\s()]+$")
    email: EmailStr | None = None
    layout_name: str | None = Field(None, max_length=200)
    plots: int | None = Field(None, ge=1, le=100000)
    city: str | None = Field(None, max_length=100)
    message: str | None = Field(None, max_length=2000)
    website: str | None = Field(None, description="Honeypot; must stay empty")


class DemoOut(Stamped):
    name: str
    phone: str
    email: str | None
    layout_name: str | None
    plots: int | None
    city: str | None
    message: str | None
    status: str


@router.post("/public/demo-requests", status_code=201)
def request_demo(body: DemoIn, request: Request, db: DB):
    ip = client_ip(request) or "unknown"
    if not limiter.allow(f"demo:{ip}", 5, 3600):
        raise HTTPException(429, "Too many requests. Please reach us on WhatsApp.")
    if body.website:  # bots fill hidden fields; pretend success
        return {"ok": True}
    db.add(DemoRequest(**body.model_dump(exclude={"website"}), ip=ip))
    db.commit()
    return {"ok": True}


@router.get("/public/demo-requests", response_model=Page[DemoOut])
def list_demo_requests(db: DB, actor: Perm("tenants.manage"), limit: int = Limit, offset: int = Offset):
    items, total = paginate(db, select(DemoRequest).order_by(DemoRequest.created_at.desc()), limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)
