"""HTTP plumbing shared by every endpoint: one error shape, and conditional GETs.

Errors keep FastAPI's "detail" (the website reads it) and add a stable machine-readable "code" and a
human "message", so the mobile apps can branch on the code and show the message as it is.
"""

import hashlib

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    410: "gone",
    413: "too_large",
    415: "unsupported_media_type",
    422: "invalid",
    423: "locked",
    429: "rate_limited",
    500: "server_error",
    502: "provider_error",
    503: "unavailable",
}


def error_body(status_code: int, detail) -> dict:
    code = ERROR_CODES.get(status_code, "error")
    message = None
    if isinstance(detail, str):
        message = detail
    elif isinstance(detail, dict):
        code = detail.get("code") if isinstance(detail.get("code"), str) else code
        message = detail.get("message") or detail.get("detail")
    return {"detail": detail, "code": code, "message": message}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        return JSONResponse(jsonable_encoder(error_body(exc.status_code, exc.detail)), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = jsonable_encoder(exc.errors())
        first = errors[0] if errors else {}
        field = ".".join(str(p) for p in first.get("loc", [])[1:])
        message = f"{field}: {first.get('msg')}" if field else first.get("msg")
        return JSONResponse({"detail": errors, "code": "validation_error", "message": message}, status_code=422)


class ETagMiddleware:
    """Weak ETags on JSON GET responses, and 304 Not Modified when the client already has them.

    Saves phones from downloading a list again when nothing changed (the server still builds it).
    Marked private so shared caches never store a signed-in person's data.
    """

    max_bytes = 2 * 1024 * 1024

    def __init__(self, app: ASGIApp, prefix: str = "") -> None:
        self.app = app
        self.prefix = prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET" or not scope["path"].startswith(self.prefix):
            await self.app(scope, receive, send)
            return
        if_none_match = Headers(scope=scope).get("if-none-match")
        start: Message | None = None
        chunks: list[bytes] = []
        size = 0
        passthrough = False

        async def wrapped(message: Message) -> None:
            nonlocal start, size, passthrough
            if passthrough:
                await send(message)
                return
            if message["type"] == "http.response.start":
                headers = Headers(raw=message["headers"])
                if (
                    message["status"] != 200
                    or not headers.get("content-type", "").startswith("application/json")
                    or "etag" in headers
                    or "content-encoding" in headers
                ):
                    passthrough = True
                    await send(message)
                else:
                    start = message
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            chunks.append(message.get("body", b""))
            size += len(chunks[-1])
            if size > self.max_bytes:  # too big to buffer: send what we have, untagged
                passthrough = True
                await send(start)
                await send({"type": "http.response.body", "body": b"".join(chunks), "more_body": message.get("more_body", False)})
                return
            if message.get("more_body"):
                return
            body = b"".join(chunks)
            etag = 'W/"' + hashlib.blake2b(body, digest_size=12).hexdigest() + '"'
            headers = MutableHeaders(raw=start["headers"])
            headers["ETag"] = etag
            headers.setdefault("Cache-Control", "private, no-cache")
            if if_none_match and etag in [t.strip() for t in if_none_match.split(",")]:
                del headers["content-length"]
                await send({**start, "status": 304})
                await send({"type": "http.response.body", "body": b""})
                return
            await send(start)
            await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, wrapped)
