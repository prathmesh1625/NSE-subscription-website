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

# Set this to True only when config.TEMPLATE_NAME is an APPROVED WhatsApp
# template with a DOCUMENT header. The previous code always added a document
# header even though the current config comments describe a text-only template,
# which can produce Meta error 100 (Invalid parameter).
TEMPLATE_HAS_DOCUMENT_HEADER = os.getenv("TEMPLATE_HAS_DOCUMENT_HEADER", "true").lower() in ("true", "1", "yes")


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
    flattened = re.sub(r"[\x00-\x1f\x7f]", " ", str(text or ""))
    flattened = re.sub(r"\s+", " ", flattened).strip()
    # Template variables are data, not WhatsApp markdown. Removing these avoids
    # Meta treating the variable differently from the approved template text.
    flattened = re.sub(r"[*_`~]", "", flattened)
    flattened = re.sub(r"\u200b|\ufeff", "", flattened)
    if len(flattened) > TEMPLATE_PARAM_MAX_LEN:
        flattened = flattened[:TEMPLATE_PARAM_MAX_LEN - 1].rstrip() + "…"
    return flattened or "NSE filing"


TEMPLATE_RENDER_MAX_LEN = 1024


def _fit_template_params(template_name: str, params: list[str]) -> list[str]:
    """Fit the rendered template under Meta's ~1024-char body limit.

    The old code capped EVERY variable at 900 chars. With five variables and
    ~170 chars of fixed footer text, a 900-char AI summary made the rendered
    message >1024 chars and Meta returned code 100. We now budget against the
    whole rendered body and preferentially preserve the company/event/link.
    """
    cleaned = [_sanitize_template_param(p) for p in params]
    bodies = getattr(config, "TEMPLATE_BODIES", {}) or {}
    template_body = bodies.get(template_name or "") or ""
    fixed_len = len(re.sub(r"\{\{\d+\}\}", "", template_body))
    variable_budget = max(200, TEMPLATE_RENDER_MAX_LEN - fixed_len)

    total = sum(len(p) for p in cleaned)
    if total <= variable_budget:
        return cleaned

    # Stock Bits layout is [title, company, event, summary, link]. Give the
    # summary the bulk of the remaining budget while protecting the URL.
    if len(cleaned) == 5:
        protected = sum(len(cleaned[i]) for i in (0, 1, 2, 4))
        summary_budget = max(120, variable_budget - protected)
        cleaned[3] = cleaned[3][:summary_budget].rstrip()
        # If other variables still make the body too large, trim them gently.
        total = sum(len(p) for p in cleaned)
        if total > variable_budget:
            overflow = total - variable_budget
            for i in (2, 0, 1):
                if overflow <= 0:
                    break
                take = min(overflow, max(0, len(cleaned[i]) - 20))
                cleaned[i] = cleaned[i][:-take].rstrip() if take else cleaned[i]
                overflow -= take
        return cleaned

    # Results templates have many small variables. Proportionally trim long
    # values until the complete rendered message fits.
    overflow = total - variable_budget
    while overflow > 0:
        idx = max(range(len(cleaned)), key=lambda i: len(cleaned[i]))
        if len(cleaned[idx]) <= 20:
            break
        take = min(overflow, max(1, len(cleaned[idx]) - 20))
        cleaned[idx] = cleaned[idx][:-take].rstrip()
        overflow -= take
    return cleaned


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

