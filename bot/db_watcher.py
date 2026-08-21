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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        # Which scraper produced the row ('BSE', or NULL for the NSE scraper,
        # which does not stamp it). Added here as well as in the BSE scraper so
        # the bot can be started against a database that scraper has never
        # touched. Reported only — delivery never depends on it.
        cur.execute("""
            ALTER TABLE announcements
            ADD COLUMN IF NOT EXISTS exchange VARCHAR(8)
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ announcements.is_notified / exchange columns ready.")
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
    _started = time.monotonic()
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
                COALESCE(exchange, 'NSE')   AS exchange,
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
        print(f"⏱ [timing] fetch_new_filings rows={len(resolved)} duration={time.monotonic()-_started:.2f}s")
        return resolved

    except Exception as e:
        print(f"❌ [timing] fetch_new_filings FAILED duration={time.monotonic()-_started:.2f}s error={e}")
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


def get_subscribers_for_symbols_pg(symbols: list[str]) -> dict[str, list]:
    """Fetch subscribers for all symbols in ONE PostgreSQL connection."""
    normalized = sorted({(x or "").upper().strip() for x in symbols if (x or "").strip()})
    if not normalized:
        return {}
    started = time.monotonic()
    try:
        conn = psycopg2.connect(
            host=config.DB_HOST, port=config.DB_PORT, dbname="nse_subscription",
            user=config.DB_USER, password=config.DB_PASSWORD,
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT UPPER(c.symbol) AS symbol, u.mobile
            FROM user_companies uc
            JOIN users u ON u.id = uc.user_id
            JOIN companies c ON c.id = uc.company_id
            JOIN subscriptions s ON s.user_id = u.id
            WHERE UPPER(c.symbol) = ANY(%s) AND s.status = 'ACTIVE';
        """, (normalized,))
        rows = cur.fetchall()
        cur.close(); conn.close()
        result = {symbol: [] for symbol in normalized}
        for symbol, raw_phone in rows:
            phone=(raw_phone or "").strip()
            if len(phone)==10 and phone.isdigit(): phone="91"+phone
            if phone: result.setdefault(symbol, []).append(phone)
        print(f"⏱ [timing] subscriber_batch symbols={len(normalized)} rows={len(rows)} duration={time.monotonic()-started:.2f}s")
        return result
    except Exception as e:
        print(f"❌ [timing] subscriber_batch FAILED symbols={len(normalized)} duration={time.monotonic()-started:.2f}s error={type(e).__name__}: {e}")
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
    # New EquiSense format opens with "📢 *EquityAlerts Stock Bits!!*"; strip any
    # leading log noise by starting at the first megaphone.
    marker = msg.find("📢")
    if marker != -1:
        return msg[marker:]
    return msg or None


