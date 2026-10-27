import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.v1 import (
    auth,
    billing,
    blog,
    comms,
    complaints,
    customers,
    devices,
    inspections,
    maintenance,
    media,
    owner_updates,
    people,
    properties,
    public,
    referrals,
    reports,
    security,
    signups,
    sms,
    store,
    subscriptions,
    system,
    tenants,
    tickets,
    users,
    whatsapp,
)
from app.core.config import get_settings
from app.core.deps import client_ip
from app.core.http import ETagMiddleware, error_body, install_error_handlers
from app.core.ratelimit import limiter

log = logging.getLogger("greenplot")


async def _worker_loop(interval: int):  # pragma: no cover - timing loop
    from app.core.db import SessionLocal
    from app.services.jobs import run_all

    while True:
        await asyncio.sleep(interval)
        try:
            with SessionLocal() as db:
                log.info("jobs: %s", run_all(db))
        except Exception:
            log.exception("background jobs failed")


def operation_id(route: APIRoute) -> str:
    """Short, stable operation ids (tickets_list_tickets) so generated mobile clients get readable method names."""
    return f"{route.tags[0]}_{route.name}" if route.tags else route.name


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    task = asyncio.create_task(_worker_loop(s.worker_interval_seconds)) if s.worker_enabled else None
    yield
    if task:
        task.cancel()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version="1.0.0",
        description="GreenPlot — Property Management Made Simple. Modular-monolith REST API (requirements §26-28).",
        lifespan=lifespan,
        docs_url=f"{s.api_prefix}/docs",
        openapi_url=f"{s.api_prefix}/openapi.json",
        generate_unique_id_function=operation_id,
    )
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        if request.url.path.startswith(s.api_prefix) and not limiter.allow(f"api:{client_ip(request)}", s.api_rate_per_minute):
            return JSONResponse(error_body(429, "Rate limit exceeded"), status_code=429, headers={"Retry-After": "60"})
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if s.environment == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    # Outermost last: compress what the ETag layer tagged. Images and video are already compressed and skipped.
    app.add_middleware(ETagMiddleware, prefix=s.api_prefix)
    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)

    for module in (
        auth,
        tenants,
        users,
        properties,
        customers,
        devices,
        maintenance,
        media,
        complaints,
        tickets,
        inspections,
        people,
        security,
        billing,
        blog,
        subscriptions,
        referrals,
        comms,
        reports,
        system,
        public,
        whatsapp,
        owner_updates,
        signups,
        sms,
        store,
    ):
        app.include_router(module.router, prefix=s.api_prefix)
    app.include_router(tenants.settings_router, prefix=s.api_prefix)
    app.include_router(maintenance.tasks_router, prefix=s.api_prefix)

    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok", "service": "greenplot-api"}

    return app


app = create_app()
