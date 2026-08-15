-- ===========================================================================
-- Read-path indexes for `announcements` (database: nse_ingestion)
--
-- WHY: the Central Dashboard's two announcements-backed panels both degraded
-- to full sequential scans of this table and started timing out:
--
--   * "Scraped companies"  -> ECONNABORTED in the dashboard (client gave up)
--   * "Alerts delivered"   -> every column silently rendered as "—", because
--                             the metadata lookup is wrapped in a catch
--
-- ensureSchema.js already creates these on scraper startup. This file is the
-- same two indexes written with CONCURRENTLY so they can be applied to a live
-- production database RIGHT NOW, without a deploy and without taking the
-- ACCESS EXCLUSIVE lock that would stall the scraper's inserts while the
-- index builds.
--
-- HOW TO RUN (must connect to nse_ingestion, NOT nse_subscription and NOT
-- pureframe_central):
--
--   psql "$INGESTION_DATABASE_URL" -f indexes_announcements.sql
--
-- CONCURRENTLY cannot run inside a transaction block, so run this file as-is
-- (psql -f, not wrapped in BEGIN/COMMIT) and do not add -1/--single-transaction.
-- ===========================================================================

-- Backs the "Scraped companies" GROUP BY and the per-company filings lookup.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_announcements_company_symbol
    ON announcements(company_symbol);

-- Backs "Alerts delivered". The query matches on the PDF's basename rather
-- than on local_path itself, so this must be an EXPRESSION index and the
-- expression must stay byte-for-byte identical to the predicate in the
-- backend's adminRepository.fetchUserDeliveries. If they drift, Postgres
-- silently falls back to a sequential scan and that panel breaks again.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_announcements_file_key
    ON announcements((regexp_replace(local_path, '^.*[/\\]', '')));

-- CONCURRENTLY leaves an INVALID index behind if a build fails, and a later
-- IF NOT EXISTS will happily skip rebuilding it. Verify all indexes below
-- report indisvalid = true; DROP and re-create any that do not.
SELECT
    i.relname                AS index_name,
    idx.indisvalid           AS is_valid,
    pg_size_pretty(pg_relation_size(i.oid)) AS size
FROM pg_index idx
JOIN pg_class i ON i.oid = idx.indexrelid
JOIN pg_class t ON t.oid = idx.indrelid
WHERE t.relname = 'announcements'
ORDER BY i.relname;
