import pytest

@pytest.mark.asyncio
async def test_auth_rejection_without_key(client):
    """Requests without valid auth are rejected with 401."""
    resp = await client.get("/api/widgets")
    assert resp.status_code == 401
    assert "error" in resp.json()

@pytest.mark.asyncio
async def test_auth_rejection_with_invalid_key(client):
    """Requests with unknown API keys are rejected with 401."""
    resp = await client.get("/api/widgets", headers={"Authorization": "Bearer invalid_secret"})
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_widget_crud_lifecycle(client):
    """Full authenticated CRUD lifecycle with embed snippet verification."""
    headers = {"Authorization": "Bearer key_acme_123"}

    # 1. Create
    payload = {
        "name": "Contact Widget",
        "type": "contact",
        "title": "Contact Us",
        "description": "Send us a note",
        "fields_schema": [
            {"name": "email", "label": "Email", "type": "email", "required": True},
            {"name": "message", "label": "Message", "type": "textarea", "required": True}
        ],
        "button_text": "Send Now",
        "display_theme": {"primary_color": "#10B981"}
    }
    create_res = await client.post("/api/widgets", json=payload, headers=headers)
    assert create_res.status_code == 201
    created_data = create_res.json()
    widget_id = created_data["id"]
    assert created_data["name"] == "Contact Widget"
    assert "<script" in created_data["embed_snippet"]
    assert widget_id in created_data["embed_snippet"]

    # 2. Read
    get_res = await client.get(f"/api/widgets/{widget_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Contact Us"

    # 3. Update
    update_res = await client.put(f"/api/widgets/{widget_id}", json={"title": "Updated Contact Us"}, headers=headers)
    assert update_res.status_code == 200
    assert update_res.json()["title"] == "Updated Contact Us"

    # 4. Delete
    del_res = await client.delete(f"/api/widgets/{widget_id}", headers=headers)
    assert del_res.status_code == 200

    # Verify deleted
    get_after = await client.get(f"/api/widgets/{widget_id}", headers=headers)
    assert get_after.status_code == 404

@pytest.mark.asyncio
async def test_multi_tenant_isolation(client):
    """
    CRITICAL REQUIREMENT: Tenant A cannot read, edit, or delete Tenant B's widgets.
    """
    acme_headers = {"Authorization": "Bearer key_acme_123"}
    beta_headers = {"Authorization": "Bearer key_beta_456"}

    # Create widget as Tenant Acme
    res = await client.post("/api/widgets", json={
        "name": "Acme Secret Widget",
        "type": "signup",
        "title": "Acme Only",
        "fields_schema": [{"name": "email", "label": "Email", "type": "email", "required": True}]
    }, headers=acme_headers)
    assert res.status_code == 201
    acme_widget_id = res.json()["id"]

    # Tenant Beta attempts to GET Acme's widget -> 404
    beta_get = await client.get(f"/api/widgets/{acme_widget_id}", headers=beta_headers)
    assert beta_get.status_code == 404

    # Tenant Beta attempts to UPDATE Acme's widget -> 404
    beta_update = await client.put(f"/api/widgets/{acme_widget_id}", json={"title": "Hacked Title"}, headers=beta_headers)
    assert beta_update.status_code == 404

    # Tenant Beta attempts to DELETE Acme's widget -> 404
    beta_delete = await client.delete(f"/api/widgets/{acme_widget_id}", headers=beta_headers)
    assert beta_delete.status_code == 404

    # Tenant Beta listing widgets must NOT see Acme's widget
    beta_list = await client.get("/api/widgets", headers=beta_headers)
    assert beta_list.status_code == 200
    beta_ids = [w["id"] for w in beta_list.json()]
    assert acme_widget_id not in beta_ids
