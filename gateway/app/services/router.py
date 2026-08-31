from __future__ import annotations

import fnmatch

from app.config import get_routing_config


def route_request(model: str) -> tuple[str, str]:
    """Return (provider, resolved_model) for the given model string."""
    config = get_routing_config()

    for route in config.get("routes", []):
        pattern = route["pattern"]
        if fnmatch.fnmatch(model, pattern):
            return route["provider"], model

    default = config.get("default", {})
    return default.get("provider", "anthropic"), default.get("model", "claude-sonnet-4-6")


def get_fallback() -> tuple[str, str]:
    config = get_routing_config()
    fallback = config.get("fallback", {})
    return fallback.get("provider", "openai"), fallback.get("model", "gpt-4o-mini")


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    config = get_routing_config()
    costs = config.get("cost_per_token", {})
    model_costs = costs.get(model) or costs.get("default", {"prompt": 3e-6, "completion": 15e-6})
    return prompt_tokens * model_costs["prompt"] + completion_tokens * model_costs["completion"]


def get_rate_limit_tier_config(tier: str) -> dict:
    config = get_routing_config()
    tiers = config.get("rate_limit_tiers", {})
    return tiers.get(tier, tiers.get("standard", {"tokens_per_minute": 5000, "tokens_per_day": 100000, "requests_per_minute": 60}))
