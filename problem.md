# Problem Report — WhatsApp Error 131047 (Async Status Callback — Template Retry Loop)

**Date:** 2026-06-08 (15:33 IST log)
**Bot:** NSE / BSE Filing Alerts WhatsApp Bot
**Error Code:** Meta 131047 — "Re-engagement message / 24-hour window closed"

---

## Observed Log (verbatim, 15:25 – 15:33 IST)

```
WhatsApp API 200
[OK] Sent PDF 'BSE_TATASTEEL_2026-06-08T15_25_05.25.pdf' to 917057004992 (free-form)
   ✅ Template retry succeeded for 917057004992.

127.0.0.1 - - [08/Jun/2026 15:33:16] "POST /webhook HTTP/1.1" 200 -
Webhook POST received: {
  "statuses": [{
    "id":           "wamid.HBgMOTE3MDU3MDA0OTkyFQIAERgSRDQ4QjMxNzA4MTVERUQzMUIwAA==",
    "status":       "failed",
    "timestamp":    "1780912995",
    "recipient_id": "917057004992",
    "errors": [{
      "code":    131047,
      "title":   "Re-engagement message",
      "message": "Re-engagement message",
      "error_data": {
        "details": "Message failed to send because more than 24 hours have passed since the customer last replied to this number."
      }
    }]
  }]
}

⚠️  Status 131047: free-form PDF not delivered to 917057004992
    (wamid=wamid.HBgMOTE3MDU3MDA0OTkyFQIAERgSRDQ4QjMxNzA4MTVERUQzMUIwAA==)
   ↩️  Unmarked sent_filings for 917057004992 / filing 5448.
   Retrying BSE_TATASTEEL_2026-06-08T15_25_05.25.pdf via template 'nse_bot'..
```

---

## Timeline of Events

| Time | Event |
|------|-------|
| **15:25** | `db_watcher.py` picks up a new BSE TATASTEEL filing and calls `send_pdf()`. |
| **15:25** | Meta API returns HTTP 200 for the **free-form** document send. |
| **15:25** | `[OK] Sent PDF ... (free-form)` is printed. |
| **15:25** | Filing is marked `sent` in SQLite (`sent_filings`) and wamid is stored in `wamid_tracking`. |
| **15:25** | Bot also prints `✅ Template retry succeeded for 917057004992` — **suspicious** (see below). |
| **15:33** | Meta sends an async webhook `status: "failed"` / code 131047 for the same wamid. |
| **15:33** | `_handle_status_update()` correctly finds the wamid, unmarks the filing, and triggers a template retry. |

---

## Two Distinct Problems in This Log

### Problem 1 — Spurious "Template retry succeeded" at Send-Time (15:25)

The line:
```
✅ Template retry succeeded for 917057004992.
```
appears **immediately after the free-form send succeeds**. This should never happen — the template path is only supposed to execute when the *synchronous* `send_pdf()` call raises a `WhatsAppError` with `is_reengagement=True`.

**Possible causes:**
- `_try_send()` / `send_pdf()` is calling the template path unconditionally (bug in calling code).
- A previous pending-retry entry for this phone+filing was queued and fired at the same time as the new free-form send, producing a race condition.
- The `pending_filings` queue had a stale entry that was processed concurrently.

This results in **two messages being sent to the user** — one free-form and one template — at 15:25, before Meta's async failure callback even arrives.

---

### Problem 2 — Async Failure Callback Triggers Yet Another Template Retry (15:33)

At 15:33, Meta delivers the async `status: failed` / 131047 webhook for the **free-form wamid**. The `_handle_status_update()` handler correctly:
1. Finds the wamid in `wamid_tracking`.
2. Unmarks the filing in `sent_filings`.
3. Triggers a **second template retry** for the same PDF.

But by this point the filing may have already been sent via template at 15:25 (Problem 1). So the user could receive **up to 3 copies** of the same PDF:
- Copy 1: free-form (failed silently — user never got it)
- Copy 2: template (sent at 15:25 from the stale queue or spurious path)
- Copy 3: template (sent at 15:33 from the webhook handler)

---

## Root Cause Analysis

### Why does the template fire at 15:25 (synchronously)?

