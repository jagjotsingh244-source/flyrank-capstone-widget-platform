import os
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.config import settings
from app.database import init_db, get_db
from app.services.rate_limiter import limiter

TEST_DB_PATH = "test_widget_platform.db"

@pytest.fixture(autouse=True)
def setup_test_db():
    settings.DATABASE_PATH = TEST_DB_PATH
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    init_db(TEST_DB_PATH)
    limiter.reset()

    # Seed baseline tenant and widget
    with get_db(TEST_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tenants (id, name, api_key) VALUES ('t_acme', 'Acme Corp', 'key_acme_123');")
        cursor.execute("INSERT INTO tenants (id, name, api_key) VALUES ('t_beta', 'Beta Corp', 'key_beta_456');")
        cursor.execute("""
            INSERT INTO widgets (id, tenant_id, name, type, title, description, fields_schema, button_text, display_theme, is_active)
            VALUES (
                'wgt_test_1', 't_acme', 'Newsletter', 'signup', 'Subscribe', 'Desc',
                '[{"name": "email", "label": "Email", "type": "email", "required": true}]',
                'Submit', '{"primary_color": "#4F46E5"}', 1
            );
        """)

    yield

    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
