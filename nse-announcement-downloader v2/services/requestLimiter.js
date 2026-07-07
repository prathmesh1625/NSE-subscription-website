const config =
    require(
        "./config"
    );

let active =
    0;

const queue =
    [];

async function execute(
    fn
) {

    return new Promise(

        (resolve, reject) => {

            queue.push({

                fn,

                resolve,

                reject

            });

            process();

        }

    );

}

async function process() {

    if (
        active
        >=
        config.requestLimit
    )
        return;

    if (
        queue.length === 0
    )
        return;

    active++;

    const task =
        queue.shift();

    try {

        const result =

            await task.fn();

        task.resolve(
            result
        );

    }
    catch (err) {

        task.reject(
            err
        );

    }
    finally {

        active--;

        process();

    }

}

module.exports = {

    execute

};