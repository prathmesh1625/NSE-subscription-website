const fetch =
    require("../services/fetchNseAnnouncements");

const config =
    require("../services/config");

const repo =
    require("../repositories/announcementRepository");

const stateRepo =
    require(
        "../repositories/companyStateRepository"
    );

const jobRepo =
    require(
        "../repositories/downloadJobRepository"
    );

const chunk =
    require("../services/chunkArray");

const symbolProvider =
    require("../services/symbolProvider");

const metrics =
    require("../services/metrics");

const processing =
    new Set();


async function processCompany(
    symbol
) {

    metrics.increment(
        "companies"
    );

    try {

        console.log(
            `\nChecking ${symbol}`
        );

        const state =

            await stateRepo.get(
                symbol
            );

        const lastSeen =

            state
                ?
                new Date(
                    state.last_announcement_time
                )
                :
                null;

        const data =
            await fetch(symbol);

        const recent =

            data.slice(
                0,
                config.maxRecords
            );

        let newestTime =
            lastSeen;

        for (
            const item
            of recent
        ) {

            if (
                !item.attchmntFile
            )
                continue;

            const itemTime =

                new Date(
                    item.sort_date
                );

            if (

                lastSeen
                &&
                itemTime
                <=
                lastSeen

            ) {

                console.log(
                    `No new announcements:
${symbol}`
                );

                break;

            }

            if (
                processing.has(
                    item.attchmntFile
                )
            ) {

                continue;

            }

            processing.add(
                item.attchmntFile
            );

            try {

                const filename =
                    `${symbol}_${item.dt}.pdf`;

                const inserted =

                    await repo.save({

                        company_symbol:
                            symbol,

                        title:
                            item.desc,

                        pdf_url:
                            item.attchmntFile,

                        local_path:
                            `storage/pdf/${filename}`,

                        announcement_time:
                            item.sort_date,

                        download_status:
                            "PENDING"

                    });

                if (
                    !inserted
                ) {

                    continue;

                }

                console.log(
                    `
Queued:
${symbol}

Title:
${item.desc}
`
                );

                metrics.increment(
                    "downloads"
                );

                await jobRepo.add(

                    item.attchmntFile,

                    filename

                );

                if (

                    !newestTime
                    ||
                    itemTime
                    >
                    newestTime

                ) {

                    newestTime =
                        itemTime;

                }

            }
            finally {

                processing.delete(
                    item.attchmntFile
                );

            }

        }

        if (
            newestTime
        ) {

            await stateRepo.update(

                symbol,

                newestTime

            );

        }

    }
    catch (err) {

        metrics.increment(
            "errors"
        );

        console.log(
            `\nWorker Error:
${symbol}`
        );

        console.log(
            err.message
        );

    }

}

async function checkAnnouncements() {

    metrics.increment(
        "cycles"
    );

    console.log(
        "\n=== New Cycle ==="
    );

    const pending =

        await jobRepo.pendingCount();

    if (

        pending
        >
        config.maxPendingJobs

    ) {

        console.log(
            `
Circuit Breaker Active

Pending Jobs:
${pending}
`
        );

        return;

    }

    const symbols =

        await symbolProvider.getSymbols();

    if (
        symbols.length === 0
    ) {

        console.log(
            "\nNo subscribed companies. Skipping NSE cycle."
        );

        return;

    }

    console.log(
        `\nNSE Monitoring ${symbols.length} subscribed companies`
    );

    const size =

        Math.ceil(

            symbols.length
            /
            config.workers

        );

    const groups =

        chunk(

            symbols,

            size

        );

    for (
        const group
        of groups
    ) {

        await Promise.all(

            group.map(
                processCompany
            )

        );

    }

    metrics.print();

    console.log(
        "\nCycle Complete"
    );

}

module.exports =
    checkAnnouncements;