# ============================================================
#  config.py  —  Fill these before running the bot
# ============================================================

import os

# ── Step 1: Meta / WhatsApp Cloud API ────────────────────────
# Get from: developers.facebook.com → Your App → WhatsApp → API Setup
WHATSAPP_TOKEN   = os.environ.get("WHATSAPP_TOKEN", "")   # Set via environment — never hardcode (it leaks in git)
PHONE_NUMBER_ID  = os.environ.get("PHONE_NUMBER_ID", "1094754613731490")          # Looks like: 123456789012345
VERIFY_TOKEN     = os.environ.get("VERIFY_TOKEN", "nse_bot_secret_2024")           # Any string you choose (used once for webhook setup)

# ── Step 2: Your PostgreSQL DB (JS scraper's database) ───────
DB_HOST     = os.environ.get("DB_HOST", "localhost")
DB_PORT     = int(os.environ.get("DB_PORT", 5433))
DB_NAME     = os.environ.get("DB_NAME", "nse_ingestion")
DB_USER     = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")   # Set via environment — never hardcode

# ── Step 3: PostgreSQL table/column names — matched to real scraper schema ───────
# Table: announcements
# Real columns: id, company_symbol, title, pdf_url, local_path, announcement_time, download_status, is_notified
FILINGS_TABLE        = "announcements"
COL_ID               = "id"
COL_COMPANY_SYMBOL   = "company_symbol"
COL_COMPANY_NAME     = "company_symbol"   # no separate display name column — symbol used
COL_FILE_PATH        = "local_path"       # relative path e.g. storage/pdf/TCS_2024-01-01.pdf
COL_FILING_TYPE      = "title"            # announcement description
COL_CREATED_AT       = "announcement_time"
COL_IS_SENT          = "is_notified"      # bot sets TRUE after sending

# Absolute path to the Node.js scraper root so relative local_path can be resolved
SCRAPER_BASE_PATH    = os.environ.get("SCRAPER_BASE_PATH", r"d:\prathmesh\shares\nse-announcement-downloader v2")

# ── Step 4: Bot settings ─────────────────────────────────────
FLASK_PORT        = int(os.environ.get("FLASK_PORT", 5000))
FLASK_DEBUG       = os.environ.get("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")
ENABLE_DB_WATCHER = os.environ.get("ENABLE_DB_WATCHER", "True").lower() in ("true", "1", "yes")
POLL_INTERVAL_SEC = int(os.environ.get("POLL_INTERVAL_SEC", 30))    # Live dispatch: check for brand-new filings every 30s (time-critical path)

# How often the SLOW subscriber catch-up/backfill runs. This task is heavy
# (every subscriber × every company × latest PDFs) so it runs on its OWN thread,
# on a long interval, and must NEVER block the live dispatch above. Keeping it
# off the hot path is what makes new announcements go out within ~1 minute
# instead of being stuck behind a long backfill sweep.
BACKFILL_INTERVAL_SEC = int(os.environ.get("BACKFILL_INTERVAL_SEC", 600))   # 10 minutes

# Max seconds to wait for the LLM PDF summary subprocess. Kept short so a slow
# or hung summary can never delay PDF delivery past the "within a minute" goal —
# on timeout we fall back to the basic caption and still send the PDF instantly.
SUMMARY_TIMEOUT_SEC = int(os.environ.get("SUMMARY_TIMEOUT_SEC", 30))

