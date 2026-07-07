const axios = require("axios");

async function test(pageNo) {

    try {

        const response = await axios.get(
            "https://www.nseindia.com/api/corporate-announcements",
            {
                params: {
                    index: "equities",
                    pageNo
                },
                headers: {
                    "User-Agent": "Mozilla/5.0"
                }
            }
        );

        console.log(
            `\n===== PAGE ${pageNo} =====`
        );

        console.log(
            "Records:",
            response.data.length
        );

        if (
            response.data.length > 0
        ) {

            console.log(
                "First Symbol:",
                response.data[0].symbol
            );

            console.log(
                "First Seq ID:",
                response.data[0].seq_id
            );

            console.log(
                "First Date:",
                response.data[0].dt
            );

        }

    }
    catch (err) {

        console.log(
            `Page ${pageNo} Failed`
        );

        console.log(
            err.message
        );

    }

}

async function main() {

    await test(1);

    await test(2);

    await test(3);

}

main();