const db =
    require(
        "../db/connection"
    );

async function add(
    url,
    filename
) {

    await db.query(

        `

INSERT INTO failed_jobs(

url,
filename

)

VALUES(

$1,
$2

)

ON CONFLICT(url)

DO NOTHING

`,

        [
            url,
            filename
        ]

    );

}

async function getAll() {

    const result =

        await db.query(

            `

SELECT *

FROM failed_jobs

ORDER BY id ASC

`

        );

    return result.rows;

}

async function remove(
    id
) {

    await db.query(

        `

DELETE FROM failed_jobs

WHERE id=$1

`,

        [
            id
        ]

    );

}

async function removeByUrl(
    url
) {

    await db.query(

        `

DELETE FROM failed_jobs

WHERE url=$1

`,

        [
            url
        ]

    );

}

// Atomically claim jobs that are due for a retry,
// bumping their retry counter so a permanently dead
// URL eventually stops being retried.
async function claimRetryable(
    maxRetries
) {

    const result =

        await db.query(

            `

UPDATE failed_jobs

SET

retries = retries + 1,

last_retry_at = NOW()

WHERE id IN (

SELECT id

FROM failed_jobs

WHERE

retries < $1

AND

(

last_retry_at IS NULL

OR

last_retry_at
<
NOW() - INTERVAL '2 minutes'

)

FOR UPDATE SKIP LOCKED

)

RETURNING *

`,

            [
                maxRetries
            ]

        );

    return result.rows;

}

module.exports = {

    add,

    getAll,

    remove,

    removeByUrl,

    claimRetryable

};