const userRepository =
    require(
        "../repositories/userRepository"
    );

const userCompanyRepository =
    require(
        "../repositories/userCompanyRepository"
    );

const jwtUtil =
    require(
        "../utils/jwt"
    );

const https = require("https");

/**
 * Normalize an Indian mobile number to its 10-digit form.
 * Accepts "9876543210", "+919876543210" or "919876543210".
 * Returns null when the input is not a valid mobile number.
 */
function normalizeMobile(
    input
) {

    if (
        typeof input !== "string" &&
        typeof input !== "number"
    ) {

        return null;

    }

    const digits =
        String(input).replace(/\D/g, "");

    if (
        digits.length === 10
    ) {

        return digits;

    }

    if (
        digits.length === 12 &&
        digits.startsWith("91")
    ) {

        return digits.slice(2);

    }

    return null;

}

/**
 * Verify the MSG91 widget access-token server-side.
 * @param {string} accessToken - JWT token returned by the MSG91 OTP widget
 * @returns {Promise<object>} Parsed MSG91 API response on success
 */
async function verifyMsg91AccessToken(accessToken) {

    const authkey = process.env.MSG91_AUTH_KEY;

    if (!authkey) {
        throw new Error("MSG91_AUTH_KEY not set in environment");
    }

    const body = JSON.stringify({
        authkey,
        "access-token": accessToken,
    });

    return new Promise((resolve, reject) => {

        const options = {
            hostname: "control.msg91.com",
            path: "/api/v5/widget/verifyAccessToken",
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Content-Length": Buffer.byteLength(body),
            },
        };

        const req = https.request(options, (res) => {
            let data = "";
            res.on("data", (chunk) => { data += chunk; });
            res.on("end", () => {
                try {
                    const parsed = JSON.parse(data);
                    if (
                        parsed.type === "error" ||
                        parsed.msgType === "error"
                    ) {
                        reject(
                            new Error(
                                parsed.message || "MSG91 token verification failed"
                            )
                        );
                    } else {
                        resolve(parsed);
                    }
                } catch (e) {
                    reject(new Error(`MSG91 parse error: ${data}`));
                }
            });
        });

        req.on("error", reject);
        req.write(body);
        req.end();

    });

}

/**
 * POST /api/auth/verify-token
 *
 * Receives the MSG91 widget access-token from the frontend,
 * validates it with MSG91, then upserts the user in the database
 * and issues an internal JWT session token.
 *
 * Body:
 *   - accessToken {string} - The JWT token returned by the MSG91 widget on success
 *   - mobile      {string} - 10-digit or 12-digit (with 91 prefix) mobile number
 *   - name        {string} - (optional) Full name, used during first-time registration
 */
async function verifyToken(
    req,
    res
) {

    try {

        const { accessToken, name: rawName } = req.body;

        const mobile =
            normalizeMobile(req.body.mobile);

        if (!accessToken) {
            return res
                .status(400)
                .json({
                    success: false,
                    message: "accessToken is required",
                });
        }

        if (!mobile) {
            return res
                .status(400)
                .json({
                    success: false,
                    message: "A valid 10-digit mobile number is required",
                });
        }

        // 1. Verify the token with MSG91 server-side
        try {
            await verifyMsg91AccessToken(accessToken);
        } catch (msg91Err) {
            console.error("❌ MSG91 token verification failed:", msg91Err.message);
            return res
                .status(401)
                .json({
                    success: false,
                    message: "OTP verification failed. Please try again.",
                });
        }

        // 2. Upsert user — find existing or create new
        let user =
            await userRepository.findByMobile(mobile);

        // QA/testing override: this specific number is always treated as a
        // first-time user so the WhatsApp onboarding screen can be re-tested
        // repeatedly without needing direct database access to delete the row.
        // It does NOT delete or reset the underlying account — the user's
        // real row, id, and session are untouched; only this response's
        // isNewUser flag is forced to true. Safe to remove once QA is done.
        const TEST_MOBILE_ALWAYS_NEW = "9767240651";

        // Track whether this person was already in our database *before*
        // this request. Used by the frontend to decide whether to show the
        // one-time "start getting Alerts on WhatsApp" screen. This is derived
        // purely in-memory from the lookup above — no schema change, and it
        // never affects existing users' data.
        const isNewUser = !user || mobile === TEST_MOBILE_ALWAYS_NEW;

        if (!user) {

            let name =
                typeof rawName === "string"
                    ? rawName.trim().slice(0, 100)
                    : null;

            if (name === "") name = null;

            user =
                await userRepository.create(
                    name,
                    mobile
                );

            // Give every brand-new user the same starter watchlist the admin
            // has broadcast to everyone via the dashboard (see
            // adminRepository.addCompaniesToAllUsers) — so they land on
            // their dashboard after login with those companies already
            // tracked, not an empty list.
            await userCompanyRepository.seedDefaultCompanies(
                user.id
            );

        }

        // 3. Issue internal session JWT
        const token =
            jwtUtil.generateToken(user);

        return res.json({
            success: true,
            message: "Verification successful",
            token,
            user,
            isNewUser,
        });

    } catch (err) {

        console.error(err);

        return res
            .status(500)
            .json({
                success: false,
                message: "Verification failed",
            });

    }

}

