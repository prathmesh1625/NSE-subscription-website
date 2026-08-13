// BSE's announcement feed is keyed on IST calendar days, and the container
// clock is UTC — between 18:30 and 24:00 UTC it is already "tomorrow" in
// India. Deriving the date from the raw UTC clock would query the wrong day
// every evening and silently return nothing, so every date the feed sees is
// computed in Asia/Kolkata explicitly.

const IST_PARTS = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hour12: false
});

function parts(date = new Date()) {
    const out = {};
    for (const p of IST_PARTS.formatToParts(date)) {
        out[p.type] = p.value;
    }
    return out;
}

/** Calendar date in IST as BSE wants it: YYYYMMDD. */
function istDateStamp(date = new Date()) {
    const p = parts(date);
    return `${p.year}${p.month}${p.day}`;
}

/** Hour of day (0-23) in IST. */
function istHour(date = new Date()) {
    // Intl renders midnight as "24" in some ICU versions.
    return Number(parts(date).hour) % 24;
}

/**
 * Which BSE calendar days this cycle should query.
 *
 * Normally just today. Shortly after IST midnight the previous day's late
 * filings (BSE accepts submissions past 23:00) are still fresh and undelivered,
 * so yesterday is polled alongside today until the new day has some history.
 */
function daysToPoll(date = new Date()) {
    const today = istDateStamp(date);

    if (istHour(date) >= 3) {
        return [today];
    }

    return [
        today,
        istDateStamp(new Date(date.getTime() - 24 * 60 * 60 * 1000))
    ];
}

module.exports = {
    istDateStamp,
    istHour,
    daysToPoll
};
