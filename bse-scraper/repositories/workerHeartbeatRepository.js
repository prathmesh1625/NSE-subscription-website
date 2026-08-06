const db = require("../db/connection");

async function beat(worker) {

    await db.query(
        `
        INSERT INTO worker_heartbeats (worker_name, last_seen)
        VALUES ($1, NOW())
        ON CONFLICT (worker_name) DO UPDATE SET last_seen = NOW()
        `,
        [worker]
    );

}

module.exports = { beat };
