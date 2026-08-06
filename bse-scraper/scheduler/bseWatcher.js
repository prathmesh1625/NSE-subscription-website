const { fetchBsePage, PAGE_SIZE } = require("../services/fetchBseFeed");
const { daysToPoll } = require("../services/istDate");
const { buildScripMap } = require("../services/scripMap");

const symbolProvider = require("../services/symbolProvider");
const config = require("../services/config");
const metrics = require("../services/metrics");

const repo = require("../repositories/announcementRepository");
const jobRepo = require("../repositories/downloadJobRepository");

// Newest filing timestamp already scanned, per BSE calendar day. The feed is
// ordered newest-first, so once a page holds nothing past this mark every
// remaining page is old news and the cycle can stop paging. In the steady
// state that means exactly ONE request per poll.
const highWater = new Map();

function timeValue(raw) {
    const ms = Date.parse(raw);
    return Number.isNaN(ms) ? 0 : ms;
}

function pruneHighWater(activeDays) {
    for (const day of highWater.keys()) {
        if (!activeDays.includes(day)) {
            highWater.delete(day);
        }
    }
}

/**
 * Deterministic, filesystem-safe name for a filing's PDF.
 *
 * The bot keys "already sent to this subscriber" off this basename, so it has
 * to be unique per filing AND stable across restarts — a re-derived name that
 * drifted would re-deliver a filing someone already received. The attachment
 * GUID prefix guarantees uniqueness when one company files twice in the same
 * second; the `BSE_` prefix keeps the two feeds distinguishable on disk.
 */
function buildFilename(symbol, item) {

    const stamp = String(item.announcedAt || "")
        .replace(/[:.]/g, "-")
        .replace(/[T ]/g, "_")
        .slice(0, 19);

    const guid = String(item.attachment || "")
        .replace(/\.pdf$/i, "")
        .replace(/[^A-Za-z0-9]/g, "")
        .slice(0, 8);

    return `BSE_${symbol}_${stamp}_${guid}.pdf`;

}

/**
 * Persist a filing and queue its PDF. The insert's ON CONFLICT (pdf_url) is
 * what makes a re-scan free: it returns null for anything already stored, so a
 * download is queued only for genuinely new filings and no subscriber is
 * notified twice.
 */
async function saveAnnouncement(symbol, item) {

    if (!item.pdfUrl) {
        return false;
    }

    const filename = buildFilename(symbol, item);

    const insertedId = await repo.save({
        company_symbol: symbol,
        title: item.title,
        pdf_url: item.pdfUrl,
        local_path: `storage/pdf/${filename}`,
        announcement_time: item.announcedAt,
        download_status: "PENDING"
    });

    if (!insertedId) {
        return false;
    }

    // Queue AFTER the row exists, so the download worker can never mark the
    // status of a row that isn't there yet.
    await jobRepo.add(item.pdfUrl, filename);

    metrics.increment("queued");

    console.log(
        `BSE Queued: ${symbol} | ${item.announcedAt} | ${item.category || "-"}\n`
        + `  ${item.title}`
    );

    return true;

}

/** Scan one BSE calendar day, newest page first, stopping at the high-water mark. */
async function scanDay(day, scripMap, seenUrls) {

    const previousMark = highWater.get(day) || 0;
    let newestSeen = previousMark;
    let matched = 0;

    for (let page = 1; page <= config.maxPages; page++) {

        const { rows, total } = await fetchBsePage(day, page);

        if (rows.length === 0) {
            break;
        }

        let oldestOnPage = Infinity;

        for (const item of rows) {

            const stamp = timeValue(item.announcedAt);
            oldestOnPage = Math.min(oldestOnPage, stamp);
            newestSeen = Math.max(newestSeen, stamp);

            const symbol = scripMap.get(item.scripCd);

            if (!symbol || !item.pdfUrl) {
                continue;
            }

            // BSE paginates over a table that is still being written to, so a
            // filing arriving mid-scan can push a row onto two consecutive
            // pages. Skip the repeat rather than round-trip to the database.
            if (seenUrls.has(item.pdfUrl)) {
                continue;
            }

            seenUrls.add(item.pdfUrl);
            matched++;

            await saveAnnouncement(symbol, item);

        }

        // Everything on this page is at or behind what a previous cycle already
        // scanned — no page after it can hold anything new.
        if (previousMark > 0 && oldestOnPage <= previousMark) {
            break;
        }

        // Reached the end of the day's rows.
        if (rows.length < PAGE_SIZE || page * PAGE_SIZE >= total) {
            break;
        }

    }

    if (newestSeen > previousMark) {
        highWater.set(day, newestSeen);
    }

    return matched;

}

async function checkBseAnnouncements() {

    metrics.increment("cycles");

    // Don't pile more work on a download queue that is already drowning.
    const pending = await jobRepo.pendingCount();

    if (pending > config.maxPendingJobs) {
        console.log(`BSE circuit breaker active — ${pending} pending downloads`);
        return;
    }

    const symbols = await symbolProvider.getSymbols();

    if (symbols.length === 0) {
        console.log("No subscribed companies — skipping BSE cycle.");
        return;
    }

    const { map: scripMap } = buildScripMap(symbols);

    if (scripMap.size === 0) {
        console.log("No subscribed company has a BSE scrip code — skipping cycle.");
        return;
    }

    const days = daysToPoll();
    pruneHighWater(days);

    const seenUrls = new Set();
    let matched = 0;

    for (const day of days) {
        matched += await scanDay(day, scripMap, seenUrls);
    }

    metrics.increment("matched", matched);

}

module.exports = checkBseAnnouncements;
module.exports.buildFilename = buildFilename;
