const axios = require("axios");
const db = require("../config/database");
const ingestionDb = require("../config/ingestionDatabase");

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
            p.name         AS plan_name,
            (SELECT COUNT(*) FROM user_companies uc WHERE uc.user_id = u.id) AS companies_count
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

/**
 * Looks up a user by their exact normalized mobile number — used to check
 * for an existing account before creating a new one from the admin
 * dashboard (see createUser below), mirroring the same check the real
 * signup flow does in authController.verifyToken.
 */
async function findUserByMobile(mobile) {
    const result = await db.query(`SELECT id, name, mobile FROM users WHERE mobile = $1`, [mobile]);
    return result.rows[0];
}

/**
 * Creates a bare user record directly from the admin dashboard, without
 * them going through mobile+OTP signup themselves — e.g. for an offline
 * sale. Same shape as what authController.verifyToken creates on a
 * first-time login. The admin can then set their subscription and tracked
 * shares from the user's profile using the existing per-user actions.
 */
async function createUser(name, mobile) {
    const result = await db.query(
        `INSERT INTO users (name, mobile) VALUES ($1, $2) RETURNING id, name, mobile, created_at`,
        [name, mobile]
    );
    return result.rows[0];
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
            s.company_limit_override,
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
        SELECT s.company_limit_override, p.company_limit
        FROM subscriptions s
        JOIN plans p ON p.id = s.plan_id
        WHERE s.user_id = $1 AND s.status = 'ACTIVE'
        ORDER BY s.id DESC LIMIT 1
        `,
        [userId]
    );

    const sub = activeSub.rows[0];
    // A per-user override (see setUserShareLimitOverride) takes priority over
    // the plan's own default — that's the whole point of setting one.
    const limit = sub ? (sub.company_limit_override ?? sub.company_limit) : null;
    const exceedsLimit = limit !== null && companyIds.length > limit;

    return { count: companyIds.length, limit, exceedsLimit };
}

/**
 * Sets (or clears, with `overrideValue = null`) a per-user override of the
 * share/company limit, independent of their plan's default — e.g. bumping
 * one Premium user from 25 to 30 without touching the Premium plan itself.
 * Only applies to the user's current ACTIVE subscription; returns null if
 * they don't have one.
 */
async function setUserShareLimitOverride(userId, overrideValue) {
    const existing = await db.query(
        `
        SELECT s.id, p.name AS plan_name, p.company_limit
        FROM subscriptions s
        JOIN plans p ON p.id = s.plan_id
        WHERE s.user_id = $1 AND s.status = 'ACTIVE'
        ORDER BY s.id DESC LIMIT 1
        `,
        [userId]
    );

    const sub = existing.rows[0];
    if (!sub) return null;

    await db.query(
        `UPDATE subscriptions SET company_limit_override = $1 WHERE id = $2`,
        [overrideValue, sub.id]
    );

    return {
        planName: sub.plan_name,
        effectiveLimit: overrideValue !== null ? overrideValue : sub.company_limit,
    };
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

    // Both writes must land together: the watchlist rows and the
    // "default for future signups" flag describe the same intent, so a
    // failure partway through must not leave one applied without the other.
    const client = await db.pool.connect();
    let addedLinks = 0;

    try {
        await client.query("BEGIN");

        const inserted = await client.query(
            `
            INSERT INTO user_companies (user_id, company_id)
            SELECT u.id, c.company_id
            FROM users u
            CROSS JOIN unnest($1::bigint[]) AS c(company_id)
            ON CONFLICT (user_id, company_id) DO NOTHING
            `,
            [ids]
        );
        addedLinks = inserted.rowCount;

        // These companies also become part of the "default watchlist" every NEW
        // user is seeded with on signup (see userCompanyRepository.seedDefaultCompanies)
        // — so this action stays true for anyone who joins after it runs, not
        // just users who already existed at the time.
        await client.query(
            `UPDATE companies SET is_default_watchlist = TRUE WHERE id = ANY($1::bigint[])`,
            [ids]
        );

        await client.query("COMMIT");
    } catch (err) {
        await client.query("ROLLBACK");
        throw err;
    } finally {
        client.release();
    }

    const userCountResult = await db.query(`SELECT COUNT(*)::int AS count FROM users`);

    return {
        addedLinks,
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

    // Wrapped in a transaction for the same reason as addCompaniesToAllUsers:
    // this is a destructive, irreversible mass delete, so it must not commit
    // unless the accompanying default-watchlist flag update also succeeds.
    const client = await db.pool.connect();
    let removedLinks = 0;

    try {
        await client.query("BEGIN");

        const deleted = await client.query(
            `DELETE FROM user_companies WHERE company_id = ANY($1::bigint[])`,
            [ids]
        );
        removedLinks = deleted.rowCount;

        // Mirror of the flag set in addCompaniesToAllUsers — a company removed
        // from everyone should also stop being seeded into anyone who signs up
        // afterwards.
        await client.query(
            `UPDATE companies SET is_default_watchlist = FALSE WHERE id = ANY($1::bigint[])`,
            [ids]
        );

        await client.query("COMMIT");
    } catch (err) {
        await client.query("ROLLBACK");
        throw err;
    } finally {
        client.release();
    }

    const userCountResult = await db.query(`SELECT COUNT(*)::int AS count FROM users`);

    return {
        removedLinks,
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

/**
 * Number of WhatsApp template messages the bot has sent today, for the
 * "WhatsApp templates sent today" stat card. Fails soft — returns null if
 * the bot is unreachable/unconfigured, same convention as
 * fetchDeliveryStatusMap, so the rest of the stats keep working.
 */
async function fetchTemplatesSentToday() {
    const baseUrl = process.env.BOT_ADMIN_URL;
    const apiKey = process.env.BOT_ADMIN_KEY;

    if (!baseUrl || !apiKey) {
        return null;
    }

    try {
        const response = await axios.get(`${baseUrl}/admin/templates-sent-today`, {
            headers: { "x-bot-admin-key": apiKey },
            timeout: 5000,
        });
        return response.data.count;
    } catch (err) {
        console.error("Failed to fetch templates-sent-today from bot:", err.message);
        return null;
    }
}

/**
 * Today's OpenAI API spend (used for the AI summaries in filing alerts), for
 * the "OpenAI cost today" stat card. Fails soft — returns null if the bot is
 * unreachable/unconfigured or OPENAI_ADMIN_API_KEY isn't set on it, same
 * convention as fetchDeliveryStatusMap/fetchTemplatesSentToday.
 */
async function fetchOpenAiCostToday() {
    const baseUrl = process.env.BOT_ADMIN_URL;
    const apiKey = process.env.BOT_ADMIN_KEY;

    if (!baseUrl || !apiKey) {
        return null;
    }

    try {
        const response = await axios.get(`${baseUrl}/admin/openai-cost-today`, {
            headers: { "x-bot-admin-key": apiKey },
            timeout: 10000,
        });
        return { cost: response.data.costToday, currency: response.data.currency };
    } catch (err) {
        console.error("Failed to fetch OpenAI cost from bot:", err.message);
        return null;
    }
}

// ---------------------------------------------------------------------------
// Delivery-time helpers
//
// The two timestamps involved come from different systems with DIFFERENT
// timezone conventions, so they can only be compared after both are pinned
// to an absolute instant:
//   • sent_at         (bot SQLite, CURRENT_TIMESTAMP) — UTC
//   • announcement_time (scraper Postgres)            — naive wall clock that
//                                                       already means IST
// Subtracting them as-is would be 5h30m out. Everything below converts to
// epoch milliseconds first, then formats for display in IST.
// ---------------------------------------------------------------------------

const IST_OFFSET_MS = (5 * 60 + 30) * 60 * 1000;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-07-20 06:31:00" (UTC) -> Date, or null. */
function parseUtcStamp(value) {
    if (!value) return null;
    const iso = String(value).trim().replace(" ", "T");
    const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`);
    return Number.isNaN(d.getTime()) ? null : d;
}

