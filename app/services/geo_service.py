import logging
from typing import Dict, Any, Optional
import httpx
from app.config import settings

logger = logging.getLogger("geo_service")

class GeoEnrichmentService:
    """
    Resilient IP Geolocation service using a deterministic fallback chain:
    Provider A (ip-api.com) -> Provider B (ipapi.co) -> Graceful degradation (None).
    """

    @staticmethod
    async def fetch_provider_a(ip: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
        if settings.GEO_FORCE_FAIL_A:
            raise RuntimeError("Provider A forced down via configuration")
        url = f"http://ip-api.com/json/{ip}"
        resp = await client.get(url, timeout=settings.GEO_TIMEOUT_SECONDS)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success" or "country" in data:
                return {
                    "country": data.get("country"),
                    "city": data.get("city"),
                    "region": data.get("regionName"),
                    "provider": settings.GEO_PROVIDER_A_NAME,
                    "status": "enriched"
                }
        raise RuntimeError(f"Provider A failed with HTTP {resp.status_code}")

    @staticmethod
    async def fetch_provider_b(ip: str, client: httpx.AsyncClient) -> Optional[Dict[str, Any]]:
        if settings.GEO_FORCE_FAIL_B:
            raise RuntimeError("Provider B forced down via configuration")
        url = f"https://ipapi.co/{ip}/json/"
        resp = await client.get(url, timeout=settings.GEO_TIMEOUT_SECONDS, headers={"User-Agent": "FlyRank-Capstone/1.0"})
        if resp.status_code == 200:
            data = resp.json()
            if not data.get("error") and data.get("country_name"):
                return {
                    "country": data.get("country_name"),
                    "city": data.get("city"),
                    "region": data.get("region"),
                    "provider": settings.GEO_PROVIDER_B_NAME,
                    "status": "enriched"
                }
        raise RuntimeError(f"Provider B failed with HTTP {resp.status_code}")

    async def enrich_ip(
        self,
        ip: str,
        force_fail_a: bool = False,
        force_fail_b: bool = False
    ) -> Dict[str, Any]:
        """
        Enriches IP with location data.
        Guarantees that no exception propagates: if all fail, returns degraded geo dict.
        """
        # Clean IP
        clean_ip = ip.strip() if ip else "127.0.0.1"
        is_mock = settings.GEO_MOCK_MODE or clean_ip in ("127.0.0.1", "localhost", "::1", "testclient") or clean_ip.startswith("203.0.113.")

        # Step 1: Provider A
        if not force_fail_a and not settings.GEO_FORCE_FAIL_A:
            try:
                if is_mock:
                    return {
                        "country": "United States",
                        "city": "Mountain View",
                        "region": "California",
                        "provider": settings.GEO_PROVIDER_A_NAME,
                        "status": "enriched"
                    }
                async with httpx.AsyncClient() as client:
                    result = await self.fetch_provider_a(clean_ip, client)
                    if result:
                        return result
            except Exception as e:
                logger.warning(f"Geo Provider A failed: {str(e)}. Proceeding to fallback Provider B.")

        # Step 2: Fallback to Provider B
        if not force_fail_b and not settings.GEO_FORCE_FAIL_B:
            try:
                if is_mock:
                    return {
                        "country": "United States",
                        "city": "Austin",
                        "region": "Texas",
                        "provider": settings.GEO_PROVIDER_B_NAME,
                        "status": "enriched"
                    }
                async with httpx.AsyncClient() as client:
                    result = await self.fetch_provider_b(clean_ip, client)
                    if result:
                        return result
            except Exception as e:
                logger.warning(f"Geo Provider B fallback failed: {str(e)}. All providers exhausted.")

        # Step 3: Graceful degradation — never fail the submission!
        logger.info("All geo providers unavailable; degrading safely to un-enriched submission.")
        return {
            "country": None,
            "city": None,
            "region": None,
            "provider": "none",
            "status": "degraded"
        }

geo_service = GeoEnrichmentService()
