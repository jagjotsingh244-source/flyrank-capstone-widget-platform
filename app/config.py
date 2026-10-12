import os
from pydantic import BaseModel

class Settings(BaseModel):
    # Core Server
    APP_NAME: str = "FlyRank Embeddable Widget Platform"
    APP_VERSION: str = "1.0.0"
    API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "widget_platform.db")

    # Security & Limits
    MAX_PAYLOAD_SIZE_BYTES: int = int(os.getenv("MAX_PAYLOAD_SIZE_BYTES", "65536"))  # 64 KB
    HONEYPOT_FIELD_NAME: str = os.getenv("HONEYPOT_FIELD_NAME", "_hp")
    
    # Rate Limiting
    # Configurable limits: burst limit per 10-second window per IP and per Widget
    RATE_LIMIT_IP_BURST: int = int(os.getenv("RATE_LIMIT_IP_BURST", "10"))
    RATE_LIMIT_IP_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_IP_WINDOW_SECONDS", "10"))
    RATE_LIMIT_WIDGET_BURST: int = int(os.getenv("RATE_LIMIT_WIDGET_BURST", "30"))
    RATE_LIMIT_WIDGET_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WIDGET_WINDOW_SECONDS", "10"))

    # Geolocation Providers
    GEO_PROVIDER_A_NAME: str = "ip-api.com"
    GEO_PROVIDER_B_NAME: str = "ipapi.co"
    GEO_TIMEOUT_SECONDS: float = float(os.getenv("GEO_TIMEOUT_SECONDS", "3.0"))
    GEO_MOCK_MODE: bool = os.getenv("GEO_MOCK_MODE", "true").lower() in ("true", "1", "yes")

    # Test & Chaos toggles for Acceptance Probes 4 & 5
    GEO_FORCE_FAIL_A: bool = os.getenv("GEO_FORCE_FAIL_A", "false").lower() in ("true", "1", "yes")
    GEO_FORCE_FAIL_B: bool = os.getenv("GEO_FORCE_FAIL_B", "false").lower() in ("true", "1", "yes")
    EMAIL_FORCE_FAIL: bool = os.getenv("EMAIL_FORCE_FAIL", "false").lower() in ("true", "1", "yes")

    # Side effect notification settings
    NOTIFICATION_WEBHOOK_URL: str = os.getenv("NOTIFICATION_WEBHOOK_URL", "")
    ALERT_ON_BACKGROUND_FAILURE: bool = True

settings = Settings()