/** "2026-07-20T12:00:00" (wall clock already meaning IST) -> Date, or null. */
function parseIstStamp(value) {
    if (!value) return null;
    const d = new Date(`${String(value).trim().replace(" ", "T")}+05:30`);
    return Number.isNaN(d.getTime()) ? null : d;
}

/** Render an absolute instant as IST, e.g. "20 Jul 2026, 12:01 PM". */
function formatIst(date) {
    if (!date) return null;
    // Shift then read with UTC getters, so the result never depends on the
    // server's own timezone.
    const t = new Date(date.getTime() + IST_OFFSET_MS);
    let hours = t.getUTCHours();
    const meridiem = hours >= 12 ? "PM" : "AM";
    hours = hours % 12 || 12;
    const mins = String(t.getUTCMinutes()).padStart(2, "0");
    return (
        `${t.getUTCDate()} ${MONTHS[t.getUTCMonth()]} ${t.getUTCFullYear()}, ` +
        `${hours}:${mins} ${meridiem}`
    );
}

/** Human-readable gap, e.g. "42 sec", "1 min", "2 hr 5 min". */
function formatDelay(ms) {
    if (ms === null || ms === undefined || Number.isNaN(ms)) return null;
    // A negative gap means the two clocks disagree (or the exchange time was
    // backdated) — report it rather than showing a misleading "0 sec".
    if (ms < 0) return "clock mismatch";

    const seconds = Math.round(ms / 1000);
    if (seconds < 60) return `${seconds} sec`;

    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} min`;

    const hours = Math.floor(minutes / 60);
    const restMin = minutes % 60;
    if (hours < 24) return restMin ? `${hours} hr ${restMin} min` : `${hours} hr`;

    const days = Math.floor(hours / 24);
    const restHr = hours % 24;
    return restHr ? `${days} d ${restHr} hr` : `${days} d`;
}

/**
 * Format one of the bot's UTC timestamps (e.g. the delivery snapshot's
 * lastDeliveredAt) as an IST display string. Exported so the controller can
 * format the directory's "Last alert" column without re-deriving the
 * timezone rules.
 */
function formatDeliveryStampIst(utcValue) {
    return formatIst(parseUtcStamp(utcValue));
}

/**
 * Every filing actually delivered to one user, most recent first, enriched
 * with the announcement's company/title from the scraper's database.
 *
 * Two data sources have to be stitched together in JS because they live in
 * different databases: the bot's SQLite records deliveries keyed by the
 * PDF's basename, while the company/title for that PDF is a row in
 * nse_ingestion.announcements. There's no SQL join across those, so this
 * fetches the delivery list, then resolves the basenames in one batched
 * query against announcements.local_path.
 *
 * Fails soft (returns []) when the bot is unreachable/unconfigured, matching
 * fetchDeliveryStatusMap — a user's profile must still open without it.
 */
async function fetchUserDeliveries(mobile, limit = 200) {
    const baseUrl = process.env.BOT_ADMIN_URL;
    const apiKey = process.env.BOT_ADMIN_KEY;

    if (!baseUrl || !apiKey) return [];

    let deliveries = [];
    try {
        const response = await axios.get(`${baseUrl}/admin/user-deliveries`, {
            headers: { "x-bot-admin-key": apiKey },
            params: { phone: normalizePhoneForBot(mobile), limit },
            timeout: 8000,
        });
        deliveries = response.data.deliveries || [];
    } catch (err) {
        console.error("Failed to fetch user deliveries from bot:", err.message);
        return [];
    }

    if (deliveries.length === 0) return [];

    // Resolve PDF basenames -> announcement metadata in ONE query rather than
    // per delivery. local_path is stored as a relative path
    // (e.g. "storage/pdf/TCS_2024-01-01.pdf"), so strip everything up to the
    // last slash/backslash to compare against the bot's file_key.
    const keys = deliveries.map((d) => d.filingKey).filter(Boolean);
    const metaByKey = new Map();

    try {
        const result = await ingestionDb.query(
            `
            SELECT
                regexp_replace(local_path, '^.*[/\\\\]', '') AS file_key,
                company_symbol,
                title,
                pdf_url,
                -- Returned as TEXT, not a timestamp: the column is
                -- "timestamp without time zone" holding a wall-clock time
                -- that already means IST (see db_watcher._format_exchange_time,
                -- which just appends " IST" to it). Letting node-postgres
                -- build a Date from it would silently reinterpret it in the
                -- container's timezone and throw the delay calculation off.
                to_char(announcement_time, 'YYYY-MM-DD"T"HH24:MI:SS') AS announcement_time_text
            FROM announcements
            WHERE regexp_replace(local_path, '^.*[/\\\\]', '') = ANY($1::text[])
            `,
            [keys]
        );
        result.rows.forEach((r) => metaByKey.set(r.file_key, r));
    } catch (err) {
        // Metadata is a nice-to-have; the delivery record itself is the point.
        console.error("Failed to resolve delivered filings to announcements:", err.message);
    }

    return deliveries.map((d) => {
        const m = metaByKey.get(d.filingKey);

        const deliveredAt = parseUtcStamp(d.sentAt);
        const filedAt = m ? parseIstStamp(m.announcement_time_text) : null;
        const delayMs = deliveredAt && filedAt ? deliveredAt.getTime() - filedAt.getTime() : null;

        return {
            filingKey: d.filingKey,
            symbol: m ? m.company_symbol : null,
            title: m ? m.title : null,
            pdfUrl: m ? m.pdf_url : null,
            // Display-ready IST strings + the gap between them, computed here
            // because only this layer knows each source's timezone convention.
            filedAtIst: formatIst(filedAt),
            deliveredAtIst: formatIst(deliveredAt),
            delayText: formatDelay(delayMs),
            delayMs,
        };
    });
}

/**
 * Runs a filing PDF through the bot's REAL summarization + WhatsApp
 * template-routing pipeline and returns exactly what subscribers would
 * receive — WITHOUT sending anything or touching bot_data.db / PostgreSQL.
 * See bot/preview.py's module docstring and Bot.py's /admin/preview-message
 * for the full trace of what it calls and why it's provably side-effect-free
 * on the WhatsApp/DB side (the only network calls are downloading this PDF
 * and the configured LLM provider, to produce the real summary).
 *
 * Unlike the stat-card fetchers above, this deliberately does NOT fail
 * soft — it's a user-initiated action (an admin clicked "Run test"), so a
 * failure (bot unreachable, PDF unreachable, LLM error) must surface as a
 * real error, not silently become "no data".
 */
async function previewWhatsAppMessage({ pdfUrl, company, symbol, filingType }) {
    const baseUrl = process.env.BOT_ADMIN_URL;
    const apiKey = process.env.BOT_ADMIN_KEY;

    if (!baseUrl || !apiKey) {
        const err = new Error(
            "BOT_ADMIN_URL/BOT_ADMIN_KEY are not configured on this backend, so it can't reach the bot's preview pipeline."
        );
        err.status = 500;
        throw err;
    }

    try {
        const response = await axios.post(
            `${baseUrl}/admin/preview-message`,
            { pdfUrl, company, symbol, filingType },
            {
                headers: { "x-bot-admin-key": apiKey },
                // The real pipeline downloads the PDF and calls the LLM
                // provider — can genuinely take 30-60s, far past this
                // file's other (fast, DB-only) admin calls.
                timeout: 90000,
            }
        );
        return response.data.report;
    } catch (err) {
        if (err.response) {
            const wrapped = new Error(
                (err.response.data && err.response.data.message) ||
                    `Bot responded with status ${err.response.status}`
            );
            wrapped.status = err.response.status;
            throw wrapped;
        }
        const wrapped = new Error(`Could not reach the bot for preview: ${err.code || err.message}`);
        wrapped.status = 502;
        throw wrapped;
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

// ---------------------------------------------------------------------------
// Scraped companies browser (backed by the SCRAPER's own database,
// nse_ingestion — separate from everything else in this file, which reads
// nse_subscription). Lets an admin see, per company the scraper tracks,
// every filing PDF it has picked up, without needing DB access.
// ---------------------------------------------------------------------------

/**
 * One row per company the scraper has ever filed an announcement for, with
 * a filing count and the most recent filing time. `search` matches the NSE/
 * BSE symbol (e.g. "TATAPOWER").
 */
async function listScrapedCompanies(search, page, pageSize) {
    const offset = (page - 1) * pageSize;
    const like = `%${search || ""}%`;

    const result = await ingestionDb.query(
        `
        SELECT
            company_symbol,
            COUNT(*)::int              AS filing_count,
            MAX(announcement_time)     AS latest_filing_at
        FROM announcements
        WHERE ($1 = '' OR company_symbol ILIKE $2)
        GROUP BY company_symbol
        ORDER BY latest_filing_at DESC NULLS LAST
        LIMIT $3 OFFSET $4
        `,
        [search || "", like, pageSize, offset]
    );

    const countResult = await ingestionDb.query(
        `
        SELECT COUNT(DISTINCT company_symbol)::int AS count
        FROM announcements
        WHERE ($1 = '' OR company_symbol ILIKE $2)
        `,
        [search || "", like]
    );

    const symbols = result.rows.map((r) => r.company_symbol);
    const nameMap = await getCompanyNamesBySymbols(symbols);

    return {
        rows: result.rows.map((r) => ({
            symbol: r.company_symbol,
            companyName: nameMap.get(r.company_symbol) || null,
            filingCount: r.filing_count,
            latestFilingAt: r.latest_filing_at,
        })),
        total: countResult.rows[0].count,
    };
}

/**
 * Looks up display names for a batch of symbols from the main
 * nse_subscription database's `companies` table. Done as a separate query
 * merged in JS (not a SQL JOIN) because announcements lives in a different
 * physical database (nse_ingestion) than companies (nse_subscription).
 */
async function getCompanyNamesBySymbols(symbols) {
    if (!symbols.length) return new Map();
    const result = await db.query(
        `SELECT symbol, company_name FROM companies WHERE symbol = ANY($1::text[])`,
        [symbols]
    );
    const map = new Map();
    result.rows.forEach((r) => map.set(r.symbol, r.company_name));
    return map;
}

/** Every filing the scraper has recorded for one company symbol, most recent first. */
async function getCompanyFilings(symbol) {
    const result = await ingestionDb.query(
        `
        SELECT id, title, pdf_url, local_path, announcement_time, download_status, created_at
        FROM announcements
        WHERE company_symbol = $1
        ORDER BY announcement_time DESC NULLS LAST, id DESC
        LIMIT 200
        `,
        [symbol]
    );
    return result.rows;
}

module.exports = {
    getStats,
    getSuccessfulPayments,
    searchUsers,
    findUserByMobile,
    createUser,
    getUserProfile,
    getUserSubscriptionHistory,
    getUserCompanies,
    getUserPayments,
    setUserCompanies,
    setUserShareLimitOverride,
    addCompaniesToAllUsers,
    removeCompaniesFromAllUsers,
    upsertUserSubscription,
    setPaymentRefundStatus,
    listPlans,
    updatePlanCompanyLimit,
    searchCompanies,
    listScrapedCompanies,
    getCompanyFilings,
    getActiveSubscribers,
    normalizePhoneForBot,
    fetchDeliveryStatusMap,
    fetchTemplatesSentToday,
    fetchOpenAiCostToday,
    fetchUserDeliveries,
    formatDeliveryStampIst,
    previewWhatsAppMessage,
};
