const repo = require("./adminRepository");
const userCompanyRepository = require("../repositories/userCompanyRepository");

const PRODUCT_KEY = "nse-subscription";
const PRODUCT_NAME = "NSE Bulk / Block Deal Alerts";

/**
 * Normalizes an Indian mobile number to its 10-digit form, same rule the
 * real OTP signup flow uses (see authController.js) — kept as its own copy
 * here since that one isn't exported, and this module has no other reason
 * to depend on the auth controller.
 */
function normalizeMobile(input) {
    if (typeof input !== "string" && typeof input !== "number") return null;
    const digits = String(input).replace(/\D/g, "");
    if (digits.length === 10) return digits;
    if (digits.length === 12 && digits.startsWith("91")) return digits.slice(2);
    return null;
}

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
        panelModules: ["stats", "user-directory", "company-directory"],
        capabilities: ["stats", "users", "actions", "options", "bulk-actions", "companies"],
        // Product-level actions that don't target a single user. The dashboard
        // renders these as a "Bulk actions" panel (see ARCHITECTURE.md) and
        // POSTs them to /bulk-actions/:actionKey. Same field-spec format as the
        // per-user `actions` below, so the dashboard reuses the same form
        // renderer for both.
        bulkActions: {
            "add-companies-to-all": {
                label: "Add shares to every user's watchlist",
                description:
                    "Adds the selected share(s) to every registered user at once. " +
                    "Existing subscriptions are kept; anyone already tracking a share is skipped.",
                submitLabel: "Add to all users",
                fields: [
                    {
                        name: "companyIds",
                        type: "multiselect",
                        label: "Shares to add",
                        optionsKey: "companies",
                    },
                ],
            },
            "remove-companies-from-all": {
                label: "Remove shares from every user's watchlist",
                description:
                    "Removes the selected share(s) from every user who is tracking them. " +
                    "Users who don't track a share are left unaffected. This cannot be undone.",
                submitLabel: "Remove from all users",
                fields: [
                    {
                        name: "companyIds",
                        type: "multiselect",
                        label: "Shares to remove",
                        optionsKey: "companies",
                    },
                ],
            },
            "update-plan-limit": {
                label: "Change a plan's share limit",
                description:
                    "Changes how many shares a plan allows (e.g. Premium 25 → 30). " +
                    "Applies immediately to every current and future subscriber on that plan.",
                submitLabel: "Update limit",
                fields: [
                    { name: "planId", type: "select", label: "Plan", optionsKey: "plans" },
                    { name: "companyLimit", type: "number", label: "New share limit" },
                ],
            },
            "create-user": {
                label: "Add a new user",
                description:
                    "Creates a new user directly, without them needing to sign up themselves " +
                    "(e.g. for an offline/manual sale). Search for them in the directory " +
                    "afterwards to set up their subscription and tracked shares.",
                submitLabel: "Create user",
                fields: [
                    { name: "name", type: "text", label: "Name (optional)" },
                    { name: "mobile", type: "text", label: "Mobile number (10 digits)" },
                ],
            },
        },
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
            "update-share-limit": {
                label: "Change this user's share limit",
                description:
                    "Overrides this user's share limit independent of their plan's default " +
                    "(e.g. bump just this one Premium user from 25 to 30). Clear the field to " +
                    "fall back to the plan's default limit again.",
                fields: [{ name: "shareLimit", type: "number", label: "Share limit" }],
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
        const { receiving, notReceiving } = await getPdfDeliveryCounts();
        const templatesSentToday = await repo.fetchTemplatesSentToday();
        const openAiCost = await repo.fetchOpenAiCostToday();

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
                {
                    key: "users_receiving_pdfs",
                    label: "Users receiving PDFs",
                    value: receiving,
                    format: "number",
                },
                {
                    key: "users_not_receiving_pdfs",
                    label: "Users not receiving PDFs",
                    value: notReceiving,
                    format: "number",
                    // Drill-down into exactly who, via GET /stats/pdf-issues/detail below.
                    detailKey: "pdf-issues",
                },
                {
                    key: "templates_sent_today",
                    label: "WhatsApp templates sent today",
                    // null (bot unreachable/unconfigured) reports as 0, same
                    // fail-soft convention as the PDF-delivery stats above.
                    value: templatesSentToday !== null && templatesSentToday !== undefined ? templatesSentToday : 0,
                    format: "number",
                },
                {
                    key: "openai_cost_today",
                    label: `OpenAI cost today (${((openAiCost && openAiCost.currency) || "usd").toUpperCase()})`,
                    // Left as null (not defaulted to 0) when unreachable/not
                    // configured — the dashboard renders that as "—", which is
                    // more honest than implying zero spend.
                    value: openAiCost ? openAiCost.cost : null,
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
// PDF delivery status helpers
//
// A user with an ACTIVE subscription is "not receiving" if they currently
// have one or more filings stuck in the bot's own pending_filings retry
// queue — that's the delivery pipeline's own ground-truth signal for a
// failed/blocked send, reused as-is rather than inventing a new heuristic.
// ---------------------------------------------------------------------------

async function getPdfDeliveryStatusForActiveSubscribers() {
    const activeSubscribers = await repo.getActiveSubscribers();
    const deliveryMap = await repo.fetchDeliveryStatusMap();

    return activeSubscribers.map((u) => ({
        user: u,
        status: deliveryMap.get(repo.normalizePhoneForBot(u.mobile)) || null,
    }));
}

async function getPdfDeliveryCounts() {
    const entries = await getPdfDeliveryStatusForActiveSubscribers();
    const notReceiving = entries.filter(
        ({ status }) => status && status.pendingCount > 0
    ).length;
    return { receiving: entries.length - notReceiving, notReceiving };
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

        if (key === "pdf-issues") {
            const entries = await getPdfDeliveryStatusForActiveSubscribers();
            const affected = entries.filter(
                ({ status }) => status && status.pendingCount > 0
            );

            return res.json({
                success: true,
                title: "Users not receiving PDFs",
                description:
                    "Active subscribers with one or more filings currently stuck in the WhatsApp delivery retry queue.",
                columns: ["Phone", "Name", "Pending filings", "Last error", "Last delivered"],
                rows: affected.map(({ user, status }) => [
                    user.mobile,
                    user.name || "(no name on file)",
                    status.pendingCount,
                    status.lastError || "—",
                    status.lastDeliveredAt || "Never",
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
        // Only active subscribers can meaningfully be "not receiving" PDFs, so
        // the delivery map only needs to be checked for those rows below.
        const deliveryMap = await repo.fetchDeliveryStatusMap();

        res.json({
            success: true,
            total,
            page,
            pageSize,
            users: rows.map((u) => {
                const tags = [u.plan_name, u.sub_status].filter(Boolean);
                if (u.sub_status === "ACTIVE") {
                    const status = deliveryMap.get(repo.normalizePhoneForBot(u.mobile));
                    if (status && status.pendingCount > 0) tags.push("PDF ISSUE");
                }
                return {
                    id: String(u.id),
                    primary: u.mobile,
                    secondary: u.name || "(no name on file)",
                    tags,
                    // Total shares/companies this user tracks, shown as its
                    // own directory column so an admin can see it without
                    // opening the user (e.g. "60").
                    companiesCount: Number(u.companies_count),
                    // Extra directory columns the dashboard's table already
                    // renders (Plan / Plan status / Plan end date / Joined
                    // on) — the query already selects all of this, it just
                    // wasn't being mapped into the response before, so those
                    // columns always rendered blank.
                    planName: u.plan_name || null,
                    subStatus: u.sub_status || null,
                    planEndDate: u.sub_end_date || null,
                    joinedOn: u.created_at,
                };
            }),
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
        // A per-user override (see repo.setUserShareLimitOverride) takes
        // priority over the plan's own default when present.
        const effectiveLimit = activeSub
            ? activeSub.company_limit_override ?? activeSub.company_limit
            : null;

        const sections = [
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
                      }
                    : { Status: "No subscription yet" },
            },
            {
                key: "share_limit",
                title: "Share limit",
                type: "keyvalue",
                editable: true,
                actionKey: "update-share-limit",
                data: activeSub
                    ? {
                          "Share limit": effectiveLimit,
                          "Plan default": activeSub.company_limit,
                      }
                    : { Status: "No active subscription" },
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
                    limit: effectiveLimit,
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
        ];

        // Only meaningful for someone who has (or had) a subscription — a
        // brand-new user with no subscription history was never eligible to
        // receive anything, so skip the section entirely for them.
        if (subs.length > 0) {
            const deliveryMap = await repo.fetchDeliveryStatusMap();
            const status = deliveryMap.get(repo.normalizePhoneForBot(profile.mobile)) || null;
            const pendingCount = status ? status.pendingCount : 0;

            sections.push({
                key: "pdf_delivery",
                title: "PDF delivery",
                type: "keyvalue",
                data: {
                    Status: pendingCount > 0 ? "Not receiving" : "Receiving",
                    "Pending filings": pendingCount,
                    "Last error": (status && status.lastError) || "—",
                    "Last delivered": (status && status.lastDeliveredAt) || "Never",
                    "WhatsApp window": status && status.windowOpen ? "Open" : "Closed",
                },
            });
        }

        res.json({
            success: true,
            id: String(profile.id),
            primary: profile.mobile,
            secondary: profile.name || "(no name on file)",
            sections,
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
                    ? `This exceeds the user's share limit of ${result.limit}.`
                    : null,
            });
        }

        if (actionKey === "update-share-limit") {
            const raw = req.body.shareLimit;
            let overrideValue = null;

            if (raw !== "" && raw !== null && raw !== undefined) {
                const parsed = Number(raw);
                if (!Number.isFinite(parsed) || parsed < 0) {
                    return res.status(400).json({
                        success: false,
                        message: "Share limit must be a non-negative number.",
                    });
                }
                overrideValue = parsed;
            }

            const result = await repo.setUserShareLimitOverride(userId, overrideValue);
            if (!result) {
                return res.status(400).json({
                    success: false,
                    message: "This user has no active subscription to set a share limit on.",
                });
            }

            return res.json({
                success: true,
                message:
                    overrideValue === null
                        ? `Share limit reverted to the ${result.planName} plan default (${result.effectiveLimit}).`
                        : `Share limit for this user set to ${overrideValue}.`,
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
// POST /api/admin/v1/bulk-actions/:actionKey
//
// Product-level actions that apply across many users at once, rather than to
// one user. Declared under `bulkActions` in /meta.
// ---------------------------------------------------------------------------
async function runBulkAction(req, res) {
    const actionKey = req.params.actionKey;

    try {
        if (actionKey === "add-companies-to-all") {
            const companyIds = Array.isArray(req.body.companyIds)
                ? req.body.companyIds.map(Number)
                : [];

            if (companyIds.length === 0) {
                return res
                    .status(400)
                    .json({ success: false, message: "Select at least one share to add." });
            }

            const result = await repo.addCompaniesToAllUsers(companyIds);

            const shareWord = companyIds.length === 1 ? "share" : "shares";
            return res.json({
                success: true,
                message:
                    `Added ${companyIds.length} ${shareWord} across ${result.userCount} user(s) ` +
                    `(${result.addedLinks} new subscription(s); already-tracked ones were skipped).`,
            });
        }

        if (actionKey === "remove-companies-from-all") {
            const companyIds = Array.isArray(req.body.companyIds)
                ? req.body.companyIds.map(Number)
                : [];

            if (companyIds.length === 0) {
                return res
                    .status(400)
                    .json({ success: false, message: "Select at least one share to remove." });
            }

            const result = await repo.removeCompaniesFromAllUsers(companyIds);

            const shareWord = companyIds.length === 1 ? "share" : "shares";
            return res.json({
                success: true,
                message:
                    `Removed ${companyIds.length} ${shareWord} from every user's watchlist ` +
                    `(${result.removedLinks} subscription(s) removed).`,
            });
        }

        if (actionKey === "update-plan-limit") {
            const { planId, companyLimit } = req.body;
            const limit = Number(companyLimit);

            if (!planId || !Number.isFinite(limit) || limit < 0) {
                return res.status(400).json({
                    success: false,
                    message: "planId and a non-negative companyLimit are required",
                });
            }

            const plan = await repo.updatePlanCompanyLimit(Number(planId), limit);
            if (!plan) {
                return res.status(404).json({ success: false, message: "Plan not found" });
            }

            return res.json({
                success: true,
                message: `${plan.name} plan's share limit is now ${plan.company_limit}.`,
            });
        }

        if (actionKey === "create-user") {
            const mobile = normalizeMobile(req.body.mobile);
            if (!mobile) {
                return res.status(400).json({
                    success: false,
                    message: "A valid 10-digit mobile number is required.",
                });
            }

            const rawName = req.body.name;
            const name = typeof rawName === "string" && rawName.trim() ? rawName.trim().slice(0, 100) : null;

            const existing = await repo.findUserByMobile(mobile);
            if (existing) {
                return res.status(400).json({
                    success: false,
                    message: `A user with mobile ${mobile} already exists — search for them in the directory instead.`,
                });
            }

            const user = await repo.createUser(name, mobile);
            // Same starter watchlist a real signup gets — see
            // authController.verifyToken and migration 002.
            await userCompanyRepository.seedDefaultCompanies(user.id);

            return res.json({
                success: true,
                message:
                    `Created user "${user.name || mobile}" (${user.mobile}). ` +
                    `Search for them in the directory to set up their subscription and shares.`,
            });
        }

        return res.status(400).json({ success: false, message: `Unknown bulk action: ${actionKey}` });
    } catch (err) {
        console.error(err);
        res.status(500).json({ success: false, message: "Bulk action failed" });
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

// ---------------------------------------------------------------------------
// GET /api/admin/v1/companies?search=&page=&pageSize=
//
// Scraped-companies browser, backed by the scraper's own database
// (nse_ingestion — see adminRepository's listScrapedCompanies). Shaped the
// same as GET /users (primary/secondary/tags) so the dashboard can reuse its
// existing directory-table renderer for this too.
// ---------------------------------------------------------------------------
async function listCompanies(req, res) {
    try {
        const search = String(req.query.search || "").trim();
        const page = Math.max(1, Number(req.query.page) || 1);
        const pageSize = Math.min(100, Math.max(1, Number(req.query.pageSize) || 20));

        const { rows, total } = await repo.listScrapedCompanies(search, page, pageSize);

        res.json({
            success: true,
            total,
            page,
            pageSize,
            companies: rows.map((c) => ({
                id: c.symbol,
                primary: c.symbol,
                secondary: c.companyName || "(name not on file)",
                tags: [],
                filingCount: c.filingCount,
                latestFilingAt: c.latestFilingAt,
            })),
        });
    } catch (err) {
        console.error(err);
        res.status(500).json({ success: false, message: "Failed to load scraped companies" });
    }
}

// ---------------------------------------------------------------------------
// GET /api/admin/v1/companies/:symbol
//
// Every filing the scraper has picked up for one company — shaped as a
// single generic "table" section, same contract as a user's payment-history
// section, so the dashboard renders it with no new component.
// ---------------------------------------------------------------------------
async function getCompanyDetail(req, res) {
    try {
        const symbol = req.params.symbol;
        const filings = await repo.getCompanyFilings(symbol);

        res.json({
            success: true,
            symbol,
            filingCount: filings.length,
            sections: [
                {
                    key: "filings",
                    title: `Scraped filings — ${symbol}`,
                    type: "table",
                    data: {
                        columns: ["Filed on", "Title", "Status", "PDF"],
                        rows: filings.map((f) => [
                            f.announcement_time,
                            f.title || "(untitled)",
                            f.download_status,
                            f.pdf_url,
                        ]),
                    },
                },
            ],
        });
    } catch (err) {
        console.error(err);
        res.status(500).json({ success: false, message: "Failed to load company filings" });
    }
}

module.exports = {
    meta,
    stats,
    statDetail,
    listUsers,
    getUser,
    runAction,
    runBulkAction,
    getOptions,
    listCompanies,
    getCompanyDetail,
};
