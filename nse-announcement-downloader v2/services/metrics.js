const stats = {

    cycles: 0,

    companies: 0,

    downloads: 0,

    errors: 0,

    started:
        Date.now()

};

function increment(
    key
) {

    stats[key]++;

}

function print() {

    console.log(

        "\n====== HEALTH ======"

    );

    console.log(

        "Cycles:",

        stats.cycles

    );

    console.log(

        "Companies:",

        stats.companies

    );

    console.log(

        "Queued Jobs:",

        stats.downloads

    );

    console.log(

        "Errors:",

        stats.errors

    );

    console.log(

        "Uptime:",

        Math.floor(

            (
                Date.now()

                -

                stats.started

            )

            / 1000

        ),

        "sec"

    );

    console.log(

        "===================="

    );

}

module.exports = {

    stats,

    increment,

    print

};