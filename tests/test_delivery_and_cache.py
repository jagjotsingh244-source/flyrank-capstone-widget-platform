import pytest

@pytest.mark.asyncio
async def test_public_config_caching_and_cors(client):
    """
    Requirements:
    - Public config endpoint serves small payload.
    - Correct HTTP cache headers (Cache-Control: public, max-age=60).
    - CORS enabled for third-party websites.
    """
    resp = await client.get("/widgets/wgt_test_1/config")
    assert resp.status_code == 200
    data = resp.json()

    assert data["id"] == "wgt_test_1"
    assert data["type"] == "signup"
    assert "fields" in data
    assert "submission_url" in data

    # Cache headers check
    cache_control = resp.headers.get("cache-control")
    assert cache_control is not None
    assert "max-age=60" in cache_control

    # CORS header check
    assert resp.headers.get("access-control-allow-origin") == "*"

@pytest.mark.asyncio
async def test_widget_script_delivery_and_versioning(client):
    """
    Requirements:
    - Widget JavaScript served as versioned bundle.
    - Cache headers: long-lived immutable cache for versioned script.
    """
    resp_loader = await client.get("/widget.js?id=wgt_test_1")
    assert resp_loader.status_code == 200
    assert "javascript" in resp_loader.headers.get("content-type", "")
    assert "window.__FLYRANK_DEFAULT_WIDGET_ID__ = 'wgt_test_1';" in resp_loader.text

    resp_versioned = await client.get("/static/widget.v1.js")
    assert resp_versioned.status_code == 200
    assert "javascript" in resp_versioned.headers.get("content-type", "")
    cache_control = resp_versioned.headers.get("cache-control", "")
    assert "max-age=31536000" in cache_control
    assert "immutable" in cache_control
