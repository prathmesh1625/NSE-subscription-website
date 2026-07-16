const db =
    require(
        "../config/database"
    );

async function getUserCompanies(
    userId
) {

    const result =

        await db.query(

            `
            SELECT

                c.id,
                c.symbol,
                c.company_name

            FROM user_companies uc

            JOIN companies c

            ON c.id = uc.company_id

            WHERE uc.user_id = $1

            ORDER BY c.company_name
            `,

            [userId]

        );

    return result.rows;

}

async function countUserCompanies(
    userId
) {

    const result =

        await db.query(

            `
            SELECT COUNT(*)

            FROM user_companies

            WHERE user_id = $1
            `,

            [userId]

        );

    return Number(
        result.rows[0].count
    );

}

async function addCompany(
    userId,
    companyId
) {

    await db.query(

        `
        INSERT INTO user_companies (

            user_id,
            company_id

        )

        VALUES (

            $1,
            $2

        )
        `,

        [

            userId,
            companyId

        ]

    );

}

async function removeCompany(
    userId,
    companyId
) {

    await db.query(

        `
        DELETE FROM user_companies

        WHERE

            user_id = $1

        AND

            company_id = $2
        `,

        [

            userId,
            companyId

        ]

    );

}

/**
 * Adds every company currently flagged as part of the "default watchlist"
 * (see migration 002 and adminRepository's addCompaniesToAllUsers) to a
 * brand-new user's own watchlist. Called right after a user row is first
 * created — real OTP signup (authController.verifyToken) and admin-created
 * users (adminController's create-user bulk action) both go through this,
 * so either path ends up with the same starter companies.
 */
async function seedDefaultCompanies(
    userId
) {

    await db.query(

        `
        INSERT INTO user_companies (

            user_id,
            company_id

        )

        SELECT

            $1,
            c.id

        FROM companies c

        WHERE c.is_default_watchlist = TRUE

        ON CONFLICT (user_id, company_id) DO NOTHING
        `,

        [
            userId
        ]

    );

}

async function alreadySelected(
    userId,
    companyId
) {

    const result =

        await db.query(

            `
            SELECT *

            FROM user_companies

            WHERE

                user_id = $1

            AND

                company_id = $2
            `,

            [

                userId,
                companyId

            ]

        );

    return result.rows.length > 0;

}

module.exports = {

    getUserCompanies,

    countUserCompanies,

    seedDefaultCompanies,

    addCompany,

    removeCompany,

    alreadySelected

};