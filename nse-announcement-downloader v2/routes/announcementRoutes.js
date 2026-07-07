const express =
    require(
        "express"
    );

const router =
    express.Router();

const db =
    require(
        "../db/connection"
    );

router.get(

    "/latest",

    async (req, res) => {

        try {

            const result =

                await db.query(

                    `

SELECT *

FROM announcements

ORDER BY announcement_time DESC

LIMIT 20

`

                );

            res.json(

                result.rows

            );

        }
        catch (err) {

            res.status(500).json({

                error:
                    "Server Error"

            });

        }

    }

);

router.get(

    "/company/:symbol",

    async (req, res) => {

        try {

            const result =

                await db.query(

                    `

SELECT *

FROM announcements

WHERE company_symbol=$1

ORDER BY announcement_time DESC

LIMIT 20

`,

                    [

                        req.params.symbol

                    ]

                );

            res.json(

                result.rows

            );

        }
        catch (err) {

            res.status(500).json({

                error:
                    "Server Error"

            });

        }

    }

);

module.exports =
    router;