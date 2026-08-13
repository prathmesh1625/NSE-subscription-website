const db = require("../db/connection");

/**
 * Insert a filing. Returns the new row id, or null if this pdf_url was already
 * known.
 *
 * The ON CONFLICT is the real dedup for this service: the unique index on
 * pdf_url means re-reading the same page of the feed every 8 seconds is free,
 * and two cycles racing on the same filing can only ever insert it once. It
 * also means a restart re-scanning the day's feed does not re-notify anyone.
 */
async function save(data) {

    const result = await db.query(
        `
        INSERT INTO announcements (
            company_symbol,
            title,
            pdf_url,
            local_path,
            announcement_time,
            download_status,
            exchange
        )
        VALUES ($1, $2, $3, $4, $5, $6, 'BSE')
        ON CONFLICT (pdf_url) DO NOTHING
        RETURNING id
        `,
        [
            data.company_symbol,
            data.title,
            data.pdf_url,
            data.local_path,
            data.announcement_time,
            data.download_status
        ]
    );

    return result.rows.length > 0 ? result.rows[0].id : null;

}

async function updateStatus(url, status) {

    await db.query(
        `UPDATE announcements SET download_status = $1 WHERE pdf_url = $2`,
        [status, url]
    );

}

module.exports = { save, updateStatus };
