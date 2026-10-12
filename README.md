# FlyRank Embeddable Widget & Lead-Capture Platform

[![Tests](https://img.shields.io/badge/tests-18%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20SQLite%20%7C%20VanillaJS-orange.svg)]()

> A resilient backend platform that lets customers create embeddable lead-capture widgets, install them on any website with a single `<script>` snippet, and safely handle public web traffic — validated, spam-protected, rate-limited, geo-enriched with a multi-provider fallback chain, and dashboarded.

Built for the **FlyRank Backend Track Capstone Project**.

---

## Architecture Overview

The system isolates three distinct request paths so that untrusted public web traffic can never compromise administrative data or crash background services:

```
+---------------------------------------------------------------------------------------+
|                                  THREE REQUEST PATHS                                  |
+---------------------------------------------------------------------------------------+

1. WIDGET OWNER (Authenticated Admin Path)
   [ Owner Browser / API Client ]
                | (Authorization: Bearer <tenant_api_key>)
                v
   [ Admin API / Dashboard ] ---> [ Tenant-Isolated DB Queries ] ---> [ Widgets & Stats ]

2. CUSTOMER WEBSITE VISITOR (Public CDN / Delivery Path)
   [ Third-Party Website ]
                | Loads <script src="/widget.js?id=..."> (Cache-Control: public, max-age=31536000)
                v
   [ Delivery Endpoint ]
                | GET /widgets/:id/config (Cache-Control: public, max-age=60)
                v
   [ Browser mounts Widget Shadow DOM / Form ]

3. PUBLIC FORM VISITOR (Public Hardened Submission Path)
   [ Visitor Submits Form ]
                | POST /submissions (Cross-Origin CORS + Idempotency-Key)
                v
   +-----------------------------------------------------------------------+
   | Boundary Validation: Payload size <= 64KB, Schema check               |
   | Abuse Protection: Per-IP & Per-Widget Rate Limiter, Honeypot check   |
   | Idempotency Check: Returns existing record on duplicate key           |
   | Geo Enrichment Chain: ip-api.com -> ipapi.co -> Degrade safely       |
   | Primary Storage: Store submission linked to Widget & Tenant           |
   | Safe Background Side Effect: Non-blocking Email / Webhook             |
   +-----------------------------------------------------------------------+
                |
                v
          HTTP 201 Created
```

---

## Core Features & Guarantees

1. **Multi-Tenant Isolation**: Every database query scopes `WHERE tenant_id = :tenant_id`. Tenant A can never view, update, or delete Tenant B's widgets or submissions.
2. **Hardened Boundary Validation**: Incoming payloads exceeding 64KB are rejected immediately with `413 Payload Too Large`. Malformed JSON yields clean `400 Bad Request` (never 500).
3. **Abuse & Bot Resistance**:
   - **Sliding-Window Rate Limiter**: Enforces burst thresholds per IP and per widget, responding with `429 Too Many Requests` and standard `Retry-After` headers.
   - **Honeypot Trap**: Invisible field `_hp` triggers immediate `400 Bad Request` ("Spam detected") if filled by automated scrapers.
4. **Resilient Geolocation Fallback Chain**:
   - Provider A (`ip-api.com`) &rarr; Provider B (`ipapi.co`) &rarr; Graceful Degradation (`provider: "none"`).
   - If all geo services are offline, the submission **still succeeds (201 Created)** and is stored safely.
5. **Non-Blocking Safe Side Effects**: Confirmation notifications (emails/webhooks) run in background worker tasks with exponential backoff retries. If the notification service throws an exception, the visitor submission remains safe and stored.
6. **Idempotency Guard**: Repeated submissions with the same `Idempotency-Key` return the cached response without duplicate insertions.
7. **Cache-Optimized Delivery**:
   - `/static/widget.v1.js`: `Cache-Control: public, max-age=31536000, immutable`.
   - `/widgets/{id}/config`: `Cache-Control: public, max-age=60`.

---

## Quickstart & Setup

### Prerequisites
- Python 3.9+ (Zero credit card, completely free $0 stack)

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/<your-username>/flyrank-capstone-widget-platform.git
cd flyrank-capstone-widget-platform

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
# (or: pip install fastapi uvicorn pydantic httpx pytest pytest-asyncio python-multipart)
```

### 2. Seed Demo Database
```bash
python3 scripts/seed.py
```
This populates sample tenants, widgets, and submissions:
- **Tenant Acme:** API Key = `demo_key_acme_123` (Widgets: `wgt_demo_newsletter`, `wgt_demo_support`)
- **Tenant Beta:** API Key = `demo_key_beta_456` (Widget: `wgt_beta_contact`)

### 3. Start the Backend API
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
- API Base: `http://localhost:8000`
- Interactive Swagger Docs: `http://localhost:8000/docs`
- Owner Dashboard UI: `http://localhost:8000/dashboard`

### 4. (Optional) Run the Cross-Origin Customer Test Site
In a second terminal:
```bash
python3 demo_site/serve.py
```
Open `http://localhost:5500` in your browser. This demonstrates the widget embedding on a separate origin and submitting back to `http://localhost:8000`.

---

## Running the Automated Test Suite & Probes

Run the full pytest suite (18 unit & integration tests):
```bash
pytest -v
```

Execute the live behavioral acceptance probe verification runner:
```bash
python3 scripts/verify_live_probes.py
```

---

## API Reference

### 1. Public Delivery & Submission Endpoints
| Method | Path | Description | Headers / Params |
|---|---|---|---|
| `GET` | `/widget.js` | Loader script | `?id={widget_id}` |
| `GET` | `/static/widget.v1.js` | Immutable versioned client bundle | `Cache-Control: max-age=31536000` |
| `GET` | `/widgets/{id}/config` | Public widget configuration JSON | `Cache-Control: max-age=60`, CORS `*` |
| `OPTIONS` | `/submissions` | CORS Preflight check | Returns 200/204 with CORS allow headers |
| `POST` | `/submissions` | Public form submission | Body: `{"widget_id": "...", "data": {...}, "_hp": ""}` |

### 2. Authenticated Management Endpoints
*Requires header `Authorization: Bearer <tenant_api_key>` or `X-API-Key: <tenant_api_key>`*

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/widgets` | Create a new widget (returns snippet) |
| `GET` | `/api/widgets` | List tenant's widgets |
| `GET` | `/api/widgets/{id}` | Get widget details |
| `PUT` | `/api/widgets/{id}` | Update widget schema/theme |
| `DELETE` | `/api/widgets/{id}` | Delete widget |
| `GET` | `/api/dashboard/stats` | Aggregated analytics & geo breakdown |
| `GET` | `/api/dashboard/submissions`| Paginated submissions list |

---

## Embed Snippet Usage

Once a widget is created, paste this snippet into any webpage:
```html
<script src="http://localhost:8000/widget.js?id=wgt_demo_newsletter"></script>
```
To specify a custom container:
```html
<div data-flyrank-widget="wgt_demo_newsletter"></div>
```
CTA Popovers render as a floating action button automatically if configured as `type: "cta_popover"`.

---

## Honest Limitations Note

1. **In-Memory Rate Limiting:** The sliding-window rate limiter stores timestamps in process memory with mutex locking. In a distributed multi-node deployment, this would be backed by Redis or Dragonfly for unified cross-instance synchronization.
2. **Single SQLite Database File:** For zero-cost local execution, SQLite WAL mode is utilized. For high-write concurrency in enterprise environments, Postgres via Docker is recommended.
3. **Simulated Email Provider:** By default, confirmation emails log to console or Mailpit. Production integration would swap in SendGrid, Postmark, or AWS SES.

---

## Submission Pack Structure

```
flyrank-capstone-widget-platform/
├── README.md               # System overview, run steps, architecture, and limitations
├── capstone.yaml           # Automated evaluation manifest
├── EVIDENCE.md             # Pasted test outputs & proof for all Section 6 requirements
├── BUILDLOG.md             # Transparent AI-usage and debugging reflection log
├── .env.example            # Environment template with safe placeholders
├── LICENSE                 # MIT License
├── app/
│   ├── config.py           # Configuration & chaos toggles
│   ├── database.py         # SQLite connection, migrations, indices
│   ├── security.py         # Tenant API key authentication & scoping
│   ├── models/             # Pydantic schemas & boundary validation
│   ├── services/           # Rate limiting, geo fallback, resilient notification
│   ├── routes/             # Widgets CRUD, delivery, submissions, dashboard
│   ├── static/             # Embeddable widget JS bundle (widget.v1.js)
│   └── templates/          # HTML Owner Dashboard
├── demo_site/              # Second-origin customer test site (port 5500)
├── scripts/                # Database seeder and live probes runner
└── tests/                  # 18 automated pytest cases
```
