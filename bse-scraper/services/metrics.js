const stats = {
    cycles: 0,
    matched: 0,
    queued: 0,
    downloaded: 0,
    errors: 0,
    started: Date.now()
};

function increment(key, by = 1) {
    if (typeof stats[key] === "number") {
        stats[key] += by;
    }
}

function print() {
    const uptime = Math.floor((Date.now() - stats.started) / 1000);

    console.log("\n====== BSE HEALTH ======");
    console.log("Cycles:     ", stats.cycles);
    console.log("Matched:    ", stats.matched);
    console.log("Queued:     ", stats.queued);
    console.log("Downloaded: ", stats.downloaded);
    console.log("Errors:     ", stats.errors);
    console.log("Uptime:     ", uptime, "sec");
    console.log("========================");
}

module.exports = { stats, increment, print };
