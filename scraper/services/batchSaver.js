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
    
    const flushStart = Date.now();

    await Promise.all(

        copy.map(
            repo.save
        )

    );
    
    const flushTime = ((Date.now() - flushStart) / 1000).toFixed(2);

    console.log(

        `💾 Batch Saved: ${copy.length} filings in ${flushTime}s`

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