def generate_pdf_summary(file_path: str, company: str | None = None,
                         filing_type: str = "", download_url: str = "") -> str | None:
    """Generate one summary directly inside the existing caption worker.

    The previous implementation started a second daemon thread and joined it
    with a hard timeout. Python cannot cancel that thread, so a timed-out LLM
    request kept running in the background and consumed an API/worker slot.
    That made retries slower instead of faster. The LLM clients now have real
    request timeouts, so this function stays single-threaded and measurable.
    """
    started = time.monotonic()
    file_name = os.path.basename(file_path)
    print(
        f"[timing] summary START file={file_name} company={company!r} type={filing_type!r}",
        flush=True,
    )
    try:
        value = _run_summary(file_path, company, filing_type, download_url)
        elapsed = time.monotonic() - started
        if value:
            print(
                f"[timing] summary DONE file={file_name} duration={elapsed:.2f}s chars={len(value)}",
                flush=True,
            )
            return value
        print(f"[timing] summary EMPTY file={file_name} duration={elapsed:.2f}s", flush=True)
        return None
    except Exception as e:
        print(
            f"[timing] summary FAIL file={file_name} duration={time.monotonic()-started:.2f}s "
            f"error={type(e).__name__}: {e}",
            flush=True,
        )
        return None


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
#   3 = EquityAlerts branding (was PureFrame), PureFrame Labs ad footer removed
#   4 = unit reconciliation + plausibility guards (output.py). Bumped because
#       the CONTENT changed, not the layout: summaries cached at v3 hold
#       mislabelled figures (a lakhs table transcribed as "Cr" overstates 100x)
#       and would otherwise be re-sent verbatim, never seeing the new guards.
#   5 = correctness fixes, all CONTENT again — a v4 cache holds values that are
#       simply wrong and must not be re-sent:
#         • per-share metrics no longer forced into crore (an EPS of ₹12.11
#           was shipped as "₹12.11 Cr", or rescaled to "₹0.12 Cr" off a lakhs
#           table);
#         • QoQ/YoY recomputed from the figures instead of trusting the model
#           (the same filing reported one margin as +1.27% and +14.86% on two
#           runs; the true change was +14.59%);
#         • abbreviations that contradict the metric name corrected, so a
#           "Profit before tax" block can no longer be labelled PAT.
#   6 = looks_like_financial_results() now also recognises the dated 4-column
#       results layout ("30.06.2026 31.03.2026 30.06.2025 ... (Unaudited)
#       (Audited)") used by "newspaper advertisement of results" filings,
#       which carry no results PHRASE at all. A v5 cache for one of these
#       holds a generic Stock Bits notice summary where a Result Bits metrics
#       table should be — re-classifying on re-cache, not just re-labelling.
#   7 = company-identity guard (output.py). A "newspaper advertisement"
#       filing can be a scan of a full newspaper PAGE carrying several
#       companies' notices — v6's wider results detection made it possible to
#       lock onto a NEIGHBOURING company's results table on the same page.
#       Seen in production: a filing under ULTRACEMCO whose extracted metrics
#       were actually CG Power and Industrial Solutions'. process_pdf now
#       discards a results block whose extracted company name doesn't match
#       the exchange's own record for the filing. A v6 cache built before
#       this guard existed may hold another company's numbers under our
#       subscriber's company name — must be regenerated, not re-sent.
#   8 = figure correctness (output.py). A v7 cache can hold values that are
#       wrong on their face and must not be re-sent:
#         • "₹1,07,496 Lakh" — only MISLABELLED denominations were rescaled to
#           Cr, so a correctly-labelled lakh/million figure went out under its
#           own name, and one message could mix Lakh and Cr rows.
#         • "₹1,075 Cr" where the filing says ₹1,074.96 Cr — decimals were
#           dropped above ₹1,000 Cr.
#         • a LOSS printed "(20.00)" or "-₹20.00 Cr" read as +20.00, so a
#           loss-to-profit quarter showed "+150.00% QoQ" and a loss showed as
#           a profit.
#         • periods emitted oldest-first were never re-ordered, inverting
#           QoQ/YoY (-27.43% where the truth was +0.10%).
#   9 = results DETECTION and units again (output.py) — a v8 cache holds a
#       generic Stock Bits notice for filings that do report figures:
#         • looks_like_financial_results() now counts the line-item names an
#           INVESTOR PRESENTATION uses (Net Sales, Gross Contribution, PBDIT)
#           and their uppercase abbreviations, not just the statutory ones.
#           Asian Paints' Q1FY27 deck matched exactly one term ("revenue") and
#           was classified as a notice despite carrying Net Sales / PBDIT / PBT
#           / PAT for two periods.
#         • detect_document_scale() tolerates an OCR-mangled denomination
#           heading ("(₹ in Crores)" scanned as "(f in Crorea)"), which
#           previously read as "no denomination stated" — so figures went out
#           with no ₹ and no Cr at all.
#         • _names_plausibly_match() no longer discards every metric when the
#           exchange's record for the filing is the bare SYMBOL ("TATAPOWER"
#           shares no word with "The Tata Power Company Limited").
#  10 = OCR (output.py). Scanned filings and newspaper cuttings now have their
#       image-only and mojibake pages read by tesseract, so a v9 cache for one
#       of those holds a summary written from the covering letter alone — or the
#       "no summary available" notice — where the published results table is now
#       readable. Re-extracting, not re-formatting.
#  11 = an earnings-call TRANSCRIPT is no longer treated as a results filing
#       (output.py). It names every metric, quotes spoken figures and says
#       "quarter ended", so it passed results detection and shipped as
#       "Jun 2026 Results Out" with a padded third period — Mar 2026 and
#       Jun 2025 carrying the same value, QoQ identical to YoY. A v10 cache for
#       one holds that fabricated metrics table and must not be re-sent.
SUMMARY_FORMAT_VERSION = 12



# The results template hard-codes its three metric HEADINGS in the fixed text
# ("Revenue (REV):", "Profit After Tax (PAT):", "Operating Profit Margin (OPM):")
# — that fixed text is what keeps the template inside Meta's variables-to-length
# budget and out of the Marketing category (see config.TEMPLATE_RESULT_NAME).
# The price is that whatever the extractor found has to be matched ONTO those
# three slots; metrics outside them (EBITDA, EPS …) are dropped from the
# closed-window template. The free-form text alert still carries all of them.
# (slot, name keywords that FIT the slot, name keywords that DISQUALIFY it).
# The exclusions are load-bearing: the extractor labelled a "Profit before
# tax" block short_name="PAT", and the fixed heading then presented
# ₹1,558.75 Cr of PRE-tax profit as "Profit After Tax" — a 34% overstatement
# (the real PAT that quarter was ₹1,160.74 Cr). A slot must never be filled
# by a metric whose own name contradicts the heading.
RESULT_TEMPLATE_SLOTS = (
    ("REV", ("revenue", "total income", "net sales", "turnover",
             "income from operations"), ()),
    ("PAT", ("profit after tax", "net profit", "profit for the period"),
             ("before tax", "before exceptional", "pre-tax", "pbt")),
    ("OPM", ("operating profit margin", "operating margin", "ebitda margin"),
             ()),
)


def _slot_rank(block: dict, short: str, keywords, exclusions) -> int:
    """
    How well `block` fits a fixed template slot:
        2 = its NAME says so, 1 = only the model's abbreviation says so, 0 = no.

    Name beats abbreviation because the model's short_name is the unreliable
    field — trusting it first is exactly what let a before-tax figure fill the
    PAT slot. `exclusions` veto outright rather than merely down-rank.
    """
    name = (block.get("name") or "").lower()
    if any(x in name for x in exclusions):
        return 0
    if any(k in name for k in keywords):
        return 2
    if block.get("short") == short:
        return 1
    return 0


# Abbreviations the extractor gets wrong often enough to correct on sight,
# as (name substrings, correct abbreviation). Without this the per-count
# result templates — which carry the heading as a VARIABLE — would render a
# self-contradicting "Profit before tax (PAT):".
_SHORT_FIXUPS = (
    (("before tax", "before exceptional", "pre-tax"), "PBT"),
)


def _canonical_short(name: str, short: str) -> str:
    """Correct an abbreviation that contradicts the metric's own name."""
    low = (name or "").lower()
    for needles, correct in _SHORT_FIXUPS:
        if any(n in low for n in needles):
            return correct
    return short


