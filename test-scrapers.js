"use strict";

const path = require("path");

const fs = require("fs");

// Automatically locate node_modules from momentum-alerts-testing or local if present
const sharedModules = path.resolve(__dirname, "../momentum-alerts-testing/scraper/node_modules");
if (fs.existsSync(sharedModules)) {
    process.env.NODE_PATH = [process.env.NODE_PATH, sharedModules].filter(Boolean).join(path.delimiter);
    require("module").Module._initPaths();
}

const fetchNsePage = require("./scraper/services/fetchNseGlobal");
const { fetchBseFeed: _raw, fetchBsePage } = require("./bse-scraper/services/fetchBseFeed");
const { istDateStamp } = require("./bse-scraper/services/istDate");

// Configuration
const POLL_INTERVAL_MS = Number(process.env.NSE_POLL_INTERVAL_MS || process.env.POLL_INTERVAL_MS || 20000);

// Tracking set for deduplication
const seenKeys = new Set();
let cycleCount = 0;
let totalDetected = 0;
let isFirstRun = true;
let isStopping = false;

// Helpers to parse dates into IST
function parseNseDate(str) {
    if (!str) return null;
    const d = new Date(str + " +0530");
    return isNaN(d.getTime()) ? null : d;
}

function parseBseDate(str) {
    if (!str) return null;
    const d = new Date(str + (str.includes("+") ? "" : "+05:30"));
    return isNaN(d.getTime()) ? null : d;
}

function formatIST(date) {
    if (!date) return "Unknown";
    return date.toLocaleString("en-IN", {
        timeZone: "Asia/Kolkata",
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: true,
    }) + " IST";
}

function formatLatency(publishedDate, detectedDate) {
    if (!publishedDate || !detectedDate) return "N/A";
    const diffMs = detectedDate.getTime() - publishedDate.getTime();
    if (diffMs < 0) return "0.00s (instant/clock skew)";
    if (diffMs < 1000) return `${diffMs}ms`;
    const sec = (diffMs / 1000).toFixed(2);
    if (sec < 60) return `${sec}s`;
    const min = Math.floor(sec / 60);
    const remainSec = (sec % 60).toFixed(0);
    return `${min}m ${remainSec}s (${sec}s total)`;
}

function printAnnouncementBanner(exchange, info) {
    const divider = "═".repeat(78);
    console.log(`\n╔${divider}╗`);
    console.log(`║ 🔔 NEW REAL-TIME ANNOUNCEMENT DETECTED [${exchange}]`.padEnd(79) + "║");
    console.log(`╠${divider}╣`);
    console.log(`║ Company:        ${info.company}`.padEnd(79) + "║");
    console.log(`║ Headline:       ${info.headline}`.padEnd(79) + "║");
    console.log(`║ Published Time: ${info.publishedTimeStr}`.padEnd(79) + "║");
    console.log(`║ Detected Time:  ${info.detectedTimeStr}`.padEnd(79) + "║");
    console.log(`║ Latency / Age:  ${info.latencyStr}`.padEnd(79) + "║");
    if (info.attachment) {
        console.log(`║ Attachment:     ${info.attachment}`.padEnd(79) + "║");
    }
    console.log(`╚${divider}╝\n`);
}

