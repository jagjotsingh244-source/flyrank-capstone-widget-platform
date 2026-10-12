import json
import uuid
from typing import Optional, Dict, Any, Tuple
from app.database import get_db

class IdempotencyService:
    """
    Guarantees that repeated form submissions with the same Idempotency-Key
    are executed once, returning the cached successful response.
    """

    @staticmethod
    def get_existing_response(widget_id: str, idempotency_key: str) -> Optional[Tuple[int, Dict[str, Any]]]:
        if not idempotency_key:
            return None
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status_code, response_json FROM idempotency_records WHERE widget_id = ? AND idempotency_key = ?",
                (widget_id, idempotency_key.strip())
            )
            row = cursor.fetchone()
            if row:
                return row["status_code"], json.loads(row["response_json"])
        return None

    @staticmethod
    def save_response(widget_id: str, idempotency_key: str, status_code: int, response_data: Dict[str, Any]):
        if not idempotency_key:
            return
        with get_db() as conn:
            cursor = conn.cursor()
            record_id = f"idemp_{uuid.uuid4().hex[:12]}"
            cursor.execute(
                """
                INSERT OR REPLACE INTO idempotency_records (id, widget_id, idempotency_key, status_code, response_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (record_id, widget_id, idempotency_key.strip(), status_code, json.dumps(response_data))
            )

idempotency_service = IdempotencyService()
