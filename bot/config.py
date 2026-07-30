# ============================================================
#  config.py  —  Fill these before running the bot
# ============================================================

import os

# ── Step 1: Meta / WhatsApp Cloud API ────────────────────────
# Get from: developers.facebook.com → Your App → WhatsApp → API Setup
WHATSAPP_TOKEN   = os.environ.get("WHATSAPP_TOKEN", "")   # Set via environment / Coolify — never hardcode (it leaks in git)
PHONE_NUMBER_ID  = os.environ.get("PHONE_NUMBER_ID", "1094754613731490")          # Looks like: 123456789012345
VERIFY_TOKEN     = os.environ.get("VERIFY_TOKEN", "nse_bot_secret_2024")           # Any string you choose (used once for webhook setup)

# ── Step 2: Your PostgreSQL DB (JS scraper's database) ───────
DB_HOST     = os.environ.get("DB_HOST", "localhost")
DB_PORT     = int(os.environ.get("DB_PORT", 5433))
DB_NAME     = os.environ.get("DB_NAME", "nse_ingestion")
DB_USER     = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")   # Set via environment / Coolify

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

# ── Admin API (Central Dashboard delivery-status endpoint) ───
# Shared secret the NSE backend presents on GET /admin/delivery-status
# (header: x-bot-admin-key). Must match BOT_ADMIN_KEY on the backend service.
# Generate with `openssl rand -hex 32`.
BOT_ADMIN_KEY = os.environ.get("BOT_ADMIN_KEY", "")

# ── Step 4: Bot settings ─────────────────────────────────────
FLASK_PORT        = int(os.environ.get("FLASK_PORT", 5000))
FLASK_DEBUG       = os.environ.get("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")
ENABLE_DB_WATCHER = os.environ.get("ENABLE_DB_WATCHER", "True").lower() in ("true", "1", "yes")
POLL_INTERVAL_SEC = int(os.environ.get("POLL_INTERVAL_SEC", 15))    # Live dispatch: check for brand-new filings every 15s (time-critical path)

# How often the SLOW subscriber catch-up/backfill runs. This task is heavy
# (every subscriber × every company × latest PDFs) so it runs on its OWN thread,
# on a long interval, and must NEVER block the live dispatch above. Keeping it
# off the hot path is what makes new announcements go out within ~1 minute
# instead of being stuck behind a long backfill sweep.
BACKFILL_INTERVAL_SEC = int(os.environ.get("BACKFILL_INTERVAL_SEC", 120))   # 2 min safety-net (live path handles the fast case)

# Max seconds to wait for ONE AI summary. The summary is generated in-process
# (no per-PDF subprocess cold start) and several at a time; this hard cap means
# a slow/hung LLM call can never push delivery past the "within a minute" goal —
# on timeout we send the PDF with the basic caption (company + exchange time +
# title) instead. Cost is not a concern, so this is generous.
#
# A RESULTS filing needs TWO calls to fit inside this one cap: the metrics
# extraction (output.RESULT_EXTRACT_TIMEOUT_SEC, 45s — it sends up to 80k chars
# of a 46-page filing) and, if that fails or finds nothing, the plain content
# summary (25s). At the old 35s the extraction alone consumed the whole budget
# on every large results PDF, so the fallback summary never ran and the filing
# went out with an EMPTY body. 45 + 25 = 70 has to FIT, hence 90.
SUMMARY_TIMEOUT_SEC = int(os.environ.get("SUMMARY_TIMEOUT_SEC", 90))

# How many AI summaries to generate concurrently. A burst of filings is built in
# parallel so later PDFs don't wait behind earlier summaries.
SUMMARY_WORKERS  = int(os.environ.get("SUMMARY_WORKERS", 6))

# LLM used for the AI summary (in-process via output.py / LangChain).
SUMMARY_PROVIDER = os.environ.get("SUMMARY_PROVIDER", "openai")
SUMMARY_MODEL    = os.environ.get("SUMMARY_MODEL", "gpt-4o-mini")

# ── OpenAI cost visibility (Central Dashboard) ───────────────
# A separate, more powerful "Admin API key" is required to read spend via
# OpenAI's Costs API — the regular OPENAI_API_KEY above (used for AI
# summaries) cannot query billing at all. Create one at
# platform.openai.com → Organization → Admin keys. Leave blank to disable;
# the dashboard's "OpenAI cost today" stat will just report unavailable.
OPENAI_ADMIN_API_KEY = os.environ.get("OPENAI_ADMIN_API_KEY", "")

