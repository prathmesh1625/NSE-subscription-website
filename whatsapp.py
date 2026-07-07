# ============================================================
#  whatsapp.py  —  Send messages & PDFs via Meta Cloud API
#
#  FIX: _post() now RAISES on any non-2xx response instead of
#  silently printing and returning. Error 131047 (re-engagement,
#  i.e. the 24-hour window has closed) is surfaced via the
#  `is_reengagement` flag so callers can re-queue the filing.
#
#  CHANGE: the template fallback now carries the AI SUMMARY itself
#  in the body {{1}} variable (alongside the PDF document header),
#  so a silent subscriber receives the summary + PDF in one utility
#  template — no "Full Summary" button to tap. The old quick-reply
#  button path has been retired (nobody tapped it).
# ============================================================
import re
import requests
import os
import sys
import config

BASE_URL = f"https://graph.facebook.com/v19.0/{config.PHONE_NUMBER_ID}"
HEADERS  = {
    "Authorization": f"Bearer {config.WHATSAPP_TOKEN}",
    "Content-Type":  "application/json",
}

# Meta error code returned when the 24-hour customer-service window is closed.
REENGAGEMENT_ERROR_CODE = 131047


class WhatsAppError(Exception):
    """Raised when the Meta Cloud API returns a non-2xx response."""

    def __init__(self, status_code, error_code, message, response_text=""):
        self.status_code   = status_code
        self.error_code    = error_code        # e.g. 131047, or None
        self.response_text = response_text
        super().__init__(
            f"WhatsApp API {status_code} (code={error_code}): {message}"
        )

    @property
    def is_reengagement(self) -> bool:
        """True when the failure is the closed 24-hour window (131047)."""
        return self.error_code == REENGAGEMENT_ERROR_CODE


def _safe_print(msg: str):
    """Print safely on Windows consoles that don't support UTF-8."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("ascii", errors="replace").decode("ascii"))


# Meta rejects a template body parameter that contains newlines, tabs, or runs
# of 4+ spaces. Our AI summaries are multi-line, so they must be flattened
# before they can ride inside a template {{n}} variable.
#
# The cap is below WhatsApp's ~1024-char body limit on purpose: the approved
# template body has a short fixed prefix around {{1}}, and the rendered body
# (prefix + this value) must still fit — otherwise Meta rejects the send.
TEMPLATE_PARAM_MAX_LEN = 900


def _sanitize_template_param(text: str) -> str:
    """
    Flatten a (possibly multi-line) string so Meta accepts it as a template
    body parameter. Collapses all whitespace runs — including newlines and
    tabs — into single spaces and truncates to TEMPLATE_PARAM_MAX_LEN.
    """
    flattened = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(flattened) > TEMPLATE_PARAM_MAX_LEN:
        flattened = flattened[:TEMPLATE_PARAM_MAX_LEN - 1].rstrip() + "…"
    return flattened or "NSE filing"


# ── Send plain text ───────────────────────────────────────────

def send_text(to: str, message: str) -> str:
    """Send a plain text WhatsApp message. Raises WhatsAppError on failure.

    Returns the wamid (Meta message id) so callers can track delivery status.
    Only valid INSIDE the 24-hour window (raises WhatsAppError 131047 otherwise).
    WhatsApp allows a body up to 4096 chars; longer text is rejected.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message[:4096], "preview_url": True},
    }
    resp = _post("/messages", payload)
    return (resp.json().get("messages") or [{}])[0].get("id", "")


# ── Send a TEXT-ONLY template (no media header) ───────────────

def send_text_template(to: str, body_params) -> str:
    """
    Deliver an approved TEXT-ONLY template — a template with NO media header,
    only body variables. Valid OUTSIDE the 24-hour window (silent subscribers).

    The template referenced by config.TEMPLATE_NAME must be APPROVED and must
    have NO header (or the send is rejected). `body_params` fills {{1}}, {{2}},
    ... in order; each is flattened via _sanitize_template_param() so Meta
    accepts it (no newlines/tabs/4+ spaces inside a variable). Returns the wamid.
    """
    params = [
        {"type": "text", "text": _sanitize_template_param(p)}
        for p in (body_params or [])
    ]
    components = []
    if params:
        components.append({"type": "body", "parameters": params})

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": config.TEMPLATE_NAME,
            "language": {"code": getattr(config, "TEMPLATE_LANG", "en")},
            "components": components,
        },
    }
    resp = _post("/messages", payload)
    return (resp.json().get("messages") or [{}])[0].get("id", "")


