# ============================================================
#  summary_agent.py  —  Background worker that pre-generates
#                        AI summaries for ALL downloaded PDFs
#                        and caches them in filing_summaries
#                        (SQLite).  The sending flow in
#                        db_watcher.py stays unchanged — it
#                        just reads from the cache instead of
#                        generating on-the-fly.
# ============================================================
import os
import time
import threading

import config
import database as bot_db
from db_watcher import get_pg_conn, generate_pdf_summary


def _fetch_all_downloaded_filings():
    """Return all downloaded PDFs from PostgreSQL, newest first (up to 500)."""
    try:
        conn = get_pg_conn()
        cur  = conn.cursor()
        cur.execute(f"""
            SELECT
                {config.COL_ID}        AS filing_id,
                {config.COL_FILE_PATH} AS file_path
            FROM {config.FILINGS_TABLE}
            WHERE download_status = 'DOWNLOADED'
            ORDER BY {config.COL_CREATED_AT} DESC
            LIMIT 500
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        resolved = []
        for row in rows:
            row = dict(row)
            rel = (row.get("file_path") or "").strip()
            row["file_path"] = os.path.join(config.SCRAPER_BASE_PATH, rel)
            resolved.append(row)
        return resolved
    except Exception as e:
        print(f"❌ [SummaryAgent] PostgreSQL error: {e}")
        return []


def process_pending_summaries():
    """
    For every downloaded PDF that has no cached summary yet, generate one
    and save it to the filing_summaries SQLite table.
    """
    filings   = _fetch_all_downloaded_filings()
    generated = 0

    for filing in filings:
        file_path = filing["file_path"]
        file_key  = os.path.basename(file_path).strip()

        if not file_key:
            continue

        if bot_db.get_filing_summary(file_key):
            continue  # already cached

        if not os.path.exists(file_path):
            continue

        print(f"🤖 [SummaryAgent] Generating summary for {file_key}...")
        summary = generate_pdf_summary(file_path)
        if summary:
            bot_db.save_filing_summary(file_key, summary)
            generated += 1
            print(f"✅ [SummaryAgent] Cached summary for {file_key}")
        else:
            print(f"⚠️  [SummaryAgent] Could not summarise {file_key} — will retry next cycle.")

    if generated:
        print(f"📋 [SummaryAgent] Generated {generated} new summary/summaries this cycle.")


def start_summary_agent(interval_sec: int = 120):
    """Start the summary agent as a background daemon thread."""
    def loop():
        print(f"🤖 Summary agent started — scanning every {interval_sec}s for un-summarised PDFs.")
        while True:
            try:
                process_pending_summaries()
            except Exception as e:
                print(f"❌ [SummaryAgent] Unexpected error: {e}")
            time.sleep(interval_sec)

    thread = threading.Thread(target=loop, daemon=True, name="SummaryAgent")
    thread.start()
