# System Design Document: Embeddable Widget & Lead-Capture Platform

> **Status:** APPROVED  
> **Author:** Jagjot Singh  
> **Track:** FlyRank Internship · Backend Track Capstone  
> **Gate Target:** Phase 1 Design Gate  

---

## 1. Problem Statement & Mission

Building an embeddable widget platform means treating the open internet as an untrusted input pipe. A customer copies a single snippet:
```html
<script src="http://localhost:8000/widget.js?id=wgt_acme123"></script>
```
When placed on third-party sites, requests arrive from origins we do not control. The platform must:
1. Deliver ultra-fast, cache-optimized JavaScript and configuration without stalling customer websites.
2. Accept cross-origin form submissions while handling CORS preflight, origin validation, and strict boundary payloads.
3. Resist abuse by applying rate limits (per IP and per widget) and trapping bot submissions with honeypot fields.
4. Enrich submissions with geographic data using a multi-provider fallback chain that **never crashes or blocks storage** if providers fail.
5. Trigger secondary side effects (email notifications/webhooks) asynchronously without breaking the core submission flow.
6. Provide authenticated, tenant-isolated widget management and analytics for business owners.

---

## 2. Core Architecture & Request Paths

The platform explicitly isolates three distinct request paths:

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

## 3. Data Model & Tenant Isolation

All queries enforce tenant isolation at the database layer using strict `WHERE tenant_id = :tenant_id` scoping.

### Entity Relationship & Tables

```
+-------------------------+            +----------------------------------+
|        tenants          |            |             widgets              |
+-------------------------+            +----------------------------------+
| id: VARCHAR PRIMARY KEY | 1        * | id: VARCHAR PRIMARY KEY          |
| name: VARCHAR NOT NULL  |<-----------| tenant_id: VARCHAR NOT NULL (FK) |
| api_key: VARCHAR UNIQUE |            | name: VARCHAR NOT NULL           |
| created_at: TIMESTAMP   |            | type: VARCHAR (signup|contact)   |
+-------------------------+            | title: VARCHAR NOT NULL          |
                                       | description: TEXT                |
                                       | fields_schema: JSON NOT NULL     |
                                       | button_text: VARCHAR NOT NULL    |
                                       | display_theme: JSON NOT NULL     |
                                       | is_active: BOOLEAN DEFAULT 1     |
                                       | created_at: TIMESTAMP            |
                                       | updated_at: TIMESTAMP            |
                                       +----------------------------------+
                                                        | 1
                                                        |
                                                        | *
                                       +----------------------------------+
                                       |           submissions            |
                                       +----------------------------------+
                                       | id: VARCHAR PRIMARY KEY          |
                                       | widget_id: VARCHAR NOT NULL (FK) |
                                       | tenant_id: VARCHAR NOT NULL (FK) |
                                       | payload: JSON NOT NULL           |
                                       | idempotency_key: VARCHAR         |
                                       | ip_address: VARCHAR              |
                                       | user_agent: VARCHAR              |
                                       | referrer: VARCHAR                |
                                       | country: VARCHAR                 |
                                       | city: VARCHAR                    |
                                       | region: VARCHAR                  |
                                       | geo_provider: VARCHAR            |
                                       | created_at: TIMESTAMP            |
                                       +----------------------------------+
```

### Database Indexes
- `idx_widgets_tenant`: `widgets(tenant_id)`
- `idx_widgets_tenant_id`: `widgets(tenant_id, id)`
- `idx_submissions_widget_tenant`: `submissions(widget_id, tenant_id)`
- `idx_submissions_tenant_created`: `submissions(tenant_id, created_at)`
- `idx_submissions_idempotency`: `submissions(widget_id, idempotency_key)`

---

## 4. API Contracts

### Path 1: Widget Management & Dashboard (Authenticated)
- `POST /api/widgets` — Create widget. (Req: `name`, `type`, `title`, `fields_schema`, `button_text`. Resp: `201 Created` + snippet).
- `GET /api/widgets` — List all widgets owned by the authenticated tenant. (Resp: `200 OK`).
- `GET /api/widgets/{id}` — Fetch specific widget. (Resp: `200 OK` or `404 Not Found`).
- `PUT /api/widgets/{id}` — Update widget properties. (Resp: `200 OK`).
- `DELETE /api/widgets/{id}` — Delete or soft-delete widget. (Resp: `200 OK` or `204 No Content`).
- `GET /api/dashboard/stats` — Metrics: Total submissions, submissions by widget, geographic breakdown, time-series counts.
- `GET /api/dashboard/submissions` — Paginated submissions list for tenant.

### Path 2: Public Delivery
- `GET /widget.js` — Bootstrapper loader script (redirects or serves versioned bundle).
- `GET /static/widget.v1.js` — Core versioned widget script.  
  *Headers:* `Cache-Control: public, max-age=31536000, immutable`, `Access-Control-Allow-Origin: *`.
- `GET /widgets/{id}/config` — Public widget configuration JSON.  
  *Headers:* `Cache-Control: public, max-age=60`, `Access-Control-Allow-Origin: *`.

### Path 3: Public Submission
- `OPTIONS /submissions` — CORS Preflight.  
  *Headers:* `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: POST, OPTIONS`, `Access-Control-Allow-Headers: Content-Type, Idempotency-Key`.
- `POST /submissions` — Public form submit.  
  *Payload:*
  ```json
  {
    "widget_id": "wgt_123",
    "data": {
      "email": "visitor@example.com",
      "name": "Alex"
    },
    "_hp": ""
  }
  ```
  *Status Responses:*
  - `201 Created` — Form saved and enriched.
  - `400 Bad Request` — Schema validation failed or honeypot filled (`{"error": "Spam detected"}`).
  - `404 Not Found` — Widget ID does not exist or is inactive.
  - `413 Payload Too Large` — Body exceeds max size (64KB).
  - `429 Too Many Requests` — Rate limit exceeded per IP or widget.

---

## 5. Resilience & Fault Tolerance Strategies

1. **Deterministic Geo Fallback:**
   - Attempt Provider A (`ip-api.com`). If timeout/HTTP error occurs:
   - Fall back to Provider B (`ipapi.co`). If both fail:
   - Store submission with `geo_provider: "none"`, `country: null`, `city: null`.
   - Result: Visitor submission is never dropped due to upstream vendor downtime.
2. **Safe Side-Effect Execution:**
   - Email dispatch is queued as a background task after the database commit.
   - Any SMTP/API exception is caught and logged as a degradation alert.
   - Result: Visitors always receive a `201 Created` confirmation.
3. **Idempotency Guard:**
   - Client sends `Idempotency-Key: <uuid>`.
   - Repeated requests with the same key for the same widget return the stored submission without re-inserting or re-firing side effects.

---

## 6. Explicit Non-Goals

1. **No Drag-and-Drop Form Builder UI:** This is a backend and resilience capstone. The admin API manages structured form schemas, and the client widget renders standard clean semantic HTML.
2. **No Proprietary Third-Party Cloud CDN or Paid Hosting:** Everything runs cleanly on localhost with zero cost ($0 stack). Multi-origin testing is achieved locally using separate ports (e.g. 8000 and 5500).
3. **No Complex Multi-Step Wizard Workflows:** Widgets support standard single-step lead capture (signup forms, contact forms, CTA popovers).