def _metric_block(head: str, periods: list, trend: str) -> dict:
    """Split a metric heading ("Revenue from Operations (REV)") into name + short."""
    sm    = re.search(r"\(([A-Za-z]{2,})\)\s*$", head)
    name  = re.sub(r"\s*\([A-Za-z]{2,}\)\s*$", "", head).strip()
    short = (sm.group(1).upper() if sm else "")
    return {
        "short":   _canonical_short(name, short),
        "name":    name,
        "periods": periods,
        "trend":   trend,
    }


def _parse_metric_blocks(caption: str) -> list:
    """
    Parse the "\U0001F4CA Key Metrics" table into one dict per metric:

        {"short": "REV", "name": "Revenue from Operations",
         "periods": ["Jun 2026: ₹858.67 Cr", "Mar 2026: ₹857.77 Cr", ...],
         "trend":   "\U0001F7E2 0.10% QoQ, \U0001F680 37.94% YoY"}

    Handles BOTH the table layout and the newer inline \U0001F916 layout — the
    inline one only carries the LATEST period per metric, so the older periods
    come back missing and the caller pads them.
    """
    m = re.search(r"\U0001F4CA Key Metrics\s*(.+?)(?:\n\s*\U0001F916|\n\s*You are receiving|$)",
                  caption or "", re.DOTALL)
    blocks = []
    if m:
        for chunk in re.split(r"\n\s*\n", m.group(1).strip()):
            rows = [r.strip() for r in chunk.split("\n") if r.strip()]
            if not rows:
                continue
            head, periods, trend = rows[0].rstrip(":").strip(), [], ""
            for r in rows[1:]:
                if r.startswith("\U0001F5D3"):                 # period row
                    periods.append(r.lstrip("\U0001F5D3️ ").strip())
                elif "QoQ" in r or "YoY" in r:
                    trend = r
            blocks.append(_metric_block(head, periods, trend))

    # No structured table — the newer summaries pack the whole run of metrics
    # INLINE on the 🤖 line as "<name> (ABBR): <latest> · <trend>".
    # Only the LATEST period survives there; the rest come back empty.
    if not blocks:
        bm = re.search(r"🤖\s*(.+?)(?:\n\s*🔗|\n\s*📎|\n\s*You are receiving|$)",
                       caption or "", re.DOTALL)
        run = re.sub(r"\s+", " ", (bm.group(1) if bm else (caption or ""))).strip()
        for chunk in re.findall(r"[A-Za-z][A-Za-z0-9 .\&()'-]*?\([A-Z]{2,}\):.*?YoY", run):
            head, _, rest = chunk.partition(":")
            tm = re.search(
                r"[🟢🔴🚀🔻➡]?\s*[+\-]?\d[\d.]*\s*%\s*QoQ,.*?YoY",
                rest,
            )
            trend = tm.group(0).strip() if tm else ""
            value = (rest[:tm.start()] if tm else rest).strip().strip("·").strip()
            blocks.append(_metric_block(head.strip(),
                                        [value] if value else [],
                                        trend))
    return blocks


def _result_template_metrics(caption: str, periods_per_metric: int = 3,
                             require_all: bool = False) -> list:
    """
    Build the 12 metric variables of the results template: for each of the three
    FIXED headings (REV / PAT / OPM), `periods_per_metric` period rows followed
    by the change row. A metric the filing didn't report — or a period it didn't
    break out — becomes "—", since Meta rejects an empty variable.

        ["Jun 2026: ₹858.67 Cr", "Mar 2026: ₹857.77 Cr",
         "Jun 2025: ₹622.50 Cr", "\U0001F7E2 0.10% QoQ, \U0001F680 37.94% YoY", ...]

    Returns [] when REVENUE is missing — or, with require_all=True, unless ALL
    THREE headings were filled. Pass require_all when sending to the
    fixed-heading template: its "Profit After Tax (PAT):" / "Operating Profit
    Margin (OPM):" lines are fixed text that render whether or not we have
    those metrics, so a partial fill puts dash rows in front of subscribers.
    The caller then drops to the free-form Stock Bits summary, which shows
    only what the filing actually reported.
    """
    blocks     = _parse_metric_blocks(caption)
    used       = set()
    params     = []
    rev_filled = False
    filled     = 0

    for short, keywords, exclusions in RESULT_TEMPLATE_SLOTS:
        # Take the BEST-ranked unused block for this slot, not merely the
        # first one that matches somehow — a name match must win over an
        # abbreviation match even when the abbreviation appears earlier.
        hit, best_rank, best_i = None, 0, None
        for i, b in enumerate(blocks):
            if i in used:
                continue
            rank = _slot_rank(b, short, keywords, exclusions)
            if rank > best_rank:
                best_rank, best_i = rank, i
        if best_i is not None:
            hit = blocks[best_i]
            used.add(best_i)
        rows  = [p for p in (hit["periods"] if hit else []) if p][:periods_per_metric]
        if rows:
            filled += 1
            if short == "REV":
                rev_filled = True
        rows += ["—"] * (periods_per_metric - len(rows))
        params.extend(rows + [(hit["trend"] if hit else "") or "—"])

    if require_all:
        return params if filled == len(RESULT_TEMPLATE_SLOTS) else []
    return params if rev_filled else []


# Which metrics get the (limited) template blocks when a filing reports more
# than fit. Ordered by what a subscriber cares about most; anything not listed
# keeps its position after these, in the order the filing reported it.
# PBT sits directly behind PAT. With nse_result_bits_3 unapproved, a filing
# reporting REV + PBT + OPM degrades to the TWO-block template, and the old
# ordering (PBT unlisted, so ranked last) kept revenue and margin and dropped
# the PROFIT line entirely — a results alert with no profit figure in it.
RESULT_METRIC_PRIORITY = ("REV", "PAT", "PBT", "OPM", "EBITDA", "EPS")


