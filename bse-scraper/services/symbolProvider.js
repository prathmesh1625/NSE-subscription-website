const subscribedRepo = require("../repositories/subscribedCompanyRepository");
const config = require("./config");

// Cached so an 8-second poll loop doesn't hammer the portal database, and so a
// transient DB error keeps the last known good list instead of blanking it —
// an empty list would silently stop every alert.
let cached = [];
let lastFetchedAt = 0;
let everFetched = false;

function diff(oldList, newList) {
    const oldSet = new Set(oldList);
    const newSet = new Set(newList);

    return {
        added: newList.filter(s => !oldSet.has(s)),
        removed: oldList.filter(s => !newSet.has(s))
    };
}

async function getSymbols() {

    const now = Date.now();

    if (everFetched && now - lastFetchedAt < config.symbolCacheMs) {
        return cached;
    }

    try {
        const symbols = await subscribedRepo.getSubscribedSymbols();
        const { added, removed } = diff(cached, symbols);

        if (added.length > 0) {
            console.log(`Subscriptions Added: ${added.join(", ")}`);
        }

        if (removed.length > 0) {
            console.log(`Subscriptions Removed: ${removed.join(", ")}`);
        }

        cached = symbols;
        lastFetchedAt = now;
        everFetched = true;
    }
    catch (err) {
        console.log("Subscribed Symbols Fetch Failed:", err.message);
    }

    return cached;

}

module.exports = { getSymbols };
