const fs = require("fs");
const nodePath = require("path");

const { client } = require("./httpClient");
const config = require("./config");

/**
 * Fetch a BSE attachment and write it to the shared storage volume.
 *
 * Writes to a temp file and renames, because the bot polls the same directory
 * and must never pick up a half-written PDF. BSE also answers a not-yet-
 * propagated attachment with an HTML error page at HTTP 200, so the content
 * type is checked rather than trusted — that turns into a retryable failure
 * instead of a 0-page "PDF" going out to subscribers.
 */
async function downloadPdf(url, filename) {

    const downloadStart = Date.now();
    const response = await client.get(url, {
        responseType: "arraybuffer",
        timeout: 60000,
        headers: {
            "Accept": "application/pdf,*/*",
            "Referer": "https://www.bseindia.com/"
        }
    });

    if (response.status !== 200) {
        throw new Error(`HTTP ${response.status}`);
    }

    const body = Buffer.from(response.data);

    if (body.length === 0) {
        throw new Error("empty body");
    }

    // %PDF- magic. BSE serves an HTML "file not found" page at 200 while an
    // attachment is still propagating to the CDN.
    if (body.subarray(0, 5).toString("latin1") !== "%PDF-") {
        throw new Error("not a PDF yet (attachment still propagating)");
    }

    fs.mkdirSync(config.storageDir, { recursive: true });

    const finalPath = nodePath.join(config.storageDir, filename);
    const tempPath = `${finalPath}.part`;

    fs.writeFileSync(tempPath, body);
    fs.renameSync(tempPath, finalPath);
    
    const downloadTime = ((Date.now() - downloadStart) / 1000).toFixed(2);
    console.log(`✅ BSE Downloaded: ${filename} in ${downloadTime}s (${(body.length / 1024).toFixed(1)}KB)`);

    return { path: finalPath, bytes: body.length };

}

module.exports = downloadPdf;
