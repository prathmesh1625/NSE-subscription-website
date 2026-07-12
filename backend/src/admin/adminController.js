const repo = require("./adminRepository");

const PRODUCT_KEY = "nse-subscription";
const PRODUCT_NAME = "NSE Bulk / Block Deal Alerts";

// ---------------------------------------------------------------------------
// GET /api/admin/v1/meta
// ---------------------------------------------------------------------------
function meta(req, res) {
    res.json({
        success: true,
        productKey: PRODUCT_KEY,
        productName: PRODUCT_NAME,
        version: "1.0",
        // Declares which panel modules the dashboard should render for this
        // product, and in what order. The dashboard has a renderer for each
        // known module type; a future product can declare an entirely
        // different set of modules and get a completely different-looking
        // panel without any change to this product or to the dashboard's
        // core code — only a new renderer needs to be added for a genuinely
        // new module type.
        panelModules: ["stats", "user-directory"],
        capabilities: ["stats", "users", "actions", "options"],
        actions: {
            "update-companies": {
                label: "Edit subscribed shares",
                fields: [
                    {
                        name: "companyIds",
                        type: "multiselect",
                        label: "Companies (shares) tracked",
                        optionsKey: "companies",
                    },
                ],
            },
            "update-subscription": {
                label: "Edit subscription",
                fields: [
                    { name: "planId", type: "select", label: "Plan", optionsKey: "plans" },
                    {
                        name: "status",
                        type: "select",
                        label: "Status",
                        options: ["ACTIVE", "INACTIVE"],
                    },
                    { name: "startDate", type: "date", label: "Start date" },
                    { name: "endDate", type: "date", label: "End date" },
                ],
            },
            "mark-refund": {
                label: "Update refund status",
                fields: [
                    {
                        name: "refundStatus",
                        type: "select",
                        label: "Refund status",
                        options: ["NONE", "PENDING", "REFUNDED"],
                    },
                    { name: "refundAmount", type: "number", label: "Refund amount (₹)" },
                    { name: "notes", type: "text", label: "Notes" },
                ],
            },
        },
    });
}

// ---------------------------------------------------------------------------
// GET /api/admin/v1/stats
// ---------------------------------------------------------------------------
async function stats(req, res) {
    try {
        const row = await repo.getStats();

        res.json({
            success: true,
            stats: [
                {
                    key: "total_received",
                    label: "Total amount received",
                    value: Number(row.total_received),
                    format: "currency",
                    // Lets the dashboard render this card as clickable and,
                    // on click, fetch GET /stats/payments/detail (below) to
                    // show exactly which payments make up this total.
                    detailKey: "payments",
                },
                {
                    key: "total_refund_pending",
                    label: "Pending refunds",
                    value: Number(row.total_refund_pending),
                    format: "currency",
                },
                {
                    key: "total_refunded",
                    label: "Total refunded",
                    value: Number(row.total_refunded),
                    format: "currency",
                },
                {
                    key: "active_subscriptions",
                    label: "Active subscriptions",
                    value: Number(row.active_subscriptions),
                    format: "number",
                },
                {
                    key: "active_premium",
                    label: "Active premium users",
                    value: Number(row.active_premium),
                    format: "number",
                },
                {
                    key: "total_users",
                    label: "Total registered users",
                    value: Number(row.total_users),
                    format: "number",
                },
            ],
        });
    } catch (err) {
        console.error(err);
        res.status(500).json({ success: false, message: "Failed to load stats" });
    }
}

