from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis

from app.config import configure_logging, get_settings
from app.models.db import create_tables, init_engine
from app.routers import auth, demo, inference, mcp, reports
from app.routers.inference import set_redis

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis_client
    settings = get_settings()
    configure_logging(settings.log_level)

    init_engine(settings.async_database_url)
    await create_tables()
    logger.info("database_ready")

    _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    await _redis_client.ping()
    set_redis(_redis_client)
    logger.info("redis_ready")

    logger.info("gateway_started", extra={"version": "1.0.0"})
    yield

    if _redis_client:
        await _redis_client.aclose()
    logger.info("gateway_stopped")


app = FastAPI(
    title="LLM Gateway",
    description="Production-grade multi-provider LLM API gateway with rate limiting, audit logging, and compliance reporting.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(inference.router)
app.include_router(auth.router)
app.include_router(mcp.router)
app.include_router(reports.router)
app.include_router(demo.router)


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
async def health(request: Request) -> dict:
    checks: dict[str, str] = {}

    try:
        await _redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    from app.models.db import engine
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ok" if all_ok else "degraded", "checks": checks}
