# ============================================================
#  database.py  —  SQLite for user subscriptions & states
#  (Separate from your JS scraper's PostgreSQL database)
#
#  ADDED: pending_filings table + helpers. When a send fails
#  because the 24-hour window is closed (error 131047), the
#  filing is parked here and re-sent the next time the user
#  messages the bot (which reopens the window).
# ============================================================
import sqlite3
import threading

import os
BOT_DB_PATH = os.environ.get("BOT_DB_PATH", "bot_data.db")
_lock = threading.Lock()


def get_conn():
    conn = sqlite3.connect(BOT_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_sent_filings(conn):
    """
    Detect and fix the legacy sent_filings schema (filing_id-only PK with no phone column,
    or phone added as plain column via ALTER TABLE). Drop and recreate with the correct
    composite PK (phone, filing_id) so per-user dedup works properly.
    """
    cur = conn.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='sent_filings'")
    row = cur.fetchone()
    if row is None:
        return  # table doesn't exist yet — will be created below

    schema_sql = row[0] or ""
    if "PRIMARY KEY (phone, filing_id)" not in schema_sql:
        print("⚠️  sent_filings schema is outdated — migrating to (phone, filing_id) PK...")
        cur.execute("DROP TABLE IF EXISTS sent_filings")
        cur.execute("""
            CREATE TABLE sent_filings (
                phone     TEXT,
                filing_id TEXT,
                sent_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (phone, filing_id)
            )
        """)
        conn.commit()
        print("✅ sent_filings migrated — old dedup records cleared (fresh start).")


def init_db():
    """Call once at startup to create tables."""
    with _lock:
        conn = get_conn()
        cur  = conn.cursor()

        _migrate_sent_filings(conn)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                phone      TEXT PRIMARY KEY,
                state      TEXT DEFAULT 'idle',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Track the 24h window per user:
        #   last_inbound_at    — when the user last messaged us (opens a window).
        #   window_reminder_at — when we last sent the pre-close reminder for the
        #                        CURRENT window (reset to NULL on every inbound),
        #                        so the reminder fires at most once per window.
        #   template_batch_at  — when we sent the SINGLE allowed template for the
        #                        CURRENT closed window (reset to NULL on every
        #                        inbound). Caps templates to one per closed window
        #                        so users never get a stack of them.
        user_cols = [r[1] for r in cur.execute("PRAGMA table_info(users)").fetchall()]
        if "last_inbound_at" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN last_inbound_at DATETIME")
        if "window_reminder_at" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN window_reminder_at DATETIME")
        if "template_batch_at" not in user_cols:
            cur.execute("ALTER TABLE users ADD COLUMN template_batch_at DATETIME")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                phone  TEXT,
                symbol TEXT,
                PRIMARY KEY (phone, symbol)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sent_filings (
                phone     TEXT,
                filing_id TEXT,
                sent_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (phone, filing_id)
            )
        """)

        # NEW: filings that could not be delivered (e.g. 24h window closed).
        # filing_id is the PG announcements.id when known (so we can mark
        # PG as notified later), or NULL for backfill-sourced rows.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pending_filings (
                phone      TEXT,
                file_key   TEXT,
                file_path  TEXT,
                caption    TEXT,
                filing_id  TEXT,
                attempts   INTEGER  DEFAULT 0,
                last_error TEXT,
                queued_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (phone, file_key)
            )
        """)

        # Maps Meta wamid → filing so status callbacks can undo a false
        # "sent" marking when Meta later reports 131047 delivery failure.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS wamid_tracking (
                wamid      TEXT PRIMARY KEY,
                phone      TEXT,
                file_key   TEXT,
                file_path  TEXT,
                caption    TEXT,
                filing_id  TEXT,
                channel    TEXT DEFAULT 'freeform',
                sent_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                handled_at DATETIME DEFAULT NULL
            )
        """)

        # Add `channel` to a pre-existing wamid_tracking table (older DBs).
        cols = [r[1] for r in cur.execute("PRAGMA table_info(wamid_tracking)").fetchall()]
        if "channel" not in cols:
            print("⚠️  Adding channel column to wamid_tracking...")
            cur.execute("ALTER TABLE wamid_tracking ADD COLUMN channel TEXT DEFAULT 'freeform'")

        # Caches the rich (free-form) AI summary per filing so it can be
        # re-sent verbatim when a silent subscriber taps the "Full Summary"
        # quick-reply button on the template (which reopens the 24h window).
        cur.execute("""
            CREATE TABLE IF NOT EXISTS filing_summaries (
                file_key   TEXT PRIMARY KEY,
                summary    TEXT,
                fmt        INTEGER  DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # `fmt` records the message-layout version that produced the cached text.
        # Older DBs predate it; default them to 1 so a layout bump (see
        # db_watcher.SUMMARY_FORMAT_VERSION) regenerates them instead of
        # re-sending a stale, old-format summary.
        sum_cols = [r[1] for r in cur.execute("PRAGMA table_info(filing_summaries)").fetchall()]
        if "fmt" not in sum_cols:
            print("⚠️  Adding fmt column to filing_summaries...")
            cur.execute("ALTER TABLE filing_summaries ADD COLUMN fmt INTEGER DEFAULT 1")

        # Branded short links: code -> real (NSE) download URL, so the alert can
        # show https://equityalerts.in/t/<code> instead of the long nseindia URL.
        # The bot's /t/<code> route resolves the code and 302-redirects.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS short_links (
                code       TEXT PRIMARY KEY,
                url        TEXT NOT NULL,
                clicks     INTEGER  DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Durable log of every WhatsApp TEMPLATE message actually sent (for the
        # Central Dashboard's "templates sent today" stat). wamid_tracking also
        # records channel="template", but those rows are hard-deleted ~30 minutes
        # after Meta's delivery callback (see remove_wamid) so they can't answer
        # "how many today" — this table is never pruned. Written from
        # mark_batch_template_sent(), which every successful template send
        # already calls.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS template_sends_log (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                phone   TEXT,
                sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # NSE/BSE often publish several PDFs for one results event (standalone
        # + consolidated + investor presentation, corrigenda, ...) as separate
        # filing rows upstream. Each is summarised independently, and the AI
        # extraction is inconsistent enough across documents that a subscriber
        # must not get one Result Bits alert per PDF. This tracks the first
        # symbol+period alert actually delivered per phone so later filings for
        # the SAME quarter are suppressed regardless of which PDF produced them.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sent_result_periods (
                phone   TEXT,
                symbol  TEXT,
                period  TEXT,
                sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (phone, symbol, period)
            )
        """)

        conn.commit()
        conn.close()
    print("✅ Bot SQLite database ready.")


# ── Branded short download links (/t/<code> redirect) ─────────

def save_short_link(code: str, url: str):
    """Store a code -> URL mapping (idempotent — same code keeps its URL)."""
    if not code or not url:
        return
    with _lock:
        conn = get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO short_links (code, url) VALUES (?, ?)",
            (code, url)
        )
        conn.commit()
        conn.close()


def get_short_link(code: str):
    """Return the real URL for a short code, or None."""
    with _lock:
        conn = get_conn()
        row  = conn.execute(
            "SELECT url FROM short_links WHERE code=?", (code,)
        ).fetchone()
        conn.close()
        return row["url"] if row else None


def increment_short_link_click(code: str):
    """Bump the click counter for a short code (best-effort analytics)."""
    with _lock:
        conn = get_conn()
        conn.execute(
            "UPDATE short_links SET clicks = clicks + 1 WHERE code=?", (code,)
        )
        conn.commit()
        conn.close()


# ── User state (tracks conversation step) ────────────────────

def get_state(phone: str) -> str:
    with _lock:
        conn = get_conn()
        row  = conn.execute("SELECT state FROM users WHERE phone=?", (phone,)).fetchone()
        conn.close()
        return row["state"] if row else "new"


def set_state(phone: str, state: str):
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO users (phone, state) VALUES (?, ?)
            ON CONFLICT(phone) DO UPDATE SET state=excluded.state
        """, (phone, state))
        conn.commit()
        conn.close()


