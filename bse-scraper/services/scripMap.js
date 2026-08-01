const bseCompanies = require("../config/bseCompanies");

/**
 * Build the reverse map BSE's feed needs: scrip code -> subscribed symbol.
 *
 * The feed identifies companies by numeric scrip code only, while everything
 * downstream (subscriptions, the bot, the NSE rows in the same table) is keyed
 * on the NSE ticker. Companies with no BSE listing simply drop out here.
 *
 * Rebuilt each cycle from the live subscription list, which costs nothing at
 * these sizes and means a new subscriber is covered on the very next poll.
 */
function buildScripMap(symbols) {

    const map = new Map();
    const unlisted = [];

    for (const raw of symbols) {

        const symbol = String(raw || "").toUpperCase().trim();

        if (!symbol) {
            continue;
        }

        const code = bseCompanies[symbol];

        if (code) {
            map.set(String(code).trim(), symbol);
        }
        else {
            unlisted.push(symbol);
        }

    }

    return { map, unlisted };

}

module.exports = { buildScripMap, bseCompanies };
