const db =
    require(
        "../config/database"
    );

async function findByMobile(
    mobile
) {

    const result =

        await db.query(

            `
            SELECT

                id,
                name,
                mobile

            FROM users

            WHERE mobile = $1
            `,

            [mobile]

        );

    return result.rows[0];

}

async function create(
    name,
    mobile
) {

    const result =

        await db.query(

            `
            INSERT INTO users (

                name,
                mobile

            )

            VALUES (

                $1,
                $2

            )

            RETURNING id, name, mobile
            `,

            [
                name,
                mobile
            ]

        );

    return result.rows[0];

}

/**
 * TEMPORARY (Razorpay testing support — see authController.loginWithTestCredentials).
 * Deletes the user row (and, via ON DELETE CASCADE, its subscriptions,
 * payments, and user_companies rows) for the given mobile/identifier.
 * Used only to guarantee the reserved test account always starts clean.
 * Safe to remove once the username/password test login is removed.
 */
async function deleteByMobile(
    mobile
) {

    await db.query(

        `
        DELETE FROM users

        WHERE mobile = $1
        `,

        [mobile]

    );

}

/**
 * Permanently delete a user's account by id (self-service account deletion).
 * Cascades via ON DELETE CASCADE to subscriptions, payments, and
 * user_companies (see migrations 003/004/006).
 * @returns {boolean} true if a row was deleted, false if no such user existed.
 */
async function deleteById(
    id
) {

    const result =

        await db.query(

            `
            DELETE FROM users

            WHERE id = $1
            `,

            [id]

        );

    return result.rowCount > 0;

}

module.exports = {

    findByMobile,

    create,

    deleteByMobile,

    deleteById

};