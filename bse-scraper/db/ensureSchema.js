const db = require("./connection");

/**
 * Idempotent schema setup for the BSE scraper.
 *
 * Deliberately additive. `announcements` is shared with the NSE scraper and is
 * only ever CREATE-IF-NOT-EXISTS'd here with the exact same DDL the NSE
 * scraper uses, so whichever service boots first on a fresh database wins and
 * the other is a no-op. Nothing existing is altered or dropped.
 *
 * The job queues, by contrast, are private to this service (bse_ prefix). A
 * shared queue would put every BSE download behind whatever backlog the NSE
 * scraper happens to have, which is exactly the delay this service exists to
 * avoid.
 */
async function ensureSchema() {

    // ── announcements (SHARED — created only if absent) ───────────────────────
    await db.query(`
        CREATE TABLE IF NOT EXISTS announcements (
          id               SERIAL PRIMARY KEY,
          company_symbol   VARCHAR(20) NOT NULL,
          title            TEXT,
          pdf_url          TEXT NOT NULL UNIQUE,
          local_path       TEXT,
          announcement_time TIMESTAMP,
          download_status  VARCHAR(20) DEFAULT 'PENDING',
          created_at       TIMESTAMP DEFAULT NOW()
        );
    `);

    // The bot sets this after delivering; it creates the column itself too, but
    // this service can insert rows before the bot has ever run.
    await db.query(`
        ALTER TABLE announcements
        ADD COLUMN IF NOT EXISTS is_notified BOOLEAN DEFAULT FALSE;
    `);

    // Which exchange produced a row. NULL on every pre-existing row, which the
    // bot treats as NSE. Nothing depends on it for delivery — it exists so the
    // BSE head start is measurable and so admin tooling can tell the feeds
    // apart.
    await db.query(`
        ALTER TABLE announcements
        ADD COLUMN IF NOT EXISTS exchange VARCHAR(8);
    `);

    // Backs the bot's cross-exchange duplicate lookup (same filing, both feeds)
    // and its per-symbol backfill scan.
    await db.query(`
        CREATE INDEX IF NOT EXISTS idx_announcements_symbol_time
        ON announcements (UPPER(company_symbol), announcement_time DESC);
    `);

    // ── bse_download_jobs (PRIVATE) ───────────────────────────────────────────
    await db.query(`
        CREATE TABLE IF NOT EXISTS bse_download_jobs (
          id         SERIAL PRIMARY KEY,
          url        TEXT NOT NULL,
          filename   TEXT,
          status     VARCHAR(20) DEFAULT 'PENDING',
          created_at TIMESTAMP DEFAULT NOW(),
          updated_at TIMESTAMP DEFAULT NOW()
        );
    `);

    await db.query(`
        CREATE INDEX IF NOT EXISTS idx_bse_download_jobs_status
        ON bse_download_jobs (status);
    `);

    // ── bse_failed_jobs (PRIVATE) ─────────────────────────────────────────────
    await db.query(`
        CREATE TABLE IF NOT EXISTS bse_failed_jobs (
          id            SERIAL PRIMARY KEY,
          url           TEXT UNIQUE,
          filename      TEXT,
          retries       INTEGER NOT NULL DEFAULT 0,
          last_retry_at TIMESTAMPTZ,
          last_error    TEXT,
          created_at    TIMESTAMP DEFAULT NOW()
        );
    `);

    // ── worker_heartbeats (SHARED — created only if absent) ───────────────────
    await db.query(`
        CREATE TABLE IF NOT EXISTS worker_heartbeats (
          worker_name VARCHAR(100) PRIMARY KEY,
          last_seen   TIMESTAMP NOT NULL
        );
    `);

    console.log("BSE Schema Verified");
}

module.exports = ensureSchema;
