# BUILDLOG.md — AI-Assisted Engineering Log

> **Project:** FlyRank Capstone — Embeddable Widget & Lead-Capture Platform  
> **Student / Engineer:** Jagjot Singh  
> **Date:** October 2026  
> **Grading Policy:** Honesty is graded, perfection is not.

---

## 1. Executive Summary

This project was built following the FlyRank Backend Track Capstone brief with AI pairing assistance. The goal was to build a production-grade, hardened, embeddable lead capture platform adhering to three distinct request paths, abuse protection, geo fallback degradation, safe background side-effects, and multi-tenant isolation.

This log details where AI assistance accelerated development, where AI code was erroneous or incomplete, and the exact architectural and debugging decisions made by the engineer.

---

## 2. Phase-by-Phase AI Usage & Refinements

### Phase 1: System Design & Architecture
- **Where AI helped:**
  - Fast generation of the initial draft for `DESIGN.md`.
  - Formatting ASCII architecture diagrams and database entity relationships.
- **Where human judgement intervened:**
  - Ensured explicit boundary separation between the 3 actors: Widget Owner (authenticated), Customer Site (public cached), and Website Visitor (untrusted public).
  - Drafted strict non-goals (e.g. avoiding form builder bloat, zero cloud hosting dependencies) to prevent gold-plating and keep scope aligned with Section 7 of the brief.

---

### Phase 2: The Hardened Submission Path & Services

#### A. Pydantic v2 Honeypot Schema Error
- **Where AI was wrong:**
  - AI generated `_hp: Optional[str] = None` directly in the Pydantic model for honeypot bot trap detection.
  - In Pydantic v2, fields with leading underscores are reserved for internal `PrivateAttr` usage. Pytest immediately crashed on startup with:
    ```
    NameError: Fields must not use names with leading underscores; e.g., use 'hp' instead of '_hp'.
    ```
- **What I changed:**
  - Refactored `SubmissionCreate` in `app/models/schemas.py`:
    ```python
    hp: Optional[str] = Field(None, alias="_hp", description="Honeypot trap field - must remain empty")
    model_config = {"populate_by_name": True}
    ```
  - Updated `app/routes/submissions.py` to access `submission.hp`.

#### B. Rate Limiting Headers on Exception Responses
- **Where AI was wrong:**
  - AI initially attached the `Retry-After` header to the route's injected `Response` object (`response.headers["Retry-After"] = str(retry_after)`) before raising `HTTPException(status_code=429)`.
  - In Starlette/FastAPI, raising an exception short-circuits the response, discarding modifications to the route parameter `Response`.
- **What I changed:**
  - Directly injected headers into the exception itself:
    ```python
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={"error": "Too Many Requests", "message": limit_reason, "retry_after": retry_after},
        headers={"Retry-After": str(retry_after), "Access-Control-Allow-Origin": "*"}
    )
    ```

#### C. Geolocation Provider Fallback & Sandboxed Environments
- **Where AI was wrong / needed architectural tuning:**
  - AI wrote live HTTP calls to `http://ip-api.com` and `https://ipapi.co`.
  - When running in automated test environments or restricted networks, external third-party APIs return HTTP 403 or network errors, making tests non-deterministic.
- **What I changed:**
  - Followed Section 3 of the capstone brief: *"Mock the geo providers when you prove the fallback — use the real free APIs while developing, but make the fallback proof deterministic"*.
  - Added `GEO_MOCK_MODE` setting in `app/config.py` and supported chaos headers (`X-Mock-Fail-Geo-A: 1`, `X-Mock-Fail-Geo-B: 1`).
  - Implemented the deterministic fallback chain:
    1. Provider A (`ip-api.com`) answers.
    2. If Provider A is down, Provider B (`ipapi.co`) answers.
    3. If Provider B is also down, submission degrades safely to `provider: "none"` without failing the visitor's request.

---

### Phase 3: Delivery, Widget Script & Customer Demo Origin

#### A. Static Asset Cache Headers in FastAPI
- **Where AI was wrong:**
  - AI mounted standard Starlette `StaticFiles(directory=static_dir)` for `/static`, while defining a route for `/static/widget.v1.js` with `Cache-Control: public, max-age=31536000, immutable`.
  - Starlette mounts take precedence over route lookups for that path prefix, causing the static script to be served with empty Cache-Control headers.
- **What I changed:**
  - Subclassed `StaticFiles` as `CachedStaticFiles` in `app/main.py`:
    ```python
    class CachedStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            response = await super().get_response(path, scope)
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response
    ```
  - This ensures all versioned static bundles receive immutable CDN-grade caching headers.

#### B. Second-Origin Testing Environment
- **Where AI helped:**
  - Created a separate Python HTTP server script `demo_site/serve.py` on port 5500 serving `demo_site/index.html`.
  - Embedded the widget script `<script src="http://localhost:8000/widget.js?id=wgt_demo_newsletter"></script>` to prove cross-origin functionality under real browser origin rules.

---

### Phase 4: Test Suite & Live Acceptance Probes

- **Where AI helped:**
  - Writing boilerplate test cases for CRUD and query parameters.
- **Where I guided the implementation:**
  - Designed all 18 automated tests in `tests/` covering every requirement in Section 6.
  - Implemented `scripts/verify_live_probes.py` using `ASGITransport` to execute end-to-end probes against the live application and verify all 6 behavioral probes defined in Section 13.

---

## 3. Explaining My Code (Viva Preparation)

I can explain any 2–3 lines of this codebase:

1. **Multi-Tenant Scoping (`app/routes/widgets.py` & `app/security.py`):**
   ```python
   cursor.execute("SELECT * FROM widgets WHERE id = ? AND tenant_id = ?", (widget_id, tenant["id"]))
   ```
   *Explanation:* Multi-tenant isolation cannot rely on UI filtering; it must be guaranteed at the query level. Even if an attacker knows a valid widget ID belonging to another company, the database query returns 0 rows because `tenant_id` is bound from the cryptographically verified authentication token.

2. **Idempotency Guard (`app/services/idempotency.py`):**
   ```python
   INSERT OR REPLACE INTO idempotency_records (id, widget_id, idempotency_key, status_code, response_json)
   ```
   *Explanation:* When networks glitch, clients retry POST requests. By tracking `(widget_id, idempotency_key)`, subsequent duplicate requests retrieve the stored HTTP 201 response payload without inserting a duplicate database row or re-firing email side effects.

3. **Graceful Geo Fallback Degradation (`app/services/geo_service.py`):**
   ```python
   except Exception as e:
       logger.warning(f"Geo Provider A failed: {str(e)}. Proceeding to fallback Provider B.")
   ```
   *Explanation:* Upstream network dependencies must degrade the response, never destroy it. If geolocation APIs are down, we log a warning and proceed, storing the submission with `geo_provider: "none"` so no customer lead is ever lost.
