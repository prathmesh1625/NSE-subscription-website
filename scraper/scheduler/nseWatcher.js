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
    const discoveryTime = Date.now();

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
        
        const saveTime = ((Date.now() - discoveryTime) / 1000).toFixed(3);

        console.log(
            `\n🆕 NSE NEW ANNOUNCEMENT: ${symbol} (${item.desc}) - Saved to DB in ${saveTime}s`
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

    const cycleStart = Date.now();
    metrics.increment("cycles");

    console.log(
        "\n⏰ === NSE CYCLE START ==="
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

    for (
        let p = 1;
        p <= pages;
        p++
    ) {

        const records =
            await fetchNsePage(p);

        if (
            !Array.isArray(records) ||
            records.length === 0
        ) {
            break;
        }

        for (
            const item
            of records
        ) {

            const sym =
                String(item.symbol || "")
                    .toUpperCase()
                    .trim();

            if (
                !subscribedSet.has(sym)
            ) {
                continue;
            }

            seenSymbols.add(sym);

            await saveAnnouncement(sym, item);

        }

    }

    const cycleTime = ((Date.now() - cycleStart) / 1000).toFixed(2);
    metrics.increment("companies", seenSymbols.size);
    metrics.print();

    console.log(
        `\n✅ NSE Cycle Complete in ${cycleTime}s (found ${seenSymbols.size} new announcements)`
    );

}

module.exports =
    checkAnnouncements;
