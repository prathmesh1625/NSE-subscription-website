const fs = require("fs");
const nodePath = require("path");

const axios = require("axios");

const STORAGE_DIR = process.env.PDF_STORAGE_PATH || nodePath.join(__dirname, "../../storage/pdf");

async function downloadPdf(
    url,
    filename
) {
    const downloadStart = Date.now();
    console.log(
        `⬇️  Downloading: ${filename}`
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

    if (
        response.status !== 200
    ) {

        throw new Error(
            `HTTP ${response.status}`
        );

    }

    fs.mkdirSync(STORAGE_DIR, { recursive: true });
    const filePath = nodePath.join(STORAGE_DIR, filename);
    fs.writeFileSync(
        filePath,
        response.data
    );
    const downloadTime = ((Date.now() - downloadStart) / 1000).toFixed(2);
    console.log(
        `✅ Saved: ${filename} in ${downloadTime}s`
    );

}

module.exports =
    downloadPdf;