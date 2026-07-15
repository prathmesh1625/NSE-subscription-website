const axios = require("axios");
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
 * Bulk-adds one or more companies to EVERY user's watchlist at once, so an
 * admin doesn't have to open each user and edit their shares one by one.
 *
 * This only ever *adds* — existing subscriptions are left untouched, and a
 * company a user already tracks is skipped (ON CONFLICT DO NOTHING). It does
 * not enforce plan company_limits: a bulk push like this is an admin
 * broadcast, so we let it through and report how many links were created.
 *
 * Returns:
 *   - addedLinks:  number of (user, company) rows actually inserted
 *   - userCount:   total number of users the company set was applied across
 */
async function addCompaniesToAllUsers(companyIds) {
    const ids = (companyIds || [])
        .map((id) => Number(id))
        .filter((id) => Number.isFinite(id));

    if (ids.length === 0) {
        return { addedLinks: 0, userCount: 0 };
    }

    const inserted = await db.query(
        `
        INSERT INTO user_companies (user_id, company_id)
        SELECT u.id, c.company_id
        FROM users u
        CROSS JOIN unnest($1::bigint[]) AS c(company_id)
        ON CONFLICT (user_id, company_id) DO NOTHING
        `,
        [ids]
    );

    const userCountResult = await db.query(`SELECT COUNT(*)::int AS count FROM users`);

    return {
        addedLinks: inserted.rowCount,
        userCount: userCountResult.rows[0].count,
    };
}

/**
 * Bulk-removes one or more companies from EVERY user's watchlist at once —
 * the mirror of addCompaniesToAllUsers. Users who weren't tracking a given
 * share are simply unaffected.
 *
 * Returns:
 *   - removedLinks: number of (user, company) rows actually deleted
 *   - userCount:    total number of users (for messaging)
 */
async function removeCompaniesFromAllUsers(companyIds) {
    const ids = (companyIds || [])
        .map((id) => Number(id))
        .filter((id) => Number.isFinite(id));

    if (ids.length === 0) {
        return { removedLinks: 0, userCount: 0 };
    }

    const deleted = await db.query(
        `DELETE FROM user_companies WHERE company_id = ANY($1::bigint[])`,
        [ids]
    );

    const userCountResult = await db.query(`SELECT COUNT(*)::int AS count FROM users`);

    return {
        removedLinks: deleted.rowCount,
        userCount: userCountResult.rows[0].count,
    };
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
// PDF delivery status (via the bot's own admin API — see the "bot" service
// in docker-compose.yml). The bot tracks WhatsApp delivery ground-truth in
// its own SQLite DB; this backend has no direct access to it, so it's read
// over HTTP with a shared secret, the same pattern the dashboard uses to
// call THIS backend (see adminAuthMiddleware.js).
// ---------------------------------------------------------------------------

/** Every user with an ACTIVE subscription — the population "PDF delivery" is evaluated over. */
async function getActiveSubscribers() {
    const result = await db.query(`
        SELECT DISTINCT u.id, u.name, u.mobile
        FROM users u
        JOIN subscriptions s ON s.user_id = u.id
        WHERE s.status = 'ACTIVE'
        ORDER BY u.mobile
    `);
    return result.rows;
}

/**
 * Converts a user's stored mobile number (10-digit, no country code) into
 * the format the bot keys its delivery-status data by (91-prefixed, the
 * WhatsApp "from" field) — mirrors the exact normalization already done in
 * bot/db_watcher.py::get_subscribers_for_symbol_pg.
 */
function normalizePhoneForBot(mobile) {
    const digits = String(mobile || "").replace(/\D/g, "");
    return digits.length === 10 ? `91${digits}` : digits;
}

/**
 * Fetches the bot's per-phone delivery snapshot and returns it as a Map
 * keyed by the bot's phone format (see normalizePhoneForBot). Fails soft —
 * if the bot is unreachable or unconfigured, callers get an empty Map so
 * the rest of the admin API (stats/users/actions) keeps working.
 */
async function fetchDeliveryStatusMap() {
    const baseUrl = process.env.BOT_ADMIN_URL;
    const apiKey = process.env.BOT_ADMIN_KEY;

    if (!baseUrl || !apiKey) {
        console.warn(
            "BOT_ADMIN_URL/BOT_ADMIN_KEY not configured — PDF delivery status will be unavailable."
        );
        return new Map();
    }

    try {
        const response = await axios.get(`${baseUrl}/admin/delivery-status`, {
            headers: { "x-bot-admin-key": apiKey },
            timeout: 5000,
        });

        const map = new Map();
        for (const u of response.data.users || []) {
            map.set(u.phone, u);
        }
        return map;
    } catch (err) {
        console.error("Failed to fetch delivery status from bot:", err.message);
        return new Map();
    }
}

// ---------------------------------------------------------------------------
// Option lists (for building forms in the dashboard)
// ---------------------------------------------------------------------------

async function listPlans() {
    const result = await db.query(`SELECT * FROM plans ORDER BY price ASC`);
    return result.rows;
}

/**
 * Changes how many companies/shares a plan allows (e.g. bump Premium from 25
 * to 30). This is stored on the plan itself, not per-subscription, so it
 * takes effect immediately for every current and future subscriber on that
 * plan — no need to touch existing subscription rows.
 */
async function updatePlanCompanyLimit(planId, companyLimit) {
    const result = await db.query(
        `UPDATE plans SET company_limit = $1 WHERE id = $2 RETURNING *`,
        [companyLimit, planId]
    );
    return result.rows[0];
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
    addCompaniesToAllUsers,
    removeCompaniesFromAllUsers,
    upsertUserSubscription,
    setPaymentRefundStatus,
    listPlans,
    updatePlanCompanyLimit,
    searchCompanies,
    getActiveSubscribers,
    normalizePhoneForBot,
    fetchDeliveryStatusMap,
};
