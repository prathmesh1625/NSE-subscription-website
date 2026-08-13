async function retry(fn, attempts = 3, delay = 1500) {

    let lastError;

    for (let i = 1; i <= attempts; i++) {

        try {
            return await fn();
        }
        catch (err) {
            lastError = err;

            if (i < attempts) {
                console.log(`Retry ${i}/${attempts}: ${err.message}`);
                await new Promise(r => setTimeout(r, delay));
            }
        }

    }

    throw lastError;
}

module.exports = retry;
