"use strict";

/**
 * NSE global corporate-announcements feed fetcher.
 *
 * Ported from momentum-alerts-testing/scraper/src/clients/nseClient.js
 * (native https, keep-alive, cache-busting, detailed timing logs).
 *
 * Production wiring preserved:
 *  - nseSession cookie injection + 401/403 auto-refresh
 *  - requestLimiter concurrency cap
 *  - Returns plain Array (same contract as before) so nseWatcher.js
 *    needs zero changes.
 */

const https   = require("https");
const { performance } = require("perf_hooks");

const limiter  = require("./requestLimiter");
const session  = require("./nseSession");

// ─── Constants ───────────────────────────────────────────────────────────────

const NSE_BASE_URL        = "https://www.nseindia.com";
const NSE_ANNOUNCEMENT_API = `${NSE_BASE_URL}/api/corporate-announcements`;

const httpsAgent = new https.Agent({
    keepAlive:  true,
    maxSockets: 20,
});

const DEFAULT_HEADERS = {
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
        "AppleWebKit/537.36 (KHTML, like Gecko) " +
        "Chrome/140.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         `${NSE_BASE_URL}/companies-listing/corporate-filings-announcements`,
    "Origin":          NSE_BASE_URL,
    "Connection":      "keep-alive",
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function buildUrl(pageNo) {
    const url = new URL(NSE_ANNOUNCEMENT_API);
    url.searchParams.set("index",  "equities");
    url.searchParams.set("pageNo", String(pageNo));

    // Cache-bust so intermediary proxies cannot serve a stale response.
    url.searchParams.set("_cacheBust", String(Date.now()));

    return url.toString();
}

/**
 * Low-level native-https fetch — detailed timing logs, hard timeout,
 * keep-alive agent.  Returns the parsed JSON array on success.
 * Rejects with an Error on any failure so the caller can retry.
 */
function fetchJson(urlStr, headers, pageNo) {

    const timeoutMs = Number(process.env.NSE_REQUEST_TIMEOUT_MS || 6000);

    const startedAt        = performance.now();
    const requestStartedAt = new Date();

    console.log(`[NSE HTTP] Page ${pageNo} START | ${requestStartedAt.toISOString()}`);

    return new Promise((resolve, reject) => {

        let settled           = false;
        let bodyCompletedAt   = null;

        function fail(err) {
            if (settled) return;
            settled = true;
            const ms = Math.round(performance.now() - startedAt);
            console.error(`[NSE HTTP] Page ${pageNo} ERROR | ${ms}ms | ${err.message}`);
            reject(err);
        }

        const req = https.get(
            urlStr,
            {
                agent:   httpsAgent,
                headers: { ...DEFAULT_HEADERS, ...headers },
            },
            (res) => {

                const headerMs = Math.round(performance.now() - startedAt);
                const receivedAt = new Date();

                console.log(
                    `[NSE HTTP] Page ${pageNo} HEADERS | ${headerMs}ms | ` +
                    `status=${res.statusCode} | received=${receivedAt.toISOString()}`
                );
                console.log(
                    `[NSE HTTP] Page ${pageNo} CACHE | ` +
                    `date=${res.headers.date || "none"} | ` +
                    `cache-control=${res.headers["cache-control"] || "none"} | ` +
                    `age=${res.headers.age || "none"} | ` +
                    `etag=${res.headers.etag || "none"} | ` +
                    `last-modified=${res.headers["last-modified"] || "none"}`
                );

                let body  = "";
                let bytes = 0;

                res.setEncoding("utf8");
                res.on("data", (chunk) => {
                    body  += chunk;
                    bytes += Buffer.byteLength(chunk, "utf8");
                });

                res.on("end", () => {

                    bodyCompletedAt = new Date();
                    const bodyMs = Math.round(performance.now() - startedAt);
                    console.log(`[NSE HTTP] Page ${pageNo} BODY END | ${bodyMs}ms | bytes=${bytes}`);

                    const status = res.statusCode || 0;

                    // Surface auth failures so caller can refresh cookies.
                    if (status === 401 || status === 403) {
                        fail(Object.assign(new Error(`NSE HTTP ${status}`), { status }));
                        return;
                    }

                    if (status < 200 || status >= 300) {
                        fail(new Error(`NSE HTTP ${status}: ${body.slice(0, 200)}`));
                        return;
                    }

                    let data;
                    try {
                        const parseStart = performance.now();
                        data = JSON.parse(body);
                        console.log(
                            `[NSE HTTP] Page ${pageNo} JSON PARSED | ` +
                            `${Math.round(performance.now() - parseStart)}ms`
                        );
                    } catch (e) {
                        fail(new Error(`NSE returned invalid JSON: ${e.message}`));
                        return;
                    }

                    if (!Array.isArray(data)) {
                        console.log(`NSE global feed page ${pageNo}: non-array body`);
                        // Return [] rather than failing — watcher handles empty gracefully.
                        if (!settled) { settled = true; resolve([]); }
                        return;
                    }

                    const completeMs = Math.round(performance.now() - startedAt);
                    console.log(
                        `[NSE HTTP] Page ${pageNo} COMPLETE | ${completeMs}ms | ` +
                        `received=${(bodyCompletedAt || receivedAt).toISOString()}`
                    );

                    if (!settled) { settled = true; resolve(data); }
                });

                res.on("error", fail);
            }
        );

        req.setTimeout(timeoutMs, () => {
            req.destroy();
            fail(new Error(`NSE request timed out after ${timeoutMs}ms`));
        });

        req.on("error", fail);
    });
}

// ─── Public API ──────────────────────────────────────────────────────────────

/**
 * Fetch ONE page of NSE's global corporate-announcements feed.
 *
 * Mirrors the original contract:
 *   - Returns a plain Array (empty array on failure)
 *   - Uses requestLimiter + nseSession cookies
 *   - Auto-refreshes cookies on 401/403
 */
async function fetchNsePage(pageNo) {

    return limiter.execute(async () => {

        const started = Date.now();
        const url     = buildUrl(pageNo);

        try {

            const cookie = await session.getCookieHeader();
            const extraHeaders = cookie ? { "Cookie": cookie } : {};

            let data = await fetchJson(url, extraHeaders, pageNo);

            console.log(`[timing] NSE page=${pageNo} duration=${Date.now() - started}ms rows=${data.length}`);
            return data;

        } catch (err) {

            // Auth failure — refresh cookies once and retry.
            if (err.status === 401 || err.status === 403) {

                console.log(`NSE page ${pageNo}: auth failure (${err.message}) — refreshing cookies`);

                await session.refresh();

                try {
                    const cookie = await session.getCookieHeader();
                    const extraHeaders = cookie ? { "Cookie": cookie } : {};
                    const data = await fetchJson(url, extraHeaders, pageNo);
                    console.log(`[timing] NSE page=${pageNo} (retry) duration=${Date.now() - started}ms rows=${data.length}`);
                    return data;
                } catch (retryErr) {
                    console.log(`[timing] NSE page=${pageNo} FAILED (retry) duration=${Date.now() - started}ms error=${retryErr.message}`);
                    return [];
                }
            }

            console.log(`[timing] NSE page=${pageNo} FAILED duration=${Date.now() - started}ms error=${err.message}`);
            return [];
        }
    });
}

module.exports = fetchNsePage;
