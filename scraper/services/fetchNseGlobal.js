const axios =
    require("axios");

const limiter =
    require("./requestLimiter");

const session =
    require("./nseSession");

/**
 * Fetch ONE page of NSE's GLOBAL corporate-announcements feed.
 *
 * Same endpoint as the per-symbol fetch but WITHOUT a `symbol` param, so a
 * single request returns the most recent announcements across ALL companies
 * (newest first). We page through a few of these per cycle and filter locally
 * to subscribed symbols — far faster than one request per company.
 *
 * Sends NSE session cookies (see nseSession) so the API answers 200 instead of
 * 401/timeout. On an auth failure we refresh cookies and retry ONCE. Uses a
 * short timeout and fails fast so one flaky page can't stall the whole cycle
 * (the next cycle ~20s later retries). Returns [] on failure.
 */
async function _request(pageNo) {
    const cookie = await session.getCookieHeader();

    return axios.get(
        "https://www.nseindia.com/api/corporate-announcements",
        {
            params: { index: "equities", pageNo },
            headers: {
                ...session.BROWSER_HEADERS,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
                ...(cookie ? { "Cookie": cookie } : {}),
            },
            timeout: Number(process.env.NSE_REQUEST_TIMEOUT_MS || 6000),
            validateStatus: () => true,   // inspect status ourselves
        }
    );
}

async function fetchNsePage(pageNo) {
    return limiter.execute(async () => {
        const started = Date.now();
        try {
            let res = await _request(pageNo);

            // Auth/challenge → re-prime cookies once and retry.
            if (res.status === 401 || res.status === 403) {
                await session.refresh();
                res = await _request(pageNo);
            }

            if (res.status !== 200 || !Array.isArray(res.data)) {
                console.log(
                    `NSE global feed page ${pageNo}: status ${res.status}, `
                    + `${Array.isArray(res.data) ? res.data.length + " rows" : "non-array body"}`
                );
                return Array.isArray(res.data) ? res.data : [];
            }

            console.log(`[timing] NSE page=${pageNo} duration=${Date.now() - started}ms rows=${res.data.length}`);
            return res.data;
        } catch (err) {
            console.log(`[timing] NSE page=${pageNo} FAILED duration=${Date.now() - started}ms error=${err.message}`);
            return [];
        }
    });
}

module.exports =
    fetchNsePage;
