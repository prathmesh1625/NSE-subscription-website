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
import time
import threading
import psycopg2
import psycopg2.extras
import subprocess
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
                {config.COL_CREATED_AT}     AS created_at
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
        print(f"❌ Error fetching PG subscribers for {symbol}: {e}")
        return []


def generate_pdf_summary(file_path: str, filing_type: str = "",
                         download_url: str = "") -> str | None:
    """Run the LLM PDF parser in a subprocess using the structured_output virtual environment.

    `filing_type` feeds the ⚡ event line and `download_url` (the NSE pdf_url)
    feeds the 📎 download link in the EquiSense-style Stock Bits message.
    """
    try:
        venv_python   = r"d:\prathmesh\structured_output\.venv\Scripts\python.exe"
        output_script = r"d:\prathmesh\structured_output\output.py"

        if not os.path.exists(venv_python) or not os.path.exists(output_script):
            print("⚠️ venv python or output.py script not found, skipping summary generation.")
            return None

        print(f"🤖 Generating AI summary for {os.path.basename(file_path)}...")

        cmd = [venv_python, "-X", "utf8", output_script, "--pdf", file_path,
               "--provider", "openai", "--model", "gpt-4o-mini", "--raw"]
        # Brand URL drives the "You are receiving…" + "Disclaimer: <brand>/disclaimer"
        # footer lines, so the alert points at our portal (not the generator default).
        brand_url = getattr(config, "BRAND_URL", "") or ""
        if brand_url:
            cmd += ["--equisense-url", brand_url]
        if filing_type:
            cmd += ["--filing-type", filing_type]
        if download_url:
            cmd += ["--download-url", download_url]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=getattr(config, "SUMMARY_TIMEOUT_SEC", 30)
        )

        if result.returncode == 0:
            stdout_clean = result.stdout.strip()
            # New format opens with "📢 *PureFrame Stock Bits!!*"; strip any
            # leading log noise by starting at the first megaphone.
            marker = stdout_clean.find("📢")
            if marker != -1:
                return stdout_clean[marker:]
            return stdout_clean if stdout_clean else None
        else:
            stderr_text = result.stderr.strip()
            print(f"❌ PDF parser failed (code {result.returncode}) for {os.path.basename(file_path)}:")
            for line in stderr_text.splitlines()[-10:]:   # last 10 lines of traceback
                print(f"   {line}")
            return None
    except Exception as e:
        print(f"❌ Error generating PDF summary: {e}")
        return None


def _with_ad(text: str) -> str:
    """
    Append the PureFrameLabs advertisement below the alert, separated by a
    blank line + divider so it reads like a small ad footer (not part of the
    filing). No-op if PUREFRAME_SITE is unset or `text` is empty.
    """
    site = getattr(config, "PUREFRAME_SITE", "") or ""
    if not site or not text:
        return text
    ad = (
        "\n\n━━━━━━━━━━━━━━\n"
        "🚀 *PureFrame Labs* — we build custom bots, dashboards & data tools.\n"
        f"🔗 {site}"
    )
    return text.rstrip() + ad


def _build_caption(file_path, fallback_caption, filing_type="", download_url=""):
    """Return cached AI summary if available; otherwise generate and cache it.

    `filing_type` and `download_url` are passed to the message generator so the
    ⚡ event line and 📎 download link appear. Text messages allow up to ~4096
    chars, so the cap is well above the old template-body limit — this keeps the
    footer + download link at the end from being truncated away.

    The PureFrameLabs ad is appended to the summary (and cached with it) so it
    rides along on both the text alert and the template body.
    """
    file_key = os.path.basename(file_path).strip()
    cached   = bot_db.get_filing_summary(file_key)
    if cached:
        return cached

    ai_summary = generate_pdf_summary(file_path, filing_type=filing_type,
                                      download_url=download_url)
    if ai_summary:
        ai_summary = _with_ad(ai_summary)
        trimmed = ai_summary[:3997] + "..." if len(ai_summary) > 4000 else ai_summary
        bot_db.save_filing_summary(file_key, trimmed)
        return trimmed
    return _with_ad(fallback_caption)


