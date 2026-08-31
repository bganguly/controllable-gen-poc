from __future__ import annotations

import time
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import APIKey, AuditLog, get_db
from app.models.schemas import ChatCompletionRequest
from app.services.providers import call_provider
from app.services.router import route_request

router = APIRouter(tags=["demo"])


@router.post("/v1/direct/chat/completions")
async def direct_completions(body: ChatCompletionRequest) -> dict:
    """
    Bypass all gateway middleware: no auth, no rate limiting, no audit log.
    Demo-only endpoint to show what the gateway adds.
    """
    start = time.monotonic()
    provider, resolved_model = route_request(body.model)
    req = body.model_copy(update={"model": resolved_model})
    result = await call_provider(provider, req)
    latency_ms = int((time.monotonic() - start) * 1000)
    result["_direct_meta"] = {
        "provider": provider,
        "model": resolved_model,
        "latency_ms": latency_ms,
        "auth_enforced": False,
        "rate_limited": False,
        "audit_logged": False,
    }
    return result


@router.get("/api/ui/recent-logs")
async def recent_logs(
    limit: int = Query(15, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    result = await db.execute(
        select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "timestamp": r.timestamp.strftime("%H:%M:%S"),
            "model_requested": r.model_requested,
            "model_used": r.model_used or "—",
            "prompt_tokens": r.prompt_tokens or 0,
            "completion_tokens": r.completion_tokens or 0,
            "cost_usd": f"${r.estimated_cost_usd:.5f}" if r.estimated_cost_usd else "—",
            "latency_ms": r.latency_ms or 0,
            "success": r.success,
        }
        for r in rows
    ]


@router.get("/api/ui/metrics-summary")
async def metrics_summary(db: AsyncSession = Depends(get_db)) -> dict:
    today_start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)

    total_today = await db.scalar(
        select(func.count()).where(AuditLog.timestamp >= today_start)
    )
    errors_today = await db.scalar(
        select(func.count()).where(
            and_(AuditLog.timestamp >= today_start, AuditLog.success.is_(False))
        )
    )
    cost_today = await db.scalar(
        select(func.sum(AuditLog.estimated_cost_usd)).where(
            AuditLog.timestamp >= today_start
        )
    )
    avg_latency = await db.scalar(
        select(func.avg(AuditLog.latency_ms)).where(AuditLog.timestamp >= today_start)
    )
    active_keys = await db.scalar(
        select(func.count()).where(APIKey.is_active.is_(True))
    )

    return {
        "requests_today": total_today or 0,
        "errors_today": errors_today or 0,
        "cost_today_usd": round(float(cost_today or 0), 5),
        "avg_latency_ms": round(float(avg_latency or 0)),
        "active_keys": active_keys or 0,
    }


@router.get("/ui", response_class=HTMLResponse)
async def ui() -> HTMLResponse:
    html_path = Path(__file__).parent.parent / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text())
