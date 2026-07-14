import React from "react";
import { useNavigate } from "react-router-dom";
import useAuth from "../../hooks/useAuth";
import useApp from "../../hooks/useApp";
import Button from "../../components/ui/Button";

/**
 * High-fidelity, mobile-first Profile and Settings View.
 */
export function Profile() {
    const { user, logout } = useAuth();
    const { currentSubscription, selectedCompanies } = useApp();
    console.log(
        "CURRENT SUBSCRIPTION:",
        currentSubscription
    );
    const navigate = useNavigate();

    // Initials helper
    const getInitials = () => {
        if (!user || !user.name) return "U";
        return user.name.slice(0, 2).toUpperCase();
    };

    // Date formatter
    const formatDate = (isoString) => {
        if (!isoString) return "Lifetime";
        try {
            const date = new Date(isoString);
            return date.toLocaleDateString("en-IN", {
                day: "numeric",
                month: "long",
                year: "numeric"
            });
        } catch {
            return "N/A";
        }
    };

    const isPremium = currentSubscription?.plan_name === "PREMIUM";

    return (
        <div className="space-y-6 pb-8 font-sans">
            {/* User Profile Avatar Card */}
            <div className="bg-[#151921] rounded-3xl p-6 border border-[#222A38] shadow-md shadow-[#0C0E14]/40 flex flex-col items-center text-center space-y-4">
                <div className="w-20 h-20 bg-[#0C0E14] rounded-3xl text-white text-3xl font-black flex items-center justify-center shadow-lg glow-cyan border-2 border-brand-cyan/20">
                    {getInitials()}
                </div>

                <div className="space-y-1">
                    <h2 className="text-xl font-extrabold text-brand-light tracking-tight">
                        {user?.name || "EquityAlerts User"}
                    </h2>
                    <span className="block text-xs font-semibold text-brand-slate">
                        Active Account Member
                    </span>
                </div>
            </div>

            {/* Profile Info Details List */}
            <div className="bg-[#151921] rounded-3xl p-6 border border-[#222A38] shadow-md shadow-[#0C0E14]/40 space-y-4 text-left font-mono text-xs">
                <h3 className="text-xs font-bold text-brand-textMuted uppercase tracking-widest border-b border-[#222A38] pb-2 mb-1">
                    Terminal Credentials
                </h3>

                <div className="grid grid-cols-2 gap-4 text-xs">
                    <div>
                        <span className="block text-brand-slate font-medium font-sans">Full Name</span>
                        <span className="font-bold text-[#E3E5EA] mt-0.5 block truncate">
                            {user?.name || "EquityAlerts User"}
                        </span>
                    </div>
                    <div>
                        <span className="block text-brand-slate font-medium font-sans">Mobile Number</span>
                        <span className="font-bold text-[#E3E5EA] mt-0.5 block">
                            +91 {user?.mobile || "N/A"}
                        </span>
                    </div>
                </div>
            </div>

            {/* Subscription & Active Limits details */}
            <div className="bg-[#151921] rounded-3xl p-6 border border-[#222A38] shadow-md shadow-[#0C0E14]/40 text-left space-y-5">
                <h3 className="text-xs font-bold text-brand-textMuted uppercase tracking-widest border-b border-[#222A38] pb-2 font-mono">
                    Terminal Clearance Tier
                </h3>

                {!currentSubscription ? (
                    <div className="text-center py-4 space-y-4 font-mono">
                        <div className="w-12 h-12 rounded-2xl bg-brand-navy border border-[#222A38] text-amber-400 flex items-center justify-center mx-auto">
                            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                        </div>

                        <div className="space-y-1">
                            <h4 className="text-sm font-extrabold text-[#E3E5EA]">
                                No active license found
                            </h4>
                            <p className="text-brand-slate text-xs max-w-xs mx-auto leading-relaxed font-sans">
                                Activate a watchlist monitoring license to begin receiving instant market disclosures.
                            </p>
                        </div>

                        <Button onClick={() => navigate("/plans")} variant="primary" className="w-full">
                            Activate License
                        </Button>
                    </div>
                ) : (
                    <div className="space-y-5 font-mono text-xs">
                        {/* Plan tag */}
                        <div className={`p-4 rounded-2xl border flex items-center justify-between ${isPremium ? "bg-brand-cyan/5 border-[#33D097]/20 text-[#E3E5EA]" : "bg-brand-navy border-[#222A38]"}`}>
                            <div className="space-y-1">
                                <span className={`text-[10px] font-bold uppercase tracking-wider block ${isPremium ? "text-[#33D097]" : "text-[#9298A0]"}`}>
                                    Clearance Level
                                </span>
                                <span className={`text-base font-black ${isPremium ? "text-[#E3E5EA]" : "text-[#E3E5EA]"}`}>
                                    {currentSubscription.plan_name} TERMINAL
                                </span>
                            </div>

                            <span className={`text-[10px] font-bold px-3 py-1 rounded-full uppercase ${isPremium ? "bg-[#33D097] text-[#0C0E14]" : "bg-[#0C0E14] border border-[#222A38] text-[#9298A0]"}`}>
                                {isPremium ? "PRO" : "STARTER"}
                            </span>
                        </div>

                        {/* Watchlist Gauge */}
                        <div className="space-y-2 text-xs">
                            <div className="flex items-center justify-between font-bold">
                                <span className="text-[#9298A0] font-sans">Tracked Symbols Capacity</span>
                                <span className="text-[#E3E5EA]">
                                    {selectedCompanies.length} / {currentSubscription.company_limit}
                                </span>
                            </div>

                            {/* visual progress gauge bar */}
                            <div className="w-full h-2 bg-[#0C0E14] border border-[#222A38] rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-[#33D097] transition-all duration-300 rounded-full"
                                    style={{
                                        width: `${Math.min(100, (selectedCompanies.length / currentSubscription.company_limit) * 100)}%`
                                    }}
                                />
                            </div>
                        </div>

                        {/* Calendar Details */}
                        <div className="grid grid-cols-2 gap-4 text-xs border-t border-[#222A38] pt-4">
                            <div>
                                <span className="block text-[#9298A0] font-medium font-sans">Billing Period</span>
                                <span className="font-bold text-[#E3E5EA] mt-0.5 block uppercase">
                                    {isPremium ? "Monthly" : "Lifetime"}
                                </span>
                            </div>
                            <div>
                                <span className="block text-[#9298A0] font-medium font-sans">License Renewal</span>
                                <span className="font-bold text-[#E3E5EA] mt-0.5 block truncate">
                                    {formatDate(currentSubscription.ends_at)}
                                </span>
                            </div>
                        </div>

                        {/* Upgrade Banner for Free Users */}
                        {!isPremium && (
                            <div className="p-4 bg-[#0C0E14] border border-[#222A38] text-left rounded-2xl space-y-3.5 mt-2 font-sans">
                                <div className="space-y-1">
                                    <h4 className="text-xs font-black text-[#33D097] uppercase tracking-wider font-mono">
                                        Need to track more stocks?
                                    </h4>
                                    <p className="text-[11px] text-[#9298A0] leading-relaxed">
                                        Upgrade your watchlist limits from 10 to 25 companies and receive accelerated WhatsApp dispatch triggers!
                                    </p>
                                </div>

                                <Button onClick={() => navigate("/plans")} variant="primary" className="w-full !h-9 text-xs">
                                    Upgrade Watchlist Limit
                                </Button>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Terminal Health Logs */}
            <div className="bg-[#151921] rounded-3xl p-6 border border-[#222A38] shadow-md shadow-[#0C0E14]/40 text-left space-y-4 font-mono text-xs">
                <h3 className="text-xs font-bold text-brand-textMuted uppercase tracking-widest border-b border-[#222A38] pb-2">
                    Terminal Engine Logs
                </h3>
                <div className="space-y-2">
                    <div className="flex justify-between items-center p-2.5 bg-[#0C0E14]/60 border border-[#222A38] rounded-xl">
                        <span className="text-[#9298A0]">WhatsApp Alert Channel</span>
                        <span className="text-[#33D097] font-bold">● ONLINE (0ms dispatch delay)</span>
                    </div>
                    <div className="flex justify-between items-center p-2.5 bg-[#0C0E14]/60 border border-[#222A38] rounded-xl">
                        <span className="text-[#9298A0]">NSE Disclosures Webhook</span>
                        <span className="text-[#33D097] font-bold">● ACTIVE (Real-time tracking)</span>
                    </div>
                    <div className="flex justify-between items-center p-2.5 bg-[#0C0E14]/60 border border-[#222A38] rounded-xl">
                        <span className="text-[#9298A0]">BSE Disclosures Webhook</span>
                        <span className="text-[#33D097] font-bold">● ACTIVE (Real-time tracking)</span>
                    </div>
                </div>
            </div>

            {/* Logout Panel */}
            <div className="px-1.5">
                <Button
                    onClick={logout}
                    variant="outline"
                    className="w-full !text-red-400 hover:!bg-red-950/20 !border-red-900/50 font-mono text-xs uppercase"
                >
                    Sign Out Terminal Session
                </Button>
            </div>
        </div>
    );
}

export default Profile;
