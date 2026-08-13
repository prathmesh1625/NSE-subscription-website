const queueRepo = require("../repositories/downloadJobRepository");
const failedRepo = require("../repositories/failedJobRepository");
const announcementRepo = require("../repositories/announcementRepository");
const heartbeat = require("../repositories/workerHeartbeatRepository");

const download = require("../services/downloadPdf");
const config = require("../services/config");
const metrics = require("../services/metrics");

const WORKER_NAME = "bse-download-worker-1";

const IDLE_MIN_MS = 500;
const IDLE_MAX_MS = 3000;

let delay = IDLE_MIN_MS;
let ticks = 0;

/** Run `task` over `items` with at most `limit` in flight. */
async function pooled(items, limit, task) {

    const queue = items.slice();
    const runners = [];

    for (let i = 0; i < Math.min(limit, queue.length); i++) {
        runners.push((async () => {
            while (queue.length > 0) {
                await task(queue.shift());
            }
        })());
    }

    await Promise.all(runners);

}

async function runJob(job) {

    try {
        await announcementRepo.updateStatus(job.url, "DOWNLOADING");

        const startedAt = Date.now();
        const { bytes } = await download(job.url, job.filename);

        // Only now is the file readable by the bot, so this is the last step.
        await announcementRepo.updateStatus(job.url, "DOWNLOADED");
        await queueRepo.markDone(job.id);
        await failedRepo.removeByUrl(job.url);

        metrics.increment("downloaded");

        console.log(
            `Downloaded: ${job.filename} (${bytes} bytes, ${Date.now() - startedAt}ms)`
        );
    }
    catch (err) {
        await announcementRepo.updateStatus(job.url, "FAILED");
        await queueRepo.markFailed(job.id);
        await failedRepo.add(job.url, job.filename, err.message);

        metrics.increment("errors");

        console.log(`Download failed: ${job.filename} — ${err.message}`);
    }

}

async function processJobs() {

    try {
        await heartbeat.beat(WORKER_NAME);
        await queueRepo.resetStuckJobs();

        const jobs = await queueRepo.claimJobs(config.downloadBatch);

        if (jobs.length === 0) {
            delay = Math.min(delay + 500, IDLE_MAX_MS);
        }
        else {
            delay = IDLE_MIN_MS;

            // BSE filings arrive in bursts (a whole results day lands at once);
            // downloading them one at a time would hand back the head start
            // this service exists to win.
            await pooled(jobs, config.downloadConcurrency, runJob);
        }

        ticks++;

        if (ticks % 30 === 0) {
            console.table(await queueRepo.stats());

            const dead = await failedRepo.deadCount(config.maxDownloadRetries);

            if (dead > 0) {
                console.log(`${dead} BSE download(s) gave up after every retry`);
            }
        }

        if (ticks % 200 === 0) {
            await queueRepo.cleanupDoneJobs();
        }
    }
    catch (err) {
        metrics.increment("errors");
        console.log("BSE download worker error:", err.message);
        delay = IDLE_MAX_MS;
    }

    setTimeout(processJobs, delay);

}

function start() {
    console.log("BSE Download Worker Started");
    processJobs();
}

module.exports = start;
