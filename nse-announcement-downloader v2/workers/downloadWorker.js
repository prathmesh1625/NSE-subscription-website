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

                    10000

                );

            console.log(
                `Idle:
${delay}ms`
            );

        }
        else {

            delay = 1000;

            for (
                const job
                of jobs
            ) {

                try {

                    await repo.updateStatus(

                        job.url,

                        "DOWNLOADING"

                    );

                    await download(

                        job.url,

                        job.filename

                    );

                    await repo.updateStatus(

                        job.url,

                        "DOWNLOADED"

                    );

                    await queueRepo.markDone(
                        job.id
                    );

                    await failedRepo.removeByUrl(
                        job.url
                    );

                    console.log(

                        `Downloaded:
${job.filename}`

                    );

                }
                catch (err) {

                    await repo.updateStatus(

                        job.url,

                        "FAILED"

                    );

                    await queueRepo.markFailed(
                        job.id
                    );

                    await failedRepo.add(

                        job.url,

                        job.filename

                    );

                    console.log(

                        `Failed:
${job.filename}
${err.message}`

                    );

                }

            }

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