async function runSingleCycle() {
    cycleCount++;
    const cycleStart = Date.now();
    const cycleStartTime = new Date();
    let newInThisCycle = 0;

    console.log(`\n--------------------------------------------------------------------------------`);
    console.log(`[Cycle #${cycleCount}] Polling NSE & BSE at ${formatIST(cycleStartTime)}`);
    console.log(`--------------------------------------------------------------------------------`);

    // ─── 1. Poll NSE ───────────────────────────────────────────────
    let nseRows = [];
    let nseDuration = 0;
    try {
        const nseStart = Date.now();
        nseRows = await fetchNsePage(1);
        nseDuration = Date.now() - nseStart;
    } catch (err) {
        console.error(`❌ [NSE] Error: ${err.message}`);
    }

    const nseDetectedAt = new Date();
    for (const item of (nseRows || [])) {
        const key = `NSE_${item.attchmntFile || item.symbol + "_" + item.an_dt}`;
        if (!seenKeys.has(key)) {
            seenKeys.add(key);

            // On initial startup, register existing ones so we only alert on newly incoming ones
            if (isFirstRun) {
                continue;
            }

            newInThisCycle++;
            totalDetected++;
            const pubDate = parseNseDate(item.an_dt);
            printAnnouncementBanner("NSE", {
                company: `${item.symbol || "UNKNOWN"} (${item.sm_name || ""})`.trim(),
                headline: (item.desc || "No Description").slice(0, 60),
                publishedTimeStr: formatIST(pubDate),
                detectedTimeStr: formatIST(nseDetectedAt),
                latencyStr: formatLatency(pubDate, nseDetectedAt),
                attachment: item.attchmntFile || null,
            });
        }
    }

    // ─── 2. Poll BSE ───────────────────────────────────────────────
    let bseRows = [];
    let bseTotal = 0;
    let bseDuration = 0;
    const today = istDateStamp();
    try {
        const bseStart = Date.now();
        const res = await fetchBsePage(today, 1);
        bseRows = res.rows || [];
        bseTotal = res.total || 0;
        bseDuration = Date.now() - bseStart;
    } catch (err) {
        console.error(`❌ [BSE] Error: ${err.message}`);
    }

    const bseDetectedAt = new Date();
    for (const item of (bseRows || [])) {
        const key = `BSE_${item.pdfUrl || item.attachment || item.scripCd + "_" + item.announcedAt}`;
        if (!seenKeys.has(key)) {
            seenKeys.add(key);

            // On initial startup, register existing ones
            if (isFirstRun) {
                continue;
            }

            newInThisCycle++;
            totalDetected++;
            const pubDate = parseBseDate(item.announcedAt);
            printAnnouncementBanner("BSE", {
                company: `Scrip: ${item.scripCd || "UNKNOWN"}`,
                headline: (item.headline || "No Headline").slice(0, 60),
                publishedTimeStr: formatIST(pubDate),
                detectedTimeStr: formatIST(bseDetectedAt),
                latencyStr: formatLatency(pubDate, bseDetectedAt),
                attachment: item.attachment || item.pdfUrl || null,
            });
        }
    }

    if (isFirstRun) {
        console.log(`[Snapshot] Initialized tracking cache with ${seenKeys.size} current exchange filings.`);
        console.log(`⚡ Live monitoring active. ANY new filing published from now on will be displayed immediately.\n`);
        isFirstRun = false;
    }

    const totalCycleTime = ((Date.now() - cycleStart) / 1000).toFixed(2);
    console.log(
        `📊 Cycle #${cycleCount} done in ${totalCycleTime}s | ` +
        `NSE: ${nseRows.length} rows (${nseDuration}ms) | ` +
        `BSE: ${bseRows.length} rows (${bseDuration}ms, today total: ${bseTotal}) | ` +
        `New: ${newInThisCycle} | Total Detected: ${totalDetected}`
    );
    console.log(`⏳ Next poll in ${POLL_INTERVAL_MS / 1000}s... (Press Ctrl+C to stop)`);
}

async function loop() {
    console.log("================================================================================");
    console.log("  REAL-TIME CONTINUOUS SCRAPER MONITOR (NSE & BSE)");
    console.log(`  Poll Interval: ${POLL_INTERVAL_MS / 1000}s | Press Ctrl+C to exit`);
    console.log("================================================================================");

    while (!isStopping) {
        await runSingleCycle();
        if (isStopping) break;
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    }
}

// Graceful shutdown
process.on("SIGINT", () => {
    if (isStopping) {
        process.exit(0);
    }
    isStopping = true;
    console.log("\n\n================================================================================");
    console.log("🛑 MONITOR STOPPED BY USER");
    console.log(`   Cycles completed: ${cycleCount}`);
    console.log(`   New announcements detected: ${totalDetected}`);
    console.log("================================================================================\n");
    process.exit(0);
});

loop();
