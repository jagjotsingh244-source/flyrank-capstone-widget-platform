import os
import json
from typing import Optional
from fastapi import APIRouter, Response, HTTPException, status, Query
from app.config import settings
from app.database import get_db
from app.models.schemas import PublicWidgetConfig, FormFieldSchema

router = APIRouter(tags=["Widget Delivery"])

WIDGET_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "widget.v1.js")

@router.get("/widget.js")
def get_loader_script(id: Optional[str] = Query(None)):
    """
    Public loader script endpoint.
    Returns the versioned JavaScript client with CORS and caching headers.
    """
    if not os.path.exists(WIDGET_SCRIPT_PATH):
        raise HTTPException(status_code=404, detail="Widget script bundle not found.")

    with open(WIDGET_SCRIPT_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Pre-inject target widget ID if passed directly in the query param
    if id:
        content = f"window.__FLYRANK_DEFAULT_WIDGET_ID__ = '{id}';\n" + content

    return Response(
        content=content,
        media_type="application/javascript; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=300, stale-while-revalidate=86400",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS"
        }
    )

@router.get("/static/widget.v1.js")
def get_versioned_script():
    """
    Direct versioned immutable bundle delivery.
    Cached long term as required by CDN best practices (Cache-Control: public, max-age=31536000, immutable).
    """
    if not os.path.exists(WIDGET_SCRIPT_PATH):
        raise HTTPException(status_code=404, detail="Widget bundle not found.")

    with open(WIDGET_SCRIPT_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    return Response(
        content=content,
        media_type="application/javascript; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS"
        }
    )

@router.get("/widgets/{widget_id}/config", response_model=PublicWidgetConfig)
def get_widget_config(widget_id: str, response: Response):
    """
    Public widget config endpoint.
    Serves a lightweight configuration payload with short-lived cache headers (max-age=60).
    Allows cross-origin access from any third-party customer site.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM widgets WHERE id = ? AND is_active = 1", (widget_id,))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Not Found", "message": f"Active widget '{widget_id}' not found."}
        )

    fields = [FormFieldSchema(**f) for f in json.loads(row["fields_schema"])]
    theme = json.loads(row["display_theme"])

    # Required cache headers
    response.headers["Cache-Control"] = "public, max-age=60"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"

    return PublicWidgetConfig(
        id=row["id"],
        type=row["type"],
        title=row["title"],
        description=row["description"],
        fields=fields,
        button_text=row["button_text"],
        display_theme=theme,
        submission_url=f"{settings.API_BASE_URL}/submissions"
    )
