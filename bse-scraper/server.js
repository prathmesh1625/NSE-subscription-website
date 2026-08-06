const config = require("./services/config");
const ensureSchema = require("./db/ensureSchema");
const metrics = require("./services/metrics");
const symbolProvider = require("./services/symbolProvider");

const { istDateStamp, istHour } = require("./services/istDate");
const { buildScripMap } = require("./services/scripMap");

const checkBseAnnouncements = require("./scheduler/bseWatcher");
const retryFailed = require("./scheduler/recoveryWorker");
const startDownloadWorker = require("./workers/downloadWorker");

let running = false;
let cycles = 0;

async function safeCycle() {

    // A cycle that overruns the interval must not stack another on top of it —
    // two concurrent scans would just race each other into the same ON CONFLICT.
    if (running) {
        console.log("Previous BSE cycle still running — skipping this tick.");
        return;
    }

    running = true;

    const startedAt = Date.now();

    try {
        await checkBseAnnouncements();
        await retryFailed();
    }
    catch (err) {
        metrics.increment("errors");
        console.log("BSE cycle error:", err.message);
    }
    finally {
        running = false;
        cycles++;

        const elapsed = Date.now() - startedAt;

        if (elapsed > config.interval) {
            console.log(`BSE cycle took ${elapsed}ms (longer than the interval)`);
        }

        // Roughly once a minute at the default cadence.
        if (cycles % Math.max(1, Math.round(60000 / config.interval)) === 0) {
            metrics.print();
        }
    }

}

async function start() {

    console.log("==========================================");
    console.log("BSE Announcement Scraper");
    console.log("==========================================");

    await ensureSchema();

    startDownloadWorker();

    const symbols = await symbolProvider.getSymbols();
    const { map, unlisted } = buildScripMap(symbols);

    console.log(`Subscribed companies:  ${symbols.length}`);
    console.log(`With a BSE scrip code: ${map.size}`);

    if (unlisted.length > 0) {
        console.log(
            `Not listed on BSE (NSE-only, skipped here): ${unlisted.join(", ")}`
        );
    }

    console.log(`Poll interval:         ${config.interval / 1000}s`);
    console.log(`Max pages per cycle:   ${config.maxPages}`);
    console.log(`Storage:               ${config.storageDir}`);
    console.log(`IST now:               ${istDateStamp()} (hour ${istHour()})`);
    console.log("==========================================\n");

    await safeCycle();

    setInterval(safeCycle, config.interval);

}

start().catch(err => {
    console.log("BSE scraper startup failed:", err.message);
    process.exit(1);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, () => {
        console.log(`\n${signal} — shutting down BSE scraper.`);
        process.exit(0);
    });
}