# ── 24h-window tracking (pre-close reminder + template cap) ───

def record_inbound(phone: str):
    """
    Record that `phone` just sent us a message. Each inbound message opens a
    fresh 24-hour window, so we stamp last_inbound_at and clear
    window_reminder_at + template_batch_at — letting the pre-close reminder fire
    again, and resetting the one-template-per-window cap, for this new window.
    """
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO users (phone, last_inbound_at, window_reminder_at, template_batch_at)
            VALUES (?, CURRENT_TIMESTAMP, NULL, NULL)
            ON CONFLICT(phone) DO UPDATE SET
                last_inbound_at    = CURRENT_TIMESTAMP,
                window_reminder_at = NULL,
                template_batch_at  = NULL
        """, (phone,))
        conn.commit()
        conn.close()


def get_users_due_for_window_reminder(min_age_hours: float,
                                      max_age_hours: float) -> list:
    """
    Phones whose 24-hour window is about to close: their last inbound message
    is between `min_age_hours` and `max_age_hours` old, and they have not yet
    been reminded for the current window. (UTC throughout.)
    """
    with _lock:
        conn = get_conn()
        rows = conn.execute("""
            SELECT phone FROM users
            WHERE last_inbound_at IS NOT NULL
              AND window_reminder_at IS NULL
              AND last_inbound_at <= datetime('now', ?)
              AND last_inbound_at >  datetime('now', ?)
        """, (f"-{min_age_hours} hours", f"-{max_age_hours} hours")).fetchall()
        conn.close()
        return [r["phone"] for r in rows]


def mark_window_reminder_sent(phone: str):
    """Stamp that the pre-close reminder was sent for this user's current window."""
    with _lock:
        conn = get_conn()
        conn.execute(
            "UPDATE users SET window_reminder_at = CURRENT_TIMESTAMP WHERE phone=?",
            (phone,)
        )
        conn.commit()
        conn.close()


