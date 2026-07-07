---
name: project-security-controls
description: Confirmed-present vs assumed-absent security controls and recurring weaknesses in EquityAlerts backend
metadata:
  type: project
---

Snapshot from review on 2026-06-11 (code provided inline, not read from disk — re-verify against files).

**Why:** Avoids re-flagging fixed items and preserves which controls were confirmed so future reviews don't assume regressions silently.

**How to apply:** Re-check each item against current code before relying on it; controls may have changed.

Confirmed PRESENT (good):
- OTP hashed with bcrypt before storage; 5-min TTL; single-use on success (`otpService.js`).
- Parameterized SQL in `otpRepository.js`, `userRepository.js` (`$1/$2`).
- Razorpay signature IS verified (just non-constant-time).
- `helmet()` applied in `app.js`.
- Client error responses are generic (no stack traces leaked to client).

Confirmed / assumed ABSENT (flagged):
- No rate limiting on `/send-otp` or `/verify-otp` (`authRoutes.js`).
- OTP plaintext + phone logged via `console.log` in `authController.sendOtp` (~line 57).
- No per-OTP attempt counter/lockout.
- Payment `verifyPayment` lacks order-ownership check, idempotency, and server-side amount/status confirmation (IDOR + replay). Amount hardcoded to 119.
- Non-constant-time HMAC compare in `verifyPayment` (use timingSafeEqual).
- JWT expiresIn 30d, no server-side revocation; token in localStorage.
- Wide-open `cors()` with no origin allowlist.
- No phone-number format validation before WhatsApp send.
- OTP generated with `Math.random()` (not crypto-secure).
- `morgan("dev")` used regardless of env.

Related: [[project-architecture]], [[project-unreviewed-surface]]
