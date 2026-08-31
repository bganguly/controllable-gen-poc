# LLM Gateway

A production-grade API gateway for multiple LLM providers (Anthropic Claude, OpenAI, NVIDIA NIM via OpenRouter). Exposes an OpenAI-compatible endpoint, enforces per-key rate limits, writes audit logs to PostgreSQL, serves Prometheus metrics, implements the Model Context Protocol (MCP), and generates compliance PDF reports (SOC 2 / ISO 27001).

## Features

| Capability | Detail |
|---|---|
| OpenAI-compatible endpoint | `POST /v1/chat/completions` — drop-in replacement |
| Multi-provider routing | Claude → Anthropic, GPT → OpenAI, nvidia/* → OpenRouter |
| Config-driven routing | `routing_config.yaml` — no code changes to add routes |
| API key auth | SHA-256-hashed keys stored in Postgres; callers never see provider keys |
| Rate limiting | Per-key token budgets (minute + day) in Redis; 429 + `Retry-After` |
| Streaming | Full SSE streaming, Anthropic↔OpenAI format conversion |
| Audit logging | Every request persisted in Postgres (content stored as hash) |
| MCP server | `/mcp` — JSON-RPC 2.0; `web_search` stub + real `calculator` tool |
| Prometheus metrics | `/metrics` — request count, p50/p95/p99 latency, tokens, errors |
| Compliance PDF | `/reports/audit` — SOC 2 (CC6.1, CC6.7) and ISO 27001 (A.9.4, A.12.4) |
| Structured JSON logs | All logs emitted as JSON to stdout |
| Health check | `/health` — verifies Postgres and Redis connectivity |

---

## Prerequisites

**Remote deploy (Fly.io) — recommended for macOS without Docker:**
- [flyctl](https://fly.io/docs/hands-on/install-flyctl/) — `curl -L https://fly.io/install.sh | sh`
- A Fly.io account (free tier available at fly.io)

**Local dev (without Docker):**
- Python 3.11+ — `brew install python@3.12`
- PostgreSQL — `brew install postgresql@16 && brew services start postgresql@16`
- Redis — `brew install redis && brew services start redis`

---

## Quick Start — Local Development

```bash
cd gateway
cp .env.example .env
```

Edit `.env` with your API keys, then:

```bash
bash start.sh
```

The gateway starts at `http://localhost:8000`.

---

## Remote Deploy — Fly.io

```bash
cd gateway
fly auth login
fly launch --name llm-gateway --region iad --no-deploy
fly postgres create --name llm-gateway-db
fly postgres attach llm-gateway-db
fly redis create
```

Set secrets:

```bash
fly secrets set \
  ANTHROPIC_API_KEY=sk-ant-... \
  OPENAI_API_KEY=sk-... \
  OPENROUTER_API_KEY=sk-or-... \
  GATEWAY_MASTER_KEY=$(openssl rand -hex 32) \
  REDIS_URL=rediss://default:...@...upstash.io:6379
```

Deploy:

```bash
fly deploy
```

---

## Running Tests

```bash
pip install -r requirements.txt
GATEWAY_URL=http://localhost:8000 GATEWAY_MASTER_KEY=your-key pytest test_gateway.py -v
```

---

## API Reference

### Create an API key

```bash
curl -X POST http://localhost:8000/auth/keys \
  -H "Authorization: Bearer $GATEWAY_MASTER_KEY" \
  -H "Content-Type: application/json" \
  -d '{"owner": "alice", "allowed_models": ["*"], "rate_limit_tier": "standard"}'
```

Response:
```json
{
  "key": "gw_a1b2c3...",
  "id": "uuid",
  "owner": "alice",
  "rate_limit_tier": "standard",
  "message": "Store this key securely — it will not be shown again."
}
```

### List keys

```bash
curl http://localhost:8000/auth/keys \
  -H "Authorization: Bearer $GATEWAY_MASTER_KEY"
```

### Revoke a key

```bash
curl -X DELETE http://localhost:8000/auth/keys/<key-id> \
  -H "Authorization: Bearer $GATEWAY_MASTER_KEY"
```

---

### Inference — non-streaming

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer gw_your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "What is 2+2?"}],
    "max_tokens": 64
  }'
```

### Inference — streaming

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer gw_your_key" \
  -H "Content-Type: application/json" \
  --no-buffer \
  -d '{
    "model": "claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Count to five"}],
    "stream": true,
    "max_tokens": 128
  }'
```

### Routing — by model prefix

```bash
# → Anthropic
curl ... -d '{"model": "claude-3-5-haiku-20241022", ...}'

# → OpenAI
curl ... -d '{"model": "gpt-4o-mini", ...}'

# → OpenRouter (NVIDIA NIM)
curl ... -d '{"model": "nvidia/llama-3.1-nemotron-70b-instruct", ...}'
```

---

### MCP — list tools

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {}}'
```

### MCP — calculator

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "2",
    "method": "tools/call",
    "params": {"name": "calculator", "arguments": {"expression": "sqrt(144)"}}
  }'
```

Note: `sqrt` is not supported (only +, -, *, /, **, %). For complex math, wire a real library.

### MCP — web search (stub)

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "3",
    "method": "tools/call",
    "params": {"name": "web_search", "arguments": {"query": "latest LLM benchmarks", "num_results": 3}}
  }'
```

---

### Prometheus metrics

```bash
curl http://localhost:8000/metrics
```

---

### Compliance PDF — SOC 2

```bash
curl "http://localhost:8000/reports/audit?start=2025-01-01&end=2025-01-31&standard=soc2" \
  -H "Authorization: Bearer $GATEWAY_MASTER_KEY" \
  --output audit_soc2.pdf
```

### Compliance PDF — ISO 27001

```bash
curl "http://localhost:8000/reports/audit?start=2025-01-01&end=2025-01-31&standard=iso27001" \
  -H "Authorization: Bearer $GATEWAY_MASTER_KEY" \
  --output audit_iso27001.pdf
```

### Compliance PDF — both standards

```bash
curl "http://localhost:8000/reports/audit?start=2025-01-01&end=2025-01-31&standard=both" \
  -H "Authorization: Bearer $GATEWAY_MASTER_KEY" \
  --output audit_combined.pdf
```

---

## Rate Limit Tiers

| Tier | Tokens/min | Tokens/day |
|---|---|---|
| free | 500 | 10,000 |
| standard | 5,000 | 100,000 |
| premium | 50,000 | 1,000,000 |

Exceeded requests receive `429 Too Many Requests` with a `Retry-After` header.

---

## Architecture

```
Client
  │  Bearer gw_key
  ▼
┌─────────────────────────────────────────┐
│  FastAPI (Uvicorn)                      │
│  ┌──────────────┐  ┌─────────────────┐  │
│  │ Auth router  │  │ Inference router│  │
│  │ /auth/keys   │  │ /v1/chat/...    │  │
│  └──────────────┘  └───────┬─────────┘  │
│  ┌──────────────┐          │            │
│  │ MCP router   │   ┌──────▼──────────┐ │
│  │ /mcp         │   │ routing_config  │ │
│  └──────────────┘   └──────┬──────────┘ │
│  ┌──────────────┐          │            │
│  │ Reports      │   Anthropic / OpenAI  │
│  │ /reports/... │   OpenRouter          │
│  └──────────────┘                       │
└─────────────────────────────────────────┘
         │              │
      Redis          PostgreSQL
   (rate limits)   (audit logs, keys)
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Anthropic console API key |
| `OPENAI_API_KEY` | Yes | OpenAI platform API key |
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key |
| `DATABASE_URL` | Yes | PostgreSQL connection string (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Yes | Redis connection string (`redis://...`) |
| `GATEWAY_MASTER_KEY` | Yes | Admin key for key management and report endpoints |
| `LOG_LEVEL` | No | `DEBUG` / `INFO` / `WARNING` (default: `INFO`) |
