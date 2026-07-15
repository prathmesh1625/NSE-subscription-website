# ============================================================
#  bot.py  —  Flask webhook + WhatsApp PDF delivery bot
#
#  FIX:
#   • Every inbound message reopens the 24-hour window, so we now
#     flush the pending_filings retry queue for that user first.
#   • The manual "pdfs" path no longer marks a filing sent unless
#     the WhatsApp API confirms delivery (was the same 131047 bug).
# ============================================================

from flask import Flask, request, jsonify, send_from_directory, redirect
import hmac
import sys
import os
import config
import database as db
import whatsapp
from whatsapp import WhatsAppError

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

app = Flask(__name__)

# ── ngrok browser-warning bypass ─────────────────────────────
@app.after_request
def add_ngrok_header(response):
    response.headers['ngrok-skip-browser-warning'] = 'true'
    return response


# ── Constants ─────────────────────────────────────────────────

PORTAL_URL = os.environ.get("PORTAL_URL", "https://equityalerts.in/portal")

# PureFrameLabs promo appended to greeting/help replies.
PROMO_FOOTER = (
    "━━━━━━━━━━━━━━\n"
    "*📢 We are PureFrameLabs* — we build similar products & custom tools.\n"
    "For any query or product, contact us: *8459625508*"
)

WELCOME_MSG = (
    "👋 Welcome to *NSE Filing Alerts Bot*!\n\n"
    "Get instant NSE company filings (earnings reports, annual results, "
    "board meetings & more) delivered directly to WhatsApp — the moment they're published.\n\n"
    "🔗 *To get started, tap the link below to register and choose your companies:*\n"
    f"{PORTAL_URL}\n\n"
    "_(Opens inside WhatsApp — complete signup & subscription there)_\n\n"
    "Once registered, PDFs will be sent to you automatically. ✅\n\n"
    f"{PROMO_FOOTER}"
)

HELP_MSG = (
    "ℹ️ *NSE Filing Alerts Bot — Help*\n\n"
    "📋 *How it works:*\n"
    "  1. Open the portal link and register with your mobile number\n"
    "  2. Verify via OTP, choose a plan, and pick your companies\n"
    "  3. New NSE filings for your companies arrive here as PDFs automatically\n\n"
    f"🔗 *Portal:* {PORTAL_URL}\n\n"
    "📩 *Commands:*\n"
    "  • *hi* / *start* — show welcome & portal link\n"
    "  • *pdfs* — manually fetch any unsent filings now\n"
    "  • *help* — show this message\n\n"
    "Type *hi* to see the portal link again.\n\n"
    f"{PROMO_FOOTER}"
)

ALREADY_REGISTERED_MSG = (
    "✅ You're all set!\n\n"
    "New NSE filings for your subscribed companies will be delivered here automatically.\n\n"
    "Type *pdfs* if you'd like your latest filings right now, or *help* for more info.\n\n"
    f"{PROMO_FOOTER}"
)


