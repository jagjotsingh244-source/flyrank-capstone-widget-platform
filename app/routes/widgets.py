import json
import uuid
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from app.config import settings
from app.database import get_db
from app.security import get_current_tenant
from app.models.schemas import WidgetCreate, WidgetUpdate, WidgetResponse, FormFieldSchema

router = APIRouter(prefix="/api/widgets", tags=["Widget Management"])

def generate_snippet(widget_id: str) -> str:
    return f'<script src="{settings.API_BASE_URL}/widget.js?id={widget_id}"></script>'

def row_to_widget_response(row: Dict[str, Any]) -> WidgetResponse:
    fields = [FormFieldSchema(**f) for f in json.loads(row["fields_schema"])]
    theme = json.loads(row["display_theme"])
    return WidgetResponse(
        id=row["id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        type=row["type"],
        title=row["title"],
        description=row["description"],
        fields_schema=fields,
        button_text=row["button_text"],
        display_theme=theme,
        is_active=bool(row["is_active"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        embed_snippet=generate_snippet(row["id"])
    )

@router.post("", response_model=WidgetResponse, status_code=status.HTTP_201_CREATED)
def create_widget(widget: WidgetCreate, tenant: Dict[str, Any] = Depends(get_current_tenant)):
    """
    Creates a new embeddable widget strictly isolated to the authenticated tenant.
    """
    widget_id = f"wgt_{uuid.uuid4().hex[:10]}"
    fields_json = json.dumps([f.model_dump() for f in widget.fields_schema])
    theme_json = json.dumps(widget.display_theme)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO widgets (id, tenant_id, name, type, title, description, fields_schema, button_text, display_theme, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                widget_id,
                tenant["id"],
                widget.name,
                widget.type,
                widget.title,
                widget.description,
                fields_json,
                widget.button_text,
                theme_json,
                1 if widget.is_active else 0
            )
        )
        cursor.execute("SELECT * FROM widgets WHERE id = ? AND tenant_id = ?", (widget_id, tenant["id"]))
        row = cursor.fetchone()

    return row_to_widget_response(row)

@router.get("", response_model=List[WidgetResponse])
def list_widgets(tenant: Dict[str, Any] = Depends(get_current_tenant)):
    """
    Lists all widgets owned by the authenticated tenant. Enforces strict tenant isolation.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM widgets WHERE tenant_id = ? ORDER BY created_at DESC", (tenant["id"],))
        rows = cursor.fetchall()

    return [row_to_widget_response(r) for r in rows]

@router.get("/{widget_id}", response_model=WidgetResponse)
def get_widget(widget_id: str, tenant: Dict[str, Any] = Depends(get_current_tenant)):
    """
    Retrieves a single widget by ID. Rejects requests trying to access other tenants' widgets.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM widgets WHERE id = ? AND tenant_id = ?", (widget_id, tenant["id"]))
        row = cursor.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Not Found", "message": f"Widget '{widget_id}' not found for authenticated tenant."}
        )

    return row_to_widget_response(row)

@router.put("/{widget_id}", response_model=WidgetResponse)
def update_widget(widget_id: str, updates: WidgetUpdate, tenant: Dict[str, Any] = Depends(get_current_tenant)):
    """
    Updates widget settings. Guarantees cross-tenant modifications are impossible.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM widgets WHERE id = ? AND tenant_id = ?", (widget_id, tenant["id"]))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Not Found", "message": f"Widget '{widget_id}' not found for authenticated tenant."}
            )

        name = updates.name if updates.name is not None else row["name"]
        w_type = updates.type if updates.type is not None else row["type"]
        title = updates.title if updates.title is not None else row["title"]
        desc = updates.description if updates.description is not None else row["description"]
        b_text = updates.button_text if updates.button_text is not None else row["button_text"]
        is_active = (1 if updates.is_active else 0) if updates.is_active is not None else row["is_active"]
        
        fields_json = row["fields_schema"]
        if updates.fields_schema is not None:
            fields_json = json.dumps([f.model_dump() for f in updates.fields_schema])
            
        theme_json = row["display_theme"]
        if updates.display_theme is not None:
            theme_json = json.dumps(updates.display_theme)

        cursor.execute(
            """
            UPDATE widgets
            SET name = ?, type = ?, title = ?, description = ?, fields_schema = ?,
                button_text = ?, display_theme = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND tenant_id = ?
            """,
            (name, w_type, title, desc, fields_json, b_text, theme_json, is_active, widget_id, tenant["id"])
        )

        cursor.execute("SELECT * FROM widgets WHERE id = ? AND tenant_id = ?", (widget_id, tenant["id"]))
        updated_row = cursor.fetchone()

    return row_to_widget_response(updated_row)

@router.delete("/{widget_id}", status_code=status.HTTP_200_OK)
def delete_widget(widget_id: str, tenant: Dict[str, Any] = Depends(get_current_tenant)):
    """
    Deletes a widget and cascading records belonging to the authenticated tenant.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM widgets WHERE id = ? AND tenant_id = ?", (widget_id, tenant["id"]))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Not Found", "message": f"Widget '{widget_id}' not found for authenticated tenant."}
            )
        cursor.execute("DELETE FROM widgets WHERE id = ? AND tenant_id = ?", (widget_id, tenant["id"]))

    return {"status": "success", "message": f"Widget '{widget_id}' deleted successfully."}
