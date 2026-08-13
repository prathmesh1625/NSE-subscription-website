/**
 * Smoke-test the BSE feed without touching the database.
 *
 *   node scripts/probeFeed.js                 # today, feed shape only
 *   node scripts/probeFeed.js RELIANCE,TCS    # show what those symbols would queue
 *   node scripts/probeFeed.js RELIANCE 20260731
 *
 * Prints exactly what the watcher would have persisted, so a feed change can be
 * diagnosed without running the service or reading the database.
 */

const { fetchBsePage, PAGE_SIZE } = require("../services/fetchBseFeed");
const { istDateStamp, istHour, daysToPoll } = require("../services/istDate");
const { buildScripMap } = require("../services/scripMap");
const { buildFilename } = require("../scheduler/bseWatcher");

const config = require("../services/config");

async function main() {

    const symbols = (process.argv[2] || "")
        .split(",")
        .map(s => s.trim().toUpperCase())
        .filter(Boolean);

    const day = process.argv[3] || istDateStamp();

    console.log(`IST now:   ${istDateStamp()} hour ${istHour()}`);
    console.log(`Would poll: ${daysToPoll().join(", ")}`);
    console.log(`Probing:   ${day}\n`);

    const { map, unlisted } = buildScripMap(symbols);

    if (symbols.length > 0) {
        console.log(`Mapped ${map.size}/${symbols.length} symbol(s) to scrip codes`);

        for (const [code, symbol] of map) {
            console.log(`  ${symbol} -> ${code}`);
        }

        if (unlisted.length > 0) {
            console.log(`  no BSE scrip code: ${unlisted.join(", ")}`);
        }

        console.log("");
    }

    let scanned = 0;
    let matches = 0;

    for (let page = 1; page <= config.maxPages; page++) {

        const startedAt = Date.now();
        const { rows, total } = await fetchBsePage(day, page);

        console.log(
            `page ${page}: ${rows.length} rows of ${total} (${Date.now() - startedAt}ms)`
        );

        if (rows.length === 0) {
            break;
        }

        scanned += rows.length;

        if (page === 1) {
            console.log("\n  newest 3 rows on the feed:");

            for (const row of rows.slice(0, 3)) {
                console.log(
                    `    ${row.announcedAt}  ${row.scripCd.padEnd(7)} `
                    + `${(row.category || "-").padEnd(18)} ${row.title.slice(0, 60)}`
                );
            }

            console.log("");
        }

        for (const row of rows) {
            const symbol = map.get(row.scripCd);

            if (!symbol || !row.pdfUrl) {
                continue;
            }

            matches++;

            console.log(`  MATCH ${symbol}  ${row.announcedAt}  [${row.category}]`);
            console.log(`     title: ${row.title}`);
            console.log(`     file:  ${buildFilename(symbol, row)}`);
            console.log(`     pdf:   ${row.pdfUrl}`);
        }

        if (rows.length < PAGE_SIZE || page * PAGE_SIZE >= total) {
            break;
        }

    }

    console.log(`\nScanned ${scanned} rows, ${matches} match the given symbols.`);

}

main().catch(err => {
    console.log("Probe failed:", err.message);
    process.exit(1);
});
