"use strict";

/**
 * BSE global corporate-announcements feed fetcher.
 *
 * Ported from momentum-alerts-testing/scraper/src/clients/bseClient.js
 * (axios with insecureHTTPParser, keep-alive agents, cache-busting,
 *  detailed timing logs, _cacheBust param).
 *
 * Production wiring preserved:
 *  - normalise() / cleanTitle() business logic untouched
 *  - requestLimiter concurrency cap kept
 *  - retry() wrapper kept
 *  - Returns { rows, total } — same contract as before so bseWatcher.js
 *    needs zero changes.
 */

const https = require("https");
const http  = require("http");
const axios = require("axios");
const { performance } = require("perf_hooks");

const limiter = require("./requestLimiter");
const retry   = require("./retry");

// ─── HTTP client ─────────────────────────────────────────────────────────────

// Keep-alive + insecureHTTPParser — both measured to be necessary for BSE.
// BSE's edge sometimes returns responses Node's strict parser rejects
// ("Parse Error: Unexpected whitespace after header value").
const httpsAgent = new https.Agent({
    insecureHTTPParser: true,
    keepAlive:          true,
    maxSockets:         16,
});

const httpAgent = new http.Agent({
    insecureHTTPParser: true,
    keepAlive:          true,
    maxSockets:         16,
});

const BROWSER_HEADERS = {
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) " +
        "AppleWebKit/537.36 (KHTML, like Gecko) " +
        "Chrome/120.0.0.0 Safari/537.36",
    "Accept":           "application/json, text/plain, */*",
    "Accept-Language":  "en-US,en;q=0.9",
    "Origin":           "https://www.bseindia.com",
    "Referer":          "https://www.bseindia.com/",
    "Sec-Fetch-Dest":   "empty",
    "Sec-Fetch-Mode":   "cors",
    "Sec-Fetch-Site":   "same-site",
};

// ─── Constants ───────────────────────────────────────────────────────────────

const FEED_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w";

const ATTACHMENT_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/";

const PAGE_SIZE = 50;

// ─── Normalisation helpers ────────────────────────────────────────────────────

/**
 * Strip BSE's "<Company Name> - <scrip code> - " prefix from a subject line.
 * Preserves original cleanTitle logic from the production file.
 */
function cleanTitle(row) {
    const subject = String(row.NEWSSUB || "").trim();
    const code    = String(row.SCRIP_CD || "").trim();

    if (subject && code) {
        const marker = ` - ${code} - `;
        const at = subject.indexOf(marker);
        if (at !== -1) {
            const rest = subject.slice(at + marker.length).trim();
            if (rest) return rest;
        }
    }

    return subject || String(row.HEADLINE || "").trim();
}

function normalise(row) {
    const attachment = String(row.ATTACHMENTNAME || "").trim();

    return {
        newsId:      row.NEWSID || null,
        scripCd:     String(row.SCRIP_CD || "").trim(),
        companyName: String(row.SLONGNAME || "").trim(),
        title:       cleanTitle(row),
        headline:    String(row.HEADLINE || "").trim(),
        category:    String(row.CATEGORYNAME || "").trim(),
        subCategory: String(row.SUBCATNAME || "").trim(),
        announcedAt:
            row.NEWS_DT || row.DT_TM || row.News_submission_dt || null,
        disseminatedAt: row.DissemDT || row.DT_TM || null,
        attachment,
        pdfUrl: attachment ? `${ATTACHMENT_BASE}${attachment}` : null,
    };
}

// ─── Date helper ─────────────────────────────────────────────────────────────

function formatDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}${m}${d}`;
}

// ─── Public API ──────────────────────────────────────────────────────────────

/**
 * Fetch ONE page of BSE's global corporate-announcements feed.
 *
 * Returns { rows, total } — same contract as the original fetchBseFeed.js
 * so bseWatcher.js needs zero changes.
 */
async function fetchBsePage(day, pageNo) {

    return limiter.execute(() =>
        retry(async () => {

            const startedAt        = performance.now();
            const requestStartedAt = new Date();
            const timeoutMs        = Number(process.env.BSE_REQUEST_TIMEOUT_MS || 6000);

            console.log(
                `[BSE HTTP] Page ${pageNo} START | ${requestStartedAt.toISOString()}`
            );

            const response = await axios.get(FEED_URL, {
                httpAgent,
                httpsAgent,

                // Must be set on the axios config AND the agents — axios
                // writes its own `insecureHTTPParser` option which silently
                // overrides the agent's setting otherwise.
                insecureHTTPParser: true,

                timeout: timeoutMs,

                params: {
                    pageno:      pageNo,
                    strCat:      "-1",
                    strPrevDate: day,
                    strToDate:   day,
                    strScrip:    "",
                    strSearch:   "P",
                    strType:     "C",
                    subcategory: "-1",

                    // Cache-bust so CDN/proxy serves fresh data every request.
                    _cacheBust:  Date.now(),
                },

                headers: BROWSER_HEADERS,
            });

            const receivedAt = new Date();
            const elapsed    = Math.round(performance.now() - startedAt);

            let bytes = 0;
            try {
                bytes = Buffer.byteLength(JSON.stringify(response.data), "utf8");
            } catch (_) { /* ignore */ }

            console.log(
                `[BSE HTTP] Page ${pageNo} RESPONSE | ${elapsed}ms | ` +
                `status=${response.status} | bytes=${bytes} | ` +
                `received=${receivedAt.toISOString()}`
            );

            const data = response.data;

            if (!data || !Array.isArray(data.Table)) {
                return { rows: [], total: 0 };
            }

            return {
                rows:  data.Table.map(normalise),
                total: Number(
                    (data.Table1 && data.Table1[0] && data.Table1[0].ROWCNT) || 0
                ),
            };

        }, 2, 1200)
    ).catch(err => {
        console.log(`BSE feed ${day} page ${pageNo} failed: ${err.message}`);
        return { rows: [], total: 0 };
    });
}

module.exports = {
    fetchBsePage,
    ATTACHMENT_BASE,
    PAGE_SIZE,
};
