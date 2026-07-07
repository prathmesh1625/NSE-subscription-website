const subscribedRepo =
    require("../repositories/subscribedCompanyRepository");

// Cache so NSE + BSE watchers in the same cycle share
// one DB query, and so a transient DB error does not
// blank out the list mid-flight.
const CACHE_TTL_MS = 20000;

let cachedSymbols = [];

let lastFetchedAt = 0;

let everFetched = false;

function diff(
    oldList,
    newList
) {

    const oldSet =
        new Set(oldList);

    const newSet =
        new Set(newList);

    const added =
        newList.filter(
            s => !oldSet.has(s)
        );

    const removed =
        oldList.filter(
            s => !newSet.has(s)
        );

    return {
        added,
        removed
    };

}

async function getSymbols() {

    const now =
        Date.now();

    if (
        everFetched
        &&
        now - lastFetchedAt
        <
        CACHE_TTL_MS
    ) {

        return cachedSymbols;

    }

    try {

        const symbols =
            await subscribedRepo
                .getSubscribedSymbols();

        const {
            added,
            removed
        } =
            diff(
                cachedSymbols,
                symbols
            );

        if (
            added.length > 0
        ) {

            console.log(
                `\nSubscriptions Added: ${added.join(", ")}`
            );

        }

        if (
            removed.length > 0
        ) {

            console.log(
                `\nSubscriptions Removed: ${removed.join(", ")}`
            );

        }

        cachedSymbols =
            symbols;

        lastFetchedAt =
            now;

        everFetched =
            true;

    }
    catch (err) {

        // Keep the last known good list on failure
        console.log(
            "\nSubscribed Symbols Fetch Failed:"
        );

        console.log(
            err.message
        );

    }

    return cachedSymbols;

}

module.exports = {

    getSymbols

};
