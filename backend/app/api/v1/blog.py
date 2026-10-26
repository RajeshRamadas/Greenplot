"""The marketing blog: public posts, RSS data and pictures, and the office's pages to write them."""

import re
import uuid
from collections import Counter
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select

from app.api.v1._util import apply
from app.core.deps import DB, Perm
from app.models import BlogImage, BlogPost
from app.models.base import utcnow
from app.schemas.common import Stamped
from app.services import audit
from app.services import blog as svc
from app.services.storage import get_storage

router = APIRouter(tags=["blog"])

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
Slug = Field(min_length=2, max_length=100, pattern=SLUG_RE.pattern)
# Keep in step with svc.CATEGORIES and the website's lib/blog.ts.
Category = Literal["costs", "plot-care", "nri", "protection", "seasonal", "gardening", "our-work", "news"]


def _check_tags(v: list[str] | None) -> list[str] | None:
    if v is None:
        return v
    if any(len(t) > 40 for t in v):
        raise ValueError("Keep each tag under 40 characters")
    return svc.clean_tags(v)


def _check_services(v: list[str] | None) -> list[str] | None:
    if v is None:
        return v
    if not all(SLUG_RE.match(s) and len(s) <= 60 for s in v):
        raise ValueError("Unknown service")
    return list(dict.fromkeys(v))


def _check_cover(v: str | None) -> str | None:
    if v and not (v.startswith("/") or v.startswith("https://")):
        raise ValueError("Use a picture uploaded here, a path on the website (/site/…) or an https:// link")
    return v or None


class PostCard(BaseModel):
    """What a list of posts needs; the body is left out."""

    slug: str
    title: str
    excerpt: str
    cover_image: str | None
    cover_alt: str | None
    category: str
    tags: list[str]
    published_at: datetime | None
    updated_at: datetime
    featured: bool
    author_name: str
    reading_minutes: int


class PostOut(PostCard):
    body: str
    services: list[str]
    seo_title: str | None
    seo_description: str | None


class PublicPostOut(BaseModel):
    post: PostOut
    related: list[PostCard]


class PostPage(BaseModel):
    items: list[PostCard]
    total: int
    limit: int
    offset: int


class AdminPostOut(PostOut, Stamped):
    status: str
    state: str  # draft, scheduled, published


class PostIn(BaseModel):
    slug: str = Slug
    title: str = Field(min_length=3, max_length=160)
    excerpt: str = Field(min_length=10, max_length=320)
    body: str = Field(min_length=1, max_length=100_000)
    cover_image: str | None = Field(None, max_length=300)
    cover_alt: str | None = Field(None, max_length=200)
    category: Category
    tags: list[str] = Field([], max_length=12)
    services: list[str] = Field([], max_length=6)
    seo_title: str | None = Field(None, max_length=70)
    seo_description: str | None = Field(None, max_length=170)
    status: Literal["draft", "published"] = "draft"
    # Leave empty to publish now; a future time schedules the post.
    published_at: datetime | None = None
    featured: bool = False
    author_name: str = Field("GreenPlot team", min_length=2, max_length=120)

    _tags = field_validator("tags")(classmethod(lambda cls, v: _check_tags(v)))
    _services = field_validator("services")(classmethod(lambda cls, v: _check_services(v)))
    _cover = field_validator("cover_image")(classmethod(lambda cls, v: _check_cover(v)))


class PostPatch(BaseModel):
    slug: str | None = Field(None, min_length=2, max_length=100, pattern=SLUG_RE.pattern)
    title: str | None = Field(None, min_length=3, max_length=160)
    excerpt: str | None = Field(None, min_length=10, max_length=320)
    body: str | None = Field(None, min_length=1, max_length=100_000)
    cover_image: str | None = Field(None, max_length=300)
    cover_alt: str | None = Field(None, max_length=200)
    category: Category | None = None
    tags: list[str] | None = Field(None, max_length=12)
    services: list[str] | None = Field(None, max_length=6)
    seo_title: str | None = Field(None, max_length=70)
    seo_description: str | None = Field(None, max_length=170)
    status: Literal["draft", "published"] | None = None
    published_at: datetime | None = None
    featured: bool | None = None
    author_name: str | None = Field(None, min_length=2, max_length=120)

    _tags = field_validator("tags")(classmethod(lambda cls, v: _check_tags(v)))
    _services = field_validator("services")(classmethod(lambda cls, v: _check_services(v)))
    _cover = field_validator("cover_image")(classmethod(lambda cls, v: _check_cover(v)))


class ImageOut(BaseModel):
    id: uuid.UUID
    url: str
    width: int
    height: int


def _card(p: BlogPost, model=PostCard):
    data = {f: getattr(p, f) for f in model.model_fields if hasattr(p, f)}
    data["reading_minutes"] = svc.reading_minutes(p.body)
    if model is AdminPostOut:
        data["state"] = svc.state(p)
    return model(**data)


# --------------------------------------------------------------------------- public


@router.get("/public/blog/posts", response_model=PostPage)
def public_posts(db: DB, category: str | None = None, tag: str | None = None, limit: int = 12, offset: int = 0):
    limit, offset = max(1, min(limit, 500)), max(0, offset)
    posts = svc.live_posts(db)
    if category:
        posts = [p for p in posts if p.category == category]
    if tag:
        posts = [p for p in posts if tag in {svc.tag_slug(t) for t in p.tags or []}]
    return PostPage(items=[_card(p) for p in posts[offset : offset + limit]], total=len(posts), limit=limit, offset=offset)


