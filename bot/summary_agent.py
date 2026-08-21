# ============================================================
# summary_agent.py — low-priority background summary pre-generator
# ============================================================
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import config
import database as bot_db
from db_watcher import (
    get_pg_conn,
    generate_pdf_summary,
    SUMMARY_FORMAT_VERSION,
)


def _fetch_pending_filings():
    """Fetch a small, ordered batch for background work only.

    The live dispatcher owns new filings. Background work deliberately starts
    only after a short age window and uses very few workers so it cannot starve
    the live alert path or trigger an LLM rate-limit storm.
    """
    try:
        conn = get_pg_conn()
        cur = conn.cursor()
        min_age = max(0, int(getattr(config, "SUMMARY_AGENT_MIN_AGE_SEC", 30)))
        limit = max(1, int(getattr(config, "SUMMARY_AGENT_MAX_CANDIDATES", 20)))
        cur.execute(f"""
            SELECT
                {config.COL_ID} AS filing_id,
                {config.COL_COMPANY_SYMBOL} AS symbol,
                {config.COL_FILING_TYPE} AS filing_type,
                {config.COL_FILE_PATH} AS file_path,
                pdf_url,
                {config.COL_CREATED_AT} AS created_at
            FROM {config.FILINGS_TABLE}
            WHERE download_status = 'DOWNLOADED'
              AND {config.COL_CREATED_AT} <= (CURRENT_TIMESTAMP - (%s * INTERVAL '1 second'))
            ORDER BY {config.COL_CREATED_AT} DESC
            LIMIT %s
        """, (min_age, limit))
        rows = cur.fetchall()
        cur.close()
        conn.close()

        resolved = []
        for row in rows:
            row = dict(row)
            rel = (row.get("file_path") or "").strip()
            path = os.path.join(config.SCRAPER_BASE_PATH, rel)
            row["file_path"] = path
            row["file_key"] = os.path.basename(path).strip()
            resolved.append(row)
        return resolved
    except Exception as e:
        print(f"❌ [SummaryAgent] PostgreSQL error: {e}")
        return []


def process_pending_summaries():
    filings = _fetch_pending_filings()
    candidates = []
    for filing in filings:
        file_key = filing.get("file_key") or ""
        file_path = filing.get("file_path") or ""
        if not file_key or not os.path.exists(file_path):
            continue
        # IMPORTANT: use the current message-format version. An old cached
        # summary must not suppress generation of the new layout.
        if bot_db.get_filing_summary(file_key, SUMMARY_FORMAT_VERSION):
            continue
        candidates.append(filing)

    if not candidates:
        return

    workers = max(1, int(getattr(config, "SUMMARY_AGENT_WORKERS", 1)))
    print(f"🤖 [SummaryAgent] {len(candidates)} pending summary(s), workers={workers}")

    def build(filing):
        file_key = filing["file_key"]
        print(f"🤖 [SummaryAgent] Generating summary for {file_key}...")
        summary = generate_pdf_summary(
            filing["file_path"],
            company=filing.get("symbol"),
            filing_type=filing.get("filing_type") or "",
            download_url=filing.get("pdf_url") or "",
        )
        return file_key, summary

    generated = 0
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="pre-summary") as pool:
        futures = [pool.submit(build, filing) for filing in candidates]
        for future in as_completed(futures):
            try:
                file_key, summary = future.result()
                if summary:
                    bot_db.save_filing_summary(file_key, summary, SUMMARY_FORMAT_VERSION)
                    generated += 1
                    print(f"✅ [SummaryAgent] Cached summary for {file_key}")
                else:
                    print(f"⚠️ [SummaryAgent] Could not summarise {file_key} — retry next cycle.")
            except Exception as e:
                print(f"⚠️ [SummaryAgent] Worker failed: {e}")

    if generated:
        print(f"📋 [SummaryAgent] Generated {generated} new summary/summaries this cycle.")


def start_summary_agent(interval_sec: int = 90):
    """Start low-priority background pre-generation."""
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
