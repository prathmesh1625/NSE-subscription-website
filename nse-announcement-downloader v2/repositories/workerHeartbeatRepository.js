const db =
    require("../db/connection");

async function beat(
    worker
) {

    await db.query(

        `

INSERT INTO worker_heartbeats(

worker_name,
last_seen

)

VALUES(

$1,
NOW()

)

ON CONFLICT(worker_name)

DO UPDATE SET

last_seen=NOW()

`,

        [
            worker
        ]

    );

}

async function getAll() {

    const result =

        await db.query(

            `

SELECT *

FROM worker_heartbeats

ORDER BY worker_name

`

        );

    return result.rows;

}

async function getDeadWorkers() {

    const result =

        await db.query(

            `

SELECT *

FROM worker_heartbeats

WHERE

last_seen
<
NOW()
-
INTERVAL '30 seconds'

`

        );

    return result.rows;

}

module.exports = {

    beat,

    getAll,

    getDeadWorkers

};