// ---------------------------------------------------------------------------
// GET /api/admin/v1/stats/:key/detail
//
// Drill-down for a stat card that declared a `detailKey` in /stats above.
// Returns a simple table (columns/rows) the dashboard renders generically —
// same shape as a "table" detail section, just not tied to one user.
// ---------------------------------------------------------------------------
async function statDetail(req, res) {
    try {
        const key = req.params.key;

        if (key === "payments") {
            const payments = await repo.getSuccessfulPayments();

            return res.json({
                success: true,
                title: "Payments received",
                // total_received is SUM(amount) over every payment with
                // status = 'SUCCESS' (see adminRepository.getStats) — this
                // is that same set of rows, so the numbers always agree.
                description:
                    "Every successful payment (status = SUCCESS) sums to the \u201cTotal amount received\u201d figure.",
                columns: ["Date", "User", "Phone", "Amount", "Razorpay payment ID"],
                rows: payments.map((p) => [
                    p.created_at,
                    p.name || "(no name on file)",
                    p.mobile,
                    Number(p.amount),
                    p.razorpay_payment_id || "—",
                ]),
            });
        }

        return res.status(400).json({ success: false, message: `Unknown stat detail key: ${key}` });
    } catch (err) {
        console.error(err);
        res.status(500).json({ success: false, message: "Failed to load stat detail" });
    }
}

// ---------------------------------------------------------------------------
// GET /api/admin/v1/users?search=&page=&pageSize=
// ---------------------------------------------------------------------------
async function listUsers(req, res) {
    try {
        const search = String(req.query.search || "").trim();
        const page = Math.max(1, Number(req.query.page) || 1);
        const pageSize = Math.min(100, Math.max(1, Number(req.query.pageSize) || 20));

        const { rows, total } = await repo.searchUsers(search, page, pageSize);

        res.json({
            success: true,
            total,
            page,
            pageSize,
            users: rows.map((u) => ({
                id: String(u.id),
                primary: u.mobile,
                secondary: u.name || "(no name on file)",
                tags: [u.plan_name, u.sub_status].filter(Boolean),
            })),
        });
    } catch (err) {
        console.error(err);
        res.status(500).json({ success: false, message: "Failed to search users" });
    }
}

// ---------------------------------------------------------------------------
// GET /api/admin/v1/users/:id
// ---------------------------------------------------------------------------
async function getUser(req, res) {
    try {
        const userId = req.params.id;

        const profile = await repo.getUserProfile(userId);
        if (!profile) {
            return res.status(404).json({ success: false, message: "User not found" });
        }

        const subs = await repo.getUserSubscriptionHistory(userId);
        const companies = await repo.getUserCompanies(userId);
        const payments = await repo.getUserPayments(userId);

        const activeSub = subs.find((s) => s.status === "ACTIVE");

        res.json({
            success: true,
            id: String(profile.id),
            primary: profile.mobile,
            secondary: profile.name || "(no name on file)",
            sections: [
                {
                    key: "profile",
                    title: "Profile",
                    type: "keyvalue",
                    data: {
                        Name: profile.name || "—",
                        Mobile: profile.mobile,
                        "Joined on": profile.created_at,
                    },
                },
                {
                    key: "subscription",
                    title: "Current subscription",
                    type: "keyvalue",
                    editable: true,
                    actionKey: "update-subscription",
                    actionParams: {
                        currentPlanId: activeSub ? activeSub.plan_id : null,
                    },
                    data: activeSub
                        ? {
                              Plan: activeSub.plan_name,
                              Status: activeSub.status,
                              "Start date": activeSub.start_date,
                              "End date": activeSub.end_date,
                              "Share limit": activeSub.company_limit,
                          }
                        : { Status: "No subscription yet" },
                },
                {
                    key: "companies",
                    title: "Subscribed shares",
                    type: "editable-list",
                    actionKey: "update-companies",
                    data: {
                        items: companies.map((c) => ({
                            id: c.id,
                            label: `${c.company_name} (${c.symbol})`,
                        })),
                        limit: activeSub ? activeSub.company_limit : null,
                    },
                },
                {
                    key: "payments",
                    title: "Payment history",
                    type: "table",
                    data: {
                        columns: ["Date", "Amount", "Status", "Refund status", "Refund amount", "Notes"],
                        rows: payments.map((p) => [
                            p.created_at,
                            Number(p.amount),
                            p.status,
                            p.refund_status,
                            p.refund_amount !== null ? Number(p.refund_amount) : null,
                            p.refund_notes || "",
                        ]),
                        rowActions: payments.map((p, idx) => ({
                            rowIndex: idx,
                            actionKey: "mark-refund",
                            actionParams: { paymentId: p.id },
                            enabled: p.status === "SUCCESS",
                        })),
                    },
                },
            ],
        });
    } catch (err) {
        console.error(err);
        res.status(500).json({ success: false, message: "Failed to load user detail" });
    }
}