def send_text_template(to: str, body_params, template_name: str = None) -> str:
    """
    Deliver an approved TEXT-ONLY template — a template with NO media header,
    only body variables. Valid OUTSIDE the 24-hour window (silent subscribers).

    The template must be APPROVED and have NO header (or the send is rejected).
    `template_name` overrides config.TEMPLATE_NAME — used to route quarterly
    RESULTS filings to their own metrics-table template. `body_params` fills
    {{1}}, {{2}}, ... in order; each is flattened via _sanitize_template_param()
    so Meta accepts it (no newlines/tabs/4+ spaces inside a variable).
    Returns the wamid.
    """
    raw_params = list(body_params or [])
    expected = getattr(config, "TEMPLATE_BODY_PARAM_COUNT", None)
    if expected is not None:
        expected = int(expected)
        if len(raw_params) != expected:
            raise WhatsAppError(
                0, 100,
                f"Template '{template_name or config.TEMPLATE_NAME}' expects "
                f"{expected} body parameters but code supplied {len(raw_params)}"
            )

    fitted_params = _fit_template_params(template_name or config.TEMPLATE_NAME, raw_params)
    params = [
        {"type": "text", "text": p}
        for p in fitted_params
    ]
    components = []
    if params:
        components.append({"type": "body", "parameters": params})

    name = template_name or config.TEMPLATE_NAME
    lang = getattr(config, "TEMPLATE_LANG", "en")
    
    # Debug: Show exactly what's being sent with FULL content
    _safe_print("")
    _safe_print("=" * 80)
    _safe_print(f"[WA TEMPLATE DEBUG] name={name!r} lang={lang!r} params={len(params)}")
    _safe_print("=" * 80)
    for i, p in enumerate(params, 1):
        text = p['text']
        _safe_print(f"\n📋 Param {i} ({len(text)} chars):")
        _safe_print("-" * 80)
        # Show first 200 chars in detail
        preview = text[:200] if len(text) > 200 else text
        _safe_print(preview)
        if len(text) > 200:
            _safe_print(f"... +{len(text) - 200} more chars")
        _safe_print("-" * 80)
        
        # Check for problematic characters
        issues = []
        if '\n' in text:
            issues.append(f"❌ Contains {text.count(chr(10))} newlines")
        if '\r' in text:
            issues.append(f"❌ Contains {text.count(chr(13))} carriage returns")
        if '\t' in text:
            issues.append(f"❌ Contains {text.count(chr(9))} tabs")
        if '    ' in text:
            issues.append(f"❌ Contains runs of 4+ spaces")
        if any(ord(c) < 32 and c not in '\n\r\t' for c in text):
            issues.append(f"❌ Contains control characters")
        
        if issues:
            _safe_print("⚠️  POTENTIAL ISSUES:")
            for issue in issues:
                _safe_print(f"   {issue}")
        else:
            _safe_print("✅ No obvious formatting issues")
    
    _safe_print("=" * 80)
    _safe_print("")
    
    _safe_print(
        f"[WA TEMPLATE] name={name!r} lang={lang!r} "
        f"params={len(params)} lengths={[len(p['text']) for p in params]}"
    )

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name or config.TEMPLATE_NAME,
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

    if not TEMPLATE_HAS_DOCUMENT_HEADER:
        raise WhatsAppError(
            0, None,
            "Configured WhatsApp template is text-only, but send_pdf_template "
            "requires an approved DOCUMENT-header template. Set "
            "TEMPLATE_HAS_DOCUMENT_HEADER=true and use the correct approved template."
        )

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
        
        # Sanitize and debug parameters
        sanitized = [_sanitize_template_param(p) for p in params]
        
        # Debug: Show PDF template parameters
        _safe_print("")
        _safe_print("=" * 80)
        _safe_print(f"[PDF TEMPLATE DEBUG] template={config.TEMPLATE_NAME!r} params={len(sanitized)}")
        _safe_print("=" * 80)
        for i, text in enumerate(sanitized, 1):
            _safe_print(f"\n📋 Body Param {i} ({len(text)} chars):")
            _safe_print("-" * 80)
            preview = text[:200] if len(text) > 200 else text
            _safe_print(preview)
            if len(text) > 200:
                _safe_print(f"... +{len(text) - 200} more chars")
            _safe_print("-" * 80)
        _safe_print("=" * 80)
        _safe_print("")
        
        components.append({
            "type": "body",
            "parameters": [
                {"type": "text", "text": text}
                for text in sanitized
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
        _safe_print(f"[WA ERROR] endpoint={endpoint} status={response.status_code} "
                    f"payload_keys={list(payload.keys())}")
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
    error_details = {}
    
    try:
        body = response.json()
        err  = body.get("error", {}) or {}
        error_code = err.get("code")
        error_msg  = err.get("message", error_msg)
        error_type = err.get("type")
        error_subcode = err.get("error_subcode")
        fbtrace_id = err.get("fbtrace_id")
        
        error_details = {
            "code": error_code,
            "type": error_type,
            "subcode": error_subcode,
            "fbtrace_id": fbtrace_id
        }
        
        if error_type or error_subcode or fbtrace_id:
            error_msg = (f"{error_msg} | type={error_type} "
                         f"subcode={error_subcode} fbtrace_id={fbtrace_id}")
    except Exception as parse_err:
        _safe_print(f"[ERROR] Failed to parse WhatsApp error response: {parse_err}")

    # Enhanced error messages for common issues
    if error_code == 131026:
        _safe_print(
            f"❌ [WhatsApp API Error {response.status_code}] Code 131026: RECIPIENT NOT VERIFIED\n"
            f"   → Recipient number is NOT a verified test number.\n"
            f"   → Go to Meta App Dashboard → WhatsApp → API Setup → 'To' field and add the number\n"
            f"   → OR publish your app to Live mode.\n"
            f"   → Error details: {error_details}"
        )
    elif error_code == 131047:
        _safe_print(
            f"⏰ [WhatsApp API Error {response.status_code}] Code 131047: 24-HOUR WINDOW CLOSED\n"
            f"   → The 24-hour customer service window has closed.\n"
            f"   → Message will be sent via template fallback."
        )
    elif error_code == 100:
        _safe_print(
            f"❌ [WhatsApp API Error {response.status_code}] Code 100: INVALID PARAMETER\n"
            f"   → Check template parameters for unsupported formatting (markdown, newlines).\n"
            f"   → Error: {error_msg}\n"
            f"   → Details: {error_details}"
        )
    elif error_code == 131053:
        _safe_print(
            f"❌ [WhatsApp API Error {response.status_code}] Code 131053: SERVICE UNAVAILABLE\n"
            f"   → Recipient's WhatsApp service is temporarily unavailable.\n"
            f"   → Error: {error_msg}"
        )
    elif error_code == 130472:
        _safe_print(
            f"❌ [WhatsApp API Error {response.status_code}] Code 130472: USER NUMBER INVALID\n"
            f"   → The phone number is not registered on WhatsApp.\n"
            f"   → Error: {error_msg}"
        )
    else:
        _safe_print(
            f"❌ [WhatsApp API Error {response.status_code}] Code {error_code}: {error_msg}\n"
            f"   → Details: {error_details}\n"
            f"   → Full response: {response.text[:500]}"
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