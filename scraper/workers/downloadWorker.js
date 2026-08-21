const queueRepo =
    require(
        "../repositories/downloadJobRepository"
    );

const download =
    require(
        "../services/downloadPdf"
    );
const heartbeat =
    require(
        "../repositories/workerHeartbeatRepository"
    );
const failedRepo =
    require(
        "../repositories/failedJobRepository"
    );

const config = require("../services/config");

const repo =
    require(
        "../repositories/announcementRepository"
    );

console.log(
    "Download Worker Started"
);

let delay = 1000;
let cleanupCounter = 0;

let cycles = 0;

async function pooled(items, limit, task) {
    const queue = items.slice();
    const runners = [];
    const workerCount = Math.min(Math.max(1, limit), queue.length);
    for (let i = 0; i < workerCount; i++) {
        runners.push((async () => {
            while (queue.length) {
                const job = queue.shift();
                await task(job);
            }
        })());
    }
    await Promise.all(runners);
}

async function processJobs() {
    await heartbeat.beat(
        "download-worker-1"
    );

    try {

        await queueRepo.resetStuckJobs();

        const jobs =

            await queueRepo.claimJobs(
                20
            );
        console.log(
            `Claimed ${jobs.length} jobs`
        );

        if (
            jobs.length === 0
        ) {

            delay =
                Math.min(

                    delay + 1000,

                    4000

                );

            console.log(
                `Idle:
${delay}ms`
            );

        }
        else {

            delay = 1000;

            const batchStarted = Date.now();
            await pooled(jobs, Number(config.downloadWorkers) || 6, async (job) => {
                try {
                    const t0 = Date.now();
                    await repo.updateStatus(job.url, "DOWNLOADING");
                    await download(job.url, job.filename);
                    await repo.updateStatus(job.url, "DOWNLOADED");
                    await queueRepo.markDone(job.id);
                    await failedRepo.removeByUrl(job.url);
                    console.log(`Downloaded: ${job.filename} (${Date.now() - t0}ms)`);
                }
                catch (err) {
                    await repo.updateStatus(job.url, "FAILED");
                    await queueRepo.markFailed(job.id);
                    await failedRepo.add(job.url, job.filename);
                    console.log(`Failed: ${job.filename}\n${err.message}`);
                }
            });
            console.log(`[timing] download batch jobs=${jobs.length} workers=${Number(config.downloadWorkers) || 6} duration=${Date.now() - batchStarted}ms`);

        }

    }
    catch (err) {

        console.log(
            "Worker Error:"
        );

        console.log(
            err.message
        );

    }
    cycles++;

    if (
        cycles % 10 === 0
    ) {

        const stats =

            await queueRepo.stats();

        console.log(
            "\n=== Queue Stats ==="
        );

        console.table(
            stats
        );

    }
    cleanupCounter++;

    if (
        cleanupCounter % 50 === 0
    ) {

        await queueRepo.cleanupDoneJobs();

        console.log(
            "Cleaned old DONE jobs"
        );

    }

    setTimeout(

        processJobs,

        delay

    );

}

processJobs();