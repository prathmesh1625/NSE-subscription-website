# NSE WhatsApp Bot — Problem Report & Files to Share with Claude

> Share this file + the files listed in each section when asking Claude for help.
> The project runs 4 services simultaneously via `start_all.bat`.

---

## 🗺️ Project Architecture Overview

```
d:\prathmesh\shares\
│
├── Bot.py                          ← Flask app (port 5000): WhatsApp webhook + PDF delivery
├── config.py                       ← All credentials & settings (WhatsApp, DB, template)
├── whatsapp.py                     ← Meta Cloud API wrapper (send text, send PDF, upload)
├── db_watcher.py                   ← Background thread: polls PG DB, sends PDFs to subscribers
├── database.py                     ← SQLite helper (sent_filings, pending_filings, wamid tracking)
├── start_all.bat                   ← Starts all 4 services in separate windows
│
├── nse-announcement-downloader v2\ ← Node.js scraper (port unknown, PostgreSQL: nse_ingestion)
│   └── server.js                   ← Scrapes NSE + BSE every 30s, downloads PDFs
│
└── nse-website\subscription-portal\
    ├── backend\                    ← Node.js API (port 3001, PostgreSQL: nse_subscription)
    │   ├── src\controllers\authController.js   ← OTP send + verify logic
    │   ├── src\services\otpService.js           ← OTP generate, hash, verify
    │   ├── src\utils\whatsappSender.js          ← Sends OTP via WhatsApp (Meta API)
    │   ├── src\repositories\userRepository.js  ← User DB queries
    │   └── .env                                 ← DB + WhatsApp + Razorpay credentials
    │
    └── frontend\                   ← React (Vite) portal, served by Flask from /portal
        ├── src\pages\Register\Register.jsx      ← Registration + OTP step
        ├── src\pages\OtpPage.jsx                ← Standalone OTP verify page
        ├── src\services\authApi.js              ← API calls (uses VITE_API_URL)
        └── .env                                 ← VITE_API_URL, VITE_RAZORPAY_KEY_ID
```

---

## 🚨 Current Problems

### Problem 1 — WhatsApp Bot Terminal Shows No Logs

**Symptom:** Sending "hi" or "help" on WhatsApp shows nothing in the terminal.

**Likely causes:**
- You are looking at the **wrong terminal window**. The bot logs appear in the CMD window titled **"WhatsApp Bot"** (opened by `start_all.bat`), NOT in the bat file's own window.
- The Meta webhook URL in your **Meta App Dashboard** may be pointing to a stale ngrok URL. It must be: `https://sensitive-fortyish-phung.ngrok-free.dev/webhook`
- The Flask bot on port 5000 may have crashed. Check the "WhatsApp Bot" window for error output.
- The ngrok tunnel may not be active — check the "ngrok Tunnel" window.