def _resolve_send_path(file_path, caption, file_key):
    """
    Decide which PDF actually gets uploaded.

    When config.SEND_AS_CARD is on, render the AI caption into a branded
    "Stock Bits" card PDF (once per filing, cached on disk and reused across
    every subscriber and every retry) and return that path. On any failure —
    or when disabled/unavailable — fall back to the raw NSE filing PDF so a
    delivery is never lost to a rendering hiccup.
    """
    if not getattr(config, "SEND_AS_CARD", False) or message_card is None:
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

        # Cache hit: caption is stable per file_key (stored in SQLite), so a
        # previously rendered card is still valid — skip the re-render.
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
    if getattr(config, "SEND_AS_TEXT", False) and window_is_open and not force_template:
        try:
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
    if getattr(config, "SEND_AS_TEXT", False):
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
            body1, url = _split_download_link(caption)
            url = url or "https://equityalerts.in"
            wamid = whatsapp.send_text_template(phone, [body1, url])
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
        channel, wamid = whatsapp.send_pdf(
            phone, send_path, caption=caption,
            template_params=template_params,
            force_template=send_force,
            allow_template_fallback=False,
        )
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
    """Main logic: fetch → check subscribers → send PDFs."""
    filings = fetch_new_filings()
    filings = _dedup_by_filename(filings)

    for filing in filings:
        filing_id   = filing["filing_id"]
        symbol      = (filing.get("symbol") or "").upper().strip()
        company     = filing.get("company_name") or symbol
        file_path   = filing["file_path"]
        filing_type = filing.get("filing_type") or "New Filing"

        subscribers = get_subscribers_for_symbol_pg(symbol)

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

        print(f"📤 Sending {symbol} '{filing_type}' to {len(subscribers)} subscriber(s)...")

        fallback = (
            f"📄 *{company}* — {filing_type}\n"
            f"🏦 NSE Symbol: {symbol}\n"
            f"📅 {filing.get('created_at', '')}"
        )
        caption  = _build_caption(file_path, fallback, filing_type=filing_type,
                                  download_url=filing.get("pdf_url") or "")
        file_key = os.path.basename(file_path).strip()
        bot_db.save_filing_summary(file_key, caption)  # for the Full Summary button

        all_sent = True
        for phone in subscribers:
            if bot_db.is_filing_sent(phone, file_key):
                print(f"ℹ️  Already sent filing {file_key} to {phone}, skipping.")
                continue
            # Only marks sent on confirmed success; queues on failure.
            ok = _try_send(phone, file_path, caption, file_key,
                           filing_id=filing_id, template_params=[company])
            if not ok:
                all_sent = False

        # Mark notified in PG only when EVERY subscriber got it. Otherwise the
        # filing stays is_notified=FALSE and is retried on the next poll for
        # anyone still missing it (already-sent users are skipped above).
        if all_sent:
            mark_notified_in_pg(filing_id)


# ── Automatic backfill for subscribers ───────────────────────

def deliver_backfill_for_subscribers():
    """
    For every active subscriber, ensure they have the latest filings for each
    company they're subscribed to. Idempotent — safe to run every poll.
    """
    LATEST_PER_COMPANY = 3
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
                SELECT c.symbol, c.company_name
                FROM user_companies uc
                JOIN companies c ON c.id = uc.company_id
                JOIN users u ON u.id = uc.user_id
                JOIN subscriptions s ON s.user_id = u.id
                WHERE (u.mobile = %s OR u.mobile = %s) AND s.status = 'ACTIVE';
            """, (phone, normalized_phone))
            subs = [(r[0], r[1]) for r in sub_cur.fetchall()]
            if not subs:
                continue

            for symbol, db_company_name in subs:
                symbol = symbol.upper().strip()
                name = config.COMPANY_LIST.get(symbol, db_company_name or symbol)
                pg_cur.execute("""
                    SELECT id, title, local_path, pdf_url, announcement_time
                    FROM announcements
                    WHERE UPPER(company_symbol) = UPPER(%s)
                      AND download_status = 'DOWNLOADED'
                    ORDER BY announcement_time DESC
                    LIMIT 15
                """, (symbol,))
                rows = _dedup_by_filename(pg_cur.fetchall())[:LATEST_PER_COMPANY]

                for row in rows:
                    file_path = os.path.join(
                        config.SCRAPER_BASE_PATH, row["local_path"].strip()
                    )
                    file_key = os.path.basename(file_path).strip()

                    if bot_db.is_filing_sent(phone, file_key):
                        continue
                    if not os.path.exists(file_path):
                        continue

                    fallback = (
                        f"📄 *{name}* — New Filing\n"
                        f"🏦 NSE Symbol: {symbol}\n"
                        f"📅 {row['announcement_time']}"
                    )
                    caption = _build_caption(file_path, fallback,
                                             filing_type=row.get("title") or "",
                                             download_url=row.get("pdf_url") or "")
                    bot_db.save_filing_summary(file_key, caption)  # for Full Summary button

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

    threading.Thread(target=live_loop, daemon=True, name="live-dispatch").start()
    threading.Thread(target=backfill_loop, daemon=True, name="subscriber-backfill").start()
    if getattr(config, "ENABLE_WINDOW_REMINDER", False):
        threading.Thread(target=reminder_loop, daemon=True, name="window-reminder").start()