// ---------------------------------------------------------------------------
// POST /api/admin/v1/users/:id/actions/:actionKey
// ---------------------------------------------------------------------------
async function runAction(req, res) {
    const userId = req.params.id;
    const actionKey = req.params.actionKey;
    const actorUsername = req.headers["x-central-actor"] || null;

    try {
        if (actionKey === "update-companies") {
            const companyIds = Array.isArray(req.body.companyIds)
                ? req.body.companyIds.map(Number)
                : [];

            const result = await repo.setUserCompanies(userId, companyIds);

            return res.json({
                success: true,
                message: `Updated to ${result.count} share(s).`,
                warning: result.exceedsLimit
                    ? `This exceeds the user's plan limit of ${result.limit}.`
                    : null,
            });
        }

        if (actionKey === "update-subscription") {
            const { planId, status, startDate, endDate } = req.body;

            if (!planId || !status) {
                return res
                    .status(400)
                    .json({ success: false, message: "planId and status are required" });
            }

            await repo.upsertUserSubscription(userId, {
                planId: Number(planId),
                status,
                startDate: startDate || null,
                endDate: endDate || null,
            });

            return res.json({ success: true, message: "Subscription updated." });
        }

        if (actionKey === "mark-refund") {
            const { paymentId, refundStatus, refundAmount, notes } = req.body;

            if (!paymentId || !refundStatus) {
                return res.status(400).json({
                    success: false,
                    message: "paymentId and refundStatus are required",
                });
            }

            await repo.setPaymentRefundStatus(paymentId, {
                refundStatus,
                refundAmount: refundAmount === undefined || refundAmount === "" ? null : Number(refundAmount),
                notes,
                actorUsername,
            });

            return res.json({ success: true, message: "Refund status updated." });
        }

        return res.status(400).json({ success: false, message: `Unknown action: ${actionKey}` });
    } catch (err) {
        console.error(err);
        res.status(500).json({ success: false, message: "Action failed" });
    }
}

// ---------------------------------------------------------------------------
// GET /api/admin/v1/options/:key
// ---------------------------------------------------------------------------
async function getOptions(req, res) {
    try {
        const key = req.params.key;
        const search = String(req.query.search || "");
        // Comma-separated ids the dashboard already has selected for this
        // field (e.g. a user's currently subscribed companyIds). Passed so
        // we can guarantee those specific rows come back even though the
        // general result set below is capped.
        const selected = String(req.query.selected || "")
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean);

        if (key === "plans") {
            const plans = await repo.listPlans();
            return res.json({
                success: true,
                options: plans.map((p) => ({
                    value: String(p.id),
                    label: `${p.name} — ₹${p.price} (${p.company_limit} shares, ${p.duration_days}d)`,
                })),
            });
        }

        if (key === "companies") {
            const companies = await repo.searchCompanies(search, selected);
            return res.json({
                success: true,
                options: companies.map((c) => ({
                    value: String(c.id),
                    label: `${c.company_name} (${c.symbol})`,
                })),
            });
        }

        return res.status(400).json({ success: false, message: `Unknown options key: ${key}` });
    } catch (err) {
        console.error(err);
        res.status(500).json({ success: false, message: "Failed to load options" });
    }
}

module.exports = {
    meta,
    stats,
    statDetail,
    listUsers,
    getUser,
    runAction,
    getOptions,
};
