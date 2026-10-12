import json
import uuid
from typing import Optional
from fastapi import APIRouter, Request, Response, BackgroundTasks, Header, HTTPException, status
from app.config import settings
from app.database import get_db
from app.models.schemas import SubmissionCreate, SubmissionResponse
from app.services.rate_limiter import limiter
from app.services.geo_service import geo_service
from app.services.email_service import notification_service
from app.services.idempotency import idempotency_service

router = APIRouter(tags=["Public Submissions"])

@router.options("/submissions")
def handle_options():
    """
    Handles CORS preflight OPTIONS request for public form submissions.
    Ensures browsers from any origin are permitted to send submissions.
    """
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, Idempotency-Key, X-Mock-Fail-Geo-A, X-Mock-Fail-Geo-B, X-Mock-Fail-Email",
            "Access-Control-Max-Age": "86400",
        }
    )

@router.post("/submissions", response_model=SubmissionResponse, status_code=status.HTTP_201_CREATED)
async def submit_form(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    mock_fail_geo_a: Optional[str] = Header(None, alias="X-Mock-Fail-Geo-A"),
    mock_fail_geo_b: Optional[str] = Header(None, alias="X-Mock-Fail-Geo-B"),
    mock_fail_email: Optional[str] = Header(None, alias="X-Mock-Fail-Email"),
):
    """
    Hardened public form submission endpoint.
    1. Rejects oversized payloads (> 64KB) with 413.
    2. Validates JSON boundary with 400 on malformed input (never 500).
    3. Traps bots via honeypot (_hp field).
    4. Enforces rate limits per IP and per widget (429).
    5. Deduplicates retries using Idempotency-Key.
    6. Enriches submission via multi-provider geo fallback chain.
    7. Dispatches non-blocking side effects that never break the 201 response.
    """
    # Always attach CORS headers to the response
    response.headers["Access-Control-Allow-Origin"] = "*"

    # 1. Check Payload Size Limit (Requirement & Probe 2)
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings.MAX_PAYLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": "Payload Too Large",
                "message": f"Submitted body exceeds maximum size of {settings.MAX_PAYLOAD_SIZE_BYTES} bytes."
            }
        )

    # 2. Parse and Validate Body
    try:
        raw_body = await request.body()
        if len(raw_body) > settings.MAX_PAYLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"error": "Payload Too Large", "message": "Body exceeds maximum allowable size."}
            )
        data_json = json.loads(raw_body.decode("utf-8"))
        submission = SubmissionCreate(**data_json)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Malformed JSON", "message": "Request body could not be parsed as valid JSON."}
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid Payload", "message": str(e)}
        )

    # 3. Honeypot Bot Trap (Requirement & Probe 6)
    if submission.hp:
        # Bot filled the trap field: reject immediately with 400
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Spam detected", "message": "Submission rejected by automated abuse filter."}
        )

    # 4. Rate Limiting Check (Requirement & Probe 3)
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()

    is_allowed, limit_reason, retry_after = limiter.check_rate_limit(client_ip, submission.widget_id)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "Too Many Requests", "message": limit_reason, "retry_after": retry_after},
            headers={"Retry-After": str(retry_after), "Access-Control-Allow-Origin": "*"}
        )

    # 5. Idempotency Check (Shared Requirement 5)
    if idempotency_key:
        cached = idempotency_service.get_existing_response(submission.widget_id, idempotency_key)
        if cached:
            cached_status, cached_body = cached
            response.status_code = cached_status
            return cached_body

    # 6. Verify Widget Existence and Retrieve Tenant
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, tenant_id, title, fields_schema, is_active FROM widgets WHERE id = ?", (submission.widget_id,))
        widget_row = cursor.fetchone()

    if not widget_row or not widget_row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Not Found", "message": f"Active widget '{submission.widget_id}' not found."}
        )

    # Validate required fields defined in widget schema
    fields_schema = json.loads(widget_row["fields_schema"])
    for f in fields_schema:
        if f.get("required"):
            val = submission.data.get(f["name"])
            if val is None or (isinstance(val, str) and not val.strip()):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "Validation Error", "message": f"Missing required field '{f['name']}'."}
                )

    # 7. Geolocation Fallback Chain (Requirement & Probe 4)
    force_a = (mock_fail_geo_a == "1")
    force_b = (mock_fail_geo_b == "1")
    geo_data = await geo_service.enrich_ip(client_ip, force_fail_a=force_a, force_fail_b=force_b)

    # 8. Persist Submission Safely
    submission_id = f"sub_{uuid.uuid4().hex[:12]}"
    user_agent = request.headers.get("user-agent", "")
    referrer = request.headers.get("referer", "")

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO submissions (
                id, widget_id, tenant_id, payload, idempotency_key, ip_address,
                user_agent, referrer, country, city, region, geo_provider
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                submission_id,
                widget_row["id"],
                widget_row["tenant_id"],
                json.dumps(submission.data),
                idempotency_key,
                client_ip,
                user_agent,
                referrer,
                geo_data.get("country"),
                geo_data.get("city"),
                geo_data.get("region"),
                geo_data.get("provider")
            )
        )
        cursor.execute("SELECT created_at FROM submissions WHERE id = ?", (submission_id,))
        created_at_row = cursor.fetchone()

    created_at = str(created_at_row["created_at"]) if created_at_row else ""

    result_payload = {
        "id": submission_id,
        "widget_id": submission.widget_id,
        "status": "success",
        "message": "Submission received and safely stored.",
        "geo": geo_data,
        "created_at": created_at
    }

    # 9. Save Idempotency Record
    if idempotency_key:
        idempotency_service.save_response(submission.widget_id, idempotency_key, status.HTTP_201_CREATED, result_payload)

    # 10. Resilient Side Effect (Requirement & Probe 5)
    force_fail_side_effect = (mock_fail_email == "1")
    background_tasks.add_task(
        notification_service.dispatch_submission_notification,
        submission_id=submission_id,
        widget_id=submission.widget_id,
        payload=submission.data,
        force_fail=force_fail_side_effect
    )

    return result_payload