# ── Step 5: WhatsApp Message Template (delivery OUTSIDE the 24h window) ──
# Meta only allows pushing a PDF to a user who has NOT messaged you in the last
# 24 hours via an APPROVED template that has a DOCUMENT header. This is what
# makes the bot deliver filings to silent subscribers.
#
# Setup (Meta WhatsApp Manager → Message Templates):
#   1. Create a template, category "Utility", with NO header (text-only).
#   2. Body — put the SPACING (blank lines) in the fixed text and use one
#      single-line variable per section, so Meta keeps the layout (it strips
#      newlines out of variables, so a single {{1}} summary becomes a wall of
#      text). Approved body should be (variables PLAIN — no emoji/branding
#      before them; the fixed text carries NO branded title):
#
#        {{1}}
#
#        {{2}}
#
#        {{3}}
#
#        {{4}}
#
#        🔗 Download filing:
#        {{5}}
#
#        You are receiving this stock update per your request on https://equityalerts.in/portal
#        Disclaimer: https://equityalerts.in/portal/disclaimer
#
#      {{1}}=title  ("📢 *PureFrame Stock/Result Bits!!*")
#      {{2}}=company  {{3}}=event(+filed time)  {{4}}=summary  {{5}}=download link.
#      The branded TITLE, the 🏢/⚡/🤖 emojis and the exchange time are all added
#      by the CODE into the variable VALUES (db_watcher._try_send), NOT the
#      template. Meta classifies on the fixed text only — so keeping the branded
#      "📢 …Bits!!" header out of the fixed text is what keeps this UTILITY. Do
#      not put the title/emojis in the fixed text or they'll show twice / flip
#      it back to Marketing.
#   3. Keep it UTILITY: no promo in the fixed text either. The PureFrame Labs ad
#      still rides on the free-form TEXT alert (output.py) inside the 24h window;
#      only this closed-window template omits it.
#   4. Submit for approval as "Utility", then set the exact name + language below.
#
# Leave TEMPLATE_NAME = "" to disable the fallback (filings will instead be
# queued and delivered the next time the user messages the bot).
TEMPLATE_NAME             = os.environ.get("TEMPLATE_NAME", "nse_bot")   # must be APPROVED
TEMPLATE_LANG             = os.environ.get("TEMPLATE_LANG", "en")   # template language code
TEMPLATE_BODY_PARAM_COUNT = 5         # {{1}}title {{2}}company {{3}}event+time {{4}}summary {{5}}link

# ── Dedicated template for quarterly/annual RESULTS filings ──────────────
# A metrics TABLE cannot render inside the Stock Bits template: every template
# variable must be a single line, so all the metrics collapse into one blob.
# A separate results template gives each metric its own line — and, since this
# rewrite, the full three-period breakdown (current qtr / prev qtr / year-ago)
# under each metric, matching the free-form text alert.
#
# APPROVED body in WhatsApp Manager (category Utility, NO header, NO footer):
#
#     📊 Quarterly results filed for a company in your subscription.
#
#     💼 {{1}}
#
#     🕒 Filed on exchange: {{2}}
#
#     Key metrics
#
#     Revenue (REV):
#     🗓️ {{3}}
#     🗓️ {{4}}
#     🗓️ {{5}}
#     Change: {{6}}
#
#     Profit After Tax (PAT):
#     🗓️ {{7}}
#     🗓️ {{8}}
#     🗓️ {{9}}
#     Change: {{10}}
#
#     Operating Profit Margin (OPM):
#     🗓️ {{11}}
#     🗓️ {{12}}
#     🗓️ {{13}}
#     Change: {{14}}
#
#     Filing and details: {{15}}
#
#     You are receiving this stock update per your request on https://equityalerts.in/portal
#     Disclaimer: https://equityalerts.in/portal/disclaimer
#
#   {{1}}="<company> | <period> Results Out"   {{2}}="<exchange time> IST"
#   {{3}}..{{5}}   = REV periods, "Jun 2026: ₹858.67 Cr" (the 🗓️ is fixed text)
#   {{6}}          = REV change,  "🟢 0.10% QoQ, 🚀 37.94% YoY"
#   {{7}}..{{10}}  = the same four for PAT     {{11}}..{{14}} = the same for OPM
#   {{15}}         = insights / download link.
# Empty positions are filled with "—" (Meta rejects an empty variable).
#
# WHY THE LAYOUT LOOKS LIKE THIS — two Meta constraints fought each other:
#   • "Too many variables for its length" — the ratio of variables to FIXED text
#     is checked, so the metric NAMES, the 🗓️/Change: labels and the opening
#     line all live in the fixed text. That is also why db_watcher has to map
#     whatever the extractor found onto exactly REV / PAT / OPM.
#   • Category = Marketing — Meta classifies on the fixed text ONLY, so the
#     branded "📢 *EquityAlerts Result Bits!!*" title and "🤖 Key Insights"
#     wording had to come OUT of it (an earlier draft carried the title as a
#     variable, but the body may not START with one). The branded header still
#     rides on the free-form text alert inside the 24h window; closed-window
#     template sends go out with the neutral opener above. Do NOT put the brand
#     name or "!!" back into the fixed text — it flips to Marketing.
#
# Defaults to the APPROVED "nse_result_bits" template so results use the
# metrics-table layout. Set to "" (via env) to fall back to TEMPLATE_NAME.
TEMPLATE_RESULT_NAME         = os.environ.get("TEMPLATE_RESULT_NAME", "nse_result_bits")
# Period rows per metric in the template above. Changing this needs a NEW
# approved template — the 🗓️ rows are fixed text, not something we can vary.
TEMPLATE_RESULT_PERIOD_SLOTS = int(os.environ.get("TEMPLATE_RESULT_PERIOD_SLOTS", 3))
# {{1}}company {{2}}filed {{3}}..{{14}} 3 metrics × (3 periods + change) {{15}}link
TEMPLATE_RESULT_PARAM_COUNT  = 15

