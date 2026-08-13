const db = require("../db/connection");

async function add(url, filename, error) {

    await db.query(
        `
        INSERT INTO bse_failed_jobs (url, filename, last_error)
        VALUES ($1, $2, $3)
        ON CONFLICT (url) DO UPDATE SET last_error = EXCLUDED.last_error
        `,
        [url, filename, error ? String(error).slice(0, 500) : null]
    );

}

async function removeByUrl(url) {
    await db.query(`DELETE FROM bse_failed_jobs WHERE url = $1`, [url]);
}

/**
 * Claim jobs due for another attempt, bumping the counter in the same
 * statement so a permanently dead URL eventually stops being retried and two
 * recovery passes can't both pick up the same row.
 */
async function claimRetryable(maxRetries, backoffSeconds = 15) {

    const result = await db.query(
        `
        UPDATE bse_failed_jobs
        SET retries = retries + 1, last_retry_at = NOW()
        WHERE id IN (
            SELECT id
            FROM bse_failed_jobs
            WHERE retries < $1
              AND (
                last_retry_at IS NULL
                OR last_retry_at < NOW() - ($2 || ' seconds')::interval
              )
            FOR UPDATE SKIP LOCKED
        )
        RETURNING *
        `,
        [maxRetries, String(backoffSeconds)]
    );

    return result.rows;

}

// Jobs that exhausted every retry — reported so a systematic breakage (BSE
// changing its attachment host, say) is visible in the logs instead of silent.
async function deadCount(maxRetries) {

    const result = await db.query(
        `SELECT COUNT(*)::int AS count FROM bse_failed_jobs WHERE retries >= $1`,
        [maxRetries]
    );

    return result.rows[0].count;

}

module.exports = { add, removeByUrl, claimRetryable, deadCount };
