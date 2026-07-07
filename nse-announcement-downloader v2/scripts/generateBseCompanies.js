const fs = require("fs");
const path = require("path");
const axios = require("axios");
const config =
    require("../services/config");

console.log(
    "TOTAL SYMBOLS:",
    config.symbols.length
);

console.log(
    config.symbols.slice(0, 20)
);
require("dotenv").config();
console.log(
    Object.keys(process.env)
        .filter(
            k =>
                k.includes("SYMBOL") ||
                k.includes("COMP")
        )
);
const OUTPUT_FILE =
    path.join(
        __dirname,
        "..",
        "config",
        "bseCompanies.js"
    );

const UNMATCHED_FILE =
    path.join(
        __dirname,
        "..",
        "config",
        "bseUnmatched.json"
    );

async function fetchScripCode(symbol) {

    try {

        const response =
            await axios.get(

                "https://api.bseindia.com/BseIndiaAPI/api/PeerSmartSearchpar/w",

                {
                    params: {
                        searchString: symbol,
                        Type: "SS"
                    },

                    headers: {
                        "User-Agent":
                            "Mozilla/5.0",
                        "Referer":
                            "https://www.bseindia.com/"
                    },

                    timeout: 15000
                }

            );

        const results =
            response.data || [];

        if (!Array.isArray(results)) {
            return null;
        }

        const exactMatch =
            results.find(

                item =>

                    item.ID &&
                    item.ID.toUpperCase() === symbol.toUpperCase()

            );

        if (exactMatch) {

            return {
                symbol,
                scripCode:
                    exactMatch.scripcode
            };

        }

        return null;

    }
    catch (err) {

        console.log(
            `Failed: ${symbol}`
        );

        return null;

    }

}

async function main() {

    const config =
        require("../services/config");

    const symbols =
        config.symbols
            .filter(Boolean);

    console.log(
        `Found ${symbols.length} symbols`
    );

    const mapping = {};

    const unmatched = [];

    for (const symbol of symbols) {

        console.log(
            `Searching ${symbol}...`
        );

        const result =
            await fetchScripCode(
                symbol
            );

        if (result) {

            mapping[
                result.symbol
            ] =
                result.scripCode;

            console.log(
                `✓ ${symbol} -> ${result.scripCode}`
            );

        }
        else {

            unmatched.push(
                symbol
            );

            console.log(
                `✗ No Match: ${symbol}`
            );

        }

        await new Promise(

            resolve =>

                setTimeout(
                    resolve,
                    500
                )

        );

    }

    const content =

        `module.exports = ${JSON.stringify(
            mapping,
            null,
            4
        )};`;

    fs.writeFileSync(
        OUTPUT_FILE,
        content
    );

    fs.writeFileSync(
        UNMATCHED_FILE,
        JSON.stringify(
            unmatched,
            null,
            4
        )
    );

    console.log(
        "\nDone."
    );

    console.log(
        `Mappings: ${Object.keys(mapping).length}`
    );

    console.log(
        `Unmatched: ${unmatched.length}`
    );

}

main().catch(
    console.error
);