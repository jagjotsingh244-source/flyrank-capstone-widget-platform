import time
from collections import defaultdict
from threading import Lock
from typing import Tuple
from app.config import settings

class SlidingWindowRateLimiter:
    """
    In-memory thread-safe sliding window rate limiter.
    Tracks timestamps per IP and per Widget to prevent burst abuse.
    """
    def __init__(self):
        self.lock = Lock()
        self.ip_hits = defaultdict(list)
        self.widget_hits = defaultdict(list)

    def check_rate_limit(self, ip: str, widget_id: str) -> Tuple[bool, str, int]:
        """
        Validates whether request from ip for widget_id is permitted.
        Returns: (is_allowed, error_reason, retry_after_seconds)
        """
        now = time.time()
        with self.lock:
            # 1. Check IP limit
            ip_window = settings.RATE_LIMIT_IP_WINDOW_SECONDS
            ip_limit = settings.RATE_LIMIT_IP_BURST
            # Clean old entries
            self.ip_hits[ip] = [t for t in self.ip_hits[ip] if now - t < ip_window]
            if len(self.ip_hits[ip]) >= ip_limit:
                earliest = self.ip_hits[ip][0]
                retry_after = max(1, int(ip_window - (now - earliest)))
                return False, f"Rate limit exceeded for IP. Maximum {ip_limit} requests per {ip_window}s.", retry_after

            # 2. Check Widget limit
            widget_window = settings.RATE_LIMIT_WIDGET_WINDOW_SECONDS
            widget_limit = settings.RATE_LIMIT_WIDGET_BURST
            self.widget_hits[widget_id] = [t for t in self.widget_hits[widget_id] if now - t < widget_window]
            if len(self.widget_hits[widget_id]) >= widget_limit:
                earliest = self.widget_hits[widget_id][0]
                retry_after = max(1, int(widget_window - (now - earliest)))
                return False, f"Rate limit exceeded for Widget {widget_id}. Maximum {widget_limit} requests per {widget_window}s.", retry_after

            # Record hit
            self.ip_hits[ip].append(now)
            self.widget_hits[widget_id].append(now)
            return True, "", 0

    def reset(self):
        """Resets all in-memory buckets (useful for deterministic testing)."""
        with self.lock:
            self.ip_hits.clear()
            self.widget_hits.clear()

limiter = SlidingWindowRateLimiter()
