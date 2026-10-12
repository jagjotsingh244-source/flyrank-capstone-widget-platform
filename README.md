# FlyRank Embeddable Widget & Lead-Capture Platform

> A resilient, multi-tenant platform for creating embeddable lead capture widgets, serving versioned scripts, and safely processing public web submissions with abuse prevention, geo-enrichment fallback, and non-blocking side effects.

## Capstone Overview

This project implements the backend and client embed system for FlyRank's Embeddable Widget & Lead-Capture Platform capstone.

### Architecture Highlights
- **Multi-Tenant Widget Management**: Authenticated CRUD API with strict tenant isolation.
- **Cached Embed Delivery**: Fast, versioned JS bundle distribution with proper `Cache-Control` headers.
- **Hardened Public Submission API**: Boundary validation, CORS preflight handling, payload-size limits, rate limiting (per IP and per widget), honeypot spam detection, and idempotency.
- **Graceful Geolocation Fallback Chain**: Primary provider (`ip-api.com`) falling back to secondary (`ipapi.co`), degrading safely without data loss.
- **Resilient Side Effects**: Non-blocking background notifications (email/webhook) where failures never abort visitor submissions.
- **Analytics & Owner Dashboard**: Real-time aggregated stats, geo breakdown, and recent submission inspection.

---
*Status: Initial project setup.*
