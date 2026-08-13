const path = require("path");

require("dotenv").config({
    path: path.resolve(__dirname, "../.env")
});

const { Pool } = require("pg");

// Ingestion database — the SAME one the NSE scraper writes to, because the bot
// reads `announcements` from it. Only the BSE job tables are private to this
// service.
const pool = new Pool({
    host: process.env.DB_HOST,
    port: Number(process.env.DB_PORT || 5432),
    database: process.env.DB_NAME || "nse_ingestion",
    user: process.env.DB_USER,
    password: process.env.DB_PASSWORD,
    max: Number(process.env.BSE_DB_POOL_MAX || 10),
    ssl: false
});

pool.on("error", err => {
    console.log("Ingestion DB Pool Error:", err.message);
});

module.exports = pool;
