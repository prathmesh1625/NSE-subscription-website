-- Cleanup script to mark old failed filings as sent
-- Run this ONCE to clear the backlog of 2-day-old announcements

-- Mark filings older than 6 hours as sent (they failed repeatedly)
UPDATE nse_announcements 
SET is_sent = TRUE
WHERE is_sent = FALSE 
  AND download_status = 'DOWNLOADED'
  AND created_at < NOW() - INTERVAL '6 hours';

-- Check how many were marked
SELECT COUNT(*) as cleaned_up_filings
FROM nse_announcements 
WHERE is_sent = TRUE 
  AND download_status = 'DOWNLOADED'
  AND created_at < NOW() - INTERVAL '6 hours'
  AND updated_at > NOW() - INTERVAL '1 minute';