@router.get("/public/blog/posts/{slug}", response_model=PublicPostOut)
def public_post(slug: str, db: DB):
    p = svc.live_post(db, slug)
    return PublicPostOut(post=_card(p, PostOut), related=[_card(r) for r in svc.related(db, p)])


@router.get("/public/blog/topics")
def public_topics(db: DB):
    """Categories and tags that have live posts, with counts, for the blog's menus and the sitemap."""
    posts = svc.live_posts(db)
    cats = Counter(p.category for p in posts)
    tags: dict[str, dict] = {}
    for p in posts:
        for t in p.tags or []:
            entry = tags.setdefault(svc.tag_slug(t), {"slug": svc.tag_slug(t), "name": t, "count": 0})
            entry["count"] += 1
    return {
        "categories": [{"slug": k, "name": v, "count": cats[k]} for k, v in svc.CATEGORIES.items() if cats[k]],
        "tags": sorted(tags.values(), key=lambda t: (-t["count"], t["name"].lower())),
        "updated_at": max((p.updated_at for p in posts), default=None),
    }


@router.get("/public/blog/images/{name}")
def public_image(name: str, db: DB):
    try:
        image_id = uuid.UUID(name.split(".", 1)[0])
    except ValueError:
        raise HTTPException(404, "Not found")
    img = db.get(BlogImage, image_id)
    if img is None:
        raise HTTPException(404, "Not found")
    try:
        content = get_storage().get(img.storage_key)
    except (FileNotFoundError, OSError):
        raise HTTPException(404, "Not found")
    # An image id never changes content, so browsers and Cloudflare can keep it for a year.
    return Response(content, media_type=img.content_type, headers={"Cache-Control": "public, max-age=31536000, immutable"})


# --------------------------------------------------------------------------- office


@router.get("/blog/posts", response_model=list[AdminPostOut])
def list_posts(db: DB, actor: Perm("blog.manage"), q: str | None = None, state: str | None = None):
    stmt = select(BlogPost)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(BlogPost.title.ilike(like), BlogPost.slug.ilike(like)))
    posts = [_card(p, AdminPostOut) for p in db.scalars(stmt.order_by(BlogPost.updated_at.desc()))]
    return [p for p in posts if not state or p.state == state]


def _post(db, post_id: uuid.UUID) -> BlogPost:
    p = db.get(BlogPost, post_id)
    if p is None:
        raise HTTPException(404, "Post not found")
    return p


def _slug_free(db, slug: str, post_id: uuid.UUID | None = None):
    other = db.scalar(select(BlogPost.id).where(BlogPost.slug == slug))
    if other and other != post_id:
        raise HTTPException(409, "Another post already uses this web address")


@router.get("/blog/posts/{post_id}", response_model=AdminPostOut)
def get_post(post_id: uuid.UUID, db: DB, actor: Perm("blog.manage")):
    return _card(_post(db, post_id), AdminPostOut)


@router.post("/blog/posts", response_model=AdminPostOut, status_code=201)
def create_post(body: PostIn, db: DB, actor: Perm("blog.manage")):
    _slug_free(db, body.slug)
    data = body.model_dump()
    if data["status"] == "published" and data["published_at"] is None:
        data["published_at"] = utcnow()
    p = BlogPost(**data, created_by=actor.id)
    db.add(p)
    db.flush()
    audit.record(db, actor, "blog.post_created", "blog_post", p.id, new={"slug": p.slug, "status": p.status})
    db.commit()
    return _card(p, AdminPostOut)


@router.patch("/blog/posts/{post_id}", response_model=AdminPostOut)
def update_post(post_id: uuid.UUID, body: PostPatch, db: DB, actor: Perm("blog.manage")):
    p = _post(db, post_id)
    # Only these can be cleared; the rest keep their value when sent empty.
    clearable = ("cover_image", "cover_alt", "seo_title", "seo_description", "published_at")
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k in clearable}
    if "slug" in data:
        _slug_free(db, data["slug"], p.id)
    status = data.get("status", p.status)
    if status == "published" and data.get("published_at", p.published_at) is None:
        data["published_at"] = utcnow()
    before = audit.snapshot(p, [k for k in data if k != "body"])
    apply(p, data)
    audit.record(
        db, actor, "blog.post_updated", "blog_post", p.id, old=before, new=audit.jsonable({k: v for k, v in data.items() if k != "body"})
    )
    db.commit()
    return _card(p, AdminPostOut)


@router.delete("/blog/posts/{post_id}", status_code=204)
def delete_post(post_id: uuid.UUID, db: DB, actor: Perm("blog.manage")):
    p = _post(db, post_id)
    audit.record(db, actor, "blog.post_deleted", "blog_post", p.id, old={"slug": p.slug, "title": p.title})
    db.delete(p)
    db.commit()
    return Response(status_code=204)


@router.post("/blog/images", response_model=ImageOut, status_code=201)
async def upload_image(file: UploadFile, db: DB, actor: Perm("blog.manage")):
    data = await file.read()
    img = svc.save_image(db, data, file.filename, actor.id)
    audit.record(db, actor, "blog.image_uploaded", "blog_image", img.id, new={"filename": img.filename, "size_bytes": img.size_bytes})
    db.commit()
    return ImageOut(id=img.id, url=svc.image_url(img), width=img.width, height=img.height)
