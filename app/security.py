from typing import Optional, Dict, Any
from fastapi import Header, HTTPException, status, Depends
from app.database import get_db

def get_current_tenant(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> Dict[str, Any]:
    """
    Extracts and authenticates tenant identity from either X-API-Key or Bearer token.
    Enforces tenant isolation by making the verified tenant context mandatory.
    """
    token = None
    if x_api_key:
        token = x_api_key.strip()
    elif authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        elif len(parts) == 1:
            token = parts[0]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Unauthorized", "message": "Missing API Key or Authorization header."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, api_key FROM tenants WHERE api_key = ?", (token,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "Unauthorized", "message": "Invalid API key."},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return {"id": row["id"], "name": row["name"], "api_key": row["api_key"]}
