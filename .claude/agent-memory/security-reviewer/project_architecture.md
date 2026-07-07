---
name: project-architecture
description: EquityAlerts fintech WhatsApp notification platform — stack, auth model, payment provider
metadata:
  type: project
---

EquityAlerts is a fintech subscription portal: NSE/BSE filings are scraped, summarized by an LLM, and delivered to subscribers via Meta WhatsApp Cloud API. Premium subscription is paid (~INR 119/month via Razorpay).

**Why:** Threat model centers on (1) prompt injection from untrusted scraped filings flowing into user-facing summaries, (2) WhatsApp toll-fraud/OTP abuse, (3) payment-grant integrity.

**How to apply:** Treat scraped content and inbound WhatsApp webhook payloads as untrusted. The reviewed backend is Node.js/Express (not the Python/Flask described in the generic brief) — confirm stack per file before assuming framework.

Stack observed in reviewed code:
- Backend: Node.js + Express (`backend/src/`), layered controllers/services/repositories.
- DB: PostgreSQL (parameterized `$1` placeholders via `db.query`).
- Auth: WhatsApp OTP -> JWT (jsonwebtoken). Token stored in frontend localStorage.
- Payments: Razorpay (HMAC-SHA256 signature over `order_id|payment_id`).
- WhatsApp: Meta Graph API v19.0 via `backend/src/utils/whatsappSender.js`.
- Frontend: React SPA, AuthContext + axios interceptor.

Related: [[project-security-controls]], [[project-unreviewed-surface]]
