const config = require("./config");

// Bounded-concurrency gate for outbound BSE calls, so a burst of pages never
// turns into a burst of sockets.
let active = 0;

const queue = [];

function drain() {
    while (active < config.requestLimit && queue.length > 0) {
        const task = queue.shift();
        active++;

        Promise.resolve()
            .then(task.fn)
            .then(task.resolve, task.reject)
            .finally(() => {
                active--;
                drain();
            });
    }
}

function execute(fn) {
    return new Promise((resolve, reject) => {
        queue.push({ fn, resolve, reject });
        drain();
    });
}

module.exports = { execute };