def _result_metric_blocks(caption: str, periods_per_metric: int = 3,
                          max_blocks: int = 3) -> list:
    """
    The metrics a filing ACTUALLY reported, as up to `max_blocks` render-ready
    blocks for the variable-heading result templates:

        {"heading": "Revenue (REV):",
         "rows":    ["Jun 2026: ₹5,972 Cr", "Mar 2026: ₹5,677 Cr", …],
         "change":  "🟢 +5.20% QoQ, 🚀 +21.10% YoY"}

    Unlike _result_template_metrics (which fills three FIXED headings and pads
    the rest with "—"), this returns only what exists — the caller then routes
    to the approved template with that many blocks, so a filing reporting one
    metric renders one block instead of two rows of dashes. It also means
    metrics outside REV/PAT/OPM (EBITDA, EPS …) can be shown rather than
    dropped, since the heading travels as a variable.

    Period rows are still padded to `periods_per_metric` with "—": a filing
    that breaks out fewer periods is rare, and per-period template variants
    would mean nine approved templates instead of three.
    """
    ordered = []
    for b in _parse_metric_blocks(caption):
        rows = [p for p in b["periods"] if p]
        if not rows:
            continue                       # nothing to show for this metric
        try:
            rank = RESULT_METRIC_PRIORITY.index(b["short"])
        except ValueError:
            rank = len(RESULT_METRIC_PRIORITY)
        ordered.append((rank, len(ordered), b, rows))

    blocks = []
    for _, _, b, rows in sorted(ordered, key=lambda t: (t[0], t[1]))[:max_blocks]:
        rows = rows[:periods_per_metric]
        rows += ["—"] * (periods_per_metric - len(rows))
        heading = f"{b['name']} ({b['short']}):" if b["short"] else f"{b['name']}:"
        blocks.append({"heading": heading, "rows": rows, "change": b["trend"] or "—"})
    return blocks


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
    Return (BODY, summary_ok) — the rich AI summary body (cached if already
    generated), or `fallback_caption` with summary_ok=False when the AI summary
    could not be produced. Caches the time-less body only. `filing_type` and
    `download_url` feed the ⚡ event line and 📎 download link. The cap is well
    above the old template limit so the footer + download link at the end of a
    text message aren't truncated away.
    """
    file_key = os.path.basename(file_path).strip()
    # Only reuse a cached summary that was produced by the CURRENT layout —
    # otherwise a filing summarised before a format change would be re-sent in
    # the old layout forever (this is why results kept arriving as "Stock Bits").
    cache_started = time.monotonic()
    cached = bot_db.get_filing_summary(file_key, SUMMARY_FORMAT_VERSION)
    if cached:
        print(f"⚡ [summary-cache] HIT file={file_key} lookup={time.monotonic()-cache_started:.3f}s")
        return cached, True

    print(f"🧠 [summary] CACHE_MISS file={file_key} company={company!r} filing_type={filing_type!r}")
    summary_started = time.monotonic()
    ai_summary = generate_pdf_summary(file_path, company, filing_type, download_url)
    elapsed = time.monotonic() - summary_started
    if ai_summary:
        trimmed = ai_summary[:3997] + "..." if len(ai_summary) > 4000 else ai_summary
        bot_db.save_filing_summary(file_key, trimmed, SUMMARY_FORMAT_VERSION)
        print(f"✅ [summary] DONE file={file_key} duration={elapsed:.2f}s chars={len(trimmed)}")
        return trimmed, True
    print(f"⚠️ [summary] FAILED file={file_key} duration={elapsed:.2f}s")
    # Failure is NOT cached — the caller decides whether to retry on a later
    # poll or accept the degraded caption.
    return fallback_caption, False


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


def _no_summary_caption(company, symbol, filing_type, download_url="") -> str:
    """
    The alert sent when the AI summary could not be produced at all (LLM error,
    or the whole summary exceeded config.SUMMARY_TIMEOUT_SEC).

    Deliberately built in the SAME 📢/🏢/⚡/🤖/📎 marker layout output.py
    produces, because _parse_stock_bits_parts() reads the template variables
    back OUT of those markers. The old fallback ("📄 *<company>* — <title>")
    carried none of them, so a closed-window send mapped {{4}} (the body) to ""
    — which whatsapp._sanitize_template_param turns into the literal
    "NSE filing" — and {{5}} to the bare equityalerts.in homepage. Subscribers
    received a template with no summary, no filing title and no working link:
    the "template fired but nothing was generated" report. The filing title and
    the real download URL are always available here, so the degraded alert can
    at least say WHAT was filed and link to it.
    """
    lines = [
        "📢 *EquityAlerts Stock Bits!!*", "",
        f"🏢 {company} ({symbol})", "",
        f"⚡ {filing_type}", "",
        f"🤖 {company} has filed \"{filing_type}\" with the exchange. "
        f"An automated summary isn't available for this filing — open it below "
        f"for the full details.", "",
    ]
    if download_url:
        lines += [f"📎 Download filing: {download_url}", ""]
    lines += [
        "You are receiving this stock update per your request on "
        "https://equityalerts.in/portal",
        "Disclaimer: https://equityalerts.in/portal/disclaimer",
    ]
    return "\n".join(lines)


def _full_caption_ex(company, symbol, filing_type, file_path, raw_time,
                     download_url="") -> tuple:
    """
    (caption, summary_ok) — the one-message EquiSense Stock Bits alert, plus
    whether the AI summary actually succeeded. Callers that can afford to wait
    use the flag to retry on a later poll instead of delivering the degraded
    caption; see _should_defer_for_summary.
    """
    # Show a branded short link under our own domain instead of the raw NSE URL.
    download_url = _shorten_download_url(download_url)
    fallback = _no_summary_caption(company, symbol, filing_type, download_url)
    started = time.monotonic()
    body, summary_ok = _build_caption(file_path, fallback, company,
                                      filing_type=filing_type,
                                      download_url=download_url)
    elapsed = time.monotonic() - started
    print(f"[timing] caption DONE symbol={symbol} file={os.path.basename(file_path)} duration={elapsed:.2f}s summary_ok={summary_ok}", flush=True)
    return _caption_with_time(body, company, symbol, raw_time), summary_ok


def _full_caption(company, symbol, filing_type, file_path, raw_time,
                  download_url="") -> str:
    """One-message caption = EquiSense Stock Bits alert (or basic fallback)."""
    caption, _ = _full_caption_ex(company, symbol, filing_type, file_path,
                                  raw_time, download_url)
    return caption


# Per-filing count of failed summary attempts, for the live dispatch path only.
# Deliberately in-process and not persisted: it exists to ride out a transient
# LLM error over the next few polls, and SUMMARY_RETRY_MAX_AGE_SEC is what
# bounds the filing after a restart clears this.
_summary_attempts = {}
_summary_attempts_lock = threading.Lock()


def _should_defer_for_summary(filing_id, age_seconds) -> bool:
    """
    True if this filing should be held back — NOT sent, NOT marked notified —
    so the next poll can retry its AI summary.

    Gives up (returns False, meaning "send the degraded caption now") once the
    filing has burned SUMMARY_RETRY_ATTEMPTS tries or is older than
    SUMMARY_RETRY_MAX_AGE_SEC. A filing whose PDF simply cannot be summarised
    must still reach subscribers; the point is only to stop a two-second API
    blip from costing them the summary permanently.
    """
    max_attempts = getattr(config, "SUMMARY_RETRY_ATTEMPTS", 3)
    max_age      = getattr(config, "SUMMARY_RETRY_MAX_AGE_SEC", 300)

    # Age wins over the counter: it is the bound that survives a restart.
    if age_seconds is not None and age_seconds >= max_age:
        return False

    with _summary_attempts_lock:
        attempts = _summary_attempts.get(filing_id, 0) + 1
        _summary_attempts[filing_id] = attempts

    return attempts < max_attempts


def _clear_summary_attempts(filing_id):
    """Drop a filing's retry counter once it is on its way out, either way."""
    with _summary_attempts_lock:
        _summary_attempts.pop(filing_id, None)


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