# ── Step 5: WhatsApp Message Template (delivery OUTSIDE the 24h window) ──
# Meta only allows pushing a PDF to a user who has NOT messaged you in the last
# 24 hours via an APPROVED template that has a DOCUMENT header. This is what
# makes the bot deliver filings to silent subscribers.
#
# Setup (Meta WhatsApp Manager → Message Templates):
#   1. Create a template, category "Utility".
#   2. Header: type = Document.
#   3. Body: a single {{1}} variable — the bot fills it with the AI SUMMARY of
#      the filing, so silent subscribers get the summary + PDF in one message.
#      (e.g. body text: "{{1}}"  — or a short prefix followed by {{1}}.)
#   4. Submit for approval, then put the exact name + language code below.
#
# Leave TEMPLATE_NAME = "" to disable the fallback (filings will instead be
# queued and delivered the next time the user messages the bot).
TEMPLATE_NAME             = "nse_bot"        # e.g. "nse_filing_alert" (must be APPROVED)
TEMPLATE_LANG             = "en"      # must match the template's language code ("en", "en_US", ...)
TEMPLATE_BODY_PARAM_COUNT = 2         # text-only template body: {{1}} = summary, {{2}} = download link
# The old "Full Summary" quick-reply button has been retired — nobody tapped it,
# and the summary now arrives inline in the template body instead. Keep this
# False. (To remove the button visually too, delete it from the approved
# template in Meta WhatsApp Manager.)
TEMPLATE_SUMMARY_BUTTON = False

# Whether to cap template sends to ONE per closed 24h window. This used to be
# enforced to avoid "many templates at once", with the rest queued until the
# user re-engaged. But users weren't re-engaging (not tapping the reminder/
# "manage companies" link), so every filing after the first was never delivered.
# Set False to push EVERY announcement as its own utility template (summary +
# PDF) so silent subscribers actually receive all their filings.
ONE_TEMPLATE_PER_WINDOW   = os.environ.get("ONE_TEMPLATE_PER_WINDOW", "False").lower() in ("true", "1", "yes")

# ── Step 6: 24h-window pre-close re-engagement reminder ──────
# A single free-form message sent shortly BEFORE a user's 24-hour service
# window closes. Goals:
#   1. Nudge the user to tap/reply — an INBOUND message reopens the window, so
#      the next filings arrive as normal messages instead of stacking up as
#      separate template alerts (the "many templates at a time" complaint).
#   2. Surface the "manage companies" link (add/remove companies).
#   3. Carry a short PureFrameLabs promo.
#
# NOTE: an outbound message does NOT by itself reopen the window — only the
# user replying does. So this reduces template stacking only when the user
# interacts after seeing it.
ENABLE_WINDOW_REMINDER       = os.environ.get("ENABLE_WINDOW_REMINDER", "True").lower() in ("true", "1", "yes")
# Page where users add/remove the companies they track (portal /companies route).
MANAGE_COMPANIES_URL         = os.environ.get(
    "MANAGE_COMPANIES_URL",
    "https://equityalerts.in/portal/companies"
)
# Send the reminder this many hours BEFORE the 24h window closes (e.g. 1 -> at
# the 23h mark since the user's last inbound message).
WINDOW_REMINDER_BEFORE_HOURS = float(os.environ.get("WINDOW_REMINDER_BEFORE_HOURS", 1))
# How often the reminder loop scans for users whose window is about to close.
REMINDER_CHECK_INTERVAL_SEC  = int(os.environ.get("REMINDER_CHECK_INTERVAL_SEC", 300))   # 5 min
# PureFrameLabs contact number shown in the promo footer.
PUREFRAME_CONTACT            = os.environ.get("PUREFRAME_CONTACT", "8459625508")

# Brand URL shown in the "You are receiving this stock update…" + "Disclaimer:"
# footer of every Stock Bits alert. It is passed to the summary generator
# (output.py), which appends "/disclaimer" for the disclaimer link — so this
# value should be the portal root (no trailing slash).
BRAND_URL      = os.environ.get("BRAND_URL", "https://equityalerts.in/portal")
# PureFrameLabs website, shown as a small advertisement line under each alert.
PUREFRAME_SITE = os.environ.get("PUREFRAME_SITE", "https://pureframelabs.in/")

