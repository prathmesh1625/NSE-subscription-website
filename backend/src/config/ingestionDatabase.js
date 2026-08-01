const { Pool } = require("pg");
require("dotenv").config();

// Separate connection to the scraper's own database (nse_ingestion) — same
// Postgres server and credentials as the main app's DB (see database/init.sql),
// just a different database name. Used only by the admin API's "scraped
// companies" browser (see admin/adminRepository.js) so the two stay decoupled
// from everything else this backend does.
const pool = new Pool({
    host: process.env.DB_HOST,
    port: Number(process.env.DB_PORT),
    database: process.env.DB_NAME_INGESTION || "nse_ingestion",
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,

    max: 5,
    idleTimeoutMillis: 30000,
    connectionTimeoutMillis: 5000,
});

pool.on("error", (err) => {
    console.error("Unexpected nse_ingestion PostgreSQL error:", err.message);
});

module.exports = {
    query: (text, params) => pool.query(text, params),
};
