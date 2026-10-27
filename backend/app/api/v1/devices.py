"""The Android and iPhone apps: push registration and the version check they make at start-up."""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DB, CurrentActor
from app.models import DeviceToken
from app.models.base import utcnow
from app.schemas.common import ORM, Message
from app.services import push

router = APIRouter(tags=["app"])


class DeviceIn(BaseModel):
    token: str = Field(min_length=20, max_length=512, description="The Firebase Cloud Messaging registration token")
    platform: Literal["android", "ios", "web"]
    app_version: str | None = Field(None, max_length=40)
    device_name: str | None = Field(None, max_length=200)


class DeviceOut(ORM):
    id: uuid.UUID
    platform: str
    app_version: str | None
    device_name: str | None
    last_seen_at: datetime | None
    created_at: datetime


@router.post("/devices", response_model=DeviceOut, status_code=201)
def register_device(body: DeviceIn, db: DB, actor: CurrentActor):
    """Register this phone for push notifications. Call after sign-in and whenever Firebase gives the app a new token.

    The phone stays registered while this sign-in session lasts; signing out stops its pushes.
    """
    if actor.session_id is None:
        raise HTTPException(422, "Sign in again to turn on notifications")
    d = db.scalar(select(DeviceToken).where(DeviceToken.token == body.token))
    if d is None:
        d = DeviceToken(token=body.token)
        db.add(d)
    # A token belongs to one app install; if someone else signs in on the phone it moves to them.
    d.user_id, d.tenant_id, d.session_id = actor.id, actor.user.tenant_id, actor.session_id
    d.platform, d.app_version, d.device_name = body.platform, body.app_version, body.device_name
    d.last_seen_at, d.disabled_at, d.disabled_reason = utcnow(), None, None
    db.commit()
    return d


@router.get("/devices", response_model=list[DeviceOut])
def my_devices(db: DB, actor: CurrentActor):
    """Phones that get your notifications."""
    return push.active_devices(db, actor.id)


@router.delete("/devices/{device_id}", response_model=Message)
def remove_device(device_id: uuid.UUID, db: DB, actor: CurrentActor):
    d = db.get(DeviceToken, device_id)
    if d is None or d.user_id != actor.id:
        raise HTTPException(404, "Device not found")
    db.delete(d)
    db.commit()
    return Message(message="Notifications turned off for this device")


class StoreLinks(BaseModel):
    android: str | None
    ios: str | None


class AppConfigOut(BaseModel):
    api_version: str
    min_version: StoreLinks
    store_url: StoreLinks
    push_enabled: bool
    whatsapp_number: str


@router.get("/app/config", response_model=AppConfigOut)
def app_config():
    """Read by the apps at start-up (no sign-in needed). An app older than min_version should ask to update."""
    s = get_settings()
    return AppConfigOut(
        api_version="v1",
        min_version=StoreLinks(android=s.app_min_version_android, ios=s.app_min_version_ios),
        store_url=StoreLinks(android=s.app_store_url_android, ios=s.app_store_url_ios),
        push_enabled=push.enabled(),
        whatsapp_number=s.whatsapp_number,
    )
