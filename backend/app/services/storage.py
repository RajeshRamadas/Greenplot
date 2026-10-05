"""Private object storage (requirements §12).

* ``local``: files on disk, served only through short-lived HMAC-signed API URLs.
* ``s3``: S3 / Cloudflare R2 with presigned PUT/GET URLs; the bucket stays private.

No backend ever produces a permanent public URL.
"""

import hashlib
import io
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from app.core.config import get_settings
from app.core.security import sign_value


class Storage(Protocol):
    def upload_url(self, key: str, content_type: str, sha256: str | None) -> dict: ...
    def download_url(self, key: str, filename: str | None = None) -> str: ...
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str, base_url: str, prefix: str, ttl: int):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")
        self.prefix = prefix
        self.ttl = ttl

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("Invalid storage key")
        return p

    def upload_url(self, key: str, content_type: str, sha256: str | None) -> dict:
        token = sign_value(f"put:{key}", self.ttl)
        return {
            "method": "PUT",
            "url": f"{self.base_url}{self.prefix}/media/blob?key={quote(key)}&token={token}",
            "headers": {"Content-Type": content_type},
        }

    def download_url(self, key: str, filename: str | None = None) -> str:
        token = sign_value(f"get:{key}", self.ttl)
        return f"{self.base_url}{self.prefix}/media/blob?key={quote(key)}&token={token}"

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.is_file():
            p.unlink()


class S3Storage:  # pragma: no cover - exercised against real S3/R2/MinIO
    def __init__(self):
        import boto3

        s = get_settings()
        self.bucket = s.s3_bucket
        self.ttl = s.signed_url_seconds
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            region_name=s.s3_region,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
        )

    def upload_url(self, key: str, content_type: str, sha256: str | None) -> dict:
        params = {"Bucket": self.bucket, "Key": key, "ContentType": content_type}
        headers = {"Content-Type": content_type}
        if sha256:
            import base64

            b64 = base64.b64encode(bytes.fromhex(sha256)).decode()
            params["ChecksumSHA256"] = b64
            headers["x-amz-checksum-sha256"] = b64
        url = self.client.generate_presigned_url("put_object", Params=params, ExpiresIn=self.ttl)
        return {"method": "PUT", "url": url, "headers": headers}

    def download_url(self, key: str, filename: str | None = None) -> str:
        params = {"Bucket": self.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'inline; filename="{filename}"'
        return self.client.generate_presigned_url("get_object", Params=params, ExpiresIn=self.ttl)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        s = get_settings()
        if s.storage_backend == "s3":
            _storage = S3Storage()
        else:
            _storage = LocalStorage(s.local_storage_path, s.public_base_url, s.api_prefix, s.signed_url_seconds)
    return _storage


def set_storage(storage: Storage | None) -> None:
    global _storage
    _storage = storage


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- content validation

ALLOWED_TYPES = {
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
    "image/heic": "image",
    "video/mp4": "video",
    "video/quicktime": "video",
    "video/webm": "video",
    "application/pdf": "document",
}

_MAGIC = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"%PDF-", "application/pdf"),
    (b"\x1aE\xdf\xa3", "video/webm"),
]


def sniff_type(data: bytes) -> str | None:
    for magic, ctype in _MAGIC:
        if data.startswith(magic):
            return ctype
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand in (b"heic", b"heix", b"mif1", b"msf1"):
            return "image/heic"
        if brand == b"qt  ":
            return "video/quicktime"
        return "video/mp4"
    return None


def content_matches(declared: str, data: bytes) -> bool:
    sniffed = sniff_type(data)
    if sniffed is None:
        return False
    if sniffed == declared:
        return True
    # mp4/quicktime/heic share the ISO-BMFF container
    iso = {"video/mp4", "video/quicktime", "image/heic"}
    return sniffed in iso and declared in iso


def max_bytes_for(content_type: str) -> int:
    s = get_settings()
    kind = ALLOWED_TYPES.get(content_type)
    return {"image": s.max_image_bytes, "video": s.max_video_bytes, "document": s.max_document_bytes}.get(kind, 0)


def make_thumbnail(data: bytes, max_px: int = 480) -> bytes | None:
    try:
        from PIL import Image, ImageOps

        with Image.open(io.BytesIO(data)) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((max_px, max_px))
            out = io.BytesIO()
            im.convert("RGB").save(out, format="JPEG", quality=78)
            return out.getvalue()
    except Exception:
        return None


def scan_for_malware(data: bytes) -> str:
    """Hook for ClamAV or a provider scanner. Rejects the EICAR test signature."""
    if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in data:
        return "infected"
    return "clean"
