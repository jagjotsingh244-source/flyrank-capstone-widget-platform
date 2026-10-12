import pytest

@pytest.mark.asyncio
async def test_dashboard_stats_and_tenant_scoping(client):
    """
    Requirement: Owner views submissions with analytics, and Tenant B cannot see Tenant A's submissions.
    """
    acme_headers = {"Authorization": "Bearer key_acme_123"}
    beta_headers = {"Authorization": "Bearer key_beta_456"}

    # Post a submission for Acme's widget
    await client.post("/submissions", json={
        "widget_id": "wgt_test_1",
        "data": {"email": "dash_test@acme.com"}
    })

    # Acme queries dashboard stats
    acme_res = await client.get("/api/dashboard/stats", headers=acme_headers)
    assert acme_res.status_code == 200
    acme_stats = acme_res.json()
    assert acme_stats["total_submissions"] >= 1
    assert len(acme_stats["recent_submissions"]) >= 1

    # Beta queries dashboard stats -> must be 0 (strict tenant isolation!)
    beta_res = await client.get("/api/dashboard/stats", headers=beta_headers)
    assert beta_res.status_code == 200
    beta_stats = beta_res.json()
    assert beta_stats["total_submissions"] == 0
    assert len(beta_stats["recent_submissions"]) == 0
