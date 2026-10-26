"""The marketing blog on the public website (not tenant data: the blog is GreenPlot's own)."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Model, UTCDateTime


class BlogPost(Model):
    """A post at /blog/<slug>. The body is Markdown; {{price:…}}-style tokens are filled in by the website."""

    __tablename__ = "blog_posts"

    slug: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    # Shown on cards and used as the meta description when seo_description is empty.
    excerpt: Mapped[str] = mapped_column(String(320))
    body: Mapped[str] = mapped_column(Text)
    cover_image: Mapped[str | None] = mapped_column(String(300), nullable=True)  # website path or full URL
    cover_alt: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    services: Mapped[list] = mapped_column(JSON, default=list)  # service slugs linked under the post
    seo_title: Mapped[str | None] = mapped_column(String(70), nullable=True)
    seo_description: Mapped[str | None] = mapped_column(String(170), nullable=True)
    # draft, or published; a published post with a future published_at is scheduled.
    status: Mapped[str] = mapped_column(String(10), default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    author_name: Mapped[str] = mapped_column(String(120), default="GreenPlot team")
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class BlogImage(Model):
    """A picture uploaded for the blog. Unlike job photos it is public, served by the API at a fixed URL."""

    __tablename__ = "blog_images"

    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    content_type: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


__all__ = ["BlogImage", "BlogPost"]
