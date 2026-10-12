import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError

from app.config import settings
from app.database import init_db
from app.routes.widgets import router as widgets_router
from app.routes.delivery import router as delivery_router
from app.routes.submissions import router as submissions_router
from app.routes.dashboard import router as dashboard_router

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("widget_platform")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB schema and indexes
    init_db()
    logger.info("Database schema and indexes initialized.")
    yield
    # Shutdown
    logger.info("Application shutting down.")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Resilient embeddable widget & lead capture backend platform.",
    lifespan=lifespan
)

# Global CORS middleware for cross-origin browser requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Retry-After", "Idempotency-Key", "Cache-Control"]
)

class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

# Mount static directory for widget client bundle with long-term immutable caching
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", CachedStaticFiles(directory=static_dir), name="static")

# Uniform Error Handling: Bad inputs must always return clean 4xx, never unhandled 500
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = errors[0].get("msg") if errors else "Invalid request data"
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Validation Error",
            "message": f"Malformed or invalid request: {msg}",
            "details": exc.errors()
        },
        headers={"Access-Control-Allow-Origin": "*"}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict):
        content = detail
    else:
        content = {"error": "HTTP Error", "message": str(detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=getattr(exc, "headers", None) or {"Access-Control-Allow-Origin": "*"}
    )

# Include API Routers
app.include_router(delivery_router)
app.include_router(submissions_router)
app.include_router(widgets_router)
app.include_router(dashboard_router)

@app.get("/", tags=["Health & Status"])
def root():
    return {
        "status": "online",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "endpoints": {
            "widget_script": "/widget.js?id={widget_id}",
            "widget_config": "/widgets/{widget_id}/config",
            "public_submission": "/submissions",
            "owner_dashboard_ui": "/dashboard",
            "owner_api": "/api/widgets",
            "owner_stats": "/api/dashboard/stats"
        }
    }

@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard UI"])
def get_dashboard_page():
    dashboard_path = os.path.join(os.path.dirname(__file__), "templates", "dashboard.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Dashboard template not found.</h1>", status_code=404)
