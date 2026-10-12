import json
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Query
from app.database import get_db
from app.security import get_current_tenant
from app.models.schemas import DashboardStats

router = APIRouter(prefix="/api/dashboard", tags=["Owner Dashboard"])

@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(tenant: Dict[str, Any] = Depends(get_current_tenant)):
    """
    Returns aggregated metrics and geo breakdown for the authenticated tenant.
    Enforces strict tenant scoping across all aggregations.
    """
    tenant_id = tenant["id"]

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Total Submissions
        cursor.execute("SELECT COUNT(*) AS total FROM submissions WHERE tenant_id = ?", (tenant_id,))
        total_submissions = cursor.fetchone()["total"]

        # 2. Total Widgets
        cursor.execute("SELECT COUNT(*) AS total FROM widgets WHERE tenant_id = ?", (tenant_id,))
        total_widgets = cursor.fetchone()["total"]

        # 3. Submissions by Widget
        cursor.execute(
            """
            SELECT w.id, w.name, w.title, COUNT(s.id) AS submission_count
            FROM widgets w
            LEFT JOIN submissions s ON w.id = s.widget_id AND s.tenant_id = ?
            WHERE w.tenant_id = ?
            GROUP BY w.id
            ORDER BY submission_count DESC
            """,
            (tenant_id, tenant_id)
        )
        submissions_by_widget = [
            {"widget_id": r["id"], "name": r["name"], "title": r["title"], "count": r["submission_count"]}
            for r in cursor.fetchall()
        ]

        # 4. Geo Breakdown
        cursor.execute(
            """
            SELECT COALESCE(country, 'Unknown') AS country, COUNT(*) AS count
            FROM submissions
            WHERE tenant_id = ?
            GROUP BY country
            ORDER BY count DESC
            """,
            (tenant_id,)
        )
        geo_breakdown = [{"country": r["country"], "count": r["count"]} for r in cursor.fetchall()]

        # 5. Recent Submissions
        cursor.execute(
            """
            SELECT s.id, s.widget_id, w.name AS widget_name, s.payload, s.country, s.city, s.geo_provider, s.created_at
            FROM submissions s
            JOIN widgets w ON s.widget_id = w.id
            WHERE s.tenant_id = ?
            ORDER BY s.created_at DESC
            LIMIT 10
            """,
            (tenant_id,)
        )
        recent_rows = cursor.fetchall()
        recent_submissions = [
            {
                "id": r["id"],
                "widget_id": r["widget_id"],
                "widget_name": r["widget_name"],
                "data": json.loads(r["payload"]),
                "country": r["country"],
                "city": r["city"],
                "geo_provider": r["geo_provider"],
                "created_at": str(r["created_at"])
            }
            for r in recent_rows
        ]

    return DashboardStats(
        total_submissions=total_submissions,
        total_widgets=total_widgets,
        submissions_by_widget=submissions_by_widget,
        geo_breakdown=geo_breakdown,
        recent_submissions=recent_submissions
    )

@router.get("/submissions")
def get_submissions_list(
    widget_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    tenant: Dict[str, Any] = Depends(get_current_tenant)
):
    """
    Returns paginated list of submissions for the authenticated tenant.
    """
    tenant_id = tenant["id"]
    query = "SELECT * FROM submissions WHERE tenant_id = ?"
    params = [tenant_id]

    if widget_id:
        query += " AND widget_id = ?"
        params.append(widget_id)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

    return [
        {
            "id": r["id"],
            "widget_id": r["widget_id"],
            "data": json.loads(r["payload"]),
            "ip_address": r["ip_address"],
            "country": r["country"],
            "city": r["city"],
            "region": r["region"],
            "geo_provider": r["geo_provider"],
            "idempotency_key": r["idempotency_key"],
            "created_at": str(r["created_at"])
        }
        for r in rows
    ]
