from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.metrics import ERROR_COUNT, RATE_LIMIT_HITS, REQUEST_COUNT, REQUEST_DURATION, TOKEN_USAGE
from app.models.db import APIKey, get_db
from app.models.schemas import ChatCompletionRequest
from app.services.audit import hash_request, write_audit_log
from app.services.providers import call_provider, stream_provider
from app.services.rate_limiter import (
    check_rate_limit,
    estimate_prompt_tokens,
    record_token_usage,
)
from app.services.router import estimate_cost, get_fallback, route_request

logger = logging.getLogger(__name__)
router = APIRouter(tags=["inference"])

_redis: Redis | None = None


def set_redis(r: Redis) -> None:
    global _redis
    _redis = r


def _get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialised")
    return _redis


async def _authenticate(authorization: str = Header(...), db: AsyncSession = Depends(get_db)) -> APIKey:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header must be: Bearer <key>")
    raw_key = authorization[7:]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True))
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    return api_key


def _model_allowed(api_key: APIKey, model: str) -> bool:
    allowed = api_key.allowed_models
    if not allowed or allowed == ["*"] or "*" in allowed:
        return True
    return model in allowed


@router.post("/v1/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    api_key: APIKey = Depends(_authenticate),
    db: AsyncSession = Depends(get_db),
) -> Any:
    redis = _get_redis()
    start_ts = time.monotonic()

    provider, resolved_model = route_request(body.model)

    if not _model_allowed(api_key, resolved_model):
        raise HTTPException(
            status_code=403,
            detail=f"Model '{resolved_model}' is not in the allowed list for this key",
        )

    messages_as_dicts = [m.model_dump() for m in body.messages]
    estimated_tokens = estimate_prompt_tokens(messages_as_dicts)
    allowed, retry_after = await check_rate_limit(
        redis, str(api_key.id), api_key.rate_limit_tier, estimated_tokens
    )
    if not allowed:
        RATE_LIMIT_HITS.labels(tier=api_key.rate_limit_tier).inc()
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    req_with_model = body.model_copy(update={"model": resolved_model})
    request_hash = hash_request(messages_as_dicts, resolved_model)

    if body.stream:
        async def _stream_and_log():
            try:
                async for chunk in stream_provider(provider, req_with_model):
                    yield chunk
            except httpx.HTTPStatusError as exc:
                logger.error("provider_stream_error", extra={"status": exc.response.status_code, "provider": provider})
                ERROR_COUNT.labels(model=resolved_model, error_type="provider_http").inc()
            finally:
                latency_ms = int((time.monotonic() - start_ts) * 1000)
                REQUEST_DURATION.labels(model=resolved_model).observe(latency_ms / 1000)
                REQUEST_COUNT.labels(model=resolved_model, status_code="200").inc()
                await record_token_usage(redis, str(api_key.id), estimated_tokens)
                await write_audit_log(
                    db,
                    api_key_id=api_key.id,
                    model_requested=body.model,
                    model_used=resolved_model,
                    prompt_tokens=estimated_tokens,
                    completion_tokens=0,
                    estimated_cost_usd=estimate_cost(resolved_model, estimated_tokens, 0),
                    latency_ms=latency_ms,
                    success=True,
                    request_hash=request_hash,
                )

        return StreamingResponse(_stream_and_log(), media_type="text/event-stream")

    try:
        response = await call_provider(provider, req_with_model)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "provider_error",
            extra={"status": exc.response.status_code, "provider": provider},
        )
        ERROR_COUNT.labels(model=resolved_model, error_type="provider_http").inc()

        fallback_provider, fallback_model = get_fallback()
        if fallback_provider == provider and fallback_model == resolved_model:
            latency_ms = int((time.monotonic() - start_ts) * 1000)
            await write_audit_log(
                db,
                api_key_id=api_key.id,
                model_requested=body.model,
                model_used=resolved_model,
                prompt_tokens=0,
                completion_tokens=0,
                estimated_cost_usd=0.0,
                latency_ms=latency_ms,
                success=False,
                request_hash=request_hash,
                error_message=f"HTTP {exc.response.status_code} from provider",
            )
            raise HTTPException(status_code=502, detail=f"Provider error: {exc.response.status_code}")

        logger.warning("falling_back", extra={"to_provider": fallback_provider, "to_model": fallback_model})
        fallback_req = body.model_copy(update={"model": fallback_model})
        try:
            response = await call_provider(fallback_provider, fallback_req)
            resolved_model = fallback_model
        except Exception as fallback_exc:
            latency_ms = int((time.monotonic() - start_ts) * 1000)
            ERROR_COUNT.labels(model=fallback_model, error_type="fallback_failed").inc()
            await write_audit_log(
                db,
                api_key_id=api_key.id,
                model_requested=body.model,
                model_used=fallback_model,
                prompt_tokens=0,
                completion_tokens=0,
                estimated_cost_usd=0.0,
                latency_ms=latency_ms,
                success=False,
                request_hash=request_hash,
                error_message=str(fallback_exc),
            )
            raise HTTPException(status_code=502, detail="Both primary and fallback providers failed")

    latency_ms = int((time.monotonic() - start_ts) * 1000)
    usage = response.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", estimated_tokens)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
    cost = estimate_cost(resolved_model, prompt_tokens, completion_tokens)

    await record_token_usage(redis, str(api_key.id), total_tokens)

    REQUEST_COUNT.labels(model=resolved_model, status_code="200").inc()
    REQUEST_DURATION.labels(model=resolved_model).observe(latency_ms / 1000)
    TOKEN_USAGE.labels(model=resolved_model, token_type="prompt").inc(prompt_tokens)
    TOKEN_USAGE.labels(model=resolved_model, token_type="completion").inc(completion_tokens)

    await write_audit_log(
        db,
        api_key_id=api_key.id,
        model_requested=body.model,
        model_used=resolved_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=cost,
        latency_ms=latency_ms,
        success=True,
        request_hash=request_hash,
    )

    return response
