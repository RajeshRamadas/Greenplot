import io
from datetime import timedelta

from PIL import Image

from app.models import AuditLog, BlogImage
from app.models.base import utcnow
from tests.conftest import jpeg_bytes


def post(**kw):
    return {
        "slug": "plot-cleaning-cost",
        "title": "What plot cleaning costs",
        "excerpt": "Prices per sq ft and what changes them.",
        "body": "Intro paragraph.\n\n## Prices\n\n- {{rate:plot-cleaning}} per sq ft",
        "category": "costs",
        "tags": ["Plot cleaning", "Prices"],
        "services": ["plot-cleaning"],
        **kw,
    }


def test_only_platform_admin_writes_posts(as_, world, client):
    for user in (world.admin, world.supervisor, world.resident):
        assert as_(user).post("/blog/posts", json=post()).status_code == 403
        assert as_(user).get("/blog/posts").status_code == 403
    assert client.post("/api/v1/blog/posts", json=post()).status_code == 401
    as_(world.super).ok("post", "/blog/posts", json=post())


def test_drafts_and_scheduled_posts_stay_hidden(as_, world, client, db):
    root = as_(world.super)
    draft = root.ok("post", "/blog/posts", json=post())
    assert draft["state"] == "draft" and draft["published_at"] is None
    assert client.get("/api/v1/public/blog/posts").json()["total"] == 0
    assert client.get("/api/v1/public/blog/posts/plot-cleaning-cost").status_code == 404

    later = (utcnow() + timedelta(days=2)).isoformat()
    scheduled = root.ok("patch", f"/blog/posts/{draft['id']}", json={"status": "published", "published_at": later})
    assert scheduled["state"] == "scheduled"
    assert client.get("/api/v1/public/blog/posts/plot-cleaning-cost").status_code == 404

    live = root.ok("patch", f"/blog/posts/{draft['id']}", json={"published_at": None})
    assert live["state"] == "published" and live["published_at"]  # publishing without a date means now
    r = client.get("/api/v1/public/blog/posts/plot-cleaning-cost")
    assert r.status_code == 200
    assert r.json()["post"]["body"].startswith("Intro paragraph.")
    assert r.json()["post"]["reading_minutes"] == 1
    assert db.query(AuditLog).filter(AuditLog.action.like("blog.%")).count() == 3


def test_publish_now_on_create_and_slug_must_be_unique(as_, world, client):
    root = as_(world.super)
    p = root.ok("post", "/blog/posts", json=post(status="published"))
    assert p["state"] == "published"
    assert root.post("/blog/posts", json=post()).status_code == 409
    other = root.ok("post", "/blog/posts", json=post(slug="another-post"))
    assert root.patch(f"/blog/posts/{other['id']}", json={"slug": "plot-cleaning-cost"}).status_code == 409
    assert root.post("/blog/posts", json=post(slug="Bad Slug")).status_code == 422
    assert root.post("/blog/posts", json=post(slug="x2", category="random")).status_code == 422
    assert root.post("/blog/posts", json=post(slug="x3", cover_image="javascript:alert(1)")).status_code == 422


def test_filters_related_and_topics(as_, world, client):
    root = as_(world.super)
    root.ok("post", "/blog/posts", json=post(status="published"))
    root.ok("post", "/blog/posts", json=post(slug="nri-guide", category="nri", tags=["NRI", "prices"], status="published"))
    root.ok("post", "/blog/posts", json=post(slug="monsoon", category="seasonal", tags=["Monsoon"], status="published"))
    root.ok("post", "/blog/posts", json=post(slug="hidden", status="draft"))

    def slugs(**q):
        return [p["slug"] for p in client.get("/api/v1/public/blog/posts", params=q).json()["items"]]

    assert sorted(slugs()) == ["monsoon", "nri-guide", "plot-cleaning-cost"]
    assert slugs(category="nri") == ["nri-guide"]
    assert sorted(slugs(tag="prices")) == ["nri-guide", "plot-cleaning-cost"]  # tags match ignoring case
    assert "body" not in client.get("/api/v1/public/blog/posts").json()["items"][0]

    related = client.get("/api/v1/public/blog/posts/plot-cleaning-cost").json()["related"]
    assert [r["slug"] for r in related] == ["nri-guide", "monsoon"]  # a shared tag ranks first; drafts never show

    topics = client.get("/api/v1/public/blog/topics").json()
    assert {c["slug"]: c["count"] for c in topics["categories"]} == {"costs": 1, "nri": 1, "seasonal": 1}
    assert (topics["tags"][0]["slug"], topics["tags"][0]["count"]) == ("prices", 2)


def test_tags_are_cleaned(as_, world):
    p = as_(world.super).ok("post", "/blog/posts", json=post(tags=["  NRI ", "nri", "Plot   cleaning", ""]))
    assert p["tags"] == ["NRI", "Plot cleaning"]


def test_image_upload_is_public_resized_and_stripped(as_, world, client, db):
    root = as_(world.super)
    big = io.BytesIO()
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"
    Image.new("RGB", (3000, 1500), (40, 120, 60)).save(big, format="JPEG", exif=exif.tobytes())
    r = root.post("/blog/images", files={"file": ("cover.jpg", big.getvalue(), "image/jpeg")})
    assert r.status_code == 201, r.text
    info = r.json()
    assert (info["width"], info["height"]) == (2000, 1000)
    assert info["url"].startswith("/api/v1/public/blog/images/") and info["url"].endswith(".jpg")

    got = client.get(info["url"])  # no sign-in needed
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    assert "immutable" in got.headers["cache-control"]
    assert not Image.open(io.BytesIO(got.content)).getexif()

    assert root.post("/blog/images", files={"file": ("x.pdf", b"%PDF-1.4 nope", "application/pdf")}).status_code == 422
    assert as_(world.admin).post("/blog/images", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")}).status_code == 403
    assert client.get("/api/v1/public/blog/images/not-an-id.jpg").status_code == 404
    assert db.query(BlogImage).count() == 1


def test_delete_post(as_, world, client):
    root = as_(world.super)
    p = root.ok("post", "/blog/posts", json=post(status="published"))
    assert root.delete(f"/blog/posts/{p['id']}").status_code == 204
    assert client.get("/api/v1/public/blog/posts/plot-cleaning-cost").status_code == 404
    assert root.get(f"/blog/posts/{p['id']}").status_code == 404
