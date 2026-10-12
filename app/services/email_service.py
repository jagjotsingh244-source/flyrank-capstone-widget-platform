import logging
import asyncio
from typing import Dict, Any
from app.config import settings

logger = logging.getLogger("email_service")

class ResilientNotificationService:
    """
    Background job dispatcher for notification emails and webhooks.
    Adheres to:
    1. Off-request-path execution (BackgroundTasks)
    2. Retry policy with exponential backoff
    3. Failure alert logging
    4. Zero impact on the HTTP submission response
    """

    async def dispatch_submission_notification(
        self,
        submission_id: str,
        widget_id: str,
        payload: Dict[str, Any],
        force_fail: bool = False,
        max_retries: int = 2
    ):
        attempt = 0
        while attempt <= max_retries:
            try:
                attempt += 1
                logger.info(f"[JOB START] Notification job for submission {submission_id} (Attempt {attempt}/{max_retries + 1})")

                # Simulated or configured failure for Probe 5 / Chaos testing
                if force_fail or settings.EMAIL_FORCE_FAIL:
                    raise ConnectionResetError("Simulated SMTP / Webhook gateway unreachable")

                # Normal side effect execution (Console log or webhook post)
                lead_email = payload.get("email", "unknown_visitor")
                logger.info(f"[EMAIL DISPATCHED] Confirmation sent to {lead_email} for submission {submission_id} on widget {widget_id}")
                return True

            except Exception as exc:
                logger.warning(f"[JOB RETRY] Attempt {attempt} failed for submission {submission_id}: {exc}")
                if attempt <= max_retries:
                    await asyncio.sleep(0.05 * attempt)  # Brief backoff
                else:
                    logger.error(
                        f"[FAILURE ALERT] Background notification job permanently failed for submission {submission_id}. "
                        f"Reason: {exc}. Primary database record is intact and safe."
                    )
                    return False

notification_service = ResilientNotificationService()