# ── Send interactive reply buttons ────────────────────────────

def send_interactive_buttons(to: str, body_text: str, buttons,
                             header_text: str = None,
                             footer_text: str = None) -> str:
    """
    Send an interactive message with up to 3 quick-reply buttons.

    Unlike a URL link (which opens a browser and sends NOTHING back), tapping a
    reply button delivers an INBOUND 'button_reply' message to our webhook —
    which reopens the 24-hour window. That's what lets the pre-close reminder
    actually keep a user's window alive so future filings arrive free-form
    instead of as stacked templates.

    `buttons` is a list of dicts: [{"id": "...", "title": "..."}] (title ≤ 20 chars).
    Only valid INSIDE the 24-hour window (raises WhatsAppError 131047 otherwise).
    Returns the wamid.
    """
    reply_buttons = [
        {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
        for b in (buttons or [])[:3]
    ]
    interactive = {
        "type": "button",
        "body": {"text": body_text[:1024]},
        "action": {"buttons": reply_buttons},
    }
    if header_text:
        interactive["header"] = {"type": "text", "text": header_text[:60]}
    if footer_text:
        interactive["footer"] = {"text": footer_text[:60]}

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": interactive,
    }
    resp = _post("/messages", payload)
    return (resp.json().get("messages") or [{}])[0].get("id", "")


# ── Send PDF document ─────────────────────────────────────────

def send_pdf(to: str, file_path: str, caption: str = "",
             template_params=None, force_template: bool = False,
             reply_payload: str = None,
             allow_template_fallback: bool = True) -> tuple:
    """
    Upload a PDF to Meta and deliver it.

    Tries a normal (free-form) document message first. If that fails with
    131047 (the 24-hour window is closed) AND a template is configured, it
    automatically re-sends the SAME uploaded file as an approved template
    message with a document header — which Meta allows outside the window.

    force_template=True skips the free-form attempt entirely and sends via
    the approved template straight away. Use this when you ALREADY know the
    24-hour window is closed (e.g. when retrying after Meta's async 131047
    delivery-failure callback). This is critical: a free-form send returns
    HTTP 200 synchronously and only fails ~minutes later via webhook, so a
    free-form "retry" for a user outside the window silently fails again and
    triggers an endless callback->retry loop.

    Returns (channel, wamid) where channel is "freeform" or "template" and
    wamid is the Meta message ID for delivery status tracking.
    Raises WhatsAppError (or another exception) on ANY unrecoverable failure
    so the caller never mistakes a failed delivery for a successful one.
    """
    filename = os.path.basename(file_path)

    # Step 1: upload once; the media id is reused for both send paths.
    media_id = _upload_media(file_path)

    # Step 2 (forced): we KNOW the window is closed — go straight to template.
    if force_template:
        template_name = getattr(config, "TEMPLATE_NAME", "") or ""
        if not template_name:
            raise WhatsAppError(
                0, None,
                "force_template requested but no TEMPLATE_NAME configured"
            )
        wamid = _send_pdf_template(to, media_id, filename, template_params or [],
                                   reply_payload=reply_payload)
        _safe_print(f"[OK] Sent PDF '{filename}' to {to} (template, forced)")
        return "template", wamid

    # Step 2a: try free-form delivery (works inside the 24h window).
    try:
        wamid = _send_pdf_document(to, media_id, filename, caption)
        _safe_print(f"[OK] Sent PDF '{filename}' to {to} (free-form)")
        return "freeform", wamid
    except WhatsAppError as e:
        # Step 2b: window closed → fall back to an approved template.
        template_name = getattr(config, "TEMPLATE_NAME", "") or ""
        if e.is_reengagement and template_name and allow_template_fallback:
            _safe_print(
                f"[INFO] 24h window closed for {to} — retrying via "
                f"template '{template_name}'..."
            )
            wamid = _send_pdf_template(to, media_id, filename, template_params or [],
                                       reply_payload=reply_payload)
            _safe_print(f"[OK] Sent PDF '{filename}' to {to} (template)")
            return "template", wamid
        # Re-engagement but no template configured, or a different error:
        # let it propagate so the caller queues it for retry.
        raise


