import React, { useState, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";
import useAuth from "../../hooks/useAuth";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import { MarketChartBackground } from "../../components/common/MarketChartBackground";

/**
 * High-fidelity, dual-step OTP Login Page for EquityAlerts.
 *
 * Flow (MSG91 widget with exposeMethods: true):
 *  Step 1 – MOBILE: user enters number → window.sendOtp() delivers SMS OTP
 *  Step 2 – OTP:    user enters code  → window.verifyOtp() validates it
 *                   on success the widget fires the main success callback
 *                   which resolves the promise in AuthContext → backend verifyToken
 */
export function Login() {
    const { login, verifyLogin, loginWithTestCredentials } = useAuth();
    const navigate = useNavigate();

    /** "MOBILE" | "OTP" */
    const [step, setStep] = useState("MOBILE");

    // ── TEMPORARY — Razorpay test-mode login (username/password) ──────────
    // Only shown/used for Razorpay's integration testing. Remove this whole
    // block (state + handler + the JSX toggle/form below) along with
    // AuthContext.loginWithTestCredentials and the backend /auth/login-test
    // route once Razorpay's testing is complete.
    const [showTestLogin, setShowTestLogin] = useState(false);
    const [testUsername, setTestUsername] = useState("");
    const [testPassword, setTestPassword] = useState("");
    const [testLoading, setTestLoading] = useState(false);
    const [testError, setTestError] = useState("");

    const handleTestLogin = async (e) => {
        e.preventDefault();
        setTestError("");
        try {
            setTestLoading(true);
            await loginWithTestCredentials(testUsername, testPassword);
            // No navigate() call needed — PublicRoute redirects automatically
            // once isAuthenticated flips true (see AppRoutes.jsx).
        } catch (err) {
            setTestError(
                err?.response?.data?.message ||
                err?.message ||
                "Invalid username or password."
            );
        } finally {
            setTestLoading(false);
        }
    };
    // ── end temporary block ────────────────────────────────────────────────

    const [countryCode, setCountryCode]     = useState("+91");
    const [mobile, setMobile]               = useState("");
    const [otp, setOtp]                     = useState("");
    const [loading, setLoading]             = useState(false);
    const [resending, setResending]         = useState(false);
    const [error, setError]                 = useState("");
    const [successMessage, setSuccessMessage] = useState("");

    // Holds the MSG91 access-token that the widget delivers once OTP is verified
    const accessTokenRef = useRef(null);

    const validateMobile = (num) => /^\d{7,15}$/.test(num);

    /**
     * Phase 1: Initialise the MSG91 widget → deliver OTP via SMS.
     * The widget's success callback (inside AuthContext.login) fires
     * only after the user has successfully verified the OTP.
     */
    const handleSendOtp = async (e) => {
        e.preventDefault();
        setError("");
        setSuccessMessage("");

        if (!mobile) {
            setError("Mobile number is required");
            return;
        }
        if (!validateMobile(mobile)) {
            setError("Please enter a valid mobile number (7-15 digits)");
            return;
        }

        try {
            setLoading(true);

            // AuthContext.login() initialises the MSG91 widget and returns a Promise
            // that resolves with the access-token once the user verifies the OTP.
            // We store the token in a ref; the page moves to the OTP step
            // so the user can type the SMS code and then click Verify.
            const tokenPromise = login(mobile);

            // Give the widget a moment to register the window methods
            // before transitioning to the OTP step.
            await new Promise((r) => setTimeout(r, 500));

            // Trigger OTP delivery via SMS (channel '11')
            if (typeof window.sendOtp === "function") {
                const pureCode = countryCode.replace(/\D/g, "");
                window.sendOtp(
                    `${pureCode}${mobile}`,
                    () => {},   // success handled by widget's main success callback
                    (err) => console.warn("sendOtp delivery warning:", err)
                );
            }

            setSuccessMessage("OTP sent to your mobile via SMS.");
            setStep("OTP");

            // When the user calls window.verifyOtp() below and it succeeds,
            // the widget resolves tokenPromise.
            tokenPromise.then((token) => {
                accessTokenRef.current = token;
            }).catch((err) => {
                // Stale widget failures (from re-initialization) are already
                // filtered out in AuthContext via the generation counter —
                // they never reach here. Only genuine failures arrive.
                console.error("Widget verification failed:", err);
                // Don't bounce back to MOBILE if the user already received
                // the OTP and is on the OTP step — let them retry verification.
                // Only show the error; the user can go back manually if needed.
                setError(err?.message || "OTP verification failed. Please try again.");
            });

        } catch (err) {
            setError(
                err?.message ||
                "Failed to initialise OTP verification. Please try again."
            );
        } finally {
            setLoading(false);
        }
    };

    /**
     * Phase 2: Call window.verifyOtp() with the code the user typed.
     * On success the widget fires the main success callback (resolving tokenPromise),
     * which sets accessTokenRef.current. We then exchange it for our session JWT.
     */
    const handleVerifyOtp = async (e) => {
        e.preventDefault();
        setError("");

        if (!otp || otp.length < 4) {
            setError("Please enter the 4-6 digit verification code");
            return;
        }

        if (typeof window.verifyOtp !== "function") {
            setError("Verification service unavailable. Please refresh the page.");
            return;
        }

        try {
            setLoading(true);

            // Wrap window.verifyOtp in a Promise
            await new Promise((resolve, reject) => {
                window.verifyOtp(
                    otp,
                    (data) => resolve(data),
                    (err)  => reject(
                        new Error(
                            (typeof err === "string" ? err : err?.message) ||
                            "Invalid OTP. Please try again."
                        )
                    )
                );
            });

            // Widget succeeded → accessTokenRef is populated by the tokenPromise callback.
            // If for some reason the ref hasn't been set yet, wait briefly.
            let attempts = 0;
            while (!accessTokenRef.current && attempts < 10) {
                await new Promise((r) => setTimeout(r, 100));
                attempts++;
            }

            if (!accessTokenRef.current) {
                throw new Error("Verification token not received. Please try again.");
            }

            const pureCode = countryCode.replace(/\D/g, "");
            await verifyLogin(`${pureCode}${mobile}`, accessTokenRef.current);

            // No navigate() call here on purpose: setting isAuthenticated
            // (inside verifyLogin) causes PublicRoute, which still wraps
            // this /login page, to re-render and redirect on its own —
            // to /whatsapp-welcome for brand-new accounts, or /dashboard
            // otherwise. Calling navigate() here too used to race with
            // that redirect and could send new users to the wrong screen.

        } catch (err) {
            setError(
                err?.response?.data?.message ||
                err?.message ||
                "Invalid code. Please check and try again."
            );
        } finally {
            setLoading(false);
        }
    };

    /** Resend OTP via SMS */
    const handleResend = async () => {
        if (typeof window.retryOtp !== "function") {
            setError("Retry service unavailable. Please go back and try again.");
            return;
        }
        try {
            setResending(true);
            setError("");
            await new Promise((resolve, reject) => {
                window.retryOtp(
                    "11",           // SMS channel
                    (data) => resolve(data),
                    (err)  => reject(err)
                );
            });
            setSuccessMessage("OTP resent via SMS.");
            setTimeout(() => setSuccessMessage(""), 4000);
        } catch (err) {
            setError("Failed to resend OTP. Please try again.");
        } finally {
            setResending(false);
        }
    };

    return (
        <div className="min-h-screen bg-[#0C0E14] flex items-center justify-center px-6 py-10 relative overflow-hidden font-sans justify-center">
            {/* Ambient Stock Market terminal graphics */}
            <MarketChartBackground />

            {/* Left Card: Secure Login Form */}
                <div className="w-full max-w-lg mx-auto bg-[#151921]/60 backdrop-blur-md rounded-3xl border border-[#222A38] p-6 sm:p-8 shadow-2xl flex flex-col justify-center">
                    {/* Brand Logo Header */}
                    <div className="flex flex-col items-center text-center">
                        <div className="w-16 h-16 bg-[#151921] border border-[#222A38] rounded-2xl flex items-center justify-center mb-6 shadow-lg glow-cyan">
                            <span className="font-extrabold text-2xl text-brand-cyan">EA</span>
                        </div>

                        <h1 className="text-3xl font-extrabold text-[#E3E5EA] tracking-tight">
                            Secure Login
                        </h1>

                        <p className="text-brand-slate text-sm mt-2 max-w-xs leading-relaxed">
                            Access premium corporate disclosures and watchlist alerts via SMS OTP.
                        </p>
                    </div>

                    {/* Main Auth Form Container */}
                    <div className="mt-8">
                        {step === "MOBILE" ? (
                            <form onSubmit={handleSendOtp} className="space-y-5">
                                <div className="flex flex-col gap-1.5">
                                    <label className="text-[13px] font-bold text-brand-slate uppercase tracking-wider pl-1">
                                        Mobile Number
                                    </label>
                                    <div className="flex gap-2">
                                        <div className="w-[85px] shrink-0">
                                            <Input
                                                value={countryCode}
                                                onChange={(e) => {
                                                    let val = e.target.value.replace(/[^\d+]/g, '');
                                                    if (val && !val.startsWith('+')) val = '+' + val;
                                                    setCountryCode(val);
                                                }}
                                                placeholder="+91"
                                                className="text-center px-1"
                                                maxLength="5"
                                            />
                                        </div>
                                        <div className="flex-1">
                                            <Input
                                                value={mobile}
                                                onChange={(e) => {
                                                    setMobile(e.target.value.replace(/\D/g, ""));
                                                    setError("");
                                                }}
                                                placeholder="Enter your mobile number"
                                                type="tel"
                                                maxLength="15"
                                                error={error}
                                                icon={
                                                    <svg className="w-5 h-5 text-brand-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                                                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.94.725l.548 2.2a1 1 0 01-.321.988l-1.305.98a10.582 10.582 0 004.872 4.872l.98-1.305a1 1 0 01.988-.321l2.2.548a1 1 0 01.725.94V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                                                    </svg>
                                                }
                                            />
                                        </div>
                                    </div>
                                </div>

                                <Button
                                    type="submit"
                                    loading={loading}
                                    disabled={loading}
                                    className="w-full"
                                >
                                    Send OTP via SMS
                                </Button>
                            </form>
                        ) : (
                            <form onSubmit={handleVerifyOtp} className="space-y-5">
                                {successMessage && (
                                    <div className="p-3 bg-brand-dark border border-brand-cyan text-brand-cyan rounded-xl text-xs font-semibold text-center">
                                        {successMessage}
                                    </div>
                                )}

                                <div className="space-y-1 text-center">
                                    <span className="text-xs text-brand-slate">
                                        Verifying connection for:
                                    </span>
                                    <span className="block text-sm font-bold text-brand-light font-mono">
                                        {countryCode} {mobile}
                                    </span>
                                </div>

                                <Input
                                    label="Verification Code (OTP)"
                                    value={otp}
                                    onChange={(e) => {
                                        setOtp(e.target.value.replace(/\D/g, ""));
                                        setError("");
                                    }}
                                    placeholder="Enter code"
                                    type="text"
                                    maxLength="6"
                                    error={error}
                                    icon={
                                        <svg className="w-5 h-5 text-brand-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                                        </svg>
                                    }
                                />

                                {/* Resend link */}
                                <div className="text-center">
                                    <button
                                        type="button"
                                        onClick={handleResend}
                                        disabled={resending}
                                        className="text-xs font-semibold text-brand-cyan hover:text-[#3BE6A7] disabled:opacity-50 transition-colors"
                                    >
                                        {resending ? "Resending..." : "Resend OTP via SMS"}
                                    </button>
                                </div>

                                <div className="flex gap-3">
                                    <Button
                                        variant="outline"
                                        type="button"
                                        onClick={() => {
                                            setStep("MOBILE");
                                            setError("");
                                            setOtp("");
                                            accessTokenRef.current = null;
                                        }}
                                        className="flex-1 !text-brand-light hover:!bg-brand-dark !border-brand-border"
                                    >
                                        Back
                                    </Button>
                                    <Button
                                        type="submit"
                                        loading={loading}
                                        disabled={loading}
                                        className="flex-1"
                                    >
                                        Verify OTP
                                    </Button>
                                </div>
                            </form>
                        )}

                        {/* Bottom registration link */}
                        <div className="mt-8 text-center text-xs text-brand-slate border-t border-brand-border/50 pt-5">
                            Don't have an account?{" "}
                            <Link
                                to="/register"
                                className="font-bold text-brand-cyan hover:underline transition-colors animate-pulse"
                            >
                                Register Here
                            </Link>
                        </div>

                        {/*
                            TEMPORARY — Razorpay test-mode login (username/password).
                            Only for Razorpay's integration testing; remove this whole
                            block once testing is complete (see AuthContext.jsx and
                            backend authController.js / authRoutes.js).
                        */}
                        <div className="mt-4 text-center">
                            <button
                                type="button"
                                onClick={() => {
                                    setShowTestLogin((v) => !v);
                                    setTestError("");
                                }}
                                className="text-[11px] text-brand-slate/70 hover:text-brand-slate underline"
                            >
                                {showTestLogin ? "Hide test login" : "Partner testing login"}
                            </button>

                            {showTestLogin && (
                                <form onSubmit={handleTestLogin} className="mt-4 space-y-3 text-left">
                                    <Input
                                        label="Username"
                                        value={testUsername}
                                        onChange={(e) => {
                                            setTestUsername(e.target.value);
                                            setTestError("");
                                        }}
                                        placeholder="Username"
                                        type="text"
                                        error={testError}
                                    />
                                    <Input
                                        label="Password"
                                        value={testPassword}
                                        onChange={(e) => {
                                            setTestPassword(e.target.value);
                                            setTestError("");
                                        }}
                                        placeholder="Password"
                                        type="password"
                                    />
                                    <Button
                                        type="submit"
                                        loading={testLoading}
                                        disabled={testLoading}
                                        className="w-full"
                                    >
                                        Test Login
                                    </Button>
                                </form>
                            )}
                        </div>
                        {/* ── end temporary block ── */}
                    </div>
                </div>
            </div>
        
    );
}export default Login;
