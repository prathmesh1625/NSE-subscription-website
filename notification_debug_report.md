# 🐛 WhatsApp Notification Not Received — Debug Report

> **Issue:** Announcements are downloaded (PDFs exist on disk, `download_status = DOWNLOADED`)  
> but `is_notified = false` on all rows. WhatsApp messages are never sent.  
> **Affected company:** CLEAN (and likely all companies)  
> **Affected users:**  (both subscribed, both ACTIVE)

---

## 📊 Current State (from DB queries)

### `nse_ingestion.announcements` — CLEAN rows

| id | title | download_status | is_notified | source | local_path |
|----|-------|----------------|-------------|--------|------------|
| 2928 | Shareholder Meeting / Postal Ballot | DOWNLOADED | **false** | BSE | `storage/pdf/BSE_CLEAN_2026-06-02T15_43_46.pdf` |
| 2927 | Announcement under Regulation 30 | DOWNLOADED | **false** | BSE | `storage/pdf/BSE_CLEAN_2026-06-03T11_40_41.pdf` |
| 2926 | Opening Of Ethos Watch Boutiques... | DOWNLOADED | **false** | BSE | `storage/pdf/BSE_CLEAN_2026-06-04T09_49_42.pdf` |

✅ PDF files **DO exist** on disk (confirmed `True`)  
✅ Subscriptions for CLEAN **ARE active** in `nse_subscription` DB  
❌ `is_notified` stays `false` → watcher is either not running or silently failing

---

## 🔍 Suspected Root Causes

### Cause 1 — `db_watcher.py` thread may be crashing silently
The watcher runs as a **background daemon thread** inside the Flask bot process.  
If it throws any exception on startup or mid-loop, the thread dies with no visible error.  
The Flask server keeps running so `start_all.bat` shows no failure.

### Cause 2 — `process_new_filings()` query may fail on new `source` / `canonical_id` columns  
We recently added `source` and `canonical_id` columns to the `announcements` table.  
The `fetch_new_filings()` SELECT in `db_watcher.py` uses `config.COL_COMPANY_NAME = "company_symbol"` as an alias — if psycopg2 mishandles it or any column rename breaks, the cursor throws and `process_new_filings()` returns `[]` silently.

### Cause 3 — `deliver_backfill_for_subscribers()` `_dedup_by_filename` bug (partially fixed)  
Fixed in last session — but the **fix may not have been saved properly** or the  
process was not restarted with the new code before the current run.

### Cause 4 — `bot_data.db` `sent_filings` already has entries  
If the SQLite `sent_filings` table already has entries for these PDFs from a previous  
broken send attempt, `is_filing_sent()` returns `True` and the bot skips them forever.

---

## 🛠️ How to Diagnose — Step by Step

### Step 1: Check if the watcher thread is actually running
Run this in a terminal to watch the bot process output live:

```powershell
# Find the python PID
Get-Process python | Select-Object Id, ProcessName, StartTime

# Tail the bot log (if it exists)
Get-Content "d:\prathmesh\shares\bot.log" -Wait -Tail 50
```

### Step 2: Check SQLite `sent_filings` — is the PDF already "sent"?
```powershell
cd d:\prathmesh\shares
python -c "
import sqlite3
conn = sqlite3.connect('bot_data.db')
rows = conn.execute(\"SELECT * FROM sent_filings WHERE filing_id LIKE '%CLEAN%' OR filing_id LIKE '%clean%'\").fetchall()
print('Sent filings for CLEAN:')
for r in rows: print(r)
conn.close()
"
```

### Step 3: Manually trigger the watcher logic once to see if it errors
```powershell
cd d:\prathmesh\shares
python -c "
import db_watcher
filings = db_watcher.fetch_new_filings()
print(f'Found {len(filings)} unnotified filings')
for f in filings[:3]:
    print(f)
"
```

### Step 4: Check subscriber lookup works for CLEAN
```powershell
cd d:\prathmesh\shares
python -c "
import db_watcher
subs = db_watcher.get_subscribers_for_symbol_pg('CLEAN')
print('Subscribers:', subs)
"
```

### Step 5: Manually force-send one PDF (test end-to-end)
```powershell
cd d:\prathmesh\shares
python -c "
import whatsapp
whatsapp.send_pdf(
    '918983119045',
    r'd:\prathmesh\shares\nse-announcement-downloader\nse-announcement-downloader\storage\pdf\BSE_CLEAN_2026-06-04T09_49_42.pdf',
    caption='Test: CLEAN announcement'
)
print('Done')
"
```

---

## 📁 Files Claude Needs to See

Share these files in the next conversation — paste their **full contents**:

| File | Path | Why Needed |
|------|------|------------|
| `db_watcher.py` | `d:\prathmesh\shares\db_watcher.py` | Main notification loop — most likely broken here |
| `database.py` | `d:\prathmesh\shares\database.py` | SQLite sent_filings tracker |
| `whatsapp.py` | `d:\prathmesh\shares\whatsapp.py` | PDF send function |
| `config.py` | `d:\prathmesh\shares\config.py` | Column names, paths, DB settings |
| `Bot.py` | `d:\prathmesh\shares\Bot.py` | Flask app + watcher startup |

> **Also paste the terminal output from Steps 1–4 above** so Claude can see exactly where it fails.

---

## 🔎 Quick SQL Checks (run these and paste output too)

```sql
-- In nse_ingestion: are there any notified rows at all?
SELECT COUNT(*) as total, 
       SUM(CASE WHEN is_notified THEN 1 ELSE 0 END) as notified,
       SUM(CASE WHEN NOT is_notified AND download_status='DOWNLOADED' THEN 1 ELSE 0 END) as pending_notify
FROM announcements;

-- In nse_subscription: all active subscriptions
SELECT u.mobile, c.symbol, s.status, s.end_date
FROM user_companies uc
JOIN users u ON u.id = uc.user_id
JOIN companies c ON c.id = uc.company_id
JOIN subscriptions s ON s.user_id = u.id
WHERE s.status = 'ACTIVE'
ORDER BY u.mobile;
```

---

## 📌 Summary

The PDFs are downloaded ✅, subscriptions are active ✅, but **the watcher is not sending**.  
The most likely culprit is either:

1. **The `db_watcher` thread dying silently** — you won't see this unless you check bot logs
2. **`sent_filings` SQLite already has these filenames** — causing bot to skip them

Run **Step 2** first — if `sent_filings` has entries for CLEAN, that's the bug.  
Run **Step 3** second — if `fetch_new_filings()` returns 0 rows, the query is broken.
