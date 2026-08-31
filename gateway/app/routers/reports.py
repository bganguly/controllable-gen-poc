from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.db import AuditLog, get_db
from app.services.pdf_report import generate_report

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"])


def _require_master(authorization: str = Header(...)) -> None:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header must be: Bearer <key>")
    if authorization[7:] != get_settings().gateway_master_key:
        raise HTTPException(status_code=403, detail="Invalid master key")


def _parse_date(val: str, field: str) -> date:
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"{field} must be YYYY-MM-DD, got: {val!r}"
        )


@router.get("/audit")
async def audit_report(
    start: str = Query(..., description="Start date YYYY-MM-DD"),
    end: str = Query(..., description="End date YYYY-MM-DD"),
    standard: str = Query("soc2", description="soc2 | iso27001 | both"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_require_master),
) -> Response:
    if standard not in ("soc2", "iso27001", "both"):
        raise HTTPException(status_code=422, detail="standard must be soc2, iso27001, or both")

    start_date = _parse_date(start, "start")
    end_date = _parse_date(end, "end")
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end must be >= start")

    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)

    result = await db.execute(
        select(AuditLog).where(
            and_(AuditLog.timestamp >= start_dt, AuditLog.timestamp <= end_dt)
        ).order_by(AuditLog.timestamp)
    )
    rows = result.scalars().all()

    logs = [
        {
            "model_requested": r.model_requested,
            "model_used": r.model_used,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "estimated_cost_usd": r.estimated_cost_usd,
            "latency_ms": r.latency_ms,
            "success": r.success,
        }
        for r in rows
    ]

    standards = ["soc2", "iso27001"] if standard == "both" else [standard]
    pdf_bytes = generate_report(start_date, end_date, standards, logs)

    filename = f"audit_{start}_{end}_{standard}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
