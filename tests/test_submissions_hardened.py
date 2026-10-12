import pytest
import json
from app.config import settings
from app.services.rate_limiter import limiter
from app.database import get_db

@pytest.mark.asyncio
async def test_cors_preflight(client):
    """
    Requirement: Cross-origin submissions work: CORS headers correct, preflight (OPTIONS) handled.
    """
    resp = await client.options(
        "/submissions",
        headers={
            "Origin": "http://localhost:5500",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, Idempotency-Key"
        }
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == "*"
    assert "POST" in resp.headers.get("access-control-allow-methods", "")

@pytest.mark.asyncio
async def test_valid_submission_stored_and_enriched(client):
    """
    Requirement: Valid submissions stored safely, linked to the right widget and tenant, enriched.
    """
    payload = {
        "widget_id": "wgt_test_1",
        "data": {"email": "visitor@acme.com"}
    }
    resp = await client.post("/submissions", json=payload, headers={"Origin": "http://localhost:5500"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "success"
    assert data["widget_id"] == "wgt_test_1"
    assert "id" in data
    assert data["geo"] is not None
    assert data["geo"]["status"] == "enriched"

    # Verify database persistence
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM submissions WHERE id = ?", (data["id"],))
        row = cursor.fetchone()
        assert row is not None
        assert row["tenant_id"] == "t_acme"
        assert "visitor@acme.com" in row["payload"]

@pytest.mark.asyncio
async def test_boundary_validation_malformed_json(client):
    """
    Requirement & Probe 2: Malformed payload rejected with clean 4xx, never 500.
    """
    malformed_body = "{invalid_json: 123"
    resp = await client.post(
        "/submissions",
        content=malformed_body,
        headers={"Content-Type": "application/json", "Origin": "http://localhost:5500"}
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "Malformed JSON" in data.get("error", "")

@pytest.mark.asyncio
async def test_boundary_validation_oversized_payload(client):
    """
    Requirement & Probe 2: Oversized payload rejected with 413, never 500.
    """
    huge_data = {"email": "a" * (settings.MAX_PAYLOAD_SIZE_BYTES + 5000)}
    payload = {"widget_id": "wgt_test_1", "data": huge_data}
    resp = await client.post(
        "/submissions",
        json=payload,
        headers={"Origin": "http://localhost:5500"}
    )
    assert resp.status_code == 413
    assert "Payload Too Large" in resp.json().get("error", "")

@pytest.mark.asyncio
async def test_boundary_validation_missing_required_field(client):
    """
    Requirement: Missing required form field returns 400 validation error.
    """
    payload = {"widget_id": "wgt_test_1", "data": {}}
    resp = await client.post("/submissions", json=payload)
    assert resp.status_code == 400
    assert "Validation Error" in resp.json().get("error", "")

@pytest.mark.asyncio
async def test_abuse_prevention_honeypot(client):
    """
    Requirement & Probe 6: Honeypot field filled by bot is detected and rejected.
    """
    bot_payload = {
        "widget_id": "wgt_test_1",
        "data": {"email": "spammer@botnet.org"},
        "_hp": "I am a malicious bot filling all fields"
    }
    resp = await client.post("/submissions", json=bot_payload)
    assert resp.status_code == 400
    data = resp.json()
    assert "Spam detected" in data.get("error", "")

    # Ensure it was NOT inserted into the database
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM submissions WHERE payload LIKE '%spammer@botnet.org%'")
        assert cursor.fetchone()["count"] == 0

@pytest.mark.asyncio
async def test_abuse_prevention_rate_limiting(client):
    """
    Requirement & Probe 3: Burst of rapid submissions triggers 429, subsequent requests succeed.
    """
    limiter.reset()
    payload = {"widget_id": "wgt_test_1", "data": {"email": "burst@example.com"}}

    got_429 = False
    # Fire requests exceeding the burst limit
    for _ in range(settings.RATE_LIMIT_IP_BURST + 2):
        resp = await client.post("/submissions", json=payload)
        if resp.status_code == 429:
            got_429 = True
            assert "Retry-After" in resp.headers

    assert got_429, "Expected 429 under rapid burst traffic"

    # Reset limiter to simulate normal request right after
    limiter.reset()
    normal_resp = await client.post("/submissions", json=payload)
    assert normal_resp.status_code == 201

@pytest.mark.asyncio
async def test_geo_fallback_provider_a_fails(client):
    """
    Requirement & Probe 4: Provider A fails -> Provider B answers -> submission enriched.
    """
    payload = {"widget_id": "wgt_test_1", "data": {"email": "geo_fallback@test.com"}}
    resp = await client.post(
        "/submissions",
        json=payload,
        headers={"X-Mock-Fail-Geo-A": "1"}
    )
    assert resp.status_code == 201
    geo = resp.json().get("geo")
    assert geo is not None
    assert geo["provider"] == settings.GEO_PROVIDER_B_NAME
    assert geo["status"] == "enriched"

@pytest.mark.asyncio
async def test_geo_fallback_all_providers_fail(client):
    """
    Requirement & Probe 4: All providers fail -> submission still succeeds (without geo). Degrade, never fail.
    """
    payload = {"widget_id": "wgt_test_1", "data": {"email": "geo_all_down@test.com"}}
    resp = await client.post(
        "/submissions",
        json=payload,
        headers={"X-Mock-Fail-Geo-A": "1", "X-Mock-Fail-Geo-B": "1"}
    )
    assert resp.status_code == 201
    geo = resp.json().get("geo")
    assert geo is not None
    assert geo["provider"] == "none"
    assert geo["status"] == "degraded"
    assert geo["country"] is None

    # Stored row in DB has NULL country
    sub_id = resp.json()["id"]
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT country, geo_provider FROM submissions WHERE id = ?", (sub_id,))
        row = cursor.fetchone()
        assert row["country"] is None
        assert row["geo_provider"] == "none"

@pytest.mark.asyncio
async def test_safe_side_effects_email_failure(client):
    """
    Requirement & Probe 5: Force email/webhook side effect to throw -> submission still returns success and is stored.
    """
    payload = {"widget_id": "wgt_test_1", "data": {"email": "email_throws@test.com"}}
    resp = await client.post(
        "/submissions",
        json=payload,
        headers={"X-Mock-Fail-Email": "1"}
    )
    assert resp.status_code == 201
    sub_id = resp.json()["id"]

    # Submission was stored safely
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM submissions WHERE id = ?", (sub_id,))
        assert cursor.fetchone() is not None

@pytest.mark.asyncio
async def test_idempotency_deduplication(client):
    """
    Shared Requirement 5: Retrying with the same Idempotency-Key returns existing response without duplicate DB rows.
    """
    payload = {"widget_id": "wgt_test_1", "data": {"email": "idempotent@test.com"}}
    headers = {"Idempotency-Key": "test-idem-key-999"}

    # First attempt
    res1 = await client.post("/submissions", json=payload, headers=headers)
    assert res1.status_code == 201
    id1 = res1.json()["id"]

    # Second attempt (same key)
    res2 = await client.post("/submissions", json=payload, headers=headers)
    assert res2.status_code == 201
    id2 = res2.json()["id"]

    assert id1 == id2

    # Check database: exactly 1 row exists
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM submissions WHERE idempotency_key = 'test-idem-key-999'")
        assert cursor.fetchone()["count"] == 1
