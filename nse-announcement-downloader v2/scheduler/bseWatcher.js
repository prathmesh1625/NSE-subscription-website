const fetch =
    require("../services/fetchBseAnnouncements");

const repo =
    require("../repositories/announcementRepository");

const jobRepo =
    require("../repositories/downloadJobRepository");

const bseCompanies =
    require("../config/bseCompanies");

const symbolProvider =
    require("../services/symbolProvider");

const metrics =
    require("../services/metrics");

let lastUnmappedKey = "";


const processing =
    new Set();

async function processCompany(
    symbol,
    scripCode
) {

    try {

        console.log(
            `\nChecking BSE ${symbol}`
        );

        const data =
            await fetch(
                scripCode,
                symbol
            );

        for (
            const item
            of data
        ) {

            if (
                !item.attchmntFile
            ) {
                continue;
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
                    `BSE_${symbol}_${item.dt}.pdf`;


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

BSE Queued:

${symbol}

Title:
${item.desc}

`
                );

                await jobRepo.add(

                    item.attchmntFile,

                    filename

                );

                metrics.increment(
                    "downloads"
                );

            }
            finally {

                processing.delete(
                    item.attchmntFile
                );

            }

        }

    }
    catch (err) {

        metrics.increment(
            "errors"
        );

        console.log(
            `BSE Error: ${symbol}`
        );

        console.log(
            err.message
        );

    }

}

async function checkBseAnnouncements() {

    console.log(
        "\n=== BSE Cycle ==="
    );
    metrics.increment(
        "cycles"
    );

    const symbols =
        await symbolProvider.getSymbols();

    if (
        symbols.length === 0
    ) {

        console.log(
            "\nNo subscribed companies. Skipping BSE cycle."
        );

        return;

    }

    const companies =
        [];

    const unmapped =
        [];

    for (
        const symbol
        of symbols
    ) {

        if (
            bseCompanies[symbol]
        ) {

            companies.push([
                symbol,
                bseCompanies[symbol]
            ]);

        }
        else {

            unmapped.push(
                symbol
            );

        }

    }

    console.log(
        `\nBSE Monitoring ${companies.length} subscribed companies`
    );

    // Warn only when the unmapped set changes, not every cycle
    const unmappedKey =
        unmapped.join(",");

    if (
        unmapped.length > 0
        &&
        unmappedKey !== lastUnmappedKey
    ) {

        console.log(
            `\nNo BSE scrip code (NSE only): ${unmapped.join(", ")}`
        );

    }

    lastUnmappedKey =
        unmappedKey;

    for (
        const [symbol, scripCode]
        of companies
    ) {
        metrics.increment(
            "companies"
        );
        await processCompany(
            symbol,
            scripCode
        );

    }
    metrics.print();
}

module.exports =
    checkBseAnnouncements;