const fetchNsePage =
    require("../services/fetchNseGlobal");

const config =
    require("../services/config");

const repo =
    require("../repositories/announcementRepository");

const jobRepo =
    require(
        "../repositories/downloadJobRepository"
    );

const symbolProvider =
    require("../services/symbolProvider");

const metrics =
    require("../services/metrics");

const processing =
    new Set();


/**
 * Persist + queue a single announcement (already known to belong to a
 * subscribed symbol). Dedup is handled by the DB: repo.save() ON CONFLICT
 * (pdf_url) DO NOTHING returns false for anything we've already seen, so we
 * only queue a download for genuinely-new filings.
 */
async function saveAnnouncement(
    symbol,
    item
) {

    if (
        !item.attchmntFile
    ) {
        return;
    }

    if (
        processing.has(item.attchmntFile)
    ) {
        return;
    }

    processing.add(item.attchmntFile);

    try {

        const filename =
            `${symbol}_${item.dt}.pdf`;

        const inserted =

            await repo.save({

                company_symbol:
                    symbol,

                title:
                    item.desc,

                pdf_url:
                    item.attchmntFile,

                local_path:
                    `storage/pdf/${filename}`,

                announcement_time:
                    item.sort_date,

                download_status:
                    "PENDING"

            });

        if (
            !inserted
        ) {
            return;
        }

        console.log(
            `\nNSE Queued: ${symbol}\nTitle: ${item.desc}`
        );

        metrics.increment("downloads");

        await jobRepo.add(
            item.attchmntFile,
            filename
        );

    }
    finally {

        processing.delete(item.attchmntFile);

    }

}


async function checkAnnouncements() {

    const cycleStarted = Date.now();
    metrics.increment("cycles");

    console.log(
        "\n=== NSE Cycle ==="
    );

    // Circuit breaker — don't pile on if downloads are badly backed up.
    const pending =
        await jobRepo.pendingCount();

    if (
        pending > config.maxPendingJobs
    ) {

        console.log(
            `\nCircuit Breaker Active — Pending Jobs: ${pending}`
        );

        return;

    }

    const symbols =
        await symbolProvider.getSymbols();

    if (
        symbols.length === 0
    ) {

        console.log(
            "\nNo subscribed companies. Skipping NSE cycle."
        );

        return;

    }

    const subscribedSet =
        new Set(
            symbols.map(s => String(s).toUpperCase().trim())
        );

    console.log(
        `\nNSE monitoring ${subscribedSet.size} subscribed companies via global feed`
    );

    // Pull a few pages of the GLOBAL feed (newest first). A handful of pages
    // covers far more than one poll-interval's worth of new announcements,
    // regardless of how many companies are subscribed.
    const pages =
        Number(config.nseGlobalPages) || 3;

    const seenSymbols =
        new Set();

    const feedStarted = Date.now();
    const pageResults = await Promise.all(
        Array.from({ length: pages }, (_, i) => fetchNsePage(i + 1))
    );
    console.log(`[timing] NSE global pages=${pages} duration=${Date.now() - feedStarted}ms`);

    const saveJobs = [];
    for (const records of pageResults) {
        if (!Array.isArray(records) || records.length === 0) continue;

        for (const item of records) {
            const sym = String(item.symbol || "").toUpperCase().trim();
            if (!subscribedSet.has(sym)) continue;
            seenSymbols.add(sym);
            saveJobs.push(() => saveAnnouncement(sym, item));
        }
    }

    // DB writes are independent. Keep a small pool so a burst of filings does
    // not turn the feed cycle into a long serial chain of INSERT + job INSERT.
    const saveQueue = saveJobs.slice();
    const saveWorkers = [];
    const saveConcurrency = Math.min(8, saveQueue.length);
    for (let i = 0; i < saveConcurrency; i++) {
        saveWorkers.push((async () => {
            while (saveQueue.length) {
                const save = saveQueue.shift();
                await save();
            }
        })());
    }
    await Promise.all(saveWorkers);

    metrics.increment("companies", seenSymbols.size);
    metrics.print();

    console.log(
        `[timing] NSE cycle complete duration=${Date.now() - cycleStarted}ms matched_symbols=${seenSymbols.size}`
    );

}

module.exports =
    checkAnnouncements;