Look at `whatsapp.py → send_pdf()`:
```python
try:
    wamid = _send_pdf_document(to, media_id, filename, caption)
    _safe_print(f"[OK] Sent PDF '{filename}' to {to} (free-form)")
    return "freeform", wamid
except WhatsAppError as e:
    template_name = getattr(config, "TEMPLATE_NAME", "") or ""
    if e.is_reengagement and template_name:
        wamid = _send_pdf_template(...)
        ...
        return "template", wamid
    raise
```

The synchronous template retry only fires if `_send_pdf_document()` raises. If `send_pdf()` returned `("freeform", wamid)` successfully, something else printed "Template retry succeeded" — most likely the **pending_filings retry queue processor** in `db_watcher.py` picked up a stale pending entry for the same phone+filing and processed it at the same moment.

### Why does the 15:33 callback re-trigger a retry?

`_handle_status_update()` in `Bot.py` uses the wamid from Meta's callback to look up the filing and unconditionally queues/performs a template retry when it finds error 131047. It has **no guard to check whether a template was already sent** for this filing, so it always retries.

---

## Impact

| Consequence | Detail |
|---|---|
| **Duplicate messages to user** | User `917057004992` may receive 2–3 copies of the same PDF. |
| **Stale pending_filings entries** | Old retry entries are being processed alongside new sends, causing template fires at wrong times. |
| **No idempotency guard** | `_handle_status_update()` doesn't check if a template was already sent before retrying. |

---

## Fixes Needed

### Fix A — Add idempotency to `_handle_status_update()` (Bot.py)
Before retrying via template, check if a template was already sent for this filing+phone:
```python
# Pseudo-code
if db.was_template_sent(phone, filing_id):
    print("Template already sent — skipping duplicate retry.")
    return
```
Add a `template_sent_filings` table or a `channel` column to `sent_filings`/`wamid_tracking` to track which channel (freeform vs template) was last used.

### Fix B — Clean up stale `pending_filings` before sending (db_watcher.py)
Before calling `send_pdf()`, clear any existing `pending_filings` entry for the same phone+filing_id to prevent the retry queue from firing a template concurrently with a new free-form attempt.

### Fix C — Mark template channel in `wamid_tracking` (database.py)
Store the delivery channel (`freeform` / `template`) in `wamid_tracking` when calling `store_wamid()`. This lets `_handle_status_update()` skip the retry if the channel is already `template` (a failed template is not retried via another template).

### Fix D — Verify "Template retry succeeded" source
Add a stack trace or caller-ID log to every place that prints "Template retry succeeded" to definitively identify whether it comes from `send_pdf()`, the pending queue processor, or elsewhere.

---

## Files to Share With Claude

Share the following **4 files** in this order:

| # | File | Why it's needed |
|---|------|----------------|
| 1 | `Bot.py` | Contains `_handle_status_update()` — the webhook handler that triggers the 15:33 retry. Primary fix site. |
| 2 | `db_watcher.py` | Contains `_try_send()` and the pending-filings retry queue — source of the spurious 15:25 template send. |
| 3 | `database.py` | Contains `store_wamid()`, `get_wamid_info()`, `remove_wamid()`, `queue_pending_filing()`, `unmark_filing_sent()` — all DB helpers in the delivery/retry flow. |
| 4 | `whatsapp.py` | Contains `send_pdf()` / `_send_pdf_template()` — the synchronous template fallback logic. |

> **Also share `config.py`** so Claude can see `TEMPLATE_NAME`, `TEMPLATE_BODY_PARAM_COUNT`, and `TEMPLATE_LANG`.

---

## Suggested Prompt for Claude

> *"My WhatsApp bot is sending duplicate PDFs to users. Here is the log and 5 files. The sequence is:*
> 1. *15:25 — free-form send returns HTTP 200 AND 'Template retry succeeded' prints immediately (shouldn't happen).*
> 2. *15:33 — Meta sends async 131047 callback; the webhook handler retries via template again.*
>
> *Please:*
> 1. *Find why 'Template retry succeeded' fires at 15:25 when the free-form send succeeded — trace all callers of `_send_pdf_template()` and the pending-filings queue processor in `db_watcher.py`.*
> 2. *Add an idempotency guard to `_handle_status_update()` so it doesn't retry via template if one was already sent for this filing+phone.*
> 3. *Add a `channel` column to `wamid_tracking` (or a new flag in `sent_filings`) to persist whether freeform or template was the last delivery attempt, so the guard in step 2 works correctly."*
