const https = require("https");
const http = require("http");
const axios = require("axios");

// BSE's edge occasionally returns responses Node's strict HTTP parser rejects,
// and every request pays a fresh TLS handshake without keep-alive (~700ms vs
// ~60ms measured against api.bseindia.com). Both matter at an 8s poll cadence.
const httpsAgent = new https.Agent({
    insecureHTTPParser: true,
    keepAlive: true,
    maxSockets: 16
});

const httpAgent = new http.Agent({
    insecureHTTPParser: true,
    keepAlive: true,
    maxSockets: 16
});

// api.bseindia.com answers with an empty body unless the request looks like it
// came from the announcements page on www.bseindia.com.
const BROWSER_HEADERS = {
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        + "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.bseindia.com",
    "Referer": "https://www.bseindia.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site"
};

const client = axios.create({
    httpAgent,
    httpsAgent,
    headers: BROWSER_HEADERS,
    timeout: 20000,

    // Must be set HERE, not only on the agents. Axios always writes an explicit
    // `options.insecureHTTPParser` from its own config, which overrides
    // whatever the agent was constructed with — so an agent-only setting
    // silently leaves the strict parser on and BSE's replies die with
    // "Parse Error: Unexpected whitespace after header value".
    insecureHTTPParser: true
});

module.exports = {
    client,
    httpAgent,
    httpsAgent,
    BROWSER_HEADERS
};
