const path = require("path");

require("dotenv").config({
    path: path.resolve(__dirname, "../.env")
});

function num(value, fallback) {
    const n = Number(value);
    return Number.isFinite(n) && n > 0 ? n : fallback;
}

module.exports = {

    // Poll cadence in ms.
    interval: num(process.env.BSE_POLL_INTERVAL_MS, num(process.env.BSE_INTERVAL, 20000)),

    // Newest-first pages (50 rows each) to pull per cycle. Page 1 covers the latest filings.
    maxPages: num(process.env.BSE_PAGES, num(process.env.BSE_MAX_PAGES, 1)),

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
