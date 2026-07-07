const heartbeat =
    require(
        "../repositories/workerHeartbeatRepository"
    );

console.log(
    "Supervisor Started"
);

async function monitor() {

    const dead =

        await heartbeat.getDeadWorkers();

    if (
        dead.length > 0
    ) {

        console.log(
            "\nDEAD WORKERS DETECTED"
        );

        console.table(
            dead
        );

    }

}

setInterval(

    monitor,

    10000

);