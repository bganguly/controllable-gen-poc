"""
Integration tests for the LLM Gateway.

Run against a live gateway:
    GATEWAY_URL=http://localhost:8000 GATEWAY_MASTER_KEY=your-key pytest test_gateway.py -v

All tests use httpx — no mocking, no side effects beyond API key creation.
"""
from __future__ import annotations

import os
import time

import httpx
import pytest

BASE_URL = os.getenv("GATEWAY_URL", "http://localhost:8000").rstrip("/")
MASTER_KEY = os.getenv("GATEWAY_MASTER_KEY", "change-me-before-deploy")
HEADERS_MASTER = {"Authorization": f"Bearer {MASTER_KEY}"}

_created_key: str | None = None
_created_key_id: str | None = None


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as c:
        yield c


def test_health(client: httpx.Client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert "checks" in body


def test_create_api_key(client: httpx.Client):
    global _created_key, _created_key_id
    r = client.post(
        "/auth/keys",
        headers=HEADERS_MASTER,
        json={"owner": "test-suite", "allowed_models": ["*"], "rate_limit_tier": "premium"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["key"].startswith("gw_")
    assert "id" in body
    _created_key = body["key"]
    _created_key_id = body["id"]


def test_list_keys(client: httpx.Client):
    r = client.get("/auth/keys", headers=HEADERS_MASTER)
    assert r.status_code == 200
    keys = r.json()
    assert isinstance(keys, list)
    assert any(k["id"] == _created_key_id for k in keys)


def test_get_key_by_id(client: httpx.Client):
    r = client.get(f"/auth/keys/{_created_key_id}", headers=HEADERS_MASTER)
    assert r.status_code == 200
    body = r.json()
    assert body["owner"] == "test-suite"
    assert body["is_active"] is True


def test_inference_bad_key(client: httpx.Client):
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer gw_invalidkey"},
        json={"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert r.status_code == 401


def test_inference_missing_auth(client: httpx.Client):
    r = client.post(
        "/v1/chat/completions",
        json={"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert r.status_code == 422


def test_inference_call(client: httpx.Client):
    assert _created_key is not None, "run test_create_api_key first"
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {_created_key}"},
        json={
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Reply with exactly one word: pong"}],
            "max_tokens": 20,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "choices" in body
    assert len(body["choices"]) > 0
    assert "usage" in body
    assert body["usage"]["prompt_tokens"] > 0


def test_routing_gpt_model(client: httpx.Client):
    assert _created_key is not None
    r = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {_created_key}"},
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Say hi"}],
            "max_tokens": 10,
        },
    )
    assert r.status_code in (200, 502), r.text


def test_rate_limit_hit(client: httpx.Client):
    assert _created_key is not None
    free_key_resp = client.post(
        "/auth/keys",
        headers=HEADERS_MASTER,
        json={"owner": "rate-limit-test", "allowed_models": ["*"], "rate_limit_tier": "free"},
    )
    assert free_key_resp.status_code == 201
    free_key = free_key_resp.json()["key"]

    responses = []
    for _ in range(15):
        r = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {free_key}"},
            json={
                "model": "claude-sonnet-4-6",
                "messages": [{"role": "user", "content": "x" * 200}],
                "max_tokens": 5,
            },
        )
        responses.append(r.status_code)
        if r.status_code == 429:
            assert "Retry-After" in r.headers
            break

    assert 429 in responses, f"Expected a 429 after 15 requests with free tier, got: {set(responses)}"


def test_mcp_tools_list(client: httpx.Client):
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert "result" in body
    tool_names = [t["name"] for t in body["result"]["tools"]]
    assert "web_search" in tool_names
    assert "calculator" in tool_names


def test_mcp_calculator(client: httpx.Client):
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "2",
            "method": "tools/call",
            "params": {"name": "calculator", "arguments": {"expression": "2 * (3 + 4)"}},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["content"][0]["text"] == "14.0"


def test_mcp_calculator_division(client: httpx.Client):
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "3",
            "method": "tools/call",
            "params": {"name": "calculator", "arguments": {"expression": "22 / 7"}},
        },
    )
    assert r.status_code == 200
    result_text = r.json()["result"]["content"][0]["text"]
    assert abs(float(result_text) - 22 / 7) < 1e-6


def test_mcp_web_search_stub(client: httpx.Client):
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "4",
            "method": "tools/call",
            "params": {"name": "web_search", "arguments": {"query": "LLM gateway", "num_results": 2}},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "result" in body
    content = body["result"]["content"][0]["text"]
    assert "LLM gateway" in content


def test_mcp_unknown_method(client: httpx.Client):
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": "5", "method": "nonexistent/method", "params": {}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["error"]["code"] == -32601


def test_prometheus_metrics(client: httpx.Client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert "llm_gateway_requests_total" in body
    assert "llm_gateway_request_duration_seconds" in body
    assert "llm_gateway_tokens_total" in body
    assert "llm_gateway_rate_limit_hits_total" in body
    assert "llm_gateway_errors_total" in body


def test_audit_report_soc2(client: httpx.Client):
    from datetime import date, timedelta
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=7)).isoformat()

    r = client.get(
        "/reports/audit",
        headers=HEADERS_MASTER,
        params={"start": start, "end": end, "standard": "soc2"},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_audit_report_iso27001(client: httpx.Client):
    from datetime import date, timedelta
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=30)).isoformat()

    r = client.get(
        "/reports/audit",
        headers=HEADERS_MASTER,
        params={"start": start, "end": end, "standard": "iso27001"},
    )
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


def test_audit_report_both_standards(client: httpx.Client):
    from datetime import date, timedelta
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=7)).isoformat()

    r = client.get(
        "/reports/audit",
        headers=HEADERS_MASTER,
        params={"start": start, "end": end, "standard": "both"},
    )
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"


def test_audit_report_bad_date(client: httpx.Client):
    r = client.get(
        "/reports/audit",
        headers=HEADERS_MASTER,
        params={"start": "not-a-date", "end": "2024-01-01", "standard": "soc2"},
    )
    assert r.status_code == 422


def test_audit_report_unauthorized(client: httpx.Client):
    r = client.get(
        "/reports/audit",
        headers={"Authorization": "Bearer wrong-key"},
        params={"start": "2024-01-01", "end": "2024-01-31", "standard": "soc2"},
    )
    assert r.status_code == 403


def test_revoke_key(client: httpx.Client):
    assert _created_key_id is not None
    r = client.delete(f"/auth/keys/{_created_key_id}", headers=HEADERS_MASTER)
    assert r.status_code == 204

    r2 = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {_created_key}"},
        json={"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r2.status_code == 401
