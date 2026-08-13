/**
 * Refresh config/bseCompanies.js — the ticker -> BSE scrip code map.
 *
 *   node scripts/generateBseCompanies.js              # look up unmapped subscribed symbols
 *   node scripts/generateBseCompanies.js NEWCO,OTHER  # look up specific tickers
 *
 * MERGES into the existing map rather than replacing it, so a lookup failure
 * can never silently drop companies that were already being monitored. Nothing
 * is written unless at least one new code was resolved.
 *
 * The startup log names any subscribed symbol with no scrip code — that list is
 * the input this script is meant to fix.
 */

const fs = require("fs");
const path = require("path");

const { client } = require("../services/httpClient");

const OUTPUT_FILE = path.join(__dirname, "..", "config", "bseCompanies.js");

const SEARCH_URL =
    "https://api.bseindia.com/BseIndiaAPI/api/PeerSmartSearchpar/w";

async function fetchScripCode(symbol) {

    try {
        const response = await client.get(SEARCH_URL, {
            params: { searchString: symbol, Type: "SS" },
            timeout: 15000
        });

        const results = response.data;

        if (!Array.isArray(results)) {
            return null;
        }

        // Only an exact ticker match is trustworthy — BSE's search happily
        // returns near-misses, and a wrong scrip code would silently deliver
        // another company's filings.
        const exact = results.find(
            item => item.ID && String(item.ID).toUpperCase() === symbol
        );

        return exact ? String(exact.scripcode).trim() : null;
    }
    catch (err) {
        console.log(`  lookup failed for ${symbol}: ${err.message}`);
        return null;
    }

}

async function resolveTargets() {

    const fromArgs = (process.argv[2] || "")
        .split(",")
        .map(s => s.trim().toUpperCase())
        .filter(Boolean);

    if (fromArgs.length > 0) {
        return fromArgs;
    }

    // No arguments — ask the subscription database which symbols are actually
    // being paid for but have no scrip code yet.
    const existing = require("../config/bseCompanies");
    const symbolProvider = require("../services/symbolProvider");

    const symbols = await symbolProvider.getSymbols();

    return symbols
        .map(s => String(s).toUpperCase().trim())
        .filter(s => s && !existing[s]);

}

async function main() {

    const targets = await resolveTargets();

    if (targets.length === 0) {
        console.log("Nothing to look up — every subscribed symbol is mapped.");
        process.exit(0);
    }

    const mapping = { ...require("../config/bseCompanies") };

    console.log(`Looking up ${targets.length} symbol(s)...\n`);

    const resolved = [];
    const unmatched = [];

    for (const symbol of targets) {
        const code = await fetchScripCode(symbol);

        if (code) {
            mapping[symbol] = code;
            resolved.push(symbol);
            console.log(`  ${symbol} -> ${code}`);
        }
        else {
            unmatched.push(symbol);
            console.log(`  ${symbol} -> no exact match`);
        }

        await new Promise(r => setTimeout(r, 400));
    }

    console.log(`\nResolved ${resolved.length}, unmatched ${unmatched.length}.`);

    if (resolved.length === 0) {
        console.log("No new codes — leaving config/bseCompanies.js untouched.");
        process.exit(0);
    }

    // Sorted so a regeneration produces a reviewable diff instead of a reshuffle.
    const sorted = {};

    for (const key of Object.keys(mapping).sort()) {
        sorted[key] = mapping[key];
    }

    fs.writeFileSync(
        OUTPUT_FILE,
        "// Auto-generated from BSE active-equity scrip master.\n"
        + "// Maps ticker (scrip_id, == NSE symbol for dual-listed) -> BSE scrip code.\n"
        + "// Regenerate with: node scripts/generateBseCompanies.js\n"
        + `module.exports = ${JSON.stringify(sorted, null, 4)};\n`
    );

    console.log(`Wrote ${Object.keys(sorted).length} mappings to config/bseCompanies.js`);

    if (unmatched.length > 0) {
        console.log(`Still unmapped: ${unmatched.join(", ")}`);
    }

    process.exit(0);

}

main().catch(err => {
    console.log("Generation failed:", err.message);
    process.exit(1);
});
