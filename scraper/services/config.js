require("dotenv").config();

module.exports = {

    symbols:

        (
            process.env.SYMBOLS
            ||
            "SUZLON"
        )

            .split(",")

            .map(
                s => s.trim()
            )
            .filter(Boolean),
    interval:

        Number(
            process.env.NSE_POLL_INTERVAL_MS
            ||
            process.env.INTERVAL
            ||
            20000
        ),

    // How many pages of NSE's GLOBAL announcements feed to pull each cycle.
    // ~50 records/page, newest first. 1 page covers latest announcements.
    nseGlobalPages:

        Number(
            process.env.NSE_PAGES
            ||
            process.env.NSE_GLOBAL_PAGES
            ||
            1
        ),

    maxRecords:

        Number(
            process.env.MAX_RECORDS
            ||
            10
        ),

    workers:

        Number(
            process.env.WORKERS
            ||
            10
        ),

    requestLimit:

        Number(
            process.env.REQUEST_LIMIT
            ||
            5
        ),

    downloadWorkers:

        Number(

            process.env.DOWNLOAD_WORKERS
            ||
            6

        ),
    maxQueueSize:

        Number(

            process.env.MAX_QUEUE_SIZE
            ||
            5000

        ),
    maxPendingJobs:

        Number(

            process.env.MAX_PENDING_JOBS
            ||
            10000

        )
};