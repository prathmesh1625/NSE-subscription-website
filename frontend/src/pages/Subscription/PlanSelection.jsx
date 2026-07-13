import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import useApp from "../../hooks/useApp";
import Button from "../../components/ui/Button";
import { createOrder, verifyPayment } from "../../api/payment.api";

/**
 * Plan Selection Page — two pricing cards.
 * PREMIUM can be unlocked either by paying via Razorpay, or by entering a
 * 100%-off coupon code (validated server-side).
 */
export function PlanSelection() {
    const {
        plans,
        currentSubscription,
        handleActivateFree,
        handleActivatePremium,
        loadAppData,
        loading
    } = useApp();

    const navigate = useNavigate();
    const [actionLoading, setActionLoading] = useState(null); // plan name being selected
    const [errorMessage, setErrorMessage] = useState("");
    const [successMessage, setSuccessMessage] = useState("");
    const [coupon, setCoupon] = useState("");

    // Fallback plans
    const activePlans = plans.length > 0 ? plans : [
        { id: 1, name: "FREE", price: 0, company_limit: 5, duration_days: 3650 },
        { id: 2, name: "PREMIUM", price: 299, company_limit: 150, duration_days: 30 }
    ];

    /**
     * Activates the FREE plan
     */
    const handleSelectFree = async () => {
        setActionLoading("FREE");
        setErrorMessage("");
        setSuccessMessage("");
        try {
            await handleActivateFree();
            setSuccessMessage("FREE plan activated! Taking you to your watchlist...");
            setTimeout(() => {
                navigate("/companies");
            }, 1200);
        } catch (err) {
            setErrorMessage(err.message || "Failed to activate Free subscription.");
        } finally {
            setActionLoading(null);
        }
    };

    /** Redeem a 100%-off coupon → activate premium with no payment. */
    const redeemCoupon = async () => {
        await handleActivatePremium(coupon.trim());
        setSuccessMessage("Coupon applied — Premium activated! Taking you to your watchlist...");
        setTimeout(() => navigate("/companies"), 1200);
    };

    /** Pay for premium via Razorpay checkout (coupon applies a discount). */
    const payWithRazorpay = async (plan) => {
        const orderData = await createOrder(coupon.trim());

        // A 100%-off coupon needs no payment — activate premium directly.
        if (orderData.fullDiscount) {
            await redeemCoupon();
            return;
        }

        const order = orderData.order;

        if (!window.Razorpay) {
            throw new Error("Payment SDK not loaded. Please refresh and try again.");
        }

        await new Promise((resolve, reject) => {
            const rzp = new window.Razorpay({
                key: import.meta.env.VITE_RAZORPAY_KEY_ID,
                amount: order.amount,
                currency: order.currency,
                name: "EquityAlerts",
                description: "Premium Subscription",
                order_id: order.id,
                handler: async (response) => {
                    try {
                        await verifyPayment({
                            razorpay_order_id: response.razorpay_order_id,
                            razorpay_payment_id: response.razorpay_payment_id,
                            razorpay_signature: response.razorpay_signature,
                        });
                        await loadAppData();
                        setSuccessMessage("Payment successful — Premium activated! Taking you to your watchlist...");
                        setTimeout(() => navigate("/companies"), 1200);
                        resolve();
                    } catch (err) {
                        reject(new Error("Payment verification failed. If money was deducted, contact support."));
                    }
                },
                modal: {
                    ondismiss: () => reject(new Error("Payment cancelled.")),
                },
                prefill: {
                    name: localStorage.getItem("name") || "",
                    contact: localStorage.getItem("mobile") || "",
                },
                theme: { color: "#33D097" },
            });
            rzp.open();
        });
    };

    /**
     * Premium: create an order (a coupon, if entered, is validated and applied
     * server-side). A 100%-off coupon activates without payment; a percentage
     * coupon discounts the Razorpay amount.
     */
    const handleSelectPremium = async (plan) => {
        setActionLoading("PREMIUM");
        setErrorMessage("");
        setSuccessMessage("");
        try {
            await payWithRazorpay(plan);
        } catch (err) {
            setErrorMessage(
                err?.response?.data?.message || err.message || "Could not activate Premium."
            );
        } finally {
            setActionLoading(null);
        }
    };

    return (
        <div className="space-y-6 pb-8 font-sans bg-transparent text-[#9298A0] relative z-10">
            {/* Minimal Header */}
            <div className="text-center max-w-sm mx-auto space-y-2 mt-4 text-left">
                <h2 className="text-2xl font-bold text-[#E3E5EA] tracking-tight text-center">
                    Terminal Licenses
                </h2>
                <p className="text-[#6B7280] text-xs leading-relaxed text-center font-mono">
                    Select your corporate watchlist monitoring clearance tier.
                </p>
            </div>

            {/* Notifications */}
            {errorMessage && (
                <div className="p-4 bg-[#151921] border border-red-900/50 text-red-400 rounded-2xl text-xs font-semibold flex items-center gap-2.5 shadow-sm max-w-md mx-auto text-left">
                    <svg className="w-4.5 h-4.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <span>{errorMessage}</span>
                </div>
            )}

            {successMessage && (
                <div className="p-4 bg-[#151921] border border-[#33D097]/40 text-[#33D097] rounded-2xl text-xs font-semibold flex items-center gap-2.5 shadow-sm max-w-md mx-auto text-left">
                    <svg className="w-4.5 h-4.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>{successMessage}</span>
                </div>
            )}

            {/* Exactly Two Plan cards */}
            <div className="flex flex-col md:flex-row gap-6 max-w-2xl mx-auto justify-center px-4">
                {activePlans.map((plan, idx) => {
                    const isPremiumPlan = plan.name === "PREMIUM";
                    const currentPlanName =
                        currentSubscription?.plan_name ||
                        currentSubscription?.name ||
                        "";

                    const isCurrent =
                        currentPlanName === plan.name;
                    const itemLoading = actionLoading === plan.name;

                    // Specialized Stock Market terminology
                    const planTitle = isPremiumPlan ? "Professional Watchlist" : "Starter Watchlist";
                    const planSub = isPremiumPlan ? "Full terminal monitoring clearance" : "Basic equity alert monitoring";

                    return (
                        <div
                            key={plan.id || idx}
                            className={`
                                relative p-6 bg-[#151921] rounded-2xl border text-left flex flex-col justify-between overflow-hidden shadow-md flex-1 min-w-[280px]
                                ${isPremiumPlan ? "border-[#33D097] shadow-lg shadow-[#33D097]/5" : "border-[#222A38] shadow-md shadow-[#0C0E14]"}
                                transition duration-150 hover:shadow-lg
                            `}
                        >
                            <div className="space-y-4">
                                <div>
                                    <h3 className="text-lg font-bold text-[#E3E5EA] uppercase tracking-wide">
                                        {planTitle}
                                    </h3>
                                    <p className="text-[10px] text-[#6B7280] font-mono mt-0.5 uppercase">
                                        {planSub}
                                    </p>
                                </div>

                                <div className="border-b border-[#222A38] pb-4">
                                    <div className="flex items-baseline gap-1">
                                        <span className="text-4xl font-bold text-[#E3E5EA] tracking-tight font-mono">
                                            ₹{parseFloat(plan.price).toFixed(0)}
                                        </span>
                                        <span className="text-xs text-[#9298A0] font-semibold uppercase">
                                            {isPremiumPlan ? "/ month" : ""}
                                        </span>
                                    </div>
                                    {isPremiumPlan && (
                                        <p className="mt-1.5 text-[10px] font-bold uppercase tracking-wider text-[#6B7280] font-mono">
                                            Pay securely via Razorpay, or use a coupon
                                        </p>
                                    )}
                                </div>

                                {/* Custom Stock Market Features list */}
                                <ul className="space-y-3 py-2 text-xs font-semibold text-[#9298A0]">
                                    <li className="flex items-center gap-2.5">
                                        <svg className="w-4 h-4 text-[#33D097] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                        </svg>
                                        Access all listed companies
                                    </li>
                                    <li className="flex items-center gap-2.5">
                                        <svg className="w-4 h-4 text-[#33D097] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                        </svg>
                                        Track up to <span className="text-[#E3E5EA] font-bold font-mono">{plan.company_limit} symbols</span>
                                    </li>
                                    <li className="flex items-center gap-2.5">
                                        <svg className="w-4 h-4 text-[#33D097] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                        </svg>
                                        {isPremiumPlan ? (
                                            <span>Real-time WhatsApp alerts</span>
                                        ) : (
                                            <span className="text-[#6B7280]">Standard alert dispatch</span>
                                        )}
                                    </li>
                                    <li className="flex items-center gap-2.5">
                                        <svg className="w-4 h-4 text-[#33D097] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                        </svg>
                                        {isPremiumPlan ? (
                                            <span>Priority accelerated crawl feed</span>
                                        ) : (
                                            <span className="text-[#6B7280]">Standard crawl speed</span>
                                        )}
                                    </li>
                                </ul>
                            </div>

                            {/* Plan Action CTA */}
                            <div className="mt-6 pt-3.5 border-t border-[#222A38] space-y-3">
                                {isCurrent ? (
                                    <button
                                        disabled
                                        className="w-full h-12 border border-[#33D097] bg-[#151921] text-[#33D097] rounded-xl font-bold text-xs uppercase tracking-wider cursor-not-allowed flex items-center justify-center gap-1.5 focus:outline-none"
                                    >
                                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3">
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                                        </svg>
                                        Current Plan
                                    </button>
                                ) : (
                                    <>
                                        {isPremiumPlan && (
                                            <input
                                                value={coupon}
                                                onChange={(e) => setCoupon(e.target.value)}
                                                placeholder="Have a coupon? (optional)"
                                                className="w-full h-11 px-3 rounded-xl bg-[#0C0E14] border border-[#222A38] text-[#E3E5EA] placeholder-[#6B7280] text-xs font-mono uppercase tracking-wider focus:outline-none focus:border-[#33D097]/60"
                                            />
                                        )}
                                        <Button
                                            onClick={isPremiumPlan ? () => handleSelectPremium(plan) : handleSelectFree}
                                            loading={itemLoading || loading}
                                            disabled={actionLoading !== null}
                                            variant="primary"
                                            className={`w-full !h-12 text-xs uppercase tracking-wider !rounded-xl !font-bold ${isPremiumPlan
                                                ? "!bg-[#33D097] hover:!bg-[#3BE6A7] !text-[#0C0E14] focus:!ring-[#33D097]/20"
                                                : "bg-transparent border border-[#222A38] !text-[#E3E5EA] hover:bg-[#151921] focus:!ring-[#222A38]"
                                                }`}
                                        >
                                            {isPremiumPlan
                                                ? (coupon.trim()
                                                    ? "Apply coupon & continue"
                                                    : `Pay ₹${parseFloat(plan.price).toFixed(0)} & activate`)
                                                : "Select Starter Plan"}
                                        </Button>
                                    </>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

export default PlanSelection;
