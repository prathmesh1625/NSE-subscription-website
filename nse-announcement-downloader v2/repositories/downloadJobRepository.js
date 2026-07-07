const db =
    require("../db/connection");

async function add(
    url,
    filename
) {

    await db.query(

        `

INSERT INTO download_jobs(

url,
filename

)

VALUES(

$1,
$2

)

`,

        [
            url,
            filename
        ]

    );

}

async function claimJobs(
    limit = 20
) {

    const result =

        await db.query(

            `

UPDATE download_jobs

SET

status='PROCESSING',

updated_at=NOW()

WHERE id IN (

SELECT id

FROM download_jobs

WHERE status='PENDING'

ORDER BY id ASC

LIMIT $1

FOR UPDATE SKIP LOCKED

)

RETURNING *

`,

            [
                limit
            ]

        );

    return result.rows;

}

async function markDone(
    id
) {

    await db.query(

        `

UPDATE download_jobs

SET

status='DONE',

updated_at=NOW()

WHERE id=$1

`,

        [
            id
        ]

    );

}

async function markFailed(
    id
) {

    await db.query(

        `

UPDATE download_jobs

SET

status='FAILED',

updated_at=NOW()

WHERE id=$1

`,

        [
            id
        ]

    );

}
async function pendingCount() {

    const result =

        await db.query(

            `

SELECT COUNT(*)

FROM download_jobs

WHERE status='PENDING'

`

        );

    return Number(
        result.rows[0].count
    );

}

async function resetStuckJobs() {

    await db.query(

        `

UPDATE download_jobs

SET

status='PENDING',

updated_at=NOW()

WHERE

status='PROCESSING'

AND

updated_at
<
NOW()
-
INTERVAL '5 minutes'

`

    );

}

async function stats() {

    const result =

        await db.query(

            `

SELECT

status,

COUNT(*) as count

FROM download_jobs

GROUP BY status

`

        );

    return result.rows;

}
async function cleanupDoneJobs() {

    await db.query(

        `

DELETE FROM download_jobs

WHERE

status='DONE'

AND

updated_at
<
NOW()
-
INTERVAL '1 day'

`

    );

}

module.exports = {

    add,

    claimJobs,

    markDone,

    markFailed,

    resetStuckJobs,

    stats,

    cleanupDoneJobs,
    pendingCount

};