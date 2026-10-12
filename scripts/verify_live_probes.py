#!/usr/bin/env python3
import sys
import os
import json
import asyncio
import httpx
from httpx import AsyncClient, ASGITransport

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.config import settings
from app.database import init_db
from app.services.rate_limiter import limiter
from scripts.seed import run_seed

DEMO_ORIGIN = "http://localhost:5500"
ACME_KEY = "demo_key_acme_123"

def print_separator(title):
    print("\n" + "=" * 75)
    print(f" {title}")
    print("=" * 75)

async def run_probes():
    # Ensure fresh seeded state
    run_seed()
    limiter.reset()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
        # Health check
        print_separator("HEALTH & ROOT ENDPOINT")
        r_health = await client.get("/")
        print(f"GET / -> HTTP {r_health.status_code}")
        print(f"Response: {json.dumps(r_health.json(), indent=2)}")
        assert r_health.status_code == 200

        # PROBE 1: POST a valid submission from the second-origin test page -> stored, 2xx, and visible via dashboard API
        print_separator("PROBE 1 — POST valid submission from second-origin test page -> 2xx, stored, visible via dashboard API")
        p1_payload = {
            "widget_id": "wgt_demo_newsletter",
            "data": {
                "name": "Sarah Connor",
                "email": "sarah.connor@resistance.net"
            }
        }
        p1_headers = {
            "Origin": DEMO_ORIGIN,
            "Content-Type": "application/json"
        }
        r1 = await client.post("/submissions", json=p1_payload, headers=p1_headers)
        print(f"Request: POST /submissions from Origin: {DEMO_ORIGIN}")
        print(f"HTTP Status: {r1.status_code} Created")
        print(f"CORS Header 'Access-Control-Allow-Origin': {r1.headers.get('access-control-allow-origin')}")
        p1_data = r1.json()
        print(f"Response JSON:\n{json.dumps(p1_data, indent=2)}")
        assert r1.status_code == 201
        sub_id = p1_data["id"]

        # Verify visibility in Dashboard API
        r1_dash = await client.get("/api/dashboard/submissions", headers={"Authorization": f"Bearer {ACME_KEY}"})
        print(f"\nVerification Query: GET /api/dashboard/submissions (Authenticated as Acme)")
        print(f"HTTP Status: {r1_dash.status_code}")
        submissions = r1_dash.json()
        matching = [s for s in submissions if s["id"] == sub_id]
        print(f"Submission Found in Dashboard: {len(matching) == 1}")
        if matching:
            print(f"Dashboard Record: {json.dumps(matching[0], indent=2)}")
        assert len(matching) == 1
        print(">>> PROBE 1: PASSED")

        # PROBE 2: Send a malformed and an oversized payload -> clean 4xx JSON errors, never a 500
        print_separator("PROBE 2 — Send malformed & oversized payload -> clean 4xx JSON errors, never a 500")
        
        # Part A: Malformed JSON
        r2_malformed = await client.post(
            "/submissions",
            content="{\"unclosed_string: 123",
            headers={"Content-Type": "application/json", "Origin": DEMO_ORIGIN}
        )
        print(f"Part A: Malformed JSON Body -> HTTP {r2_malformed.status_code} (Expected 400 Bad Request)")
        print(f"Response JSON: {r2_malformed.text}")
        assert r2_malformed.status_code == 400

        # Part B: Oversized Payload (>64KB)
        oversized_data = {"name": "Big Data", "email": "a" * (settings.MAX_PAYLOAD_SIZE_BYTES + 1024)}
        r2_oversized = await client.post(
            "/submissions",
            json={"widget_id": "wgt_demo_newsletter", "data": oversized_data},
            headers={"Origin": DEMO_ORIGIN}
        )
        print(f"\nPart B: Oversized Payload (>64KB) -> HTTP {r2_oversized.status_code} (Expected 413 Payload Too Large)")
        print(f"Response JSON: {r2_oversized.text}")
        assert r2_oversized.status_code == 413
        print(">>> PROBE 2: PASSED")

        # PROBE 3: Fire a burst of rapid submissions -> 429s appear, and normal request right after still succeeds
        print_separator("PROBE 3 — Fire burst of rapid submissions -> 429s appear, normal request after succeeds")
        limiter.reset()
        burst_payload = {
            "widget_id": "wgt_demo_newsletter",
            "data": {"name": "Burst Tester", "email": "burst@flood.io"}
        }
        burst_detected = False
        rate_limit_resp = None
        for i in range(settings.RATE_LIMIT_IP_BURST + 4):
            rb = await client.post("/submissions", json=burst_payload, headers={"Origin": DEMO_ORIGIN})
            if rb.status_code == 429:
                burst_detected = True
                rate_limit_resp = rb
                print(f"Attempt #{i+1:02d}: HTTP 429 Too Many Requests | Retry-After: {rb.headers.get('Retry-After')}s")
                break
            else:
                print(f"Attempt #{i+1:02d}: HTTP {rb.status_code}")

        assert burst_detected, "Did not receive HTTP 429 during burst"
        print(f"429 Response JSON: {rate_limit_resp.text}")

        # Normal request after resetting or from another IP succeeds immediately
        print("\nSubsequent legitimate request from separate IP (198.51.100.50):")
        r_legit = await client.post(
            "/submissions",
            json=burst_payload,
            headers={"Origin": DEMO_ORIGIN, "X-Forwarded-For": "198.51.100.50"}
        )
        print(f"HTTP Status: {r_legit.status_code} (Expected 201 Created)")
        assert r_legit.status_code == 201
        print(">>> PROBE 3: PASSED")

        # PROBE 4: Disable geo provider A -> next submission stored, enriched by provider B. Disable both -> stored anyway, without geo.
        print_separator("PROBE 4 — Provider Fallback Chain (A fails -> B answers; Both fail -> stored anyway without geo)")
        
        # Part A: Provider A down, Provider B answers
        r4_a = await client.post(
            "/submissions",
            json={"widget_id": "wgt_demo_newsletter", "data": {"name": "Fallback Visitor", "email": "fallback@geo.org"}},
            headers={"Origin": DEMO_ORIGIN, "X-Mock-Fail-Geo-A": "1", "X-Forwarded-For": "203.0.113.19"}
        )
        print(f"Part A (Provider A down): HTTP {r4_a.status_code}")
        geo_a = r4_a.json().get("geo")
        print(f"Enrichment result: {json.dumps(geo_a, indent=2)}")
        assert r4_a.status_code == 201
        assert geo_a["provider"] == settings.GEO_PROVIDER_B_NAME
        assert geo_a["status"] == "enriched"

        # Part B: Both Provider A & B down
        r4_both = await client.post(
            "/submissions",
            json={"widget_id": "wgt_demo_newsletter", "data": {"name": "Degrade Visitor", "email": "degrade@geo.org"}},
            headers={"Origin": DEMO_ORIGIN, "X-Mock-Fail-Geo-A": "1", "X-Mock-Fail-Geo-B": "1", "X-Forwarded-For": "203.0.113.20"}
        )
        print(f"\nPart B (Both providers down): HTTP {r4_both.status_code}")
        geo_both = r4_both.json().get("geo")
        print(f"Enrichment result (Degraded safely): {json.dumps(geo_both, indent=2)}")
        assert r4_both.status_code == 201
        assert geo_both["provider"] == "none"
        assert geo_both["status"] == "degraded"
        assert geo_both["country"] is None
        print(">>> PROBE 4: PASSED")

        # PROBE 5: Force the email/webhook side effect to throw -> submission still returns success and is stored
        print_separator("PROBE 5 — Force email/webhook side effect to throw -> submission returns success & is stored")
        r5 = await client.post(
            "/submissions",
            json={"widget_id": "wgt_demo_newsletter", "data": {"name": "Side Effect Test", "email": "fails@side-effect.org"}},
            headers={"Origin": DEMO_ORIGIN, "X-Mock-Fail-Email": "1", "X-Forwarded-For": "203.0.113.25"}
        )
        print(f"POST /submissions with forced email failure: HTTP {r5.status_code}")
        print(f"Response JSON: {json.dumps(r5.json(), indent=2)}")
        assert r5.status_code == 201
        print("Submission safely stored and acknowledged despite side effect failure.")
        print(">>> PROBE 5: PASSED")

        # PROBE 6: Fill the honeypot field like a bot would -> submission is silently dropped or rejected
        print_separator("PROBE 6 — Fill honeypot field like a bot would -> submission is rejected / dropped")
        bot_payload = {
            "widget_id": "wgt_demo_newsletter",
            "data": {"name": "Web Crawler Bot", "email": "crawler@botnet.biz"},
            "_hp": "malicious_bot_injected_data"
        }
        r6 = await client.post("/submissions", json=bot_payload, headers={"Origin": DEMO_ORIGIN})
        print(f"POST /submissions with populated honeypot: HTTP {r6.status_code}")
        print(f"Response JSON: {r6.text}")
        assert r6.status_code == 400
        assert "Spam detected" in r6.json().get("error", "")
        print("Bot submission blocked cleanly by honeypot filter.")
        print(">>> PROBE 6: PASSED")

        print_separator("ALL 6 ACCEPTANCE PROBES VERIFIED AND PASSED!")
    return True

if __name__ == "__main__":
    success = asyncio.run(run_probes())
    sys.exit(0 if success else 1)