# ── Per-metric-COUNT result templates (variable headings) ────────────────
# A WhatsApp template has no conditionals: every fixed line renders on every
# send. The template above hard-codes three headings, so a filing reporting
# only revenue still shows "Profit After Tax (PAT):" over three "—" rows,
# which looks broken to subscribers. The only fix is one approved template per
# block count, selected at send time.
#
# These also carry the metric HEADING as a variable, which the 3-block
# template above cannot afford (it spends its variable budget on the fixed
# headings). That means a filing reporting EBITDA or EPS shows them under
# their own name instead of being dropped for not being REV/PAT/OPM.
#
# Bodies to create in WhatsApp Manager — category Utility, NO header, NO
# footer. ONE-METRIC body (8 variables):
#
#     📊 Quarterly results filed for a company in your subscription.
#
#     💼 {{1}}
#
#     🕒 Filed on exchange: {{2}}
#
#     Key metrics
#
#     {{3}}
#     🗓️ {{4}}
#     🗓️ {{5}}
#     🗓️ {{6}}
#     Change: {{7}}
#
#     Figures as reported by the company in its exchange filing.
#
#     Filing and details: {{8}}
#
#     You are receiving this stock update per your request on https://equityalerts.in/portal
#     Disclaimer: https://equityalerts.in/portal/disclaimer
#
# TWO-METRIC body (13 variables): same, with a second block
#
#     {{8}}
#     🗓️ {{9}}
#     🗓️ {{10}}
#     🗓️ {{11}}
#     Change: {{12}}
#
# inserted after the first, and the link becoming {{13}}.
#
# THREE-METRIC body (18 variables): a third block, link = {{18}}.
#
#   {{1}}="<company> | <period> Results Out"   {{2}}="<exchange time> IST"
#   then per block: heading ("Revenue (REV):"), 3 period rows, change row.
#   Last variable is always the insights/download link.
#
# The "Figures as reported…" line is not decoration — Meta rejects a body with
# too many variables for its fixed-text length, and the 3-block one is close to
# that limit. If the 18-variable body is rejected anyway, leave
# TEMPLATE_RESULT_NAME_3 empty: 3-metric results then keep using the approved
# fixed-heading TEMPLATE_RESULT_NAME above (correct, since a 3-metric filing is
# almost always exactly REV/PAT/OPM), and only 1- and 2-metric results use the
# new layouts.
#
# Leave a name EMPTY until that template is APPROVED — the code falls back to
# the old behaviour for that count, so deploying this early is safe.
# _1 and _2 are APPROVED and live. _3 stays empty on purpose: 3-metric results
# use the already-approved fixed-heading TEMPLATE_RESULT_NAME above.
TEMPLATE_RESULT_NAME_1 = os.environ.get("TEMPLATE_RESULT_NAME_1", "nse_result_bits_1")
TEMPLATE_RESULT_NAME_2 = os.environ.get("TEMPLATE_RESULT_NAME_2", "nse_result_bits_2")
TEMPLATE_RESULT_NAME_3 = os.environ.get("TEMPLATE_RESULT_NAME_3", "")

