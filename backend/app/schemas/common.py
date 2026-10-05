import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Stamped(ORM):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class Message(BaseModel):
    message: str


class GeoPoint(BaseModel):
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    accuracy_m: float | None = Field(None, ge=0)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class CommentIn(BaseModel):
    comment: str | None = Field(None, max_length=4000)
