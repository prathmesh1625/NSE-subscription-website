const repo =
    require(
        "../repositories/announcementRepository"
    );

let queue =
    [];

async function flush() {

    if (
        queue.length === 0
    )
        return;

    const copy =
        [
            ...queue
        ];

    queue = [];

    await Promise.all(

        copy.map(
            repo.save
        )

    );

    console.log(

        `Batch Saved:
${copy.length}`

    );

}

function push(
    item
) {

    queue.push(
        item
    );

    if (
        queue.length
        >= 20
    ) {

        flush();

    }

}

module.exports = {

    push,

    flush

};