def window_open(phone: str) -> bool:
    """
    Best-effort check of whether the user's 24-hour window is still open, based
    on our own record of their last inbound message. True only if they messaged
    us within the last 24 hours. (Meta is still the source of truth on the actual
    send — this just lets us decide up front whether a filing is template-bound.)
    """
    with _lock:
        conn = get_conn()
        row = conn.execute("""
            SELECT 1 FROM users
            WHERE phone=? AND last_inbound_at IS NOT NULL
              AND last_inbound_at > datetime('now', '-24 hours')
        """, (phone,)).fetchone()
        conn.close()
        return row is not None


def can_send_batch_template(phone: str) -> bool:
    """
    True if we have NOT yet sent the one allowed template for this user's current
    closed window. Used to cap templates to a single message per closed window so
    a burst of filings never arrives as a stack of templates — the rest are
    queued in pending_filings and flushed (free-form) when the user re-engages.
    """
    with _lock:
        conn = get_conn()
        row = conn.execute(
            "SELECT 1 FROM users WHERE phone=? AND template_batch_at IS NOT NULL",
            (phone,)
        ).fetchone()
        conn.close()
        return row is None


def mark_batch_template_sent(phone: str):
    """
    Stamp that this user has received their single template for the current
    closed window, and append a durable entry to template_sends_log (used by
    count_templates_sent_today for the admin dashboard). Every successful
    template send in db_watcher.py calls this exactly once, so it doubles as
    the one place that logs "a template was sent" without touching each call
    site individually.
    """
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO users (phone, template_batch_at)
            VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT(phone) DO UPDATE SET template_batch_at = CURRENT_TIMESTAMP
        """, (phone,))
        conn.execute(
            "INSERT INTO template_sends_log (phone) VALUES (?)",
            (phone,)
        )
        conn.commit()
        conn.close()


def count_templates_sent_today() -> int:
    """
    Number of WhatsApp template messages sent since midnight (UTC — matches
    CURRENT_TIMESTAMP's own timezone, so "today" is computed consistently).
    Backs the Central Dashboard's "WhatsApp templates sent today" stat.
    """
    with _lock:
        conn = get_conn()
        row = conn.execute("""
            SELECT COUNT(*) AS count
            FROM template_sends_log
            WHERE date(sent_at) = date('now')
        """).fetchone()
        conn.close()
        return row["count"] if row else 0


# ── Subscriptions ─────────────────────────────────────────────

def get_subscriptions(phone: str) -> list:
    with _lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT symbol FROM subscriptions WHERE phone=?", (phone,)
        ).fetchall()
        conn.close()
        return [r["symbol"] for r in rows]


def add_subscription(phone: str, symbol: str):
    with _lock:
        conn = get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO subscriptions (phone, symbol) VALUES (?, ?)",
            (phone, symbol)
        )
        conn.commit()
        conn.close()


def remove_subscription(phone: str, symbol: str):
    with _lock:
        conn = get_conn()
        conn.execute(
            "DELETE FROM subscriptions WHERE phone=? AND symbol=?",
            (phone, symbol)
        )
        conn.commit()
        conn.close()


def get_subscribers_for_symbol(symbol: str) -> list:
    """Returns all phone numbers subscribed to a given company symbol."""
    with _lock:
        conn  = get_conn()
        rows  = conn.execute(
            "SELECT phone FROM subscriptions WHERE symbol=?", (symbol,)
        ).fetchall()
        conn.close()
        return [r["phone"] for r in rows]


# ── Sent filings tracker ──────────────────────────────────────

def is_filing_sent(phone: str, filing_id: str) -> bool:
    """Returns True if this filing was already sent to this specific phone."""
    with _lock:
        conn = get_conn()
        row  = conn.execute(
            "SELECT 1 FROM sent_filings WHERE phone=? AND filing_id=?",
            (phone, str(filing_id))
        ).fetchone()
        conn.close()
        return row is not None


def mark_filing_sent(phone: str, filing_id: str):
    """Mark a filing as sent to a specific phone number."""
    with _lock:
        conn = get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO sent_filings (phone, filing_id) VALUES (?, ?)",
            (phone, str(filing_id))
        )
        conn.commit()
        conn.close()


def get_deliveries_for_phone(phone: str, limit: int = 200) -> list:
    """
    Every filing actually delivered to one phone, most recent first — backs
    the Central Dashboard's per-user "Alerts delivered" view.

    `filing_id` here is the PDF's basename (see db_watcher's
    `file_key = os.path.basename(file_path)`), NOT the scraper's
    announcements.id — the caller joins it back to announcement metadata
    (company, title) via announcements.local_path, since that table lives in
    a different database entirely.

    The (phone, filing_id) primary key makes this an index scan on phone.
    """
    with _lock:
        conn = get_conn()
        rows = conn.execute(
            """
            SELECT filing_id, sent_at
            FROM sent_filings
            WHERE phone = ?
            ORDER BY sent_at DESC
            LIMIT ?
            """,
            (phone, int(limit))
        ).fetchall()
        conn.close()
        return [{"filingKey": r["filing_id"], "sentAt": r["sent_at"]} for r in rows]


# ── Sent RESULT periods tracker (symbol+quarter, not per-PDF) ──

def is_result_period_sent(phone: str, symbol: str, period: str) -> bool:
    """True if this phone already received a Result Bits alert for this
    symbol+reporting-period (from ANY of the possibly-several filing PDFs)."""
    if not period:
        return False
    with _lock:
        conn = get_conn()
        row  = conn.execute(
            "SELECT 1 FROM sent_result_periods WHERE phone=? AND symbol=? AND period=?",
            (phone, symbol, period)
        ).fetchone()
        conn.close()
        return row is not None


def mark_result_period_sent(phone: str, symbol: str, period: str):
    """Record that this phone received the results alert for symbol+period."""
    if not period:
        return
    with _lock:
        conn = get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO sent_result_periods (phone, symbol, period) VALUES (?, ?, ?)",
            (phone, symbol, period)
        )
        conn.commit()
        conn.close()


# ── Pending (retry) queue ─────────────────────────────────────

def queue_pending_filing(phone: str, file_key: str, file_path: str,
                         caption: str = "", filing_id=None, error: str = ""):
    """
    Park a filing that could not be delivered (e.g. 24-hour window closed).
    Idempotent on (phone, file_key); bumps the attempt counter on re-queue.
    """
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO pending_filings
                (phone, file_key, file_path, caption, filing_id, attempts, last_error)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(phone, file_key) DO UPDATE SET
                attempts   = pending_filings.attempts + 1,
                last_error = excluded.last_error,
                caption    = excluded.caption,
                file_path  = excluded.file_path,
                filing_id  = COALESCE(excluded.filing_id, pending_filings.filing_id)
        """, (phone, file_key, file_path, caption,
              str(filing_id) if filing_id is not None else None, error))
        conn.commit()
        conn.close()


