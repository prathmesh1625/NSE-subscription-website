# ============================================================
#  db_watcher.py  —  Poll your JS scraper's PostgreSQL DB
#                    and push new filings to WhatsApp subscribers
#
#  FIX: a filing is marked sent (SQLite) / notified (PG) ONLY after
#  whatsapp.send_pdf() confirms success. A failure caused by the
#  closed 24-hour window (131047) parks the filing in the
#  pending_filings retry queue instead of dropping it.
# ============================================================
import os
import re
import sys
import time
import hashlib
import threading
import psycopg2
import psycopg2.extras
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import config
import database as bot_db
import whatsapp
from whatsapp import WhatsAppError

try:
    import message_card
except Exception as _mc_err:      # Pillow missing, etc. — degrade to raw PDFs.
    message_card = None
    print(f"⚠️  message_card unavailable ({_mc_err}); will send raw filing PDFs.")


def get_pg_conn():
    """Connect to the JS scraper's PostgreSQL database."""
    return psycopg2.connect(
        host     = config.DB_HOST,
        port     = config.DB_PORT,
        dbname   = config.DB_NAME,
        user     = config.DB_USER,
        password = config.DB_PASSWORD,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def ensure_schema():
    try:
        conn = get_pg_conn()
        cur  = conn.cursor()
        cur.execute("""
            ALTER TABLE announcements
            ADD COLUMN IF NOT EXISTS is_notified BOOLEAN DEFAULT FALSE
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ announcements.is_notified column ready.")
    except Exception as e:
        print(f"❌ Schema migration error: {e}")


def _dedup_by_filename(rows):
    """Keep only the first row per unique PDF filename."""
    seen   = []
    unique = []
    for row in rows:
        if not isinstance(row, dict):
            keys = ("id", "title", "local_path", "announcement_time")
            row  = dict(zip(keys, row))
        key = os.path.basename((row.get("local_path") or "").strip())
        if not key or key in seen:
            continue
        seen.append(key)
        unique.append(row)
    return unique


def fetch_new_filings():
    try:
        conn = get_pg_conn()
        cur  = conn.cursor()
        query = f"""
            SELECT
                {config.COL_ID}             AS filing_id,
                {config.COL_COMPANY_SYMBOL} AS symbol,
                {config.COL_COMPANY_NAME}   AS company_name,
                {config.COL_FILE_PATH}      AS file_path,
                {config.COL_FILING_TYPE}    AS filing_type,
                pdf_url                     AS pdf_url,
                {config.COL_CREATED_AT}     AS created_at,
                EXTRACT(EPOCH FROM (NOW() - created_at))::int AS age_seconds
            FROM {config.FILINGS_TABLE}
            WHERE {config.COL_IS_SENT} = FALSE
              AND download_status = 'DOWNLOADED'
            ORDER BY {config.COL_CREATED_AT} ASC
        """
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        resolved = []
        for row in rows:
            row = dict(row)
            rel = row.get("file_path") or ""
            row["file_path"] = os.path.join(config.SCRAPER_BASE_PATH, rel.strip())
            resolved.append(row)
        return resolved

    except Exception as e:
        print(f"❌ PostgreSQL error while fetching filings: {e}")
        return []


def mark_notified_in_pg(filing_id):
    try:
        conn = get_pg_conn()
        cur  = conn.cursor()
        cur.execute(
            f"UPDATE {config.FILINGS_TABLE} SET {config.COL_IS_SENT} = TRUE WHERE {config.COL_ID} = %s",
            (filing_id,)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ Could not mark filing {filing_id} as notified: {e}")


def unmark_notified_in_pg(filing_id):
    """Reset is_notified to FALSE so a failed delivery gets retried on the next poll."""
    try:
        conn = get_pg_conn()
        cur  = conn.cursor()
        cur.execute(
            f"UPDATE {config.FILINGS_TABLE} SET {config.COL_IS_SENT} = FALSE WHERE {config.COL_ID} = %s",
            (filing_id,)
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"↩️  Unmarked PG filing {filing_id} as notified (will retry).")
    except Exception as e:
        print(f"❌ Could not unmark filing {filing_id}: {e}")


def get_subscribers_for_symbol_pg(symbol: str) -> list:
    """Get active subscribers from the website's PostgreSQL database 'nse_subscription'."""
    try:
        conn = psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            dbname="nse_subscription",
            user=config.DB_USER,
            password=config.DB_PASSWORD
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT u.mobile
            FROM user_companies uc
            JOIN users u ON u.id = uc.user_id
            JOIN companies c ON c.id = uc.company_id
            JOIN subscriptions s ON s.user_id = u.id
            WHERE UPPER(c.symbol) = UPPER(%s) AND s.status = 'ACTIVE';
        """, (symbol,))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        phones = []
        for r in rows:
            p = r[0].strip()
            if len(p) == 10 and p.isdigit():
                p = "91" + p
            phones.append(p)
        return phones
    except Exception as e:
        # Return None (NOT []) so the caller can tell a transient lookup FAILURE
        # apart from a genuine "nobody is subscribed". Treating a failed lookup
        # as "no subscribers" used to mark the filing notified and drop it to the
        # slow 10-min backfill — the cause of occasional very-late deliveries.
        print(f"❌ Error fetching PG subscribers for {symbol}: {e}")
        return None


_company_name_cache = {}


def get_company_display_name(symbol: str) -> str:
    """
    Resolve a human company NAME for a symbol (e.g. TATAPOWER -> Tata Power),
    so messages never say "Unknown Company". Prefers the curated short name in
    config.COMPANY_LIST, then the full name from the portal's companies table,
    then the symbol itself. Cached — names don't change.
    """
    symbol = (symbol or "").upper().strip()
    if not symbol:
        return "Unknown Company"
    if symbol in config.COMPANY_LIST:
        return config.COMPANY_LIST[symbol]
    if symbol in _company_name_cache:
        return _company_name_cache[symbol]

    name = symbol
    try:
        conn = psycopg2.connect(
            host=config.DB_HOST, port=config.DB_PORT,
            dbname="nse_subscription",
            user=config.DB_USER, password=config.DB_PASSWORD,
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT company_name FROM companies WHERE UPPER(symbol)=UPPER(%s) LIMIT 1",
            (symbol,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0] and row[0].strip():
            name = row[0].strip()
    except Exception as e:
        print(f"⚠️  Company-name lookup failed for {symbol}: {e}")

    _company_name_cache[symbol] = name
    return name


# ── In-process AI summary engine ─────────────────────────────────────────────
# output.py sits next to this file and its deps (LangChain, pdfplumber, ...) are
# in the bot image. We import it ONCE and call process_pdf() in-process instead
# of spawning a fresh Python per PDF — the old subprocess paid ~10s of
# Python+LangChain startup on EVERY filing, which was the single biggest reason
# summaries were slow. In-process + parallel (see _caption_pool) lets the
# summary stay inside the one PDF caption and still land within ~1 minute.

_output_mod = None
_output_import_lock = threading.Lock()
_output_import_failed = False


def _get_output_module():
    """Import bot/output.py once (lazily) and cache the module (or the failure)."""
    global _output_mod, _output_import_failed
    if _output_mod is not None:
        return _output_mod
    if _output_import_failed:
        return None
    with _output_import_lock:
        if _output_mod is not None:
            return _output_mod
        if _output_import_failed:
            return None
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            if here not in sys.path:
                sys.path.insert(0, here)
            import output as _out          # heavy import (LangChain) — paid once
            _output_mod = _out
            print("🤖 AI summary engine loaded (in-process).")
            return _out
        except Exception as e:
            print(f"⚠️ Could not load output.py in-process ({e}); summaries disabled.")
            _output_import_failed = True
            return None


def warm_up_summary_engine():
    """Pre-import the engine at startup so the first real filing isn't slowed."""
    try:
        _get_output_module()
    except Exception:
        pass


def _run_summary(file_path: str, company: str | None = None,
                 filing_type: str = "", download_url: str = ""):
    out = _get_output_module()
    if out is None:
        return None
    msg = out.process_pdf(
        file_path,
        provider=getattr(config, "SUMMARY_PROVIDER", "openai"),
        model=getattr(config, "SUMMARY_MODEL", "gpt-4o-mini"),
        company_hint=company,
        filing_type=filing_type,
        download_url=download_url,
    )
    if not msg:
        return None
    msg = msg.strip()
    # New EquiSense format opens with "📢 *PureFrame Stock Bits!!*"; strip any
    # leading log noise by starting at the first megaphone.
    marker = msg.find("📢")
    if marker != -1:
        return msg[marker:]
    return msg or None


def generate_pdf_summary(file_path: str, company: str | None = None,
                         filing_type: str = "", download_url: str = "") -> str | None:
    """
    Generate the AI summary for one PDF, in-process, with a HARD timeout so a
    slow/hung LLM call can never stall delivery. Returns None on any failure
    (caller then sends the basic caption). Safe to run from several threads at
    once (the caption pool does exactly that). `company` is used as the display
    name when the PDF text doesn't state it (avoids "Unknown Company").
    `filing_type` feeds the ⚡ event line and `download_url` the 📎 link.
    """
    print(f"🤖 Generating AI summary for {os.path.basename(file_path)}...")
    box = {}

    def _worker():
        try:
            box["value"] = _run_summary(file_path, company, filing_type, download_url)
        except Exception as e:
            box["error"] = e

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(getattr(config, "SUMMARY_TIMEOUT_SEC", 35))

    if t.is_alive():
        print(f"⏱️  Summary timed out for {os.path.basename(file_path)} — sending basic caption.")
        return None
    if "error" in box:
        print(f"❌ Summary failed for {os.path.basename(file_path)}: {box['error']}")
        return None
    return box.get("value")


def _format_exchange_time(raw) -> str:
    """Format the NSE/BSE announcement timestamp for display in the message."""
    if not raw:
        return "time not available"
    s = str(raw).strip().replace("T", " ")
    # Drop fractional seconds / timezone noise (e.g. "2026-06-14 09:01:23.000").
    if "." in s:
        s = s.split(".")[0]
    return f"{s} IST"


# Bump this whenever the generated message LAYOUT changes (output.py). Cached
# summaries tagged with an older version are regenerated instead of re-sent, so
# a format change actually takes effect on filings summarised before the deploy.
#   1 = legacy Stock-Bits-only layout
#   2 = Stock Bits + structured Result Bits (metrics table)
SUMMARY_FORMAT_VERSION = 2


def _compact_metric_lines(caption: str, slots: int = 3) -> list:
    """
    Turn the Result Bits metrics table into ONE COMPACT LINE PER METRIC, for the
    dedicated results template (each template variable must be a single line, so
    the 3-period breakdown can't survive there — the free-form text alert keeps
    the full table).

        "Revenue from operations (REV): ₹72,275 Cr · 🟢 +2.03% QoQ, 🟢 +13.00% YoY"

    Always returns exactly `slots` non-empty strings: unused slots become "—"
    (Meta rejects an empty variable) and any metrics beyond `slots` are merged
    into the last line.
    """
    m = re.search(r"📊 Key Metrics\s*(.+?)(?:\n\s*🤖|\n\s*You are receiving|$)",
                  caption or "", re.DOTALL)
    lines = []
    if m:
        for chunk in re.split(r"\n\s*\n", m.group(1).strip()):
            rows = [r.strip() for r in chunk.split("\n") if r.strip()]
            if not rows:
                continue
            name, latest, trend = rows[0].rstrip(":"), "", ""
            for r in rows[1:]:
                if r.startswith("🗓️") and not latest:
                    latest = r.split(":", 1)[1].strip() if ":" in r else ""
                elif "QoQ" in r or "YoY" in r:
                    trend = r
            seg = name
            if latest:
                seg += f": {latest}"
            if trend:
                seg += f" · {trend}"
            lines.append(seg)

    if not lines:
        return ["—"] * slots
    if len(lines) > slots:                       # merge the overflow into the last slot
        lines = lines[:slots - 1] + ["  •  ".join(lines[slots - 1:])]
    while len(lines) < slots:                    # pad — Meta rejects empty variables
        lines.append("—")
    return lines


def _insert_filed_time(body: str, time_str: str) -> str:
    """
    Insert a '🕒 Filed on exchange: <time>' line right after the company line
    (🏢 Stock Bits, or 💼 Result Bits) of a 📢 message. Idempotent. This is how
    the exchange time is re-added to the new EquiSense-style layout without the
    generator having to know it.
    """
    if not time_str:
        return body
    line = f"🕒 Filed on exchange: {time_str}"
    if line in body:
        return body
    out, inserted = [], False
    for ln in body.split("\n"):
        out.append(ln)
        if not inserted and (ln.lstrip().startswith("🏢") or ln.lstrip().startswith("💼")):
            out.append(line)
            inserted = True
    if not inserted:                     # no company line — put it under the title
        return f"{line}\n{body}"
    return "\n".join(out)


def _caption_with_time(body: str, company: str, symbol: str, raw_time) -> str:
    """
    Build the SINGLE WhatsApp caption: company + exchange filing time, then the
    AI summary (or a basic fallback). The exchange time is added HERE, per-send,
    and is NEVER stored in the summary cache — so it can't be duplicated on
    re-sends. Capped at WhatsApp's 1024-char caption limit.
    """
    # The EquiSense-style 'Stock Bits'/'Result Bits' body is self-contained (it
    # opens with 📢 and already carries the company). Add ONLY the exchange-time
    # line back into it (after the company line), and allow the full text-message
    # length (WhatsApp text caps at 4096).
    if body.lstrip().startswith("📢"):
        body = _insert_filed_time(body, _format_exchange_time(raw_time))
        return body if len(body) <= 4096 else body[:4093].rstrip() + "..."

    header = (
        f"🏢 *{company}* ({symbol})\n"
        f"🕒 Filed on exchange: {_format_exchange_time(raw_time)}"
    )
    caption = f"{header}\n\n{body}".strip()
    if len(caption) > 1024:
        caption = caption[:1021].rstrip() + "..."
    return caption


def _build_caption(file_path, fallback_caption, company=None,
                   filing_type="", download_url=""):
    """
    Return the rich AI summary BODY (cached if already generated). Caches the
    time-less body only. `filing_type` and `download_url` feed the ⚡ event line
    and 📎 download link. The cap is well above the old template limit so the
    footer + download link at the end of a text message aren't truncated away.
    """
    file_key = os.path.basename(file_path).strip()
    # Only reuse a cached summary that was produced by the CURRENT layout —
    # otherwise a filing summarised before a format change would be re-sent in
    # the old layout forever (this is why results kept arriving as "Stock Bits").
    cached   = bot_db.get_filing_summary(file_key, SUMMARY_FORMAT_VERSION)
    if cached:
        return cached

    ai_summary = generate_pdf_summary(file_path, company, filing_type, download_url)
    if ai_summary:
        trimmed = ai_summary[:3997] + "..." if len(ai_summary) > 4000 else ai_summary
        bot_db.save_filing_summary(file_key, trimmed, SUMMARY_FORMAT_VERSION)
        return trimmed
    return fallback_caption


# ── Parallel single-message caption builder ──────────────────────────────────
# Summaries run IN-PROCESS (generate_pdf_summary) and SEVERAL AT ONCE here, so a
# burst of filings doesn't serialize into a long queue. This keeps the PDF +
# summary + exchange-time in ONE WhatsApp message AND within ~1 minute.

_caption_pool = ThreadPoolExecutor(
    max_workers=getattr(config, "SUMMARY_WORKERS", 6),
    thread_name_prefix="summary",
)


# base62 alphabet for compact short codes (like equisense.ai/t/XWFNMh).
_B62_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _b62(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    s = ""
    while n:
        n, r = divmod(n, 62)
        s = _B62_ALPHABET[r] + s
    return s or "0"


def _shorten_download_url(url: str) -> str:
    """
    Turn a raw NSE PDF URL into a branded short link under our own domain,
    e.g. https://equityalerts.in/t/<code>, that 302-redirects to the real PDF
    (see Bot.py /t/<code>). Deterministic (same URL → same code, so the table
    self-dedupes). Falls back to the raw URL if shortening is disabled or fails.
    """
    if not url or not url.startswith("http"):
        return url
    base = getattr(config, "SHORTLINK_BASE", "") or ""
    if not base:
        return url
    try:
        code = _b62(hashlib.sha1(url.encode("utf-8")).digest())[:7]
        bot_db.save_short_link(code, url)
        return f"{base}/t/{code}"
    except Exception as e:
        whatsapp._safe_print(f"⚠️  Short-link create failed ({e}) — using raw URL.")
        return url


def _full_caption(company, symbol, filing_type, file_path, raw_time,
                  download_url="") -> str:
    """One-message caption = EquiSense Stock Bits alert (or basic fallback)."""
    # Show a branded short link under our own domain instead of the raw NSE URL.
    download_url = _shorten_download_url(download_url)
    fallback = (
        f"📄 *{company}* — {filing_type}\n"
        f"🏦 Symbol: {symbol}"
    )
    body = _build_caption(file_path, fallback, company,
                          filing_type=filing_type, download_url=download_url)
    return _caption_with_time(body, company, symbol, raw_time)


def _resolve_send_path(file_path, caption, file_key):
    """
    Decide which PDF actually gets uploaded.

    Renders the AI caption into a branded "Stock Bits" card PDF (once per
    filing, cached on disk and reused across every subscriber and every retry)
    and returns that path — so subscribers receive the nicely laid-out card
    instead of the raw NSE filing. On any failure — or when disabled/unavailable
    — falls back to the raw filing PDF so a delivery is never lost to a
    rendering hiccup.

    Defaults ON. Set config.SEND_AS_CARD = False to ship the original NSE PDF.
    """
    if not getattr(config, "SEND_AS_CARD", True) or message_card is None:
        return file_path
    if not caption:
        return file_path

    try:
        cache_dir = getattr(config, "CARD_CACHE_DIR", "") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "generated_cards"
        )
        os.makedirs(cache_dir, exist_ok=True)
        # Same basename as the filing, so the document the user sees keeps a
        # recognisable filename (e.g. "TCS_28052026.pdf").
        card_path = os.path.join(cache_dir, file_key or "filing.pdf")
        if not card_path.lower().endswith(".pdf"):
            card_path += ".pdf"

        # Cache hit: caption is stable per file_key, so a previously rendered
        # card is still valid — skip the re-render.
        if os.path.exists(card_path) and os.path.getsize(card_path) > 0:
            return card_path

        message_card.render_message_pdf(
            caption, card_path, timestamp=datetime.now().strftime("%H:%M")
        )
        whatsapp._safe_print(f"🎨 Rendered Stock Bits card → {os.path.basename(card_path)}")
        return card_path
    except Exception as e:
        whatsapp._safe_print(f"⚠️  Card render failed for {file_key} ({e}) — sending raw PDF.")
        return file_path


def _split_download_link(caption: str):
    """
    Split the '📎 Download filing: <url>' line out of the caption.

    Returns (body_without_that_line, url). Used for the TEXT-ONLY template,
    whose body is  "{{1}}\\n\\n📎 Download filing: {{2}}"  — so {{1}} must NOT
    already contain the link (or it would show twice), and {{2}} carries the raw
    URL on its own so it can never be truncated.
    """
    url = ""
    m = re.search(r"📎[^\n]*?(https?://\S+)", caption or "")
    if m:
        url = m.group(1)
        caption = re.sub(r"\n?📎[^\n]*", "", caption).strip()
    return caption, url


def _parse_stock_bits_parts(caption: str):
    """
    Split an assembled caption into its dynamic pieces for the SPACED template:
    (title, company, event, body, download_url, filed_time).

    Meta strips newlines out of a template *variable*, so the approved template
    carries the blank-line spacing as FIXED text and takes one single-line
    variable per section — this pulls those sections back out (the caller maps
    them to the template variables, adding emojis/time):

        title   = the 📢 header line   → {{1}}
        company = 🏢 / 💼 line          → {{2}}
        event   = ⚡ line / "<period> Results Out" (+filed time) → {{3}}
        body    = 🤖 summary / flattened metrics → {{4}}
        url     = 📎 / 🤖 Key Insights link → {{5}}

    Handles BOTH the 'Stock Bits' (🏢/⚡/🤖 summary) and 'Result Bits'
    (💼 company | period / 📊 metrics) layouts. `filed_time` is the exchange
    time so the caller can keep showing it in the closed-window template too.
    """
    text = caption or ""

    def _after(marker: str) -> str:
        m = re.search(marker + r"\s*(.+)", text)
        return m.group(1).strip() if m else ""

    fm    = re.search(r"🕒[^\n]*?:\s*(.+)", text)
    filed = fm.group(1).strip() if fm else ""
    # Branded title (📢 *PureFrame Stock/Result Bits!!*) — carried as a VARIABLE
    # value, not the template's fixed text, so it can't push the template into
    # the Marketing category.
    tm    = re.search(r"(📢[^\n]*)", text)
    title = tm.group(1).strip() if tm else ""

    if "💼" in text and "📊" in text:
        # ── Result Bits (financial results) ──────────────────────────────
        cline = _after("💼")
        if "|" in cline:
            company, event = (p.strip() for p in cline.split("|", 1))
        else:
            company, event = cline, "Results Out"
        m = re.search(r"📊 Key Metrics\s*(.+?)(?:\n\s*🤖|\n\s*You are receiving|$)",
                      text, re.DOTALL)
        body = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
        um = (re.search(r"🤖 Key Insights:\s*\n?\s*(https?://\S+)", text)
              or re.search(r"(https?://\S+)", text))
        url = um.group(1) if um else ""
        return title, company, event, body, url, filed

    # ── Stock Bits (default) ─────────────────────────────────────────────
    company = _after("🏢")
    event   = _after("⚡")
    body = ""
    m = re.search(r"🤖\s*(.+?)(?:\n\s*🔗|\n\s*📎|\n\s*You are receiving|$)",
                  text, re.DOTALL)
    if m:
        body = re.sub(r"\s+", " ", m.group(1)).strip()
        body = re.sub(r"\s*#\w*Impact\s*$", "", body).strip()   # drop trailing #HighImpact
    um  = re.search(r"📎[^\n]*?(https?://\S+)", text)
    url = um.group(1) if um else ""
    return title, company, event, body, url, filed


def _try_send(phone, file_path, caption, file_key, filing_id=None,
              template_params=None, force_template=False):
    """
    Attempt one delivery.

    Tries free-form first; if the 24h window is closed, whatsapp.send_pdf falls
    back to the approved template (when configured). Returns True only on
    confirmed success (and marks it sent). If delivery still fails (e.g. no
    template configured, or template not yet approved) the filing is queued
    for retry. Never marks a filing sent on failure.

    force_template=True skips the free-form attempt and sends via template
    directly. Pass this when retrying after a 131047 callback — we already
    KNOW the window is closed, so re-trying free-form would just fail again
    asynchronously and loop forever.

    SUMMARY + PDF: when a filing goes out as a template (window closed), the
    body {{1}} variable carries the AI summary (`caption`) so the subscriber
    receives the summary text AND the PDF together — no button to tap.

    TEMPLATE-STACKING CAP: by default every filing for a recipient OUTSIDE the
    24h window is delivered as its own utility template, so silent subscribers
    receive all their filings. Set config.ONE_TEMPLATE_PER_WINDOW = True to cap
    this to a single template per closed window (queuing the rest until the user
    re-engages) — the old behaviour, kept as an option.
    """
    # The template body {{1}} carries the AI summary itself, so the user gets
    # summary + PDF in one message. whatsapp.py flattens it for Meta.
    template_params = [caption] if caption else (template_params or [])

    template_configured = bool(getattr(config, "TEMPLATE_NAME", "") or "")
    window_is_open      = bot_db.window_open(phone)
    cap_templates       = bool(getattr(config, "ONE_TEMPLATE_PER_WINDOW", False))

    # ── TEXT delivery for OPEN windows (EquiSense style, link only) ──────────
    # INSIDE the 24h window we push the EquiSense text message with the 📎 link
    # (no attachment). OUTSIDE the window we DO NOT touch it here — we fall
    # through to the approved template + document path below, exactly as before,
    # so silent subscribers keep receiving their filings as template+PDF.
    if getattr(config, "SEND_AS_TEXT", True) and window_is_open and not force_template:
        try:
            # Attach a "Manage companies" CTA button that opens the add/remove
            # page. A cta_url body is capped at 1024 chars, so very long alerts
            # (large metrics tables) fall back to a plain text send.
            manage_url = getattr(config, "MANAGE_COMPANIES_URL", "")
            if manage_url and len(caption) <= 1024:
                wamid = whatsapp.send_cta_url_button(
                    phone, caption,
                    button_text="Manage companies",
                    url=manage_url,
                )
            else:
                wamid = whatsapp.send_text(phone, caption)
            bot_db.mark_filing_sent(phone, file_key)
            bot_db.remove_pending_filing(phone, file_key)
            if wamid:
                bot_db.store_wamid(wamid, phone, file_key, file_path, caption,
                                   filing_id=filing_id, channel="text")
            whatsapp._safe_print(f"[OK] Sent text alert to {phone} for {file_key}")
            return True
        except WhatsAppError as e:
            if e.is_reengagement:
                # Our window read was stale — the window is actually closed.
                # Fall through to the template + document path below.
                print(f"⏳ Window actually closed for {phone} — using template "
                      f"(document) for {file_key}.")
            else:
                print(f"❌ Text send failed for {phone} ({file_key}): {e}")
                bot_db.queue_pending_filing(
                    phone, file_key, file_path, caption, filing_id=filing_id,
                    error=f"text send failed: {e}"
                )
                return False
        except Exception as e:
            print(f"❌ Unexpected text send error for {phone} ({file_key}): {e}")
            bot_db.queue_pending_filing(
                phone, file_key, file_path, caption, filing_id=filing_id,
                error=f"text send error: {e}"
            )
            return False

    # ── Closed window → TEXT-ONLY template (no attachment) ───────────────────
    # The approved template is body-only (no media header):
    #   {{1}} = summary (download line stripped), {{2}} = the download link.
    # Reached only when the window is closed or a template retry is forced — the
    # open-window text send above already returned on success.
    if getattr(config, "SEND_AS_TEXT", True):
        if not template_configured:
            bot_db.queue_pending_filing(
                phone, file_key, file_path, caption, filing_id=filing_id,
                error="window closed, no template configured"
            )
            print(f"⏳ Window closed for {phone} & no template — queued {file_key}.")
            return False
        if cap_templates and not bot_db.can_send_batch_template(phone):
            bot_db.queue_pending_filing(
                phone, file_key, file_path, caption, filing_id=filing_id,
                error="template cap: suppressed to avoid stacking"
            )
            print(f"🔕 Template already sent to {phone} this window — queued {file_key}.")
            return False
        try:
            # SPACED template: one single-line variable per section so the
            # template's own fixed newlines provide the spacing (Meta strips
            # newlines from a variable). Body {{1..4}} = company, event,
            # summary, download link.
            title, company, event, body, url, filed = _parse_stock_bits_parts(caption)

            # ── RESULTS → dedicated metrics-table template (if approved) ──────
            # A metrics table can't render in the Stock Bits template (one line
            # per variable). When TEMPLATE_RESULT_NAME is configured, results go
            # to their own template with one metric per line. Until then they
            # fall through to the Stock Bits template below (current behaviour).
            result_tpl = getattr(config, "TEMPLATE_RESULT_NAME", "") or ""
            # Route to nse_result_bits whenever the topic/event line below the
            # company says "Results Out" — this catches BOTH the structured
            # Result Bits layout (💼 … | … Results Out / 📊 metrics) AND a flat
            # Stock Bits summary of a results filing (⚡ … Results Out). Anything
            # else stays on the earlier Stock Bits template (TEMPLATE_NAME).
            is_result = (
                bool(re.search(r"results?\s+out", caption or "", re.IGNORECASE))
                or ("💼" in (caption or "") and "📊" in (caption or ""))
            )
            if is_result and result_tpl:
                slots   = int(getattr(config, "TEMPLATE_RESULT_METRIC_SLOTS", 3))
                metrics = _compact_metric_lines(caption, slots)
                # Flat results (no 📊 Key Metrics table) come back as empty "—"
                # slots. Rather than ship a blank table, carry the 🤖 summary
                # body in the first slot so the numbers still reach the user.
                if body and all(m == "—" for m in metrics):
                    metrics = [body] + ["—"] * (slots - 1)
                params  = [
                    title or "📢 *PureFrame Result Bits!!*",
                    f"💼 {company} | {event}" if event else f"💼 {company}",
                    f"🕒 Filed on exchange: {filed}" if filed else "🕒 Filed on exchange: n/a",
                    *metrics,
                    url or "https://equityalerts.in",
                ]
                wamid = whatsapp.send_text_template(phone, params,
                                                    template_name=result_tpl)
                bot_db.mark_batch_template_sent(phone)
                bot_db.mark_filing_sent(phone, file_key)
                bot_db.remove_pending_filing(phone, file_key)
                if wamid:
                    bot_db.store_wamid(wamid, phone, file_key, file_path, caption,
                                       filing_id=filing_id, channel="template")
                whatsapp._safe_print(f"[OK] Sent RESULT template to {phone} for {file_key}")
                return True

            # The branded TITLE and the 🏢/⚡/🤖 emojis ride INSIDE the variable
            # values (not the approved template's fixed text) — so the template's
            # fixed text stays neutral/Utility while the "📢 PureFrame … Bits!!"
            # header and markers still show. Meta's category check looks at the
            # fixed text only, so this is safe.
            title = title or "📢 *PureFrame Stock Bits!!*"
            if company:
                company = f"🏢 {company}"
            # The exchange time has no variable of its own (no new template), so it
            # rides on the event line: "⚡ <event> · 🕒 Filed <time>".
            event = f"⚡ {event}" if event else ""
            if filed:
                event = (f"{event} · 🕒 Filed {filed}" if event
                         else f"🕒 Filed on exchange: {filed}")
            if body:
                body = f"🤖 {body}"
            url = url or "https://equityalerts.in"
            # {{1}}=title, {{2}}=company, {{3}}=event(+time), {{4}}=summary, {{5}}=link
            wamid = whatsapp.send_text_template(
                phone, [title, company, event, body, url]
            )
            bot_db.mark_batch_template_sent(phone)
            bot_db.mark_filing_sent(phone, file_key)
            bot_db.remove_pending_filing(phone, file_key)
            if wamid:
                bot_db.store_wamid(wamid, phone, file_key, file_path, caption,
                                   filing_id=filing_id, channel="template")
            whatsapp._safe_print(f"[OK] Sent text template to {phone} for {file_key}")
            return True
        except WhatsAppError as e:
            print(f"❌ Template send failed for {phone} ({file_key}): {e}")
            bot_db.queue_pending_filing(
                phone, file_key, file_path, caption, filing_id=filing_id,
                error=f"text template failed: {e}"
            )
            return False
        except Exception as e:
            print(f"❌ Unexpected template error for {phone} ({file_key}): {e}")
            bot_db.queue_pending_filing(
                phone, file_key, file_path, caption, filing_id=filing_id,
                error=f"text template error: {e}"
            )
            return False

    # If this filing is template-bound (window closed, or an explicit template
    # retry), make sure a template is configured — and optionally enforce the
    # one-template-per-window cap.
    if force_template or not window_is_open:
        if not template_configured:
            bot_db.queue_pending_filing(
                phone, file_key, file_path, caption, filing_id=filing_id,
                error="window closed, no template configured"
            )
            print(f"⏳ Window closed for {phone} & no template — queued {file_key}.")
            return False
        if cap_templates and not bot_db.can_send_batch_template(phone):
            bot_db.queue_pending_filing(
                phone, file_key, file_path, caption, filing_id=filing_id,
                error="template cap: suppressed to avoid stacking"
            )
            print(f"🔕 Template already sent to {phone} this window — queued "
                  f"{file_key} instead of stacking another template.")
            return False

    # Render (or reuse) the branded card PDF that will actually be uploaded.
    # Falls back to the raw filing PDF if cards are disabled or rendering fails.
    send_path = _resolve_send_path(file_path, caption, file_key)

    try:
        # Window open  → free-form (no auto-template fallback: if our window
        #                read is stale, the 131047 below routes through the cap).
        # Window closed/forced → go straight to the template (summary + PDF).
        send_force = bool(force_template or not window_is_open)
        channel, wamid = whatsapp.send_pdf(phone, send_path, caption=caption,
                                           template_params=template_params,
                                           force_template=send_force,
                                           allow_template_fallback=False)
        if channel == "template":
            # Spend this window's single template allowance.
            bot_db.mark_batch_template_sent(phone)
        bot_db.mark_filing_sent(phone, file_key)
        bot_db.remove_pending_filing(phone, file_key)  # clear any prior retry entry
        # Track the wamid so status callbacks can undo this if Meta later
        # reports 131047 (free-form accepted but not delivered).
        tracked = False
        if wamid:
            bot_db.store_wamid(wamid, phone, file_key, file_path, caption,
                               filing_id=filing_id, channel=channel)
            # Verify the row actually landed (guards against "table not ready" edge case).
            if bot_db.get_wamid_info(wamid):
                tracked = True
            else:
                print(f"⚠️  WAMID STORE FAILED for {phone} / {file_key} — "
                      f"status callbacks will not be able to retry this filing!")
        else:
            # Empty wamid means Meta's response had no messages[0].id.
            # The 131047 status callback will arrive later but cannot be matched.
            print(f"⚠️  EMPTY WAMID returned for {phone} / {file_key} ({channel}) — "
                  f"wamid tracking disabled for this send.")

        # ── SAFETY NET ──────────────────────────────────────────────────
        # If a FREE-FORM send could not be tracked, a later 131047 async
        # failure callback can't be matched back to this filing and would be
        # silently dropped. Park a recoverable copy in pending_filings so it
        # goes out the next time the user messages (which reopens the window).
        # Template sends deliver outside the window and won't get 131047, so
        # they don't need this.
        if not tracked and channel == "freeform":
            bot_db.queue_pending_filing(
                phone, file_key, file_path, caption,
                filing_id=filing_id,
                error="untracked freeform send (empty/failed wamid)"
            )
            print(f"   🛟 Parked {file_key} for {phone} in pending_filings "
                  f"(untracked send — recoverable on next inbound message).")
        return True
    except WhatsAppError as e:
        if e.is_reengagement:
            # Our window read was stale (we thought it was open) — the window is
            # actually closed. Route through the cap: send the ONE allowed
            # template now, otherwise queue so we never stack templates.
            if template_configured and (not cap_templates or bot_db.can_send_batch_template(phone)):
                print(f"⏳ Window actually closed for {phone} — sending the "
                      f"template (summary + PDF) for {file_key}.")
                try:
                    channel, wamid = whatsapp.send_pdf(
                        phone, send_path, caption=caption,
                        template_params=template_params,
                        force_template=True,
                    )
                    bot_db.mark_batch_template_sent(phone)
                    bot_db.mark_filing_sent(phone, file_key)
                    bot_db.remove_pending_filing(phone, file_key)
                    if wamid:
                        bot_db.store_wamid(wamid, phone, file_key, file_path,
                                           caption, filing_id=filing_id,
                                           channel=channel)
                    return True
                except Exception as e2:
                    print(f"❌ Template send failed for {phone} ({file_key}): {e2}")
                    bot_db.queue_pending_filing(
                        phone, file_key, file_path, caption,
                        filing_id=filing_id, error=str(e2)
                    )
                    return False
            print(f"⏳ Window closed for {phone} — queued {file_key} "
                  f"(template cap / no template).")
            bot_db.queue_pending_filing(
                phone, file_key, file_path, caption,
                filing_id=filing_id, error="131047 re-engagement (capped/queued)"
            )
        else:
            print(f"❌ WhatsApp send failed for {phone} ({file_key}): {e}")
            bot_db.queue_pending_filing(
                phone, file_key, file_path, caption,
                filing_id=filing_id, error=str(e)
            )
        return False
    except Exception as e:
        print(f"❌ Unexpected send error for {phone} ({file_key}): {e}")
        bot_db.queue_pending_filing(
            phone, file_key, file_path, caption,
            filing_id=filing_id, error=str(e)
        )
        return False


def process_new_filings():
    """
    Fetch new filings → build (exchange time + AI summary) captions for the
    whole batch CONCURRENTLY → deliver one WhatsApp message each.

    Building captions in parallel means a burst of N filings takes about as long
    as ONE summary, not N — so every PDF lands with its summary within ~1 minute
    instead of the later ones queuing for minutes.
    """
    filings = fetch_new_filings()
    filings = _dedup_by_filename(filings)
    if not filings:
        return

    # ── Phase 1: resolve subscribers / drop undeliverable filings ────────
    jobs = []
    for filing in filings:
        filing_id   = filing["filing_id"]
        symbol      = (filing.get("symbol") or "").upper().strip()
        company     = get_company_display_name(symbol)
        file_path   = filing["file_path"]
        filing_type = filing.get("filing_type") or "New Filing"

        subscribers = get_subscribers_for_symbol_pg(symbol)
        if subscribers is None:
            # Lookup FAILED (transient DB error) — do NOT mark notified; leave it
            # is_notified=FALSE so the very next poll retries instead of dropping
            # it to the slow backfill.
            print(f"⚠️  Subscriber lookup failed for {symbol}; will retry next poll.")
            continue
        if not subscribers:
            mark_notified_in_pg(filing_id)
            print(f"ℹ️  No subscribers for {symbol}, skipping.")
            continue

        if not os.path.exists(file_path):
            print(f"⚠️  File not found: {file_path} — marking to prevent loop.")
            file_key = os.path.basename(file_path).strip()
            for phone in subscribers:
                bot_db.mark_filing_sent(phone, file_key)
            mark_notified_in_pg(filing_id)
            continue

        jobs.append({
            "filing_id":    filing_id,
            "symbol":       symbol,
            "company":      company,
            "file_path":    file_path,
            "filing_type":  filing_type,
            "download_url": filing.get("pdf_url") or "",
            "raw_time":     filing.get("created_at"),
            "age_seconds":  filing.get("age_seconds"),
            "subscribers":  subscribers,
            "file_key":     os.path.basename(file_path).strip(),
        })

    if not jobs:
        return

    # ── Phase 2: build all captions concurrently (summary + exchange time) ─
    futures = {
        j["file_key"]: _caption_pool.submit(
            _full_caption, j["company"], j["symbol"], j["filing_type"],
            j["file_path"], j["raw_time"], j["download_url"],
        )
        for j in jobs
    }

    # ── Phase 3: deliver ONE message per subscriber ──────────────────────
    for j in jobs:
        try:
            caption = futures[j["file_key"]].result()
        except Exception as e:
            print(f"❌ Caption build failed for {j['file_key']}: {e}")
            caption = _caption_with_time(
                f"📄 *{j['company']}* — {j['filing_type']}\n🏦 Symbol: {j['symbol']}",
                j["company"], j["symbol"], j["raw_time"],
            )

        age = j.get("age_seconds")
        age_note = f" [saved {age}s ago by scraper]" if age is not None else ""
        print(f"📤 Sending {j['symbol']} '{j['filing_type']}' to {len(j['subscribers'])} subscriber(s)...{age_note}")
        all_sent = True
        for phone in j["subscribers"]:
            if bot_db.is_filing_sent(phone, j["file_key"]):
                print(f"ℹ️  Already sent filing {j['file_key']} to {phone}, skipping.")
                continue
            # Only marks sent on confirmed success; queues on failure.
            ok = _try_send(phone, j["file_path"], caption, j["file_key"],
                           filing_id=j["filing_id"], template_params=[j["company"]])
            if not ok:
                all_sent = False

        # Mark notified in PG only when EVERY subscriber got it. Otherwise the
        # filing stays is_notified=FALSE and is retried on the next poll for
        # anyone still missing it (already-sent users are skipped above).
        if all_sent:
            mark_notified_in_pg(j["filing_id"])


# ── Automatic backfill for subscribers ───────────────────────

def deliver_backfill_for_subscribers():
    """
    For every active subscriber, ensure they have the latest filings for each
    company they're subscribed to. Idempotent — safe to run every poll.
    """
    try:
        sub_conn = psycopg2.connect(
            host=config.DB_HOST, port=config.DB_PORT,
            dbname="nse_subscription",
            user=config.DB_USER, password=config.DB_PASSWORD,
        )
        sub_cur = sub_conn.cursor()
        sub_cur.execute("""
            SELECT DISTINCT u.mobile
            FROM users u
            JOIN subscriptions s ON s.user_id = u.id
            WHERE s.status = 'ACTIVE';
        """)
        active_users = [r[0].strip() for r in sub_cur.fetchall()]

        pg_conn = get_pg_conn()
        pg_cur  = pg_conn.cursor()

        for raw_phone in active_users:
            phone = raw_phone
            if len(phone) == 10 and phone.isdigit():
                phone = "91" + phone
            normalized_phone = (
                phone[2:] if (phone.startswith("91") and len(phone) == 12) else phone
            )

            sub_cur.execute("""
                SELECT c.symbol, c.company_name, uc.created_at
                FROM user_companies uc
                JOIN companies c ON c.id = uc.company_id
                JOIN users u ON u.id = uc.user_id
                JOIN subscriptions s ON s.user_id = u.id
                WHERE (u.mobile = %s OR u.mobile = %s) AND s.status = 'ACTIVE';
            """, (phone, normalized_phone))
            subs = [(r[0], r[1], r[2]) for r in sub_cur.fetchall()]
            if not subs:
                continue

            for symbol, db_company_name, subscribed_at in subs:
                symbol = symbol.upper().strip()
                name = config.COMPANY_LIST.get(symbol, db_company_name or symbol)
                pg_cur.execute("""
                    SELECT id, title, local_path, pdf_url, announcement_time
                    FROM announcements
                    WHERE UPPER(company_symbol) = UPPER(%s)
                      AND download_status = 'DOWNLOADED'
                      AND announcement_time > %s
                    ORDER BY announcement_time ASC
                    LIMIT 50
                """, (symbol, subscribed_at))
                rows = _dedup_by_filename(pg_cur.fetchall())

                for row in rows:
                    file_path = os.path.join(
                        config.SCRAPER_BASE_PATH, row["local_path"].strip()
                    )
                    file_key = os.path.basename(file_path).strip()

                    if bot_db.is_filing_sent(phone, file_key):
                        continue
                    if not os.path.exists(file_path):
                        continue

                    # One message: exchange time + AI summary (cached after the
                    # first build, so repeated backfill passes are cheap).
                    caption = _full_caption(name, symbol, row.get("title") or "New Filing",
                                            file_path, row['announcement_time'],
                                            row.get("pdf_url") or "")

                    # Only marks sent on confirmed success; queues on failure.
                    if _try_send(phone, file_path, caption, file_key,
                                 filing_id=row["id"], template_params=[name]):
                        print(f"✅ Auto-delivered {file_key} to {phone}")

        pg_cur.close()
        pg_conn.close()
        sub_cur.close()
        sub_conn.close()
    except Exception as e:
        print(f"❌ Error in deliver_backfill_for_subscribers: {e}")


# ── Retry queue flush (called when a user re-opens the 24h window) ──

def flush_pending_filings(phone: str) -> int:
    """
    Re-attempt every parked filing for `phone`. Call this from the webhook
    handler whenever the user sends ANY inbound message — that message
    reopens the 24-hour window, so previously-blocked PDFs can now go out.

    Returns the number of filings successfully delivered.
    """
    pending = bot_db.get_pending_filings(phone)
    if not pending:
        return 0

    print(f"🔁 Flushing {len(pending)} pending filing(s) for {phone}...")
    delivered = 0
    for item in pending:
        file_path = item["file_path"]
        file_key  = item["file_key"]
        caption   = item.get("caption") or ""
        filing_id = item.get("filing_id")

        if not os.path.exists(file_path):
            # Source file gone — drop it from the queue to avoid a stuck loop.
            bot_db.remove_pending_filing(phone, file_key)
            continue

        if _try_send(phone, file_path, caption, file_key, filing_id=filing_id):
            delivered += 1
            # If the originating PG row is now fully delivered, mark it notified.
            if filing_id:
                mark_notified_in_pg(filing_id)

    return delivered


# ── 24h-window pre-close re-engagement reminder ──────────────

# Button id sent back when a user taps the re-engage button. Bot.py handles it.
REENGAGE_BUTTON_ID = "REENGAGE_KEEP"


def _build_window_reminder_body() -> str:
    """Body text for the interactive reminder: manage-companies link + nudge."""
    url = getattr(config, "MANAGE_COMPANIES_URL", "")
    return (
        "You can add or remove companies anytime here 👇\n"
        f"{url}\n\n"
        "Tap *Keep alerts on* below so your NSE filings keep arriving smoothly "
        "(without piling up). 📈"
    )


def send_window_closing_reminders():
    """
    Send a one-time INTERACTIVE reminder to every user whose 24-hour window is
    about to close (last inbound between (24 - WINDOW_REMINDER_BEFORE_HOURS) and
    24 hours ago, not yet reminded for this window).

    It carries a reply BUTTON, not just a link: tapping a reply button sends an
    inbound message that REOPENS the 24h window (a URL tap does not), so the
    user's next filings arrive as normal messages instead of stacked templates.
    Header/body show the manage-companies link; the footer carries the
    PureFrameLabs promo.
    """
    if not getattr(config, "ENABLE_WINDOW_REMINDER", False):
        return

    before  = float(getattr(config, "WINDOW_REMINDER_BEFORE_HOURS", 1))
    min_age = max(0.0, 24.0 - before)   # e.g. 23h old
    due     = bot_db.get_users_due_for_window_reminder(min_age, 24.0)
    if not due:
        return

    body    = _build_window_reminder_body()
    contact = getattr(config, "PUREFRAME_CONTACT", "")
    buttons = [{"id": REENGAGE_BUTTON_ID, "title": "Keep alerts on ✅"}]
    print(f"🔔 {len(due)} user(s) due for a window-closing reminder.")
    for phone in due:
        try:
            whatsapp.send_interactive_buttons(
                phone, body, buttons,
                header_text="🔔 Manage your NSE alerts",
                footer_text=f"📢 PureFrameLabs • {contact}",
            )
            bot_db.mark_window_reminder_sent(phone)
            print(f"   ✅ Reminder sent to {phone}")
        except WhatsAppError as e:
            # If the window has already closed (131047), an interactive message
            # can't be delivered. Mark it sent anyway so we don't retry every
            # cycle — it resets automatically when the user next messages us.
            if e.is_reengagement:
                bot_db.mark_window_reminder_sent(phone)
                print(f"   ⏳ Window already closed for {phone} — reminder skipped.")
            else:
                print(f"   ❌ Reminder send failed for {phone}: {e}")
        except Exception as e:
            print(f"   ❌ Reminder error for {phone}: {e}")


# Backwards-compatible alias
catch_up_new_subscribers = deliver_backfill_for_subscribers


# ── Background polling thread ────────────────────────────────

def start_watcher():
    """
    Run two INDEPENDENT background loops:

      1. live_loop      — the time-critical path. Polls for brand-new filings
                          (is_notified=FALSE) every POLL_INTERVAL_SEC and ships
                          them immediately. Nothing slow runs here, so a fresh
                          announcement goes out within ~1 minute of appearing.

      2. backfill_loop  — the slow subscriber catch-up (every subscriber ×
                          every company × latest PDFs). Heavy, so it runs on its
                          OWN thread on a long interval. It can take minutes
                          without ever delaying live delivery.

    Previously both ran in a single loop, so a long backfill sweep blocked new
    filings for up to an hour. Splitting them is the fix.
    """
    ensure_schema()

    def live_loop():
        print(f"⚡ Live dispatch started — checking for NEW filings every {config.POLL_INTERVAL_SEC}s")
        while True:
            try:
                process_new_filings()
            except Exception as e:
                print(f"❌ Live dispatch error: {e}")
            time.sleep(config.POLL_INTERVAL_SEC)

    def backfill_loop():
        interval = getattr(config, "BACKFILL_INTERVAL_SEC", 600)
        print(f"🪃 Subscriber backfill started — running every {interval}s (off the hot path)")
        while True:
            try:
                deliver_backfill_for_subscribers()
            except Exception as e:
                print(f"❌ Backfill task error: {e}")
            time.sleep(interval)

    def reminder_loop():
        interval = int(getattr(config, "REMINDER_CHECK_INTERVAL_SEC", 300))
        print(f"🔔 Window-close reminder loop started — checking every {interval}s")
        while True:
            try:
                send_window_closing_reminders()
            except Exception as e:
                print(f"❌ Reminder loop error: {e}")
            time.sleep(interval)

    # Warm the AI summary engine (one-time LangChain import) so the first real
    # filing isn't slowed by it.
    threading.Thread(target=warm_up_summary_engine, daemon=True, name="summary-warmup").start()
    threading.Thread(target=live_loop, daemon=True, name="live-dispatch").start()
    threading.Thread(target=backfill_loop, daemon=True, name="subscriber-backfill").start()
    if getattr(config, "ENABLE_WINDOW_REMINDER", False):
        threading.Thread(target=reminder_loop, daemon=True, name="window-reminder").start()