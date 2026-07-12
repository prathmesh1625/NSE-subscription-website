const db = require("../config/database");

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

async function getStats() {
    const result = await db.query(`
        SELECT
            COALESCE((SELECT SUM(amount) FROM payments WHERE status = 'SUCCESS'), 0)                AS total_received,
            COALESCE((SELECT SUM(COALESCE(refund_amount, amount)) FROM payments
                        WHERE status = 'SUCCESS' AND refund_status = 'PENDING'), 0)                  AS total_refund_pending,
            COALESCE((SELECT SUM(refund_amount) FROM payments WHERE refund_status = 'REFUNDED'), 0)  AS total_refunded,
            (SELECT COUNT(*) FROM users)                                                             AS total_users,
            (SELECT COUNT(*) FROM subscriptions WHERE status = 'ACTIVE')                              AS active_subscriptions,
            (SELECT COUNT(*) FROM subscriptions s JOIN plans p ON p.id = s.plan_id
                        WHERE s.status = 'ACTIVE' AND p.name = 'PREMIUM')                              AS active_premium,
            (SELECT COUNT(*) FROM payments WHERE status = 'SUCCESS')                                  AS successful_payments
    `);

    return result.rows[0];
}

// Every payment that counts toward `total_received` in getStats() above
// (status = 'SUCCESS'), joined with the paying user's name/mobile so the
// dashboard's drill-down view can show who each payment came from.
async function getSuccessfulPayments() {
    const result = await db.query(`
        SELECT
            p.id,
            p.amount,
            p.razorpay_payment_id,
            p.created_at,
            u.name,
            u.mobile
        FROM payments p
        JOIN users u ON u.id = p.user_id
        WHERE p.status = 'SUCCESS'
        ORDER BY p.created_at DESC
    `);
    return result.rows;
}

// ---------------------------------------------------------------------------
// Users - search / list / detail
// ---------------------------------------------------------------------------

async function searchUsers(search, page, pageSize) {
    const offset = (page - 1) * pageSize;
    const like = `%${search || ""}%`;

    const result = await db.query(
        `
        SELECT
            u.id,
            u.name,
            u.mobile,
            u.created_at,
            s.status       AS sub_status,
            s.end_date     AS sub_end_date,
            p.name         AS plan_name
        FROM users u
        LEFT JOIN subscriptions s
            ON s.user_id = u.id AND s.status = 'ACTIVE'
        LEFT JOIN plans p
            ON p.id = s.plan_id
        WHERE
            ($1 = '' OR u.mobile ILIKE $2 OR u.name ILIKE $2)
        ORDER BY u.created_at DESC
        LIMIT $3 OFFSET $4
        `,
        [search || "", like, pageSize, offset]
    );

    const countResult = await db.query(
        `
        SELECT COUNT(*) FROM users u
        WHERE ($1 = '' OR u.mobile ILIKE $2 OR u.name ILIKE $2)
        `,
        [search || "", like]
    );

    return {
        rows: result.rows,
        total: Number(countResult.rows[0].count),
    };
}

async function getUserProfile(userId) {
    const result = await db.query(
        `SELECT id, name, mobile, created_at FROM users WHERE id = $1`,
        [userId]
    );
    return result.rows[0];
}

async function getUserSubscriptionHistory(userId) {
    const result = await db.query(
        `
        SELECT
            s.id,
            s.status,
            s.start_date,
            s.end_date,
            s.created_at,
            p.id   AS plan_id,
            p.name AS plan_name,
            p.price,
            p.company_limit,
            p.duration_days
        FROM subscriptions s
        JOIN plans p ON p.id = s.plan_id
        WHERE s.user_id = $1
        ORDER BY s.id DESC
        `,
        [userId]
    );
    return result.rows;
}

async function getUserCompanies(userId) {
    const result = await db.query(
        `
        SELECT c.id, c.symbol, c.company_name
        FROM user_companies uc
        JOIN companies c ON c.id = uc.company_id
        WHERE uc.user_id = $1
        ORDER BY c.company_name
        `,
        [userId]
    );
    return result.rows;
}

