const db = require("../db/connection");

async function add(url, filename) {

    await db.query(
        `INSERT INTO bse_download_jobs (url, filename) VALUES ($1, $2)`,
        [url, filename]
    );

}

/**
 * Atomically take up to `limit` pending jobs. FOR UPDATE SKIP LOCKED lets more
 * than one worker (or a restarted one) run without ever handing the same job
 * out twice.
 */
async function claimJobs(limit = 20) {

    const result = await db.query(
        `
        UPDATE bse_download_jobs
        SET status = 'PROCESSING', updated_at = NOW()
        WHERE id IN (
            SELECT id
            FROM bse_download_jobs
            WHERE status = 'PENDING'
            ORDER BY id ASC
            LIMIT $1
            FOR UPDATE SKIP LOCKED
        )
        RETURNING *
        `,
        [limit]
    );

    return result.rows;

}

async function markDone(id) {
    await db.query(
        `UPDATE bse_download_jobs SET status = 'DONE', updated_at = NOW() WHERE id = $1`,
        [id]
    );
}

async function markFailed(id) {
    await db.query(
        `UPDATE bse_download_jobs SET status = 'FAILED', updated_at = NOW() WHERE id = $1`,
        [id]
    );
}

async function pendingCount() {

    const result = await db.query(
        `SELECT COUNT(*) FROM bse_download_jobs WHERE status = 'PENDING'`
    );

    return Number(result.rows[0].count);

}

// A worker killed mid-download leaves its jobs stuck in PROCESSING forever.
async function resetStuckJobs() {
    await db.query(`
        UPDATE bse_download_jobs
        SET status = 'PENDING', updated_at = NOW()
        WHERE status = 'PROCESSING'
          AND updated_at < NOW() - INTERVAL '90 seconds'
    `);
}

async function stats() {

    const result = await db.query(
        `SELECT status, COUNT(*)::int AS count FROM bse_download_jobs GROUP BY status`
    );

    return result.rows;

}

async function cleanupDoneJobs() {
    await db.query(`
        DELETE FROM bse_download_jobs
        WHERE status = 'DONE' AND updated_at < NOW() - INTERVAL '1 day'
    `);
}

module.exports = {
    add,
    claimJobs,
    markDone,
    markFailed,
    pendingCount,
    resetStuckJobs,
    stats,
    cleanupDoneJobs
};