def _is_result_caption(caption: str) -> bool:
    """
    True when `caption` is a financial-RESULTS alert (Result Bits), as opposed
    to a routine filing (board meeting notice, Reg 30 disclosure, …).

    The generator brands a message "… Result Bits!!" ONLY when it actually
    detected a financial-results filing (everything else is "… Stock Bits!!"),
    so the title is the reliable signal. The "<period> Results Out" event line
    is not — it varies ("Jun 2026 Results Out", "Results Out", or a heading
    with no "Out" at all) — so it's only a fallback signal alongside it.
    """
    title_line = re.search(r"📢[^\n]*", caption or "")
    return (
        (bool(title_line) and "result bits" in title_line.group(0).lower())
        or bool(re.search(r"results?\s+out", caption or "", re.IGNORECASE))
        or ("💼" in (caption or "") and "📊" in (caption or ""))
    )


def _result_period_key(caption: str) -> str:
    """
    Normalised "reporting period" for a Result Bits caption, e.g. "jun 2026"
    from "💼 <company> | Jun 2026 Results Out". Used to dedup — NSE/BSE often
    publish several PDFs for the same result (standalone + consolidated +
    investor presentation, …), each becoming its own filing row upstream. Each
    is independently summarised, and the AI extraction is inconsistent enough
    across documents that a subscriber must not get 3 conflicting alerts for
    one quarter. Returns "" when no period can be parsed — callers then skip
    period-based dedup entirely rather than dedup on an empty/shared key.
    """
    m = re.search(r"💼[^\n|]*\|\s*(.+)", caption or "")
    event = m.group(1).strip() if m else ""
    if not event:
        return ""
    period = re.sub(r"\s*results?\s+out\s*$", "", event, flags=re.IGNORECASE).strip()
    return period.lower()


_FLATTEN_TITLE = re.compile(r"[^a-z0-9]+")
_BSE_SUBJECT_PREFIX = re.compile(r"^.*?\s-\s\d{4,7}\s-\s")


def _cross_exchange_key(symbol: str, filing_type: str) -> str:
    """
    Stable identity for "this document", independent of which exchange
    published it.

    The same filing reaches us twice — once from the NSE scraper and once from
    the standalone BSE scraper — as two unrelated rows with different pdf_urls,
    so neither the upstream pdf_url constraint nor sent_filings can tell they
    are one document. What they do share is the subject line, modulo BSE's
    Title Casing, doubled apostrophes and "<Company> - <scrip code> - " prefix.
    Flattening to symbol + alphanumerics makes the two copies collide.

    Returns "" when the subject is too short to identify anything (a bare
    "AGM"), which disables suppression for that filing rather than risking a
    false match.
    """
    symbol = (symbol or "").upper().strip()
    title = (filing_type or "").strip()
    if not symbol or not title:
        return ""

    title = _BSE_SUBJECT_PREFIX.sub("", title)
    flat = _FLATTEN_TITLE.sub("", title.lower())
    if len(flat) < 12:
        return ""

    return f"{symbol}|{flat}"


# Minimum extracted characters before a fingerprint is trusted. A near-empty
# text layer (a scan) would otherwise hash a handful of stray glyphs and
# collide with every other scan from the same company.
_FINGERPRINT_MIN_CHARS = 400

