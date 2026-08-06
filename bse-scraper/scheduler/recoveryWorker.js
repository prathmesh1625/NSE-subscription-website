const failedRepo = require("../repositories/failedJobRepository");
const jobRepo = require("../repositories/downloadJobRepository");
const announcementRepo = require("../repositories/announcementRepository");

const config = require("../services/config");

// BSE routinely lists a filing in the feed a few seconds before its PDF is
// readable on the attachment CDN — the first download attempt 404s or gets an
// HTML placeholder. With a 15s backoff, the default 8 attempts cover about two
// minutes of propagation, which is the whole point of polling this fast.
const BACKOFF_SECONDS = 15;

async function retryFailed() {

    let jobs;

    try {
        jobs = await failedRepo.claimRetryable(
            config.maxDownloadRetries,
            BACKOFF_SECONDS
        );
    }
    catch (err) {
        console.log("BSE recovery error:", err.message);
        return;
    }

    if (jobs.length === 0) {
        return;
    }

    console.log(`Retrying ${jobs.length} failed BSE download(s)`);

    for (const task of jobs) {
        try {
            await announcementRepo.updateStatus(task.url, "PENDING");
            await jobRepo.add(task.url, task.filename);

            console.log(
                `Requeued (attempt ${task.retries}/${config.maxDownloadRetries}): `
                + task.filename
            );
        }
        catch (err) {
            console.log(`Requeue failed: ${task.filename} — ${err.message}`);
        }
    }

}

module.exports = retryFailed;