# ── Approved template FIXED TEXT, keyed by template name ─────────────────
# The bodies above only ever existed as comments — nobody could see the
# literal message a template send would render without actually sending one
# to a real subscriber. This is the same fixed text, copied verbatim from
# what's approved in WhatsApp Manager, so bot/preview.py can substitute the
# {{n}} params db_watcher.resolve_template_send() computes and show the
# exact WhatsApp bubble before anything goes out. Keep these in sync with
# WhatsApp Manager by hand — Meta has no API to read a template body back.
TEMPLATE_BODIES = {
    TEMPLATE_NAME: (
        "{{1}}\n\n{{2}}\n\n{{3}}\n\n{{4}}\n\n"
        "🔗 Download filing:\n{{5}}\n\n"
        "You are receiving this stock update per your request on https://equityalerts.in/portal\n"
        "Disclaimer: https://equityalerts.in/portal/disclaimer"
    ),
    TEMPLATE_RESULT_NAME: (
        "📊 Quarterly results filed for a company in your subscription.\n\n"
        "💼 {{1}}\n\n"
        "🕒 Filed on exchange: {{2}}\n\n"
        "Key metrics\n\n"
        "Revenue (REV):\n🗓️ {{3}}\n🗓️ {{4}}\n🗓️ {{5}}\nChange: {{6}}\n\n"
        "Profit After Tax (PAT):\n🗓️ {{7}}\n🗓️ {{8}}\n🗓️ {{9}}\nChange: {{10}}\n\n"
        "Operating Profit Margin (OPM):\n🗓️ {{11}}\n🗓️ {{12}}\n🗓️ {{13}}\nChange: {{14}}\n\n"
        "Filing and details: {{15}}\n\n"
        "You are receiving this stock update per your request on https://equityalerts.in/portal\n"
        "Disclaimer: https://equityalerts.in/portal/disclaimer"
    ),
    TEMPLATE_RESULT_NAME_1: (
        "📊 Quarterly results filed for a company in your subscription.\n\n"
        "💼 {{1}}\n\n"
        "🕒 Filed on exchange: {{2}}\n\n"
        "Key metrics\n\n"
        "{{3}}\n🗓️ {{4}}\n🗓️ {{5}}\n🗓️ {{6}}\nChange: {{7}}\n\n"
        "Figures as reported by the company in its exchange filing.\n\n"
        "Filing and details: {{8}}\n\n"
        "You are receiving this stock update per your request on https://equityalerts.in/portal\n"
        "Disclaimer: https://equityalerts.in/portal/disclaimer"
    ),
    TEMPLATE_RESULT_NAME_2: (
        "📊 Quarterly results filed for a company in your subscription.\n\n"
        "💼 {{1}}\n\n"
        "🕒 Filed on exchange: {{2}}\n\n"
        "Key metrics\n\n"
        "{{3}}\n🗓️ {{4}}\n🗓️ {{5}}\n🗓️ {{6}}\nChange: {{7}}\n\n"
        "{{8}}\n🗓️ {{9}}\n🗓️ {{10}}\n🗓️ {{11}}\nChange: {{12}}\n\n"
        "Figures as reported by the company in its exchange filing.\n\n"
        "Filing and details: {{13}}\n\n"
        "You are receiving this stock update per your request on https://equityalerts.in/portal\n"
        "Disclaimer: https://equityalerts.in/portal/disclaimer"
    ),
    # Not yet approved (TEMPLATE_RESULT_NAME_3 is ""), but keeping the body
    # ready means the preview tool renders it correctly the day it is —
    # rather than someone having to remember to update this file too.
    "nse_result_bits_3": (
        "📊 Quarterly results filed for a company in your subscription.\n\n"
        "💼 {{1}}\n\n"
        "🕒 Filed on exchange: {{2}}\n\n"
        "Key metrics\n\n"
        "{{3}}\n🗓️ {{4}}\n🗓️ {{5}}\n🗓️ {{6}}\nChange: {{7}}\n\n"
        "{{8}}\n🗓️ {{9}}\n🗓️ {{10}}\n🗓️ {{11}}\nChange: {{12}}\n\n"
        "{{13}}\n🗓️ {{14}}\n🗓️ {{15}}\n🗓️ {{16}}\nChange: {{17}}\n\n"
        "Figures as reported by the company in its exchange filing.\n\n"
        "Filing and details: {{18}}\n\n"
        "You are receiving this stock update per your request on https://equityalerts.in/portal\n"
        "Disclaimer: https://equityalerts.in/portal/disclaimer"
    ),
}
# "" is not a real template name (it means "not configured") — drop any
# entry that collapsed onto that key so a lookup miss reliably means
# "no body known for this template", not garbage from an unset name.
TEMPLATE_BODIES.pop("", None)