# file_path -> fingerprint. The backfill loop reaches the same PDF once per
# subscriber, and re-parsing it each time would multiply the cost by the
# subscriber count for no gain.
_FINGERPRINT_CACHE: dict[str, str] = {}


def _document_fingerprint(file_path: str) -> str:
    """
    A hash of the PDF's own text, identifying the DOCUMENT rather than the
    words an exchange chose to file it under. "" when it can't be computed.

    The subject line cannot carry this job. NSE and BSE describe one filing
    from their own taxonomies — the JINDALSTEL analyst-meet intimation of
    2026-08-13 arrived as "Analysts/Institutional Investor Meet/Con. Call
    Updates" from NSE and "Announcement under Regulation 30 (LODR)-Analyst /
    Investor Meet - Intimation" from BSE. Those share two tokens out of
    fourteen; a threshold loose enough to unite them also unites filings that
    are genuinely different, so no amount of fuzzy matching on the subject
    separates the two cases. The documents behind them are the same document.

    Uses the pypdf text layer ONLY — no pdfplumber fallback, no OCR. This runs
    in the delivery path where latency is the whole point of the BSE fast loop,
    and a filing whose text layer is unusable simply gets no fingerprint and
    falls back to subject matching, exactly as before.
    """
    if not file_path:
        return ""
    if file_path in _FINGERPRINT_CACHE:
        return _FINGERPRINT_CACHE[file_path]

    fingerprint = ""
    try:
        import output
        pages = output._extract_pages_pypdf(file_path)
        if pages:
            flat = _FLATTEN_TITLE.sub("", "".join(pages).lower())
            if len(flat) >= _FINGERPRINT_MIN_CHARS:
                fingerprint = hashlib.sha1(flat.encode("utf-8")).hexdigest()[:16]
    except Exception as e:
        print(f"⚠️  fingerprint failed for {os.path.basename(file_path)}: {e}")

    _FINGERPRINT_CACHE[file_path] = fingerprint
    return fingerprint


def _dedup_keys(symbol: str, filing_type: str, file_path: str) -> list:
    """
    Every key under which this filing may already have been delivered, best
    evidence first.

    Two independent identities, because each covers the other's blind spot:

      fp:  the document's own text. Unites the same filing across exchanges
           however differently they title it, and — unlike a looser subject
           match — never unites two filings that merely sound alike.
      subject: the historical key. Still needed for filings whose text layer
           is a scan, where no fingerprint can be computed.

    A hit on EITHER suppresses, and BOTH are recorded on a successful send.
    Adding the fingerprint can only suppress more than before, never less:
    the subject key still fires exactly where it fired previously.
    """
    keys = []
    fingerprint = _document_fingerprint(file_path)
    if fingerprint:
        keys.append(f"{(symbol or '').upper().strip()}|fp:{fingerprint}")
    subject_key = _cross_exchange_key(symbol, filing_type)
    if subject_key:
        keys.append(subject_key)
    return keys


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
    # Branded title (📢 *EquityAlerts Stock/Result Bits!!*) — carried as a VARIABLE
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
    # The download link may sit under 📎 OR 🔗, on the same line or the next one.
    um = (re.search(r"Download filing:\s*(?:\n\s*)?(https?://\S+)", text)
          or re.search(r"(?:📎|🔗)[^\n]*?(https?://\S+)", text)
          or re.search(r"(https?://equityalerts\.in/t/\S+)", text))
    url = um.group(1) if um else ""
    return title, company, event, body, url, filed


