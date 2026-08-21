const axios = require("axios");

/**
 * NSE's APIs reject requests that don't carry the session cookies you get by
 * first loading the website. Without them the corporate-announcements endpoint
 * intermittently returns 401/403 or an HTML challenge — which made some cycles
 * time out and retry (slow) or come back empty (announcement missed that cycle
 * and only delivered minutes later by the backfill). This primes and caches
 * those cookies, refreshing them on demand / on auth failures.
 */

const BROWSER_HEADERS = {
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        + "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept":
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
};

let cookieHeader = "";
let lastRefresh = 0;
const REFRESH_EVERY_MS = 30 * 60 * 1000;  // avoid blocking every 5 min on a cookie refresh
const REFRESH_FAILURE_GRACE_MS = 60 * 1000;

let inflight = null;


async function _doRefresh() {
    try {
        // Hitting the homepage first, then a section page, yields the full set
        // of cookies NSE expects on its API calls.
        const res = await axios.get("https://www.nseindia.com/", {
            headers: BROWSER_HEADERS,
            timeout: 12000,
            validateStatus: () => true,
        });

        const setCookie = res.headers["set-cookie"];
        if (setCookie && setCookie.length) {
            cookieHeader = setCookie.map(c => c.split(";")[0]).join("; ");
            lastRefresh = Date.now();
            console.log(`NSE session cookies refreshed (${setCookie.length} cookies).`);
        } else {
            console.log("NSE cookie refresh returned no Set-Cookie header.");
        }
    } catch (err) {
        // Keep the last known-good cookies. Mark the attempt time so a transient
        // NSE outage does not cause every API request to wait another 12s.
        lastRefresh = Date.now();
        console.log(`NSE cookie refresh failed: ${err.message} — using cached cookies=${Boolean(cookieHeader)}`);
    }
    return cookieHeader;
}


/** Refresh cookies now (deduped so concurrent callers share one request). */
async function refresh() {
    if (inflight) return inflight;
    inflight = _doRefresh().finally(() => { inflight = null; });
    return inflight;
}


/** Cookie header string for NSE API calls; refreshes if missing/stale. */
async function getCookieHeader() {
    const age = Date.now() - lastRefresh;
    if (!cookieHeader) {
        await refresh();
    } else if (age > REFRESH_EVERY_MS) {
        await refresh();
    } else if (age < REFRESH_FAILURE_GRACE_MS) {
        // A recent failed refresh should never block the hot path again.
        return cookieHeader;
    }
    return cookieHeader;
}


module.exports = {
    BROWSER_HEADERS,
    getCookieHeader,
    refresh,
};
