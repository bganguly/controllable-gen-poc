from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "llm_gateway_requests_total",
    "Total inference requests",
    ["model", "status_code"],
)

REQUEST_DURATION = Histogram(
    "llm_gateway_request_duration_seconds",
    "End-to-end request latency",
    ["model"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)

TOKEN_USAGE = Counter(
    "llm_gateway_tokens_total",
    "Tokens consumed",
    ["model", "token_type"],
)

RATE_LIMIT_HITS = Counter(
    "llm_gateway_rate_limit_hits_total",
    "Rate limit rejections",
    ["tier"],
)

ERROR_COUNT = Counter(
    "llm_gateway_errors_total",
    "Inference errors by type",
    ["model", "error_type"],
)