def get_pending_filings(phone: str) -> list:
    """Return all pending (undelivered) filings for a phone, oldest first."""
    with _lock:
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM pending_filings WHERE phone=? ORDER BY queued_at ASC",
            (phone,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def remove_pending_filing(phone: str, file_key: str):
    """Remove a filing from the retry queue once it has been delivered."""
    with _lock:
        conn = get_conn()
        conn.execute(
            "DELETE FROM pending_filings WHERE phone=? AND file_key=?",
            (phone, file_key)
        )
        conn.commit()
        conn.close()


def is_filing_pending(phone: str, file_key: str) -> bool:
    with _lock:
        conn = get_conn()
        row  = conn.execute(
            "SELECT 1 FROM pending_filings WHERE phone=? AND file_key=?",
            (phone, file_key)
        ).fetchone()
        conn.close()
        return row is not None


# ── Sent filings: undo helper ─────────────────────────────────

def unmark_filing_sent(phone: str, filing_id: str):
    """Remove a filing from sent_filings so it can be retried."""
    with _lock:
        conn = get_conn()
        conn.execute(
            "DELETE FROM sent_filings WHERE phone=? AND filing_id=?",
            (phone, str(filing_id))
        )
        conn.commit()
        conn.close()


# ── wamid tracking (status callback support) ─────────────────

def store_wamid(wamid: str, phone: str, file_key: str,
                file_path: str, caption: str, filing_id=None,
                channel: str = "freeform"):
    """Store a Meta message ID → filing mapping for status callback lookups.

    `channel` records HOW this message was sent ('freeform' or 'template') so
    the status-callback handler can avoid retrying a failed template as yet
    another template (which would never succeed and would loop forever).
    """
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO wamid_tracking
                (wamid, phone, file_key, file_path, caption, filing_id, channel)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (wamid, phone, file_key, file_path, caption,
              str(filing_id) if filing_id is not None else None, channel))
        conn.commit()
        conn.close()