# ── Step 7: Delivery style ───────────────────────────────────
# SEND_AS_TEXT: deliver the EquiSense-style "Stock Bits" alert as a PLAIN TEXT
# message (with the 📎 NSE download link) and NO attachment. The long download
# URL widens the WhatsApp bubble to the full-width reference look. Meta only
# allows free-form text inside the 24-hour window, so filings for silent users
# (window closed) are queued and delivered the moment they next message the bot.
SEND_AS_TEXT   = os.environ.get("SEND_AS_TEXT", "True").lower() in ("true", "1", "yes")

# SEND_AS_CARD: (only used when SEND_AS_TEXT is False) render each filing into a
# WhatsApp-style dark-bubble card PDF and send THAT as the document instead of
# the raw NSE PDF. Off by default now that we deliver text + link.
SEND_AS_CARD   = os.environ.get("SEND_AS_CARD", "False").lower() in ("true", "1", "yes")
# Where generated card PDFs are cached (one per filing, reused across subscribers
# and across retries). Kept next to the bot so retries/flushes can find them.
CARD_CACHE_DIR = os.environ.get(
    "CARD_CACHE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_cards"),
)

# ── Companies users can subscribe to ─────────────────────────
# Key = NSE symbol, Value = display name shown in bot menu
COMPANY_LIST = {
    # ── Large Cap / Nifty 50 ──────────────────────────────────
    "HDFCBANK":   "HDFC Bank",
    "TCS":        "Tata Consultancy Services",
    "INFY":       "Infosys",
    "RELIANCE":   "Reliance Industries",
    "WIPRO":      "Wipro",
    "ICICIBANK":  "ICICI Bank",
    "SBIN":       "State Bank of India",
    "AXISBANK":   "Axis Bank",
    "KOTAKBANK":  "Kotak Mahindra Bank",
    "BAJFINANCE": "Bajaj Finance",
    "HINDUNILVR": "Hindustan Unilever",
    "ITC":        "ITC Limited",
    "LT":         "Larsen & Toubro",
    "TITAN":      "Titan Company",
    "MARUTI":     "Maruti Suzuki",
    "BHARTIARTL": "Bharti Airtel",
    "HCLTECH":    "HCL Technologies",
    "TECHM":      "Tech Mahindra",
    "SUNPHARMA":  "Sun Pharmaceutical",
    "TATAMOTORS": "Tata Motors",
    "TATASTEEL":  "Tata Steel",
    "JSWSTEEL":   "JSW Steel",
    "NTPC":       "NTPC Limited",
    "POWERGRID":  "Power Grid Corp",
    "ONGC":       "Oil & Natural Gas Corp",
    "COALINDIA":  "Coal India",
    "BAJAJFINSV": "Bajaj Finserv",
    "ADANIENT":   "Adani Enterprises",
    "ADANIPORTS": "Adani Ports",
    "ASIANPAINT": "Asian Paints",
    "NESTLEIND":  "Nestle India",
    "ULTRACEMCO": "UltraTech Cement",
    "GRASIM":     "Grasim Industries",
    "INDUSINDBK": "IndusInd Bank",
    "HDFCLIFE":   "HDFC Life Insurance",
    "SBILIFE":    "SBI Life Insurance",
    "CIPLA":      "Cipla",
    "DRREDDY":    "Dr. Reddy's Laboratories",
    "DIVISLAB":   "Divi's Laboratories",
    "EICHERMOT":  "Eicher Motors",
    "HEROMOTOCO": "Hero MotoCorp",
    "BRITANNIA":  "Britannia Industries",
    "APOLLOHOSP": "Apollo Hospitals",
    "TRENT":      "Trent Limited",
    "PIDILITIND": "Pidilite Industries",
    # ── Mid Cap ───────────────────────────────────────────────
    "BEL":        "Bharat Electronics",
    "HAL":        "Hindustan Aeronautics",
    "DABUR":      "Dabur India",
    "SIEMENS":    "Siemens India",
    "WOCKPHARMA": "Wockhardt Pharma",
}