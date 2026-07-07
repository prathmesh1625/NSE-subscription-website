const path = require("path");

console.log(
    "Loading env from:",
    path.resolve(__dirname, "../.env")
);

require("dotenv").config({
    path: path.resolve(__dirname, "../.env")
});

console.log({
    DB_HOST: process.env.DB_HOST,
    DB_PORT: process.env.DB_PORT,
    DB_NAME: process.env.DB_NAME,
    DB_USER: process.env.DB_USER,
    DB_PASSWORD: process.env.DB_PASSWORD
        ? "FOUND"
        : "MISSING"
});
const { Pool } =
    require("pg");


require("dotenv").config({
    path: path.resolve(
        __dirname,
        "../.env"
    )
});

const pool =
    new Pool({

        host:
            process.env.DB_HOST,

        port:
            Number(
                process.env.DB_PORT
            ),

        database:
            process.env.DB_NAME,

        user:
            process.env.DB_USER,

        password:
            process.env.DB_PASSWORD,

        ssl: false

    });

module.exports =
    pool;