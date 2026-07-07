const axios =
    require(
        "axios"
    );

const limiter =
    require(
        "./requestLimiter"
    );

const retry =
    require(
        "./retry"
    );

async function fetchAnnouncements(
    symbol
) {

    return limiter.execute(

        () => retry(

            async () => {

                const response =

                    await axios.get(

                        "https://www.nseindia.com/api/corporate-announcements",

                        {

                            params: {

                                index:
                                    "equities",

                                symbol

                            },

                            headers: {

                                "User-Agent":
                                    "Mozilla/5.0"

                            },

                            timeout:
                                15000

                        }

                    );

                return (

                    response.data
                    ||
                    []

                );

            },

            3,

            2000

        )

    )

        .catch(

            err => {

                console.log(

                    `Failed:
${symbol}`

                );

                return [];

            }

        );

}

module.exports =
    fetchAnnouncements;