def resolve_template_send(caption: str) -> dict:
    """
    PURE decision: given a caption, which approved WhatsApp template a
    closed-window (or forced-template) delivery would use, and what its
    rendered {{n}} params would be. No DB access, no network call — this is
    the exact routing logic _try_send() uses to actually send, extracted so
    a preview/testing tool can call it and see precisely what production
    would do, without sending a real message.

    Returns {"route": "result_count" | "result_legacy" | "stock_bits",
             "template_name": str, "params": [str, ...]}.
    `template_name` is "" when no template is configured for that route.
    """
    title, company, event, body, url, filed = _parse_stock_bits_parts(caption)

    if _is_result_caption(caption):
        periods = int(getattr(config, "TEMPLATE_RESULT_PERIOD_SLOTS", 3))
        cline   = (f"{company} | {event}" if event else company) or "Results Out"

        # ── Preferred: a template sized to the metrics we actually have.
        blocks     = _result_metric_blocks(caption, periods, max_blocks=3)
        result_tpl = getattr(config, "TEMPLATE_RESULT_NAME", "") or ""
        # The legacy fixed-heading template covers the 3 × REV/PAT/OPM case
        # correctly, so try it BEFORE degrading — degrading first would drop
        # OPM from a filing that reported all three.
        legacy_ok = bool(
            result_tpl and len(blocks) == 3
            and _result_template_metrics(caption, periods, require_all=True)
        )
        count_tpl = ""
        if blocks and hasattr(config, "result_template_for"):
            count_tpl = config.result_template_for(len(blocks))
            if not count_tpl and not legacy_ok:
                for n in range(len(blocks) - 1, 0, -1):
                    count_tpl = config.result_template_for(n)
                    if count_tpl:
                        blocks = blocks[:n]
                        break
        if count_tpl:
            params = [cline, filed or "n/a"]
            for b in blocks:
                params.append(b["heading"])
                params.extend(b["rows"])
                params.append(b["change"])
            params.append(url or "https://equityalerts.in")
            return {"route": "result_count", "template_name": count_tpl, "params": params}

        # ── Fallback: the fixed-heading REV/PAT/OPM template.
        metrics = (_result_template_metrics(caption, periods, require_all=True)
                   if result_tpl else [])
        if metrics:
            params = [cline, filed or "n/a", *metrics, url or "https://equityalerts.in"]
            return {"route": "result_legacy", "template_name": result_tpl, "params": params}
        # Neither result template matched (e.g. only 1-2 metrics but no
        # per-count template configured for that size AND not all 3 fixed
        # slots filled) — falls through to the Stock Bits template below,
        # same as the original inline logic.

    # The branded TITLE and the 🏢/⚡/🤖 emojis ride INSIDE the variable
    # values (not the approved template's fixed text) — so the template's
    # fixed text stays neutral/Utility while the "📢 EquityAlerts … Bits!!"
    # header and markers still show. Meta's category check looks at the
    # fixed text only, so this is safe.
    title = title or "📢 *EquityAlerts Stock Bits!!*"
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
    return {
        "route": "stock_bits",
        "template_name": getattr(config, "TEMPLATE_NAME", "") or "",
        "params": [title, company, event, body, url],
    }


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
            # Routing (which template + rendered params) is decided by the
            # PURE resolve_template_send() so preview/testing tooling can
            # compute the identical decision without sending anything.
            decision = resolve_template_send(caption)
            wamid = whatsapp.send_text_template(
                phone, decision["params"], template_name=decision["template_name"]
            )
            bot_db.mark_batch_template_sent(phone)
            bot_db.mark_filing_sent(phone, file_key)
            bot_db.remove_pending_filing(phone, file_key)
            if wamid:
                bot_db.store_wamid(wamid, phone, file_key, file_path, caption,
                                   filing_id=filing_id, channel="template")
            if decision["route"] in ("result_count", "result_legacy"):
                whatsapp._safe_print(f"[OK] Sent RESULT template to {phone} for {file_key}")
            else:
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
    _cycle_started = time.monotonic()
    print("[timing] live_cycle START", flush=True)
    filings = fetch_new_filings()
    filings = _dedup_by_filename(filings)
    if not filings:
        return

    # Subscriber membership is stable during one polling cycle.
    # Fetch all symbols with ONE PostgreSQL query.
    symbols = [(f.get("symbol") or "").upper().strip() for f in filings]
    subscriber_map = get_subscribers_for_symbols_pg(symbols)
    if subscriber_map is None:
        print("⚠️ [timing] Subscriber batch lookup failed; leaving filings for next poll.")
        return
    print(f"⏱ [timing] live_batch filings={len(filings)} symbols={len(set(symbols))}")

    # ── Phase 1: resolve subscribers / drop undeliverable filings ────────
    jobs = []
    for filing in filings:
        filing_id   = filing["filing_id"]
        symbol      = (filing.get("symbol") or "").upper().strip()
        company     = get_company_display_name(symbol)
        file_path   = filing["file_path"]
        filing_type = filing.get("filing_type") or "New Filing"

        subscribers = subscriber_map.get(symbol, [])
        print(f"🔎 [timing] subscribers symbol={symbol} count={len(subscribers)}")
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
            "exchange":     filing.get("exchange") or "NSE",
            "raw_time":     filing.get("created_at"),
            "age_seconds":  filing.get("age_seconds"),
            "subscribers":  subscribers,
            "file_key":     os.path.basename(file_path).strip(),
        })

    if not jobs:
        return

    print(f"⏱ Phase 1 (DB/subscribers): {time.monotonic() - _cycle_started:.2f}s")
    # ── Phase 2: build all captions concurrently (summary + exchange time) ─
    _summary_phase_started = time.monotonic()
    futures = {
        j["file_key"]: _caption_pool.submit(
            _full_caption_ex, j["company"], j["symbol"], j["filing_type"],
            j["file_path"], j["raw_time"], j["download_url"],
        )
        for j in jobs
    }

    print(f"⏱ [timing] caption_jobs_submitted count={len(futures)} submit={time.monotonic()-_summary_phase_started:.3f}s")
    # ── Phase 3: deliver READY captions immediately ──────────────────────
    # Avoid head-of-line blocking: a slow old PDF must not hold a ready new filing.
    _delivery_started = time.monotonic()
    future_to_job = {futures[j["file_key"]]: j for j in jobs}
    completed = 0
    for future in as_completed(future_to_job):
        j = future_to_job[future]
        completed += 1
        ready_at = time.monotonic() - _summary_phase_started
        try:
            caption, summary_ok = future.result()
        except Exception as e:
            print(f"❌ Caption build failed for {j['file_key']}: {e}")
            caption = _caption_with_time(
                f"📄 *{j['company']}* — {j['filing_type']}\n🏦 Symbol: {j['symbol']}",
                j["company"], j["symbol"], j["raw_time"],
            )
            summary_ok = False
        print(f"🚦 [ready] {j['symbol']} file={j['file_key']} completed={completed}/{len(futures)} ready_after={ready_at:.2f}s summary_ok={summary_ok}")

        # The AI summary failed. Leave the filing is_notified=FALSE and send
        # nothing this round, so the next poll re-summarises it — the LLM
        # errors behind this (a 429 in a results-day burst, a timeout) clear in
        # seconds, and delivering now would lock in the degraded caption
        # forever. Bounded by attempts and age; once those run out the filing
        # goes out with the fallback exactly as before.
        if not summary_ok and _should_defer_for_summary(
            j["filing_id"], j.get("age_seconds")
        ):
            print(f"⏳ Summary unavailable for {j['symbol']} '{j['filing_type']}' — "
                  f"holding delivery for the next poll.")
            continue

        if not summary_ok:
            print(f"⚠️  Summary still unavailable for {j['symbol']} "
                  f"'{j['filing_type']}' after retries — sending basic caption.")

        _clear_summary_attempts(j["filing_id"])

        age = j.get("age_seconds")
        age_note = f" [saved {age}s ago by scraper]" if age is not None else ""
        print(f"📤 Sending {j['symbol']} '{j['filing_type']}' via {j['exchange']} "
              f"to {len(j['subscribers'])} subscriber(s)...{age_note}")

        # NSE/BSE often file several PDFs for one results event (standalone +
        # consolidated + investor presentation, corrigenda, ...), each a
        # separate row upstream. Each is summarised independently and the AI
        # extraction is inconsistent enough across documents that subscribers
        # must not get one alert per PDF — cap it to one per symbol+period.
        # period_key == "" for non-results filings, which skips this entirely.
        period_key = _result_period_key(caption) if _is_result_caption(caption) else ""

        # NSE and BSE both publish the same document. Whichever exchange we
        # ingested FIRST is the one that gets delivered — usually BSE, which is
        # exactly why it is scraped on its own tighter loop.
        exchange_keys = _dedup_keys(j["symbol"], j["filing_type"], j["file_path"])
        # See the matching diagnostic in deliver_backfill_for_subscribers —
        # a duplicate can arrive through either path, so both log the keys.
        print(f"🔑 {j['symbol']} [{j.get('exchange') or '?'}] "
              f"title={j['filing_type']!r} keys={exchange_keys or '(none)'}")

        all_sent = True
        for phone in j["subscribers"]:
            if bot_db.is_filing_sent(phone, j["file_key"]):
                print(f"ℹ️  Already sent filing {j['file_key']} to {phone}, skipping.")
                continue
            if period_key and bot_db.is_result_period_sent(phone, j["symbol"], period_key):
                print(f"ℹ️  Already sent {j['symbol']} results for '{period_key}' to {phone} "
                      f"(different filing PDF) — skipping duplicate.")
                bot_db.mark_filing_sent(phone, j["file_key"])
                continue
            hit = next((k for k in exchange_keys
                        if bot_db.is_cross_exchange_sent(phone, k, j["raw_time"])), None)
            if hit:
                print(f"ℹ️  {j['symbol']} '{j['filing_type']}' already delivered to "
                      f"{phone} from the other exchange — skipping duplicate "
                      f"(matched {hit}).")
                bot_db.mark_filing_sent(phone, j["file_key"])
                continue
            # Only marks sent on confirmed success; queues on failure.
            ok = _try_send(phone, j["file_path"], caption, j["file_key"],
                           filing_id=j["filing_id"], template_params=[j["company"]])
            if ok and period_key:
                bot_db.mark_result_period_sent(phone, j["symbol"], period_key)
            if ok:
                for k in exchange_keys:
                    bot_db.mark_cross_exchange_sent(
                        phone, k, j.get("exchange") or "", j["raw_time"]
                    )
            if not ok:
                all_sent = False

        # Mark notified in PG only when EVERY subscriber got it. Otherwise the
        # filing stays is_notified=FALSE and is retried on the next poll for
        # anyone still missing it (already-sent users are skipped above).
        if all_sent:
            mark_notified_in_pg(j["filing_id"])

    print(
        f"🏁 [timing] cycle_complete total={time.monotonic()-_cycle_started:.2f}s "
        f"filings={len(filings)} jobs={len(jobs)} "
        f"caption_phase={time.monotonic()-_summary_phase_started:.2f}s "
        f"delivery_phase={time.monotonic()-_delivery_started:.2f}s"
    )


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
                    SELECT id, title, local_path, pdf_url, announcement_time,
                           COALESCE(exchange, 'NSE') AS exchange
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

                    # Same symbol+period dedup as process_new_filings — the
                    # backfill window can contain several PDFs for one results
                    # event too, and a brand-new subscriber shouldn't get one
                    # alert per PDF for their first quarter either.
                    period_key = _result_period_key(caption) if _is_result_caption(caption) else ""
                    if period_key and bot_db.is_result_period_sent(phone, symbol, period_key):
                        bot_db.mark_filing_sent(phone, file_key)
                        continue

                    # The backfill window spans both feeds, so it can hold the
                    # NSE and BSE copies of one document — a brand-new
                    # subscriber must not be welcomed with each filing twice.
                    filed_at = row["announcement_time"]
                    exchange_keys = _dedup_keys(symbol, row.get("title") or "",
                                                file_path)
                    # Log what each copy identifies as, so a miss stays
                    # diagnosable from the deployment logs alone — no DB
                    # access needed. This is how the subject-only key was
                    # caught failing on 2026-08-13.
                    print(f"🔑 {symbol} [{row.get('exchange') or '?'}] "
                          f"title={(row.get('title') or '')!r} "
                          f"keys={exchange_keys or '(none)'}")
                    hit = next((k for k in exchange_keys
                                if bot_db.is_cross_exchange_sent(phone, k, filed_at)),
                               None)
                    if hit:
                        print(f"ℹ️  {symbol} already delivered to {phone} from the "
                              f"other exchange — skipping duplicate (matched {hit}).")
                        bot_db.mark_filing_sent(phone, file_key)
                        continue

                    # Only marks sent on confirmed success; queues on failure.
                    if _try_send(phone, file_path, caption, file_key,
                                 filing_id=row["id"], template_params=[name]):
                        if period_key:
                            bot_db.mark_result_period_sent(phone, symbol, period_key)
                        for k in exchange_keys:
                            bot_db.mark_cross_exchange_sent(
                                phone, k,
                                row.get("exchange") or "", filed_at
                            )
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