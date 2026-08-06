const path = require("path");

require("dotenv").config({
    path: path.resolve(__dirname, "../.env")
});

function num(value, fallback) {
    const n = Number(value);
    return Number.isFinite(n) && n > 0 ? n : fallback;
}

module.exports = {

    // Poll cadence. BSE disseminates a lot of filings minutes before the same
    // document shows up on NSE, so this service runs a much tighter loop than
    // the NSE scraper's 20s cycle — that head start is the whole point of it.
    interval: num(process.env.BSE_INTERVAL, 8000),

    // Newest-first pages (50 rows each) to pull per cycle. Paging stops early
    // as soon as a page holds nothing newer than the previous cycle's
    // high-water mark, so the steady-state cost is one request per cycle.
    maxPages: num(process.env.BSE_MAX_PAGES, 6),

    // Concurrent in-flight requests to BSE's API.
    requestLimit: num(process.env.BSE_REQUEST_LIMIT, 4),

    // PDFs downloaded in parallel per worker tick.
    downloadConcurrency: num(process.env.BSE_DOWNLOAD_CONCURRENCY, 8),

    // Jobs claimed per download-worker tick.
    downloadBatch: num(process.env.BSE_DOWNLOAD_BATCH, 20),

    // Circuit breaker — stop queueing if downloads are badly backed up.
    maxPendingJobs: num(process.env.BSE_MAX_PENDING_JOBS, 10000),

    // A filing's PDF is often not on the CDN the instant the row appears in
    // the feed. Retried with ~15s backoff, this covers ~2 min of propagation.
    maxDownloadRetries: num(process.env.BSE_MAX_DOWNLOAD_RETRIES, 8),

    // Where downloaded PDFs land. Must be the same volume the bot reads from.
    storageDir:
        process.env.PDF_STORAGE_PATH
        || path.join(__dirname, "../../storage/pdf"),

    // Subscribed-symbol list cache TTL.
    symbolCacheMs: num(process.env.BSE_SYMBOL_CACHE_MS, 20000)

};
