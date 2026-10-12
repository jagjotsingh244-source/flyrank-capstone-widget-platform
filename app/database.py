import sqlite3
import json
from contextlib import contextmanager
from typing import Generator
from app.config import settings

def get_connection(db_path: str = None) -> sqlite3.Connection:
    path = db_path or settings.DATABASE_PATH
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

@contextmanager
def get_db(db_path: str = None) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db(db_path: str = None):
    """
    Initializes database schema with tables, constraints, and indexes.
    Implements real persistence and tenant isolation guarantees.
    """
    with get_db(db_path) as conn:
        cursor = conn.cursor()

        # Tenants Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Widgets Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS widgets (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            fields_schema TEXT NOT NULL,
            button_text TEXT NOT NULL DEFAULT 'Submit',
            display_theme TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        );
        """)

        # Submissions Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            widget_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            idempotency_key TEXT,
            ip_address TEXT,
            user_agent TEXT,
            referrer TEXT,
            country TEXT,
            city TEXT,
            region TEXT,
            geo_provider TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (widget_id) REFERENCES widgets(id) ON DELETE CASCADE,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        );
        """)

        # Idempotency Records Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_records (
            id TEXT PRIMARY KEY,
            widget_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            response_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(widget_id, idempotency_key)
        );
        """)

        # Performance and isolation indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_widgets_tenant ON widgets(tenant_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_widgets_tenant_id ON widgets(tenant_id, id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_submissions_widget_tenant ON submissions(widget_id, tenant_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_submissions_tenant_created ON submissions(tenant_id, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_submissions_idempotency ON submissions(idempotency_key);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_idempotency_lookup ON idempotency_records(widget_id, idempotency_key);")