// ─────────────────────────────────────────────────────────────────────────
// TEMPORARY — Razorpay test-mode login (username/password)
//
// Razorpay asked for a way to log in without going through SMS OTP so they
// can run their integration testing. This is NOT meant to replace the
// mobile+OTP flow for real users — it only exists so Razorpay's tester can
// get in. Remove `loginWithTestCredentials`, its route in authRoutes.js,
// and the frontend hook for it once Razorpay's testing is complete.
//
// The credentials are read from env vars so they can be rotated/removed
// without a code change; the literal values below are just the agreed
// fallback so this works even if the env vars are not set.
// ─────────────────────────────────────────────────────────────────────────

const TEMP_TEST_USERNAME =
    process.env.TEMP_RAZORPAY_TEST_USERNAME || "testuser123razorpay";

const TEMP_TEST_PASSWORD =
    process.env.TEMP_RAZORPAY_TEST_PASSWORD || "razorpay@test123";

// Reserved, non-numeric identifier stored in the `mobile` column for this
// single test account. It can never collide with a real user's row because
// normalizeMobile() (used by the real OTP flow) only ever produces 10-digit
// numeric strings.
const TEMP_TEST_MOBILE = "TESTRZP0001";

/**
 * POST /api/auth/login-test
 *
 * TEMPORARY username/password login used only for Razorpay's integration
 * testing. On every successful call the reserved test account is wiped and
 * re-created from scratch, so the tester always lands on a clean, brand-new
 * account — same as any other first-time signup (isNewUser stays true, so
 * the frontend sends them through onboarding instead of straight to the
 * dashboard). It does not read, modify, or affect any real user who logs in
 * with their mobile number.
 *
 * Body:
 *   - username {string}
 *   - password {string}
 */
async function loginWithTestCredentials(
    req,
    res
) {

    try {

        const { username, password } = req.body || {};

        if (
            username !== TEMP_TEST_USERNAME ||
            password !== TEMP_TEST_PASSWORD
        ) {

            return res
                .status(401)
                .json({
                    success: false,
                    message: "Invalid username or password",
                });

        }

        // Always start this account fresh — delete any prior row first.
        await userRepository.deleteByMobile(TEMP_TEST_MOBILE);

        const user =
            await userRepository.create(
                "Razorpay Test User",
                TEMP_TEST_MOBILE
            );

        await userCompanyRepository.seedDefaultCompanies(
            user.id
        );

        const token =
            jwtUtil.generateToken(user);

        return res.json({
            success: true,
            message: "Verification successful",
            token,
            user,
            isNewUser: true,
        });

    } catch (err) {

        console.error(err);

        return res
            .status(500)
            .json({
                success: false,
                message: "Login failed",
            });

    }

}

module.exports = {

    verifyToken,

    loginWithTestCredentials,

};
