# tax-email-agent — Implementation Plan

## Purpose
Agentic UI for processing customer service emails that ask what state/local taxes
were applied to a purchase. Agent looks up the applicable tax rate, calculates the
tax amount, and drafts a complete reply — no follow-up questions, no fluff.

---

## Repo structure

```
tax-email-agent/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI: email queue CRUD + /api/process
│   └── agent.py         # Two-step LLM agent + TaxJar rate lookup
├── data/
│   └── emails.json      # Persisted queue [{id, raw, status, response, reply_to}]
├── docs/
│   └── index.html       # React + Babel standalone SPA
├── .env.example
├── requirements.txt
└── PLAN.md
```

---

## Frontend (docs/index.html) — React + Babel standalone

### Layout: two-panel

**Top bar**
- Provider toggle: `Claude | OpenAI | Gemini` (3 buttons; active provider sent as
  `X-Provider` header on every API call)

**Left panel — work queue**
- List of stored emails; each row shows truncated subject/first line + status chip
  (`pending` / `done`)
- Click a row to select it
- "Add Email" textarea + submit button (paste raw customer email text)

**Right panel — selected email**
- Raw email text (read-only)
- Response style selector: `Standard | Formal | Brief` (radio group — no free text)
- "Process" button → POST /api/process → shows draft response
- "Mark Done" button → PATCH /api/emails/{id}
- "Send Email" button → EmailJS send (service/template/key from localStorage,
  seeded once via ?s=&t=&k= query params; same pattern as ../portfolio/js/main.js)
  Template vars: {{to_email}}, {{subject}}, {{body}}

**No free-text prompt field anywhere** — user never types to the agent directly.

---

## Backend (app/)

| Route | Purpose |
|---|---|
| GET  /api/emails | Return full queue |
| POST /api/emails | Add raw email; assign UUID; status=pending |
| PATCH /api/emails/{id} | Set status=done |
| POST /api/process | Two-step agent call (see below) |

---

## Agent (app/agent.py) — two-step, hard-scoped

### Step 1 — structured extraction (JSON mode, ~50 tokens)

System prompt:
> "You are a data extraction assistant. Extract tax inquiry fields from the email
> text below. Return only JSON. If the email is not a customer tax inquiry about a
> purchase, return all fields as null."

Extract: `{item, purchase_price, state, city, reply_to_email, customer_name}`

**Python gate:** if `state` is null OR `purchase_price` is null → return HTTP 400
`{"error": "not_a_tax_inquiry"}`. No further LLM call. No token spend on generation.

### Step 2 — tax rate lookup (TaxJar API, no LLM)

Call TaxJar `GET /v2/rates/{zip}?city={city}&state={state}&country=US`
(zip derived from city+state via a lightweight lookup, or pass state+city directly).

Parse `combined_rate` from response. Compute:
```
tax_amount = purchase_price * combined_rate
breakdown  = {state_rate, county_rate, city_rate, combined_rate, tax_amount}
```

### Step 3 — response generation

System prompt (hard-scoped):
> "You are a customer service tax response agent. Your only job is to write a
> complete, professional reply to a customer tax inquiry. Use only the data
> provided. Do not ask follow-up questions. Do not discuss anything outside
> the scope of this tax inquiry."

Input to LLM: `{item, purchase_price, state, city, breakdown, response_style,
customer_name}` — the raw email text is NOT forwarded here (prompt injection
mitigation).

Output: complete reply email body, ready to send.

---

## Tax rate API — TaxJar

- Endpoint: `GET https://api.taxjar.com/v2/rates/{zip}`
- Free tier: 50 API calls/month (sufficient for demo)
- Auth: `Authorization: Bearer {TAXJAR_API_KEY}`
- Env var: `TAXJAR_API_KEY`
- Docs: https://developers.taxjar.com/api/reference/#get-show-tax-rates-for-a-location

For city+state without zip: use TaxJar's `city` + `state` query params.

---

## Provider dispatch (app/agent.py)

| Provider | SDK | Model |
|---|---|---|
| Claude | anthropic Python SDK | claude-sonnet-4-6 |
| OpenAI | openai Python SDK | gpt-4o |
| Gemini | google-generativeai SDK | gemini-1.5-pro |

All three use JSON mode / structured output for step 1.
Selected via `X-Provider: claude|openai|gemini` request header.

---

## Send Email — EmailJS (client-side)

Same pattern as `../portfolio/js/main.js`:
- Load `@emailjs/browser@4` from jsDelivr CDN
- `emailjs.init({ publicKey: localStorage.getItem('ejs_key') })`
- `emailjs.send(service, template, { to_email, subject, body })`
- Seed credentials once: visit page with `?s=SERVICE&t=TEMPLATE&k=KEY`

---

## Security properties

| Risk | Mitigation |
|---|---|
| User prompt injection | No free-text prompt field; user selects from predefined actions only |
| Email content injection | Raw email not forwarded to step 3; only extracted structured fields are |
| Off-topic LLM use | Python validation gate after step 1; step 3 never reached if not a tax inquiry |
| API key exposure | All keys in .env / environment; never in frontend code |

---

## Environment variables (.env)

```
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
TAXJAR_API_KEY=
```
