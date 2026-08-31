from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import AuditLog

logger = logging.getLogger(__name__)


def hash_request(messages: list[dict], model: str) -> str:
    payload = json.dumps({"model": model, "messages": messages}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


async def write_audit_log(
    db: AsyncSession,
    *,
    api_key_id: UUID | None,
    model_requested: str,
    model_used: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    estimated_cost_usd: float,
    latency_ms: int,
    success: bool,
    request_hash: str,
    error_message: str | None = None,
) -> None:
    log = AuditLog(
        timestamp=datetime.now(timezone.utc),
        api_key_id=api_key_id,
        model_requested=model_requested,
        model_used=model_used,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=estimated_cost_usd,
        latency_ms=latency_ms,
        success=success,
        error_message=error_message,
        request_hash=request_hash,
    )
    db.add(log)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Failed to write audit log")