def get_wamid_info(wamid: str):
    """Return the filing info for a wamid, or None if not tracked or already handled."""
    with _lock:
        conn = get_conn()
        row  = conn.execute(
            "SELECT * FROM wamid_tracking WHERE wamid=? AND handled_at IS NULL",
            (wamid,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def remove_wamid(wamid: str):
    """
    Soft-delete: mark wamid as handled rather than deleting it immediately.
    This prevents duplicate webhook events (Meta re-delivers occasionally)
    from losing the tracking info before the second callback is processed.
    Rows older than 30 minutes are fully pruned on each call.
    """
    with _lock:
        conn = get_conn()
        # Soft-delete this wamid.
        conn.execute(
            "UPDATE wamid_tracking SET handled_at = CURRENT_TIMESTAMP WHERE wamid = ?",
            (wamid,)
        )
        # Hard-delete rows handled more than 30 minutes ago (cleanup).
        conn.execute("""
            DELETE FROM wamid_tracking
            WHERE handled_at IS NOT NULL
              AND handled_at <= datetime('now', '-30 minutes')
        """)
        conn.commit()
        conn.close()


# ── Filing summary cache (for the "Full Summary" button) ─────

def save_filing_summary(file_key: str, summary: str, fmt: int = 1):
    """
    Cache the rich AI summary for a filing. `fmt` records WHICH message layout
    generated it (see db_watcher.SUMMARY_FORMAT_VERSION) so a layout change
    invalidates stale entries instead of silently re-sending the old text.
    """
    if not file_key or not summary:
        return
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT INTO filing_summaries (file_key, summary, fmt) VALUES (?, ?, ?)
            ON CONFLICT(file_key) DO UPDATE SET
                summary = excluded.summary,
                fmt     = excluded.fmt
        """, (file_key, summary, int(fmt)))
        conn.commit()
        conn.close()


def get_filing_summary(file_key: str, fmt: int = None):
    """
    Return the cached summary for a filing, or None.

    When `fmt` is given, only return the entry if it was generated by that same
    message-layout version — otherwise it's stale and the caller regenerates.
    Callers that just want whatever text we have (e.g. the Full-Summary reply)
    omit `fmt`.
    """
    with _lock:
        conn = get_conn()
        if fmt is None:
            row = conn.execute(
                "SELECT summary FROM filing_summaries WHERE file_key=?", (file_key,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT summary FROM filing_summaries WHERE file_key=? AND fmt=?",
                (file_key, int(fmt))
            ).fetchone()
        conn.close()
        return row["summary"] if row else None


# ── Delivery status summary (for the Central Dashboard admin API) ────

def get_delivery_status_summary() -> dict:
    """
    Per-phone delivery snapshot, built entirely from existing tables (no new
    schema). Keyed by phone (WhatsApp format, e.g. "919876543210"):

        {
            "<phone>": {
                "pending_count":    2,
                "last_error":       "template send failed (131047)",
                "last_queued_at":   "2026-07-13 10:02:00",
                "last_delivered_at": "2026-07-10 09:15:00",
                "window_open":      False,
            }
        }

    A phone with no pending_filings rows gets pending_count=0 / last_error=None.
    A phone that has never appeared in sent_filings gets last_delivered_at=None.
    """
    with _lock:
        conn = get_conn()

        pending_rows = conn.execute("""
            SELECT phone,
                   COUNT(*)      AS pending_count,
                   MAX(queued_at) AS last_queued_at
            FROM pending_filings
            GROUP BY phone
        """).fetchall()

        # last_error should come from the MOST RECENTLY queued row per phone,
        # not an arbitrary one — fetch separately since SQLite has no simple
        # "value associated with the max of another column" aggregate.
        last_error_rows = conn.execute("""
            SELECT pf.phone, pf.last_error
            FROM pending_filings pf
            INNER JOIN (
                SELECT phone, MAX(queued_at) AS max_queued_at
                FROM pending_filings
                GROUP BY phone
            ) latest ON latest.phone = pf.phone AND latest.max_queued_at = pf.queued_at
        """).fetchall()

        sent_rows = conn.execute("""
            SELECT phone,
                   MAX(sent_at) AS last_delivered_at,
                   COUNT(*)     AS delivered_count
            FROM sent_filings
            GROUP BY phone
        """).fetchall()

        window_rows = conn.execute("""
            SELECT phone, last_inbound_at
            FROM users
            WHERE last_inbound_at IS NOT NULL
        """).fetchall()

        conn.close()

    summary = {}

    def _entry(phone):
        return summary.setdefault(phone, {
            "pending_count": 0,
            "last_error": None,
            "last_queued_at": None,
            "last_delivered_at": None,
            "delivered_count": 0,
            "window_open": False,
        })

    for row in pending_rows:
        e = _entry(row["phone"])
        e["pending_count"] = row["pending_count"]
        e["last_queued_at"] = row["last_queued_at"]

    for row in last_error_rows:
        _entry(row["phone"])["last_error"] = row["last_error"]

    for row in sent_rows:
        e = _entry(row["phone"])
        e["last_delivered_at"] = row["last_delivered_at"]
        e["delivered_count"] = row["delivered_count"]

    for row in window_rows:
        # Same 24h rule as window_open() above, evaluated in Python since we
        # already have every row in hand (avoids one query per phone).
        e = _entry(row["phone"])
        if row["last_inbound_at"]:
            from datetime import datetime, timedelta, timezone
            try:
                last = datetime.strptime(row["last_inbound_at"], "%Y-%m-%d %H:%M:%S")
                e["window_open"] = last > (datetime.utcnow() - timedelta(hours=24))
            except ValueError:
                pass

    return summary