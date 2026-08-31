from __future__ import annotations

import time
from datetime import date, datetime, timezone

from redis.asyncio import Redis

from app.services.router import get_rate_limit_tier_config

_MINUTE_TTL = 120
_DAY_TTL = 172800


def _minute_key(key_id: str) -> str:
    return f"rl:{key_id}:minute:{int(time.time() // 60)}"


def _day_key(key_id: str) -> str:
    return f"rl:{key_id}:day:{date.today().isoformat()}"


async def check_rate_limit(
    redis: Redis,
    key_id: str,
    tier: str,
    estimated_tokens: int,
) -> tuple[bool, int]:
    """
    Returns (allowed, retry_after_seconds).
    Uses a read-then-check pattern for pre-request gating.
    Actual token deduction happens in record_token_usage after the response.
    """
    limits = get_rate_limit_tier_config(tier)
    tpm = limits["tokens_per_minute"]
    tpd = limits["tokens_per_day"]

    pipe = redis.pipeline()
    pipe.get(_minute_key(key_id))
    pipe.get(_day_key(key_id))
    results = await pipe.execute()

    minute_used = int(results[0] or 0)
    day_used = int(results[1] or 0)

    if minute_used + estimated_tokens > tpm:
        retry_after = 60 - int(time.time() % 60)
        return False, max(retry_after, 1)

    if day_used + estimated_tokens > tpd:
        now = datetime.now(timezone.utc)
        seconds_until_midnight = int(
            (86400 - (now.hour * 3600 + now.minute * 60 + now.second))
        )
        return False, max(seconds_until_midnight, 1)

    return True, 0


async def record_token_usage(redis: Redis, key_id: str, tokens: int) -> None:
    pipe = redis.pipeline()
    pipe.incrby(_minute_key(key_id), tokens)
    pipe.expire(_minute_key(key_id), _MINUTE_TTL)
    pipe.incrby(_day_key(key_id), tokens)
    pipe.expire(_day_key(key_id), _DAY_TTL)
    await pipe.execute()


def estimate_prompt_tokens(messages: list[dict]) -> int:
    total_chars = sum(len(m.get("content", "")) for m in messages)
    return max(1, int(total_chars / 4))
