---
name: project-unreviewed-surface
description: EquityAlerts components flagged for security review but not yet shown in code
metadata:
  type: project
---

As of 2026-06-11, these surfaces were referenced/mounted but their code was NOT provided, so their controls are unverified.

**Why:** Prevents silent passes — these are the highest-value places to look next.

**How to apply:** Request/read this code in future sessions before declaring the platform reviewed.

- Inbound Meta WhatsApp webhook: cannot confirm X-Hub-Signature-256 HMAC, hub.verify_token check, or replay/dedup protection. Treat as absent.
- Scraper + LLM summarizer: prompt-injection delimiting, output schema/length validation, URL allowlist (SSRF), PDF parser hardening (size/timeout/zip-bomb) all unverified. Highest priority given untrusted scraped filings reach user summaries.
- Repositories not seen: subscriptionRepository, paymentRepository, companyRepository, userCompanyRepository, plan queries — verify parameterization and per-user scoping (IDOR).
- Route auth wiring: confirm authMiddleware is actually applied to payment/subscription/company/user routes in routes files (app.js mounts them but middleware application not shown).
- JWT_SECRET strength/presence not confirmed — weak/missing secret would be Critical (forgeable tokens).
- .env gitignore status and secrets-in-bundle not confirmed.
- Frontend render code (company names, user name, AI summaries) — check escaping and dangerouslySetInnerHTML.

Related: [[project-architecture]], [[project-security-controls]]