def render_template_body(template_name: str, params: list) -> str | None:
    """
    Substitute `params` into the approved fixed text for `template_name`,
    exactly like Meta would render it. Returns None when the body isn't
    known (template not yet added to TEMPLATE_BODIES above) or the param
    count doesn't match what the body expects — callers should fall back to
    showing the raw params list rather than a silently wrong render.
    """
    body = TEMPLATE_BODIES.get(template_name or "")
    if body is None:
        return None
    expected = body.count("{{")
    if len(params) != expected:
        return None
    rendered = body
    for i, p in enumerate(params, start=1):
        rendered = rendered.replace("{{%d}}" % i, str(p))
    return rendered


def result_template_for(block_count: int) -> str:
    """The approved template name for a results alert with `block_count`
    metric blocks, or "" when none is configured for that count."""
    return {
        1: TEMPLATE_RESULT_NAME_1,
        2: TEMPLATE_RESULT_NAME_2,
        3: TEMPLATE_RESULT_NAME_3,
    }.get(block_count, "") or ""
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

# ── Delivery style ───────────────────────────────────────────
# SEND_AS_TEXT: INSIDE the 24-hour window, deliver the EquiSense-style "Stock
# Bits" alert as a PLAIN TEXT message (with the 📎 NSE download link) and NO
# attachment. The long download URL widens the WhatsApp bubble to the full-width
# reference look. OUTSIDE the window Meta requires a template, so silent users
# still receive the approved template + PDF document exactly as before.
# Set False to send the PDF/card as a document for everyone.
SEND_AS_TEXT   = os.environ.get("SEND_AS_TEXT", "True").lower() in ("true", "1", "yes")

# SEND_AS_CARD: (only used when SEND_AS_TEXT is False) render each filing into a
# WhatsApp-style card PDF and send THAT as the document instead of the raw NSE
# PDF. Off by default now that we deliver text + link.
SEND_AS_CARD   = os.environ.get("SEND_AS_CARD", "False").lower() in ("true", "1", "yes")

# Public base for branded short download links, e.g. https://equityalerts.in/t/<code>.
# Instead of the long raw nseindia.com URL, the alert shows a link under our own
# domain that 302-redirects to the real PDF (served by the bot's /t/<code> route,
# see Bot.py). Must be the public origin that reaches this bot. Empty = use the
# raw NSE URL (no shortening).
SHORTLINK_BASE = os.environ.get("SHORTLINK_BASE", "https://equityalerts.in").rstrip("/")

# ── Step 6: 24h-window pre-close re-engagement reminder ──────
# A single INTERACTIVE message sent shortly BEFORE a user's 24-hour service
# window closes. Goals:
#   1. Nudge the user to tap the reply button — an INBOUND message reopens the
#      window, so the next filings arrive as normal messages instead of stacking
#      up as separate template alerts (the "many templates at a time" complaint).
#   2. Surface the "manage companies" link (add/remove companies).
#   3. Carry a short PureFrameLabs promo.
# Works together with the one-template-per-closed-window cap in db_watcher so a
# user can never receive a stack of templates.
ENABLE_WINDOW_REMINDER       = os.environ.get("ENABLE_WINDOW_REMINDER", "True").lower() in ("true", "1", "yes")
# Page where users add/remove the companies they track (portal /companies route).
# Defaults off PORTAL_URL so it follows the deployed portal automatically.
MANAGE_COMPANIES_URL         = os.environ.get(
    "MANAGE_COMPANIES_URL",
    os.environ.get("PORTAL_URL", "https://equityalerts.in/portal").rstrip("/") + "/companies",
)
# Send the reminder this many hours BEFORE the 24h window closes (e.g. 1 -> at
# the 23h mark since the user's last inbound message).
WINDOW_REMINDER_BEFORE_HOURS = float(os.environ.get("WINDOW_REMINDER_BEFORE_HOURS", 1))
# How often the reminder loop scans for users whose window is about to close.
REMINDER_CHECK_INTERVAL_SEC  = int(os.environ.get("REMINDER_CHECK_INTERVAL_SEC", 300))   # 5 min
# PureFrameLabs contact number shown in the promo footer.
PUREFRAME_CONTACT            = os.environ.get("PUREFRAME_CONTACT", "8459625508")

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