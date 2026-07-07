const db =
    require("../db/connection");

async function save(
    data
) {

    const result =

        await db.query(

            `

INSERT INTO announcements(

company_symbol,

title,

pdf_url,

local_path,

announcement_time,

download_status

)

VALUES(

$1,
$2,
$3,
$4,
$5,
$6

)

ON CONFLICT(pdf_url)

DO NOTHING

RETURNING id

`,

            [

                data.company_symbol,

                data.title,

                data.pdf_url,

                data.local_path,

                data.announcement_time,

                data.download_status

            ]

        );

    return (
        result.rows.length
        > 0
    );

}

async function updateStatus(
    url,
    status
) {

    await db.query(

        `

UPDATE announcements

SET download_status=$1

WHERE pdf_url=$2

`,

        [
            status,
            url
        ]

    );

}

module.exports = {

    save,

    updateStatus

};