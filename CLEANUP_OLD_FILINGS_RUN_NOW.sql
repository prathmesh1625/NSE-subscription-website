-- ============================================
-- CLEANUP OLD FILINGS - RUN THIS IMMEDIATELY
-- ============================================
-- This will mark all old filings (>6 hours) as sent
-- so they stop appearing in your logs
-- ============================================

UPDATE nse_announcements 
SET is_sent = TRUE
WHERE is_sent = FALSE 
  AND download_status = 'DOWNLOADED'
  AND created_at < NOW() - INTERVAL '6 hours';

-- Check how many were updated
SELECT COUNT(*) as cleaned_up_count 
FROM nse_announcements 
WHERE is_sent = TRUE 
  AND created_at < NOW() - INTERVAL '6 hours';

-- Verify only recent filings remain unsent
SELECT 
  COUNT(*) as remaining_unsent,
  MIN(EXTRACT(EPOCH FROM (NOW() - created_at))) as oldest_seconds
FROM nse_announcements 
WHERE is_sent = FALSE 
  AND download_status = 'DOWNLOADED';
