import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import (
    auth,
    billing,
    comms,
    complaints,
    inspections,
    maintenance,
    media,
    people,
    properties,
    public,
    reports,
    security,
    system,
    tenants,
    tickets,
    users,
    whatsapp,
)
from app.core.config import get_settings
from app.core.deps import client_ip
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
    )
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
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if s.environment == "production":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    for module in (
        auth,
        tenants,
        users,
        properties,
        maintenance,
        media,
        complaints,
        tickets,
        inspections,
        people,
        security,
        billing,
        comms,
        reports,
        system,
        public,
        whatsapp,
    ):
        app.include_router(module.router, prefix=s.api_prefix)
    app.include_router(tenants.settings_router, prefix=s.api_prefix)
    app.include_router(maintenance.tasks_router, prefix=s.api_prefix)

    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok", "service": "greenplot-api"}

    return app


app = create_app()