async function getUserPayments(userId) {
    const result = await db.query(
        `
        SELECT
            id,
            amount,
            status,
            razorpay_order_id,
            razorpay_payment_id,
            refund_status,
            refund_amount,
            refund_notes,
            refunded_at,
            created_at
        FROM payments
        WHERE user_id = $1
        ORDER BY id DESC
        `,
        [userId]
    );
    return result.rows;
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

/**
 * Replaces a user's tracked companies with the given list of company ids.
 * Soft-validates against the plan's company_limit — does not block the
 * admin, but reports whether the new count exceeds the plan limit so the
 * dashboard can surface a warning.
 */
async function setUserCompanies(userId, companyIds) {
    const client = await db.pool.connect();

    try {
        await client.query("BEGIN");

        await client.query(`DELETE FROM user_companies WHERE user_id = $1`, [
            userId,
        ]);

        for (const companyId of companyIds) {
            await client.query(
                `INSERT INTO user_companies (user_id, company_id)
                 VALUES ($1, $2)
                 ON CONFLICT (user_id, company_id) DO NOTHING`,
                [userId, companyId]
            );
        }

        await client.query("COMMIT");
    } catch (err) {
        await client.query("ROLLBACK");
        throw err;
    } finally {
        client.release();
    }

    const activeSub = await db.query(
        `
        SELECT p.company_limit
        FROM subscriptions s
        JOIN plans p ON p.id = s.plan_id
        WHERE s.user_id = $1 AND s.status = 'ACTIVE'
        ORDER BY s.id DESC LIMIT 1
        `,
        [userId]
    );

    const limit = activeSub.rows[0] ? activeSub.rows[0].company_limit : null;
    const exceedsLimit = limit !== null && companyIds.length > limit;

    return { count: companyIds.length, limit, exceedsLimit };
}

/**
 * Upserts the user's active subscription: updates the existing ACTIVE row
 * in place if one exists, otherwise creates a new one. Also allows changing
 * the status directly (e.g. to deactivate).
 */
async function upsertUserSubscription(userId, { planId, status, startDate, endDate }) {
    const existing = await db.query(
        `SELECT id FROM subscriptions WHERE user_id = $1 AND status = 'ACTIVE' ORDER BY id DESC LIMIT 1`,
        [userId]
    );

    if (existing.rows[0]) {
        const result = await db.query(
            `
            UPDATE subscriptions
            SET plan_id = $1, status = $2, start_date = $3, end_date = $4, updated_at = NOW()
            WHERE id = $5
            RETURNING *
            `,
            [planId, status, startDate, endDate, existing.rows[0].id]
        );
        return result.rows[0];
    }

    const result = await db.query(
        `
        INSERT INTO subscriptions (user_id, plan_id, status, start_date, end_date)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        `,
        [userId, planId, status, startDate, endDate]
    );
    return result.rows[0];
}

async function setPaymentRefundStatus(paymentId, { refundStatus, refundAmount, notes, actorUsername }) {
    const result = await db.query(
        `
        UPDATE payments
        SET
            refund_status = $1::VARCHAR,
            refund_amount = $2::NUMERIC,
            refund_notes = $3::TEXT,
            refund_updated_by = $4::VARCHAR,
            refunded_at = CASE WHEN $1::VARCHAR = 'REFUNDED' THEN NOW() ELSE refunded_at END
        WHERE id = $5
        RETURNING *
        `,
        [refundStatus, refundAmount, notes || null, actorUsername || null, paymentId]
    );
    return result.rows[0];
}

// ---------------------------------------------------------------------------
// Option lists (for building forms in the dashboard)
// ---------------------------------------------------------------------------

async function listPlans() {
    const result = await db.query(`SELECT * FROM plans ORDER BY price ASC`);
    return result.rows;
}

async function searchCompanies(search, selectedIds = []) {
    const like = `%${search || ""}%`;
    const ids = (selectedIds || [])
        .map((id) => Number(id))
        .filter((id) => Number.isFinite(id));

    // Always fetch the caller's already-selected companies by id, however
    // many there are — this is what guarantees a subscribed share still
    // shows up (checked, with a label) in the multiselect even if it falls
    // outside the capped/paged general results below or doesn't match
    // whatever the admin is currently typing into the search box.
    const selectedResult = ids.length
        ? await db.query(
              `
              SELECT id, symbol, company_name
              FROM companies
              WHERE id = ANY($1::bigint[])
              ORDER BY company_name
              `,
              [ids]
          )
        : { rows: [] };

    // A bounded page of everything else matching the search term, so a
    // single request never ships the entire (multi-thousand-row) companies
    // table just to populate one dropdown.
    const generalResult = await db.query(
        `
        SELECT id, symbol, company_name
        FROM companies
        WHERE (symbol ILIKE $1 OR company_name ILIKE $1)
          AND NOT (id = ANY($2::bigint[]))
        ORDER BY company_name
        LIMIT 200
        `,
        [like, ids]
    );

    return [...selectedResult.rows, ...generalResult.rows];
}

module.exports = {
    getStats,
    getSuccessfulPayments,
    searchUsers,
    getUserProfile,
    getUserSubscriptionHistory,
    getUserCompanies,
    getUserPayments,
    setUserCompanies,
    upsertUserSubscription,
    setPaymentRefundStatus,
    listPlans,
    searchCompanies,
};
