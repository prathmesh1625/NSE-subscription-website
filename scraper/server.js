const config =
    require(
        "./services/config"
    );

const ensureSchema =
    require(
        "./db/ensureSchema"
    );

const symbolProvider =
    require(
        "./services/symbolProvider"
    );

let running =
    false;

async function safeWatch() {

    if (running) {

        console.log(
            "\nPrevious cycle still running"
        );

        return;

    }

    running =
        true;

    console.log(
        "\nCycle Started"
    );

    try {

        const nseWatch =
            require(
                "./scheduler/nseWatcher"
            );

        const bseWatch =
            require(
                "./scheduler/bseWatcher"
            );

        const retryFailed =
            require(
                "./scheduler/recoveryWorker"
            );

        console.log(
            "\n=== NSE + BSE Parallel Cycle ==="
        );

        const startedAt =
            Date.now();

        await Promise.all([

            nseWatch(),

            bseWatch()

        ]);

        console.log(

            `\nNSE + BSE completed in ${Date.now() - startedAt
            } ms`

        );

        console.log(
            "\n=== Recovery Cycle ==="
        );

        await retryFailed();

    }
    catch (err) {

        console.log(
            "\nServer Error:"
        );

        console.log(
            err.message
        );

    }
    finally {

        running =
            false;

        console.log(
            "\nCycle Finished"
        );

    }

}

async function start() {

    console.log(
        "\n=================================="
    );

    console.log(
        "NSE + BSE Watcher Started"
    );

    // Make sure retry-pipeline columns exist before
    // the download worker starts touching failed_jobs
    await ensureSchema();

    // Prime NSE session cookies up front so the very first cycle's API calls
    // succeed (200) instead of 401/timeout.
    try {
        await require("./services/nseSession").refresh();
    } catch (e) {
        console.log("NSE cookie prime skipped:", e.message);
    }

    // Start the download worker only after the schema check
    require(
        "./workers/downloadWorker"
    );

    const symbols =
        await symbolProvider.getSymbols();

    console.log(
        `\nMonitoring ${symbols.length} subscribed companies (refreshed every cycle):`
    );

    console.log(
        symbols
    );

    console.log(
        `\nInterval:
${config.interval / 1000}
seconds`
    );

    console.log(
        "\nExchanges:"
    );

    console.log(
        [
            "NSE",
            "BSE"
        ]
    );

    console.log(
        "==================================\n"
    );

    safeWatch();

    setInterval(

        safeWatch,

        config.interval

    );

}

start()
    .catch(err => {

        console.log(
            "\nStartup Failed:"
        );

        console.log(
            err.message
        );

        process.exit(1);

    });

process.on(

    "SIGINT",

    () => {

        console.log(
            "\nGraceful Shutdown..."
        );

        process.exit(0);

    }

);

process.on(

    "SIGTERM",

    () => {

        console.log(
            "\nServer Terminated"
        );

        process.exit(0);

    }

);
