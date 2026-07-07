const path = require("path");

require("dotenv").config({
    path: path.resolve(__dirname, "../.env")
});

const { Pool } = require("pg");

// Read-only pool to the subscription portal database
// (same Postgres server, different database).
const pool =
    new Pool({

        host:
            process.env.SUB_DB_HOST
            ||
            process.env.DB_HOST,

        port:
            Number(
                process.env.SUB_DB_PORT
                ||
                process.env.DB_PORT
            ),

        database:
            process.env.SUB_DB_NAME
            ||
            "nse_subscription",

        user:
            process.env.SUB_DB_USER
            ||
            process.env.DB_USER,

        password:
            process.env.SUB_DB_PASSWORD
            ||
            process.env.DB_PASSWORD,

        max: 5,

        ssl: false

    });

pool.on(
    "error",
    (err) => {

        console.log(
            "Subscription DB Pool Error:"
        );

        console.log(
            err.message
        );

    }
);

module.exports =
    pool;
