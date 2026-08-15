const db =
    require("./connection");

// Idempotent schema setup — must match every repository's column names exactly.
async function ensureSchema() {

    // ── announcements ─────────────────────────────────────────────────────────
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

    // Rename legacy columns created with wrong names (idempotent)
    await db.query(`
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='announcements' AND column_name='symbol'
            ) THEN
                ALTER TABLE announcements RENAME COLUMN symbol TO company_symbol;
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='announcements' AND column_name='announced_at'
            ) THEN
                ALTER TABLE announcements RENAME COLUMN announced_at TO announcement_time;
            END IF;
        END $$;
    `);

    // Ensure pdf_url has a standalone unique constraint (old schema used composite unique)
    await db.query(`
        CREATE UNIQUE INDEX IF NOT EXISTS announcements_pdf_url_key ON announcements(pdf_url);
    `);

    // Read-path indexes for the Central Dashboard's admin API. Without these
    // both of its announcements-backed panels degrade to full sequential
    // scans and start timing out once this table gets large:
    //
    //   - listScrapedCompanies groups by company_symbol ("Scraped companies")
    //   - getCompanyFilings filters by company_symbol (one company's filings)
    //   - fetchUserDeliveries resolves PDF basenames back to announcements
    //     ("Alerts delivered" — the company/title/filed-at/PDF columns)
    //
    // The last one matches on regexp_replace(local_path, ...) rather than on
    // the bare column, so it needs an EXPRESSION index. The expression below
    // must stay byte-for-byte identical to the one in the backend's
    // adminRepository.fetchUserDeliveries, or Postgres won't use this index
    // and that panel silently falls back to "—" in every column.
    await db.query(`
        CREATE INDEX IF NOT EXISTS idx_announcements_company_symbol
            ON announcements(company_symbol);
    `);

    await db.query(`
        CREATE INDEX IF NOT EXISTS idx_announcements_file_key
            ON announcements((regexp_replace(local_path, '^.*[/\\\\]', '')));
    `);

    // ── company_state ─────────────────────────────────────────────────────────
    await db.query(`
        CREATE TABLE IF NOT EXISTS company_state (
          symbol                VARCHAR(20) PRIMARY KEY,
          last_announcement_time TIMESTAMP NOT NULL
        );
    `);

    // Rename legacy column created with wrong name (idempotent)
    await db.query(`
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='company_state' AND column_name='last_seen_at'
            ) THEN
                ALTER TABLE company_state RENAME COLUMN last_seen_at TO last_announcement_time;
            END IF;
        END $$;
    `);

    // ── download_jobs ─────────────────────────────────────────────────────────
    // downloadJobRepository uses: url, filename, status, updated_at
    await db.query(`
        CREATE TABLE IF NOT EXISTS download_jobs (
          id         SERIAL PRIMARY KEY,
          url        TEXT NOT NULL,
          filename   TEXT,
          status     VARCHAR(20) DEFAULT 'PENDING',
          created_at TIMESTAMP DEFAULT NOW(),
          updated_at TIMESTAMP DEFAULT NOW()
        );
    `);

    // Rename pdf_url -> url on tables created with the old schema
    await db.query(`
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='download_jobs' AND column_name='pdf_url'
            ) THEN
                ALTER TABLE download_jobs RENAME COLUMN pdf_url TO url;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='download_jobs' AND column_name='filename'
            ) THEN
                ALTER TABLE download_jobs ADD COLUMN filename TEXT;
            END IF;
        END $$;
    `);

    await db.query(`
        CREATE INDEX IF NOT EXISTS idx_download_jobs_status ON download_jobs(status);
    `);

    // ── failed_jobs ───────────────────────────────────────────────────────────
    // failedJobRepository uses: url, filename, retries, last_retry_at
    await db.query(`
        CREATE TABLE IF NOT EXISTS failed_jobs (
          id           SERIAL PRIMARY KEY,
          url          TEXT UNIQUE,
          filename     TEXT,
          retries      INTEGER NOT NULL DEFAULT 0,
          last_retry_at TIMESTAMPTZ,
          created_at   TIMESTAMP DEFAULT NOW()
        );
    `);

    // Rename pdf_url -> url on tables created with the old schema
    await db.query(`
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='failed_jobs' AND column_name='pdf_url'
            ) THEN
                -- Dedupe first so the rename doesn't violate the unique constraint
                DELETE FROM failed_jobs a
                USING failed_jobs b
                WHERE a.id > b.id AND a.pdf_url = b.pdf_url;

                ALTER TABLE failed_jobs RENAME COLUMN pdf_url TO url;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='failed_jobs' AND column_name='filename'
            ) THEN
                ALTER TABLE failed_jobs ADD COLUMN filename TEXT;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='failed_jobs' AND column_name='retries'
            ) THEN
                ALTER TABLE failed_jobs ADD COLUMN retries INTEGER NOT NULL DEFAULT 0;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='failed_jobs' AND column_name='last_retry_at'
            ) THEN
                ALTER TABLE failed_jobs ADD COLUMN last_retry_at TIMESTAMPTZ;
            END IF;
        END $$;
    `);

    await db.query(`
        CREATE UNIQUE INDEX IF NOT EXISTS failed_jobs_url_key ON failed_jobs(url);
    `);

    // ── worker_heartbeats ─────────────────────────────────────────────────────
    // workerHeartbeatRepository uses: worker_name, last_seen
    await db.query(`
        CREATE TABLE IF NOT EXISTS worker_heartbeats (
          worker_name VARCHAR(100) PRIMARY KEY,
          last_seen   TIMESTAMP NOT NULL
        );
    `);

    // Rename worker_id -> worker_name on tables created with the old schema
    await db.query(`
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='worker_heartbeats' AND column_name='worker_id'
            ) THEN
                ALTER TABLE worker_heartbeats RENAME COLUMN worker_id TO worker_name;
            END IF;
        END $$;
    `);

    console.log("Schema Verified");
}

module.exports =
    ensureSchema;
