const fs = require("fs");

const axios = require("axios");

async function downloadPdf(
    url,
    filename
) {
    console.log(
        `Downloading: ${filename}`
    );
    const referer =

        url.includes("bseindia.com")

            ? "https://www.bseindia.com/"

            : "https://www.nseindia.com/";


    const response =
        await axios({

            url,

            method: "GET",

            responseType: "arraybuffer",

            timeout: 60000,

            headers: {

                "User-Agent":
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",

                "Referer":
                    referer,

                "Accept":
                    "application/pdf,*/*",

                "Connection":
                    "keep-alive"

            }

        });

    const path =
        `storage/pdf/${filename}`;
    if (
        response.status !== 200
    ) {

        throw new Error(
            `HTTP ${response.status}`
        );

    }
    fs.writeFileSync(
        path,
        response.data
    );
    console.log(
        `Saved: ${filename}`
    );
    console.log(
        "Saved locally"
    );

}

module.exports =
    downloadPdf;