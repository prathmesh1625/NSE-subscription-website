const db =
    require(
        "../db/connection"
    );

async function get(
    symbol
) {

    const result =

        await db.query(

            `

SELECT *

FROM company_state

WHERE symbol=$1

`,

            [
                symbol
            ]

        );

    return result.rows[0];

}

async function update(
    symbol,
    time
) {

    await db.query(

        `

INSERT INTO company_state(

symbol,
last_announcement_time

)

VALUES(

$1,
$2

)

ON CONFLICT(symbol)

DO UPDATE SET

last_announcement_time
=
EXCLUDED.last_announcement_time

`,

        [
            symbol,
            time
        ]

    );

}

module.exports = {

    get,

    update

};