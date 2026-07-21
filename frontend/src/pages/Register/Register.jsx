import React, { useState, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";
import useAuth from "../../hooks/useAuth";
import Input from "../../components/ui/Input";
import Button from "../../components/ui/Button";
import { MarketChartBackground } from "../../components/common/MarketChartBackground";

/**
 * High-fidelity, dual-step registration page for EquityAlerts.
 *
 * Flow (MSG91 widget with exposeMethods: true):
 *  Step 1 – DETAILS: user enters name + number → window.sendOtp() delivers SMS OTP
 *  Step 2 – OTP:     user enters code → window.verifyOtp() validates it
 *                    on success the widget fires the main success callback
 *                    which resolves the promise in AuthContext → backend verifyToken
 */
export function Register() {
    const { register, verifyRegister } = useAuth();
    const navigate = useNavigate();

    /** "DETAILS" | "OTP" */
    const [step, setStep] = useState("DETAILS");

    const [name, setName]                   = useState("");
    const [countryCode, setCountryCode]     = useState("+91");
    const [mobile, setMobile]               = useState("");
    const [otp, setOtp]                     = useState("");
    const [loading, setLoading]             = useState(false);
    const [resending, setResending]         = useState(false);
    const [nameError, setNameError]         = useState("");
    const [mobileError, setMobileError]     = useState("");
    const [otpError, setOtpError]           = useState("");
    const [apiError, setApiError]           = useState("");
    const [successMessage, setSuccessMessage] = useState("");

    // Holds the MSG91 access-token resolved by the widget on OTP success
    const accessTokenRef = useRef(null);

    const validateMobile = (num) => /^\d{7,15}$/.test(num);

    /**
     * Phase 1: Validate inputs → initialise the MSG91 widget → deliver OTP via SMS.
     */
    const handleRegisterDetails = async (e) => {
        e.preventDefault();
        setNameError("");
        setMobileError("");
        setApiError("");

        let isValid = true;

        if (!name.trim()) {
            setNameError("Full name is required");
            isValid = false;
        }
        if (!mobile) {
            setMobileError("Mobile number is required");
            isValid = false;
        } else if (!validateMobile(mobile)) {
            setMobileError("Please enter a valid mobile number (7-15 digits)");
            isValid = false;
        }

        if (!isValid) return;

        try {
            setLoading(true);

            // AuthContext.register() initialises the MSG91 widget and returns a
            // Promise that resolves with the access-token once OTP is verified.
            const tokenPromise = register(name, mobile);

            // Give the widget a moment to register the window methods
            await new Promise((r) => setTimeout(r, 500));

            // Trigger OTP delivery via SMS
            if (typeof window.sendOtp === "function") {
                const pureCode = countryCode.replace(/\D/g, "");
                window.sendOtp(
                    `${pureCode}${mobile}`,
                    () => {},
                    (err) => console.warn("sendOtp delivery warning:", err)
                );
            }

            setSuccessMessage("OTP sent to your mobile via SMS.");
            setStep("OTP");

            // Capture the access-token when the widget resolves
            tokenPromise.then((token) => {
                accessTokenRef.current = token;
            }).catch((err) => {
                // Stale widget failures (from re-initialization) are already
                // filtered out in AuthContext via the generation counter —
                // they never reach here. Only genuine failures arrive.
                console.error("Widget verification failed:", err);
                // Don't bounce back to DETAILS if the user already received
                // the OTP and is on the OTP step — let them retry verification.
                // Only show the error; the user can go back manually if needed.
                setApiError(err?.message || "OTP verification failed. Please try again.");
            });

        } catch (err) {
            setApiError(
                err?.message ||
                "Registration failed. Please try again."
            );
        } finally {
            setLoading(false);
        }
    };

    /**
     * Phase 2: Call window.verifyOtp() with the code the user typed,
     * then exchange the widget's access-token for an internal session JWT.
     */
    const handleVerifyOtp = async (e) => {
        e.preventDefault();
        setOtpError("");
        setApiError("");

        if (!otp) {
            setOtpError("Verification code is required");
            return;
        }

        if (typeof window.verifyOtp !== "function") {
            setOtpError("Verification service unavailable. Please refresh the page.");
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

            // Wait briefly for the accessTokenRef to be set by the tokenPromise
            let attempts = 0;
            while (!accessTokenRef.current && attempts < 10) {
                await new Promise((r) => setTimeout(r, 100));
                attempts++;
            }

            if (!accessTokenRef.current) {
                throw new Error("Verification token not received. Please try again.");
            }

            const pureCode = countryCode.replace(/\D/g, "");
            await verifyRegister(name, `${pureCode}${mobile}`, accessTokenRef.current);

            // No navigate() call here on purpose: setting isAuthenticated
            // (inside verifyRegister) causes PublicRoute, which still wraps
            // this /register page, to re-render and redirect on its own —
            // to /whatsapp-welcome for brand-new accounts, or /dashboard
            // otherwise. Calling navigate() here too used to race with
            // that redirect and could send new users to the wrong screen.

        } catch (err) {
            setOtpError(
                err?.response?.data?.message ||
                err?.message ||
                "Verification failed. The code entered may be incorrect."
            );
        } finally {
            setLoading(false);
        }
    };

    /** Resend OTP via SMS */
    const handleResend = async () => {
        if (typeof window.retryOtp !== "function") {
            setOtpError("Retry service unavailable. Please go back and try again.");
            return;
        }
        try {
            setResending(true);
            setOtpError("");
            await new Promise((resolve, reject) => {
                window.retryOtp(
                    "11",          // SMS channel
                    (data) => resolve(data),
                    (err)  => reject(err)
                );
            });
            setSuccessMessage("OTP resent via SMS.");
            setTimeout(() => setSuccessMessage(""), 4000);
        } catch (err) {
            setOtpError("Failed to resend OTP. Please try again.");
        } finally {
            setResending(false);
        }
    };

    return (
        <div className="min-h-screen bg-[#0C0E14] flex items-center justify-center px-4 py-8 relative overflow-hidden font-sans">
            {/* Ambient Stock Market terminal graphics */}
            <MarketChartBackground />

        
            {/* Left Card: Secure Onboarding Form */}
                <div className="w-full max-w-lg mx-auto bg-[#151921]/60 backdrop-blur-md rounded-3xl border border-[#222A38] p-8 sm:p-10 shadow-2xl flex flex-col justify-center">
                    {/* Header */}
                    <div className="flex flex-col items-center text-center">
                        <div className="w-16 h-16 bg-[#151921] border border-[#222A38] rounded-2xl flex items-center justify-center mb-6 shadow-lg glow-cyan">
                            <span className="font-extrabold text-2xl text-brand-cyan">EA</span>
                        </div>

                        <h1 className="text-3xl font-extrabold text-[#E3E5EA] tracking-tight">
                            Create License
                        </h1>

                        <p className="text-brand-slate text-sm mt-2 max-w-xs leading-relaxed">
                            Register to unlock instant SMS alerts for NSE &amp; BSE disclosures.
                        </p>
                    </div>

                    {/* Form Wrapper */}
                    <div className="mt-8">
                        {apiError && (
                            <div className="p-3 bg-[#151921] border border-red-900 text-red-400 rounded-xl text-xs font-semibold text-center mb-5">
                                {apiError}
                            </div>
                        )}

                        {step === "DETAILS" ? (
                            <form onSubmit={handleRegisterDetails} className="space-y-4">
                                <Input
                                    label="Full Name"
                                    value={name}
                                    onChange={(e) => {
                                        setName(e.target.value);
                                        setNameError("");
                                    }}
                                    placeholder="Enter your full name"
                                    error={nameError}
                                    icon={
                                        <svg className="w-5 h-5 text-brand-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                                        </svg>
                                    }
                                />

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
                                                    setMobileError("");
                                                }}
                                                placeholder="Enter your mobile number"
                                                type="tel"
                                                maxLength="15"
                                                error={mobileError}
                                                icon={
                                                    <svg className="w-5 h-5 text-brand-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                                                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.94.725l.548 2.2a1 1 0 01-.321.988l-1.305.98a10.582 10.582 0 004.872 4.872l.98-1.305a1 1 0 01.988-.321l2.2.548a1 1 0 01.725.94V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                                                    </svg>
                                                }
                                            />
                                        </div>
                                    </div>
                                </div>

                                <div className="pt-2">
                                    <Button
                                        type="submit"
                                        loading={loading}
                                        disabled={loading}
                                        className="w-full"
                                    >
                                        Register Watchlist Terminal
                                    </Button>
                                </div>
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
                                        Verifying phone connection:
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
                                        setOtpError("");
                                    }}
                                    placeholder="Enter code"
                                    type="text"
                                    maxLength="6"
                                    error={otpError}
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
                                            setStep("DETAILS");
                                            setOtpError("");
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
                                        Verify Code
                                    </Button>
                                </div>
                            </form>
                        )}

                        {/* Bottom login link */}
                        <div className="mt-8 text-center text-xs text-brand-slate border-t border-brand-border/50 pt-5">
                            Already have a terminal license?{" "}
                            <Link
                                to="/login"
                                className="font-bold text-brand-cyan hover:underline transition-colors"
                            >
                                Sign In Here
                            </Link>
                        </div>
                    </div>
                </div>
        </div>
        
    );
}

export default Register;
