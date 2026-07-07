async function retry(

    fn,

    attempts = 3,

    delay = 2000

) {

    let error;

    for (

        let i = 1;

        i <= attempts;

        i++

    ) {

        try {

            return await fn();

        }
        catch (err) {

            error =
                err;

            console.log(

                `Retry
${i}
/
${attempts}`

            );

            if (
                i <
                attempts
            ) {

                await new Promise(

                    r =>

                        setTimeout(

                            r,

                            delay

                        )

                );

            }

        }

    }

    throw error;

}

module.exports =
    retry;