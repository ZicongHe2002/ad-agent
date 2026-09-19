from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST

from app.api.error_handlers import install_error_handlers
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.observability.tracing import trace_id_var

settings = get_settings()
configure_logging(level=settings.log_level, json_output=settings.log_json)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("firstcomment service starting")
    yield
    try:
        from app.db.session import dispose_engine

        await dispose_engine()
    finally:
        logger.info("firstcomment service stopped")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "Last-Event-ID", "X-Trace-ID"],
)


@app.middleware("http")
async def trace_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    raw_trace_id = request.headers.get("x-trace-id")
    try:
        trace_id = UUID(raw_trace_id) if raw_trace_id else uuid4()
    except ValueError:
        trace_id = uuid4()
    token = trace_id_var.set(trace_id)
    started = perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Trace-ID"] = str(trace_id)
        logger.info(
            "request completed method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            (perf_counter() - started) * 1000,
            extra={"trace_id": trace_id},
        )
        return response
    finally:
        trace_id_var.reset(token)


app.include_router(api_router, prefix=settings.api_v1_prefix)
install_error_handlers(app)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "health": f"{settings.api_v1_prefix}/system/health"}


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    from app.db.session import AsyncSessionFactory
    from app.observability.durable_metrics import generate_durable_metrics

    async with AsyncSessionFactory() as session:
        content = await generate_durable_metrics(session)
    return Response(content, media_type=CONTENT_TYPE_LATEST)
