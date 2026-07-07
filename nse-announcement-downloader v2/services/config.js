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
            process.env.INTERVAL
            ||
            30000
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
            10

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