def _send_pdf_document(to: str, media_id: str, filename: str, caption: str) -> str:
    """Free-form document message (only valid inside the 24-hour window). Returns wamid."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "document",
        "document": {
            "id": media_id,
            "filename": filename,
            "caption": caption,
        },
    }
    resp = _post("/messages", payload)
    return (resp.json().get("messages") or [{}])[0].get("id", "")


def _send_pdf_template(to: str, media_id: str, filename: str, body_params,
                       reply_payload: str = None) -> str:
    """
    Deliver the PDF via an approved template with a DOCUMENT header.
    Valid OUTSIDE the 24-hour window.

    The template referenced by config.TEMPLATE_NAME must be APPROVED in Meta
    WhatsApp Manager and have a Document header. config.TEMPLATE_BODY_PARAM_COUNT
    must equal the number of {{n}} variables in the template body (0 if none).

    The body parameters now carry the AI SUMMARY (see db_watcher._try_send), so a
    silent subscriber receives the summary text AND the PDF together in this one
    utility template — without having to tap anything. Each parameter is flattened
    via _sanitize_template_param() so multi-line summaries don't get rejected by
    Meta (which forbids newlines/tabs/4+ spaces inside a template variable).

    reply_payload is accepted for backwards compatibility but is intentionally
    IGNORED — the old "Full Summary" quick-reply button has been retired because
    nobody tapped it (the summary now arrives inline in the body instead).
    """
    count = int(getattr(config, "TEMPLATE_BODY_PARAM_COUNT", 0) or 0)

    components = [{
        "type": "header",
        "parameters": [{
            "type": "document",
            "document": {"id": media_id, "filename": filename},
        }],
    }]

    if count > 0:
        params = list(body_params or [])[:count]
        # Pad with a placeholder if the caller supplied fewer than required,
        # so the API call is well-formed (Meta rejects missing params).
        while len(params) < count:
            params.append("NSE filing")
        components.append({
            "type": "body",
            "parameters": [
                {"type": "text", "text": _sanitize_template_param(p)}
                for p in params
            ],
        })

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": config.TEMPLATE_NAME,
            "language": {"code": getattr(config, "TEMPLATE_LANG", "en")},
            "components": components,
        },
    }
    resp = _post("/messages", payload)
    return (resp.json().get("messages") or [{}])[0].get("id", "")


def _upload_media(file_path: str) -> str:
    """Upload a file to WhatsApp media endpoint, return media_id. Raises on failure."""
    with open(file_path, "rb") as f:
        response = requests.post(
            f"https://graph.facebook.com/v19.0/{config.PHONE_NUMBER_ID}/media",
            headers={"Authorization": f"Bearer {config.WHATSAPP_TOKEN}"},
            files={"file": (os.path.basename(file_path), f, "application/pdf")},
            data={"messaging_product": "whatsapp", "type": "application/pdf"},
            timeout=60,
        )

    if response.status_code not in (200, 201):
        _raise_for_response(response)

    media_id = response.json().get("id")
    if not media_id:
        raise WhatsAppError(
            response.status_code, None,
            "Upload succeeded but no media id returned", response.text
        )
    return media_id


def _raise_for_response(response):
    """Parse a Meta error response and raise a WhatsAppError."""
    error_code = None
    error_msg  = response.text
    try:
        body = response.json()
        err  = body.get("error", {}) or {}
        error_code = err.get("code")
        error_msg  = err.get("message", error_msg)
    except Exception:
        pass

    if error_code == 131026:
        _safe_print(
            f"[ERROR] WhatsApp API {response.status_code} code=131026: "
            f"Recipient number is NOT a verified test number. "
            f"Go to Meta App Dashboard → WhatsApp → API Setup → "
            f"'To' field and add the number, OR publish your app to Live mode."
        )
    else:
        _safe_print(
            f"[ERROR] WhatsApp API {response.status_code} "
            f"(code={error_code}): {error_msg}"
        )
    raise WhatsAppError(response.status_code, error_code, error_msg, response.text)


def _post(endpoint: str, payload: dict):
    """
    POST to the WhatsApp API.

    Raises WhatsAppError on any non-2xx response, and lets network/timeout
    errors propagate as their native exceptions. NEVER returns silently
    on failure.
    """
    response = requests.post(
        BASE_URL + endpoint,
        headers=HEADERS,
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 201):
        _raise_for_response(response)

    _safe_print(f"[OK] WhatsApp API {response.status_code}")
    return response