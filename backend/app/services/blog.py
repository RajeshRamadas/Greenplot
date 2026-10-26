"""The marketing blog: which posts are live, related posts, and the pictures uploaded for posts."""

import io
import re
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BlogImage, BlogPost
from app.models.base import utcnow
from app.services.storage import get_storage, sniff_type

CATEGORIES = {
    "costs": "Costs & pricing",
    "plot-care": "Plot care",
    "nri": "For NRI owners",
    "protection": "Protecting your plot",
    "seasonal": "Seasonal guides",
    "gardening": "Gardens & plants",
    "our-work": "Our work",
    "news": "GreenPlot news",
}

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MAX_IMAGE_PX = 2000  # longest side; big enough for a full-width cover on a large screen


def state(p: BlogPost) -> str:
    """draft, scheduled (published with a future date) or published."""
    if p.status != "published" or p.published_at is None:
        return "draft"
    return "scheduled" if p.published_at > utcnow() else "published"


def reading_minutes(body: str) -> int:
    return max(1, round(len(re.findall(r"\w+", body)) / 200))


def tag_slug(tag: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")


def clean_tags(tags: list[str]) -> list[str]:
    """Trimmed, de-duplicated (ignoring case), in the order given."""
    out, seen = [], set()
    for t in tags:
        t = " ".join(t.split())
        if t and tag_slug(t) and tag_slug(t) not in seen:
            seen.add(tag_slug(t))
            out.append(t)
    return out


def live_posts(db: Session) -> list[BlogPost]:
    """Posts visitors can see now, newest first."""
    stmt = select(BlogPost).where(BlogPost.status == "published", BlogPost.published_at <= utcnow())
    return list(db.scalars(stmt.order_by(BlogPost.published_at.desc(), BlogPost.title)))


def live_post(db: Session, slug: str) -> BlogPost:
    p = db.scalar(select(BlogPost).where(BlogPost.slug == slug))
    if p is None or state(p) != "published":
        raise HTTPException(404, "Post not found")
    return p


def related(db: Session, post: BlogPost, limit: int = 3) -> list[BlogPost]:
    """Posts sharing the most tags, then the same category, then the newest."""
    tags = {tag_slug(t) for t in post.tags or []}

    def score(p: BlogPost) -> tuple:
        shared = len(tags & {tag_slug(t) for t in p.tags or []})
        return (shared, p.category == post.category)

    others = [p for p in live_posts(db) if p.id != post.id]
    # sorted() is stable, so posts with the same score stay newest first
    return sorted(others, key=score, reverse=True)[:limit]


def save_image(db: Session, data: bytes, filename: str | None, uploaded_by: uuid.UUID | None) -> BlogImage:
    """Check, resize and re-encode an uploaded picture. Re-encoding drops the camera's EXIF data,
    including the GPS location a phone photo carries."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if len(data) > get_settings().max_image_bytes:
        raise HTTPException(413, "This picture is too large. Please use one under 15 MB.")
    if sniff_type(data) not in IMAGE_TYPES:
        raise HTTPException(422, "Please upload a JPEG, PNG or WebP picture.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((MAX_IMAGE_PX, MAX_IMAGE_PX))
            out = io.BytesIO()
            if im.mode in ("RGBA", "LA", "P") and im.convert("RGBA").getextrema()[3][0] < 255:
                im.convert("RGBA").save(out, format="PNG", optimize=True)
                ctype, ext = "image/png", "png"
            else:
                im.convert("RGB").save(out, format="JPEG", quality=82, optimize=True, progressive=True)
                ctype, ext = "image/jpeg", "jpg"
            width, height = im.size
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, "This picture could not be read. Please try a JPEG or PNG.")
    content = out.getvalue()
    image_id = uuid.uuid4()
    key = f"blog/{image_id}.{ext}"
    get_storage().put(key, content, ctype)
    img = BlogImage(
        id=image_id,
        storage_key=key,
        content_type=ctype,
        size_bytes=len(content),
        width=width,
        height=height,
        filename=(filename or "")[:200] or None,
        uploaded_by=uploaded_by,
    )
    db.add(img)
    db.flush()
    return img


def image_url(img: BlogImage) -> str:
    """Same-origin path: the website forwards /api/v1 to the API."""
    ext = img.storage_key.rsplit(".", 1)[-1]
    return f"{get_settings().api_prefix}/public/blog/images/{img.id}.{ext}"
