const db =
    require("../db/subscriptionConnection");

// Distinct symbols selected by users who currently
// hold an ACTIVE subscription in the portal.
async function getSubscribedSymbols() {

    const result =

        await db.query(

            `

SELECT DISTINCT

c.symbol

FROM user_companies uc

JOIN companies c

ON c.id = uc.company_id

JOIN subscriptions s

ON s.user_id = uc.user_id

AND s.status = 'ACTIVE'

ORDER BY c.symbol

`

        );

    return result.rows.map(
        row => row.symbol
    );

}

module.exports = {

    getSubscribedSymbols

};