def get_subscriptions_pg(phone: str) -> list:
    """Returns the company symbols this user is subscribed to from the PostgreSQL database."""
    import psycopg2
    normalized_phone = phone
    if phone.startswith("91") and len(phone) == 12:
        normalized_phone = phone[2:]

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
            SELECT c.symbol
            FROM user_companies uc
            JOIN companies c ON c.id = uc.company_id
            JOIN users u ON u.id = uc.user_id
            JOIN subscriptions s ON s.user_id = u.id
            WHERE (u.mobile = %s OR u.mobile = %s) AND s.status = 'ACTIVE';
        """, (phone, normalized_phone))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [r[0].strip().upper() for r in rows]
    except Exception as e:
        print(f"Error fetching PG subscriptions for {phone}: {e}")
        return []


def is_user_registered_pg(phone: str) -> bool:
    """Returns True if the user has an active subscription in PostgreSQL."""
    return len(get_subscriptions_pg(phone)) > 0


# ── Status callback handler (delivery failures) ───────────────

def _handle_status_update(status: dict):
    """
    Process a Meta delivery status callback.

    When status='failed' with error 131047, the free-form message was
    accepted by Meta (HTTP 200) but not delivered because the 24-hour
    window had already closed. We undo the 'sent' marking and retry
    via the approved template fallback.
    """
    if status.get("status") != "failed":
        return

    wamid  = status.get("id", "")
    phone  = status.get("recipient_id", "")
    errors = status.get("errors", [])

    is_reengagement = any(e.get("code") == 131047 for e in errors)
    if not is_reengagement:
        print(f"⚠️  Delivery failed for {phone} wamid={wamid}, errors={errors}")
        return

    print(f"⚠️  Status 131047: free-form PDF not delivered to {phone} (wamid={wamid})")

    info = db.get_wamid_info(wamid)

    if not info:
        # No tracking row for this wamid. Two cases land here:
        #   1. A DUPLICATE webhook for a wamid we already handled (we soft-delete
        #      via remove_wamid, so the second callback finds nothing). This is
        #      EXPECTED — Meta re-delivers callbacks — and must be a no-op.
        #   2. The original send returned an empty wamid (rare), so we never
        #      stored it.
        # The previous "blind recovery" here unmarked every filing sent in the
        # last 2 hours and let the watcher re-send them free-form — which, for a
        # user still outside the 24h window, fails again and loops. So we now
        # simply log and stop. The watcher's normal poll + the template retry on
        # the NEXT (tracked) send will recover any genuinely-missed filing.
        print(f"   ℹ️  No (unhandled) wamid tracking info for {phone} "
              f"(duplicate callback or empty-wamid send) — skipping retry.")
        return

    # ── NORMAL PATH: wamid was tracked ───────────────────────────────────
    file_key  = info["file_key"]
    file_path = info["file_path"]
    caption   = info.get("caption") or ""
    filing_id = info.get("filing_id")
    channel   = info.get("channel") or "freeform"

    # ── IDEMPOTENCY GUARD ────────────────────────────────────────────────
    # If the message that just failed was ITSELF a template send, retrying via
    # template will not help (templates are allowed outside the window, so a
    # failed template means a real problem — wrong template name, language
    # mismatch, media issue, etc.). Re-sending would loop. Park it instead.
    if channel == "template":
        db.remove_wamid(wamid)
        print(f"   ⚠️  A TEMPLATE send to {phone} failed (code 131047). "
              f"Not retrying via template again — check the template "
              f"(name='{getattr(config, 'TEMPLATE_NAME', '')}', "
              f"lang='{getattr(config, 'TEMPLATE_LANG', '')}') in WhatsApp Manager.")
        db.queue_pending_filing(phone, file_key, file_path, caption,
                                filing_id=filing_id,
                                error="template send failed (131047)")
        return

    # Soft-delete the wamid so a duplicate callback for it becomes a no-op.
    db.remove_wamid(wamid)

    # Undo the false "sent" marking for this free-form attempt.
    if filing_id:
        db.unmark_filing_sent(phone, filing_id)
        print(f"   ↩️  Unmarked sent_filings for {phone} / filing {filing_id}.")
    else:
        # filing_id unknown — fall back to clearing by file_key via direct SQL
        try:
            conn = db.get_conn()
            conn.execute(
                "DELETE FROM sent_filings WHERE phone=? AND filing_id=?",
                (phone, file_key)
            )
            conn.commit()
            conn.close()
            print(f"   ↩️  Unmarked sent_filings for {phone} / file_key {file_key}.")
        except Exception as e:
            print(f"   ❌ Could not unmark sent_filings: {e}")

    # Retry via template ONLY — we know the 24h window is closed, so a
    # free-form retry would silently fail again and loop. force_template=True
    # makes _try_send go straight to the approved template path.
    template_name = getattr(config, "TEMPLATE_NAME", "") or ""
    if template_name and os.path.exists(file_path):
        # Derive a clean display name for the template {{1}} variable from the
        # filename (e.g. "TATASTEEL_0806...pdf" / "BSE_TATASTEEL_...pdf" -> Tata
        # Steel) so the body doesn't fall back to a generic placeholder.
        _base  = os.path.splitext(file_key)[0]
        _parts = [p for p in _base.split("_") if p]
        if _parts and _parts[0].upper() in ("NSE", "BSE"):
            _parts = _parts[1:]
        _symbol  = (_parts[0] if _parts else _base).upper()
        _company = config.COMPANY_LIST.get(_symbol, _symbol)

        print(f"   Retrying {file_key} via template '{template_name}' (forced)...")
        try:
            from db_watcher import _try_send
            ok = _try_send(phone, file_path, caption, file_key,
                           filing_id=filing_id, force_template=True,
                           template_params=[_company])
            if ok:
                print(f"   ✅ Template retry succeeded for {phone}.")
                # PG row stays is_notified=TRUE (template delivered), so the
                # watcher won't re-poll this filing. Done.
                return
            else:
                print(f"   ⚠️  Template retry failed — queued in pending_filings.")
        except Exception as e:
            print(f"   ❌ Template retry error: {e}")
            db.queue_pending_filing(phone, file_key, file_path, caption,
                                    filing_id=filing_id, error=str(e))
    else:
        db.queue_pending_filing(phone, file_key, file_path, caption,
                                filing_id=filing_id,
                                error="131047 status callback (no template/file)")
        print(f"   Queued {file_key} for {phone} (will retry on next user message).")

    # Reached only if the template retry did NOT succeed. Reset PG so the
    # watcher poll can also attempt re-delivery later.
    if filing_id:
        try:
            from db_watcher import unmark_notified_in_pg
            unmark_notified_in_pg(filing_id)
        except Exception as e:
            print(f"   Could not reset PG row: {e}")


# ── Core conversation handler ─────────────────────────────────

def handle_message(phone: str, text: str):
    """Simplified router — send portal link on greeting, deliver PDFs on demand."""
    text  = text.strip()
    lower = text.lower()

    # ── "Full Summary" button tap ────────────────────────────────────────
    # Payload looks like "SUM::<file_key>". This inbound tap has just reopened
    # the 24h window, so we can push the full rich summary as a free-form
    # message — the exact multi-line / linked format that templates can't carry.
    if text.startswith("SUM::"):
        file_key = text[len("SUM::"):].strip()
        summary  = db.get_filing_summary(file_key)
        if summary:
            try:
                whatsapp.send_text(phone, summary)
                print(f"📊 Sent full summary for {file_key} to {phone}.")
            except Exception as e:
                print(f"⚠️  Could not send full summary to {phone}: {e}")
        else:
            whatsapp.send_text(phone,
                "Sorry, the full summary for that filing isn't available anymore. "
                "The PDF is attached above. 📄"
            )
        # The tap also reopened the window — flush anything else pending.
        try:
            from db_watcher import flush_pending_filings
            flush_pending_filings(phone)
        except Exception as e:
            print(f"⚠️  Flush error after summary tap: {e}")
        return

    # ── Re-engagement: this inbound message reopened the 24h window. ──
    # Flush any filings that previously failed with 131047 BEFORE anything else.
    try:
        from db_watcher import flush_pending_filings
        delivered = flush_pending_filings(phone)
        if delivered:
            print(f"📨 Delivered {delivered} previously-pending filing(s) to {phone}.")
    except Exception as e:
        print(f"⚠️  Could not flush pending filings for {phone}: {e}")

    # ── "Keep alerts on" button tap (from the pre-close reminder) ─────
    # This inbound tap has already reopened the 24h window and flushed any
    # pending filings above. Just confirm, and remind them where to manage
    # their companies. No template will be needed now — they're back in-window.
    if text == "REENGAGE_KEEP":
        manage_url = getattr(config, "MANAGE_COMPANIES_URL", PORTAL_URL)
        whatsapp.send_text(phone,
            "✅ Great — your NSE filing alerts will keep arriving smoothly.\n\n"
            "➕ Add or remove companies anytime here:\n"
            f"{manage_url}"
        )
        return

    # ── Greeting → dynamically send welcome message or 'all set' ──────
    if lower in ("hi", "hello", "hey", "start", "menu", "0"):
        if is_user_registered_pg(phone):
            whatsapp.send_text(phone, ALREADY_REGISTERED_MSG)
        else:
            whatsapp.send_text(phone, WELCOME_MSG)
        return

    # ── Help ─────────────────────────────────────────────────
    if lower in ("help", "?"):
        whatsapp.send_text(phone, HELP_MSG)
        return

    # ── Manual PDF fetch ──────────────────────────────────────
    if lower in ("pdfs", "files", "send", "get"):
        import psycopg2, psycopg2.extras
        subs = get_subscriptions_pg(phone)
        if not subs:
            whatsapp.send_text(phone,
                "You don't have any active subscriptions yet.\n\n"
                f"👉 Register here first: {PORTAL_URL}"
            )
            return

        whatsapp.send_text(phone,
            f"📂 Fetching latest filings for *{len(subs)}* "
            f"subscribed {'company' if len(subs)==1 else 'companies'}...\nPlease wait."
        )
        total_sent = 0
        try:
            conn = psycopg2.connect(
                host=config.DB_HOST, port=config.DB_PORT,
                dbname=config.DB_NAME, user=config.DB_USER,
                password=config.DB_PASSWORD,
                cursor_factory=psycopg2.extras.RealDictCursor
            )
            cur = conn.cursor()
            for symbol in subs:
                name = config.COMPANY_LIST.get(symbol, symbol)
                cur.execute("""
                    SELECT id, title, local_path, announcement_time
                    FROM announcements
                    WHERE company_symbol = %s
                      AND download_status = 'DOWNLOADED'
                    ORDER BY announcement_time DESC
                    LIMIT 10
                """, (symbol,))
                rows = cur.fetchall()
                sent = 0
                skipped = 0
                for row in rows:
                    file_path = os.path.join(
                        config.SCRAPER_BASE_PATH,
                        row["local_path"].strip()
                    )
                    file_key = os.path.basename(file_path).strip()

                    if db.is_filing_sent(phone, file_key):
                        skipped += 1
                        continue

                    if os.path.exists(file_path):
                        caption = (
                            f"*{name}* ({symbol})\n"
                            f"{row['title']}\n"
                            f"{row['announcement_time']}"
                        )
                        # Only mark sent if delivery is confirmed.
                        try:
                            # If this has to fall back to a template, the body
                            # {{1}} carries the caption so the user still gets
                            # the details + PDF together (no button to tap).
                            _, wamid = whatsapp.send_pdf(
                                phone, file_path, caption=caption,
                                template_params=[caption]
                            )
                            db.mark_filing_sent(phone, file_key)
                            db.remove_pending_filing(phone, file_key)
                            # Track wamid so status callbacks can detect
                            # false delivery (131047 arrives after HTTP 200).
                            if wamid:
                                db.store_wamid(wamid, phone, file_key,
                                               file_path, caption,
                                               filing_id=row["id"])
                            cur.execute(
                                "UPDATE announcements SET is_notified = TRUE WHERE id = %s",
                                (row["id"],)
                            )
                            conn.commit()
                            sent += 1
                            total_sent += 1
                        except WhatsAppError as e:
                            # Should be rare here (user just messaged us), but
                            # queue it so the next inbound message retries it.
                            db.queue_pending_filing(
                                phone, file_key, file_path, caption,
                                filing_id=row["id"], error=str(e)
                            )
                            print(f"⚠️  Queued {file_key} for {phone} ({e}).")
                if sent == 0:
                    msg = (
                        f"✅ All recent filings for *{name}* ({symbol}) already sent."
                        if skipped > 0
                        else f"✅ No new filings for *{name}* ({symbol}) — you're up to date."
                    )
                    whatsapp.send_text(phone, msg)
            cur.close()
            conn.close()
        except Exception as e:
            print(f"pdfs fetch DB error: {e}")
            whatsapp.send_text(phone, "❌ Could not fetch filings. Try again later.")
            return

        if total_sent > 0:
            whatsapp.send_text(phone,
                f"✅ Sent *{total_sent}* new filing(s) across your subscriptions.\n\n"
                "New filings will also be sent automatically as they are published."
            )
        return

    # ── Anything else → guide user to portal ─────────────────
    whatsapp.send_text(phone,
        "I can only deliver NSE filing PDFs here. 📄\n\n"
        "To register or manage your subscriptions:\n"
        f"👉 {PORTAL_URL}\n\n"
        "Type *help* for more info."
    )


# ── Branded short download links (/t/<code>) ─────────────────

@app.route("/t/<code>")
def short_link_redirect(code):
    """
    Resolve a branded short code to the real NSE PDF URL and 302-redirect.
    This is what lets alerts show https://equityalerts.in/t/<code> instead of
    the long nseindia.com link. Counts clicks for basic analytics.
    """
    url = db.get_short_link(code)
    if not url:
        return "Link not found or expired.", 404
    try:
        db.increment_short_link_click(code)
    except Exception as e:
        print(f"⚠️  Could not record click for {code}: {e}")
    return redirect(url, code=302)


# ── Admin API (Central Dashboard delivery-status endpoint) ───

@app.route("/admin/delivery-status", methods=["GET"])
def admin_delivery_status():
    """
    Read-only snapshot of per-user WhatsApp delivery state, for the NSE
    backend's Admin API to merge into the Central Dashboard. Guarded by a
    shared secret (mirrors adminAuthMiddleware.js on the backend) — never
    exposed to regular WhatsApp users or the public portal.
    """
    provided = request.headers.get("x-bot-admin-key", "")
    expected = config.BOT_ADMIN_KEY

    if not expected:
        return jsonify({"success": False, "message": "Admin API is not configured on this server"}), 500

    if not hmac.compare_digest(provided, expected):
        return jsonify({"success": False, "message": "Invalid or missing x-bot-admin-key header"}), 401

    try:
        summary = db.get_delivery_status_summary()
        users = [
            {
                "phone": phone,
                "pendingCount": s["pending_count"],
                "lastError": s["last_error"],
                "lastQueuedAt": s["last_queued_at"],
                "lastDeliveredAt": s["last_delivered_at"],
                "windowOpen": s["window_open"],
            }
            for phone, s in summary.items()
        ]
        return jsonify({"success": True, "users": users})
    except Exception as e:
        print(f"❌ /admin/delivery-status error: {e}")
        return jsonify({"success": False, "message": "Failed to load delivery status"}), 500


# ── Serve React portal (static files) ────────────────────────

PORTAL_DIST = os.path.join(
    os.path.dirname(__file__),
    "nse-website", "subscription-portal", "frontend", "dist"
)

@app.route("/")
def root_redirect():
    """Bare domain (equityalerts.in) → the portal app.

    The site lives under /portal (that's the URL given to Meta for app review,
    so we can't drop it), but users keep typing just equityalerts.in and hit a
    dead root. Send them straight to /portal. 302 (temporary) so this stays
    reversible if a marketing landing page is ever added at the root.
    """
    return redirect("/portal", code=302)


@app.route("/portal", defaults={"path": ""})
@app.route("/portal/<path:path>")
def serve_portal(path):
    """Serve the built React subscription portal.

    conditional=False disables Flask/Werkzeug Range handling. Otherwise a
    crawler that sends a `Range: bytes=0-` header (e.g. facebookexternalhit)
    gets a 206 Partial Content, which makes Meta domain verification fail —
    it only accepts a 200 on the verified URL (e.g. /portal/disclaimer).
    """
    if path and os.path.exists(os.path.join(PORTAL_DIST, path)):
        return send_from_directory(PORTAL_DIST, path, conditional=False)
    return send_from_directory(PORTAL_DIST, "index.html", conditional=False)


# ── Proxy API calls to website backend (port 3001) ───────────

import requests as req_lib

@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
def proxy_api(path):
    """Forward /api/* requests from the portal to the local website backend (port 3001)."""
    target_url = f"http://backend:3001/api/{path}"
    try:
        resp = req_lib.request(
            method=request.method,
            url=target_url,
            headers={k: v for k, v in request.headers if k.lower() != "host"},
            data=request.get_data(),
            params=request.args,
            allow_redirects=False,
            timeout=30,
        )
        excluded = {"content-encoding", "transfer-encoding", "connection"}
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in excluded}
        return resp.content, resp.status_code, headers
    except Exception as e:
        print(f"[Proxy Error] /api/{path}: {e}")
        return jsonify({"success": False, "message": "Backend unavailable"}), 502


# ── Flask webhook routes ──────────────────────────────────────

@app.route("/webhook", methods=["GET"])
def verify():
    """Meta calls this once to verify your webhook URL."""
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == config.VERIFY_TOKEN:
        print("✅ Webhook verified by Meta!")
        return challenge, 200

    print("❌ Webhook verification failed — check VERIFY_TOKEN in config.py")
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    """Receives incoming WhatsApp messages."""
    data = request.get_json(silent=True) or {}
    print(f"Webhook POST received: {data}")

    try:
        entry   = data["entry"][0]
        changes = entry["changes"][0]
        value   = changes["value"]

        if "messages" not in value and "statuses" not in value:
            return jsonify({"status": "ok"}), 200

        # ── Process delivery status callbacks (BEFORE message handling) ──
        if "statuses" in value:
            for status_update in value["statuses"]:
                try:
                    _handle_status_update(status_update)
                except Exception as e:
                    print(f"⚠️  Status handler error: {e}")

        if "messages" not in value:
            return jsonify({"status": "ok"}), 200

        msg   = value["messages"][0]
        phone = msg["from"]
        mtype = msg.get("type", "")

        # Every inbound message opens a fresh 24h window — stamp it so the
        # pre-close reminder loop knows when this user's window will close, and
        # the one-template-per-window cap resets.
        try:
            db.record_inbound(phone)
        except Exception as e:
            print(f"⚠️  Could not record inbound for {phone}: {e}")

        if mtype == "text":
            text = msg["text"]["body"]
        elif mtype == "button":
            # Tap on a TEMPLATE quick-reply button (e.g. "Full Summary").
            text = msg.get("button", {}).get("payload", "") or \
                   msg.get("button", {}).get("text", "")
        elif mtype == "interactive":
            interactive = msg["interactive"]
            if interactive["type"] == "button_reply":
                text = interactive["button_reply"]["id"]
            elif interactive["type"] == "list_reply":
                text = interactive["list_reply"]["id"]
            else:
                text = ""
        else:
            # Even a non-text message reopens the window — flush the queue.
            try:
                from db_watcher import flush_pending_filings
                flush_pending_filings(phone)
            except Exception as e:
                print(f"⚠️  Flush error: {e}")
            whatsapp.send_text(phone,
                "I can only understand text messages. "
                "Type *hi* to get started. 👋"
            )
            return jsonify({"status": "ok"}), 200

        print(f"📩 Message from {phone}: {text!r}")
        handle_message(phone, text)

    except (KeyError, IndexError) as e:
        print(f"Ignored webhook payload without a user message: {e}")
    except Exception as e:
        print(f"Webhook handler error: {e}")

    return jsonify({"status": "ok"}), 200


# ── Start everything ──────────────────────────────────────────

if __name__ == "__main__":
    db.init_db()

    # ── Startup banner ────────────────────────────────────────
    print("")
    print("=" * 55)
    print("  NSE WhatsApp Filing Bot — STARTUP")
    print("=" * 55)
    print(f"  📱 Phone Number ID : {config.PHONE_NUMBER_ID}")
    print(f"  🔑 Token (first 20) : {config.WHATSAPP_TOKEN[:20]}...")
    print(f"  🔒 Verify Token    : {config.VERIFY_TOKEN}")
    print(f"  🗄️  Scraper DB      : {config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}")
    print(f"  📂 Scraper Base    : {config.SCRAPER_BASE_PATH}")
    print(f"  📋 Template Name   : {config.TEMPLATE_NAME or '(none — queuing only)'}")
    print(f"  ⏱️  Poll Interval   : {config.POLL_INTERVAL_SEC}s")
    print(f"  🌐 Portal URL      : {PORTAL_URL}")
    print(f"  🚀 Flask Port      : {config.FLASK_PORT}")
    print("=" * 55)
    print("")
    print("  ⚠️  If Meta rejects sends to a number with error 131026,")
    print("      that number is NOT added as a test number in your")
    print("      Meta App Dashboard → WhatsApp → API Setup → To.")
    print("      Add it there, or go LIVE on Meta to send to all numbers.")
    print("")
    print("  📌 Watching terminal for:")
    print("      📩 Message from <phone>: <text>   ← inbound messages")
    print("      📤 Sending <symbol> to <N> subs   ← PDF dispatch")
    print("      [OK] Sent PDF '<file>' to <phone> ← confirmed delivery")
    print("      ❌ / ⚠️  lines                     ← errors")
    print("=" * 55)
    print("")

    if config.ENABLE_DB_WATCHER:
        from db_watcher import start_watcher
        start_watcher()
    else:
        print("PostgreSQL watcher disabled. Set ENABLE_DB_WATCHER=True in config.py.")

    print(f"🚀 NSE WhatsApp Bot running on port {config.FLASK_PORT}")
    print(f"🌐 Subscription portal: {PORTAL_URL}")
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=config.FLASK_DEBUG)