**How to verify:**
1. Open the "WhatsApp Bot" CMD window — look for the startup banner showing `📱 Phone Number ID`.
2. Open `https://sensitive-fortyish-phung.ngrok-free.dev/webhook` in a browser — it should show `{"status":"ok"}` or similar (not an ngrok warning page).
3. Go to [Meta App Dashboard](https://developers.facebook.com) → Your App → WhatsApp → Configuration → confirm Webhook URL and Verify Token match.

**Files to share with Claude:**
- `d:\prathmesh\shares\Bot.py`
- `d:\prathmesh\shares\config.py`
- `d:\prathmesh\shares\start_all.bat`

---

### Problem 2 — OTP Was Auto-Filled (DEV Mode) Instead of Sent to WhatsApp

**Symptom:** When registering on the portal, the OTP field gets auto-filled from the API response. The user never receives anything on WhatsApp.

**Root cause (now fixed):**
- `authController.js` had a dev-mode that returned `dev_otp` in the JSON response when `MSG91_AUTH_KEY` was empty.
- `Register.jsx` read `result.dev_otp` and auto-filled it into the OTP input.
- `authApi.js` had the base URL hardcoded to `http://localhost:5000/api` instead of using `VITE_API_URL`.

**Fix applied:**
- Created `backend/src/utils/whatsappSender.js` — sends WhatsApp text via Meta Cloud API.
- `authController.js` now calls `sendWhatsAppText()` with the OTP message.
- `Register.jsx` no longer reads or auto-fills `dev_otp`.
- `authApi.js` now uses `import.meta.env.VITE_API_URL`.
- Frontend rebuilt with `npm run build`.

**If OTP still not arriving on WhatsApp, check:**
1. Is the recipient's number added as a **test number** in Meta App Dashboard → WhatsApp → API Setup → "To" field? (Required while app is in Development mode)
2. Check "NSE Website Backend" terminal for: `✅ OTP sent to <phone> via WhatsApp` or `❌ WhatsApp OTP send failed`.
3. Is `WHATSAPP_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` set in `backend/.env`?

**Files to share with Claude:**
- `d:\prathmesh\shares\nse-website\subscription-portal\backend\.env`
- `d:\prathmesh\shares\nse-website\subscription-portal\backend\src\controllers\authController.js`
- `d:\prathmesh\shares\nse-website\subscription-portal\backend\src\utils\whatsappSender.js`
- `d:\prathmesh\shares\nse-website\subscription-portal\backend\src\services\otpService.js`
- `d:\prathmesh\shares\nse-website\subscription-portal\frontend\src\pages\Register\Register.jsx`
- `d:\prathmesh\shares\nse-website\subscription-portal\frontend\src\services\authApi.js`
- `d:\prathmesh\shares\nse-website\subscription-portal\frontend\.env`

---

### Problem 3 — PDFs Not Being Sent to WhatsApp After Subscription

**Symptom:** PDF filings are downloaded by the scraper but users don't receive them on WhatsApp.

**How the flow works:**
1. Scraper (`nse-announcement-downloader v2/server.js`) downloads PDFs → stores in `nse_ingestion` PostgreSQL DB with `is_notified = FALSE`.
2. `db_watcher.py` polls `nse_ingestion` every 60s, finds `is_notified = FALSE` rows.
3. For each filing, it queries `nse_subscription` DB to find subscribers for that company symbol.
4. Sends PDF via `whatsapp.send_pdf()` → marks `is_notified = TRUE` in PG + `sent_filings` in SQLite.

**Common failure points:**
- **Error 131047** (24-hour window closed): User hasn't messaged the bot recently. Bot queues filing in `pending_filings` and retries via approved template `nse_bot`.
- **Error 131026** (unverified number): Number not added as test number in Meta Dashboard (Dev mode only).
- **Template not approved**: Check `config.py` → `TEMPLATE_NAME = "nse_bot"` must match an APPROVED template in Meta WhatsApp Manager.
- **Phone number format mismatch**: Subscribers stored as `9876543210` (10 digits) but bot sends to `919876543210` (12 digits with country code).

**Files to share with Claude:**
- `d:\prathmesh\shares\db_watcher.py`
- `d:\prathmesh\shares\Bot.py`
- `d:\prathmesh\shares\whatsapp.py`
- `d:\prathmesh\shares\database.py`
- `d:\prathmesh\shares\config.py`

---

## 📁 Master File List — Share ALL of These for Full Context

### Python Bot (WhatsApp delivery engine)
| File | Purpose |
|------|---------|
| `d:\prathmesh\shares\Bot.py` | Flask webhook, message handler, portal server |
| `d:\prathmesh\shares\config.py` | All credentials & settings |
| `d:\prathmesh\shares\whatsapp.py` | Meta API wrapper — send text/PDF |
| `d:\prathmesh\shares\db_watcher.py` | Polling loop, PDF dispatch, backfill |
| `d:\prathmesh\shares\database.py` | SQLite: sent_filings, pending_filings, wamid |
| `d:\prathmesh\shares\start_all.bat` | Service orchestrator |

### Node.js Website Backend (OTP, auth, subscriptions)
| File | Purpose |
|------|---------|
| `backend\.env` | DB + WhatsApp + Razorpay credentials |
| `backend\src\controllers\authController.js` | OTP send + verify endpoint |
| `backend\src\services\otpService.js` | OTP create/verify logic |
| `backend\src\utils\whatsappSender.js` | Sends OTP via WhatsApp |
| `backend\src\utils\otpGenerator.js` | Generates 6-digit OTP |
| `backend\src\repositories\userRepository.js` | User DB queries |
| `backend\src\repositories\otpRepository.js` | OTP DB queries |
| `backend\src\routes\authRoutes.js` | Auth route definitions |
| `backend\src\app.js` | Express app setup |
| `backend\src\server.js` | Server entry point |

### React Frontend (Portal UI)
| File | Purpose |
|------|---------|
| `frontend\.env` | `VITE_API_URL` + Razorpay key |
| `frontend\src\services\authApi.js` | API calls for OTP |
| `frontend\src\pages\Register\Register.jsx` | Registration + OTP step |
| `frontend\src\pages\OtpPage.jsx` | Standalone OTP verify |

### Database Migrations
| File | Purpose |
|------|---------|
| `database\migrations\001_create_users.sql` | users table |
| `database\migrations\003_create_subscriptions.sql` | subscriptions table |
| `database\migrations\005_create_companies.sql` | companies table |
| `database\migrations\006_create_user_companies.sql` | user_companies table |
| `database\migrations\007_create_otp_verifications.sql` | otp_verifications table |

---

## ⚙️ Key Config Values (for quick reference)

```
WhatsApp Phone Number ID : 1094754613731490
Verify Token             : nse_bot_secret_2024
Template Name            : nse_bot
Template Language        : en
ngrok Domain             : sensitive-fortyish-phung.ngrok-free.dev
Flask Port               : 5000
Backend Port             : 3001
Scraper DB               : localhost:5433 / nse_ingestion
Subscription DB          : localhost:5433 / nse_subscription
Scraper Base Path        : d:\prathmesh\shares\nse-announcement-downloader v2
```

---

## 🔄 How to Restart Services

```bat
REM Restart everything
d:\prathmesh\shares\start_all.bat

REM Rebuild frontend only (after code changes)
cd d:\prathmesh\shares\nse-website\subscription-portal\frontend
npm run build
```

After rebuilding frontend, the new `dist/` is automatically served by the Flask bot at `/portal`.
