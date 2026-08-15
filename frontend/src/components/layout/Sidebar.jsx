import React from "react";
import { useNavigate, useLocation } from "react-router-dom";
import useAuth from "../../hooks/useAuth";

export function Sidebar({ collapsed, setCollapsed, mobileOpen, setMobileOpen }) {
    const { logout } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();

    const menuItems = [
        {
            name: "Dashboard",
            path: "/dashboard",
            icon: (
                <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 002 2h2a2 2 0 002-2z" />
                </svg>
            ),
        },
        {
            name: "My Watchlist",
            path: "/companies",
            icon: (
                <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                </svg>
            ),
        },
        {
            name: "My Plan",
            path: "/plans",
            icon: (
                <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                </svg>
            ),
        },
        {
            name: "Account Settings",
            path: "/profile",
            icon: (
                <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
            ),
        },
    ];

    const handleNavigation = (path) => {
        navigate(path);
        setMobileOpen(false);
    };

    return (
        <>
            {/* Mobile overlay */}
            {mobileOpen && (
                <div
                    className="fixed inset-0 z-30 bg-[#07090F]/70 backdrop-blur-sm md:hidden"
                    onClick={() => setMobileOpen(false)}
                />
            )}

            <aside
                className={`
                    fixed top-0 bottom-0 left-0 z-40
                    hidden md:flex flex-col
                    bg-[#07090F] text-[#EDF0F4]
                    border-r border-[#1E2535]
                    transition-all duration-300 ease-in-out
                    ${collapsed ? "w-[72px]" : "w-64"}
                    ${mobileOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"}
                `}
            >
                {/* ── LOGO HEADER ──────────────────────────────────────── */}
                <div className="h-16 flex items-center justify-between px-4 border-b border-[#1E2535] shrink-0">
                    <div className="flex items-center gap-3 overflow-hidden min-w-0">
                        {/* Gradient logo badge — matches landing page */}
                        <div
                            className="min-w-[38px] min-h-[38px] w-[38px] h-[38px] rounded-[11px] flex items-center justify-center shadow-[0_4px_20px_rgba(51,208,151,0.28)] shrink-0"
                            style={{
                                background:
                                    "linear-gradient(92deg, #33D097 0%, #2DD4BF 55%, #38BDF8 110%)",
                            }}
                        >
                            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none">
                                <path
                                    d="M3 17l5-6 4 4 6-8 3 3"
                                    stroke="#04130C"
                                    strokeWidth="2.6"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                />
                            </svg>
                        </div>
                        {!collapsed && (
                            <span className="font-display font-bold text-[17px] tracking-tight text-[#EDF0F4] truncate">
                                EquityAlerts
                            </span>
                        )}
                    </div>

                    {/* Collapse toggle */}
                    <button
                        onClick={() => setCollapsed(!collapsed)}
                        className="hidden md:flex p-1.5 rounded-lg text-[#646E7E] hover:text-[#EDF0F4] hover:bg-[#10141E] transition-colors shrink-0"
                    >
                        <svg
                            className={`w-4 h-4 transition-transform duration-300 ${collapsed ? "rotate-180" : ""}`}
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth="2"
                        >
                            <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                        </svg>
                    </button>
                </div>

                {/* ── NAV LINKS ─────────────────────────────────────────── */}
                <nav className="flex-1 py-5 px-3 space-y-1 overflow-y-auto custom-scrollbar text-left">
                    {menuItems.map((item) => {
                        const isActive = location.pathname === item.path;

                        return (
                            <button
                                key={item.path}
                                onClick={() => handleNavigation(item.path)}
                                title={collapsed ? item.name : undefined}
                                className={`
                                    w-full flex items-center gap-3 py-2.5 px-3 rounded-xl font-semibold text-sm
                                    transition-all duration-150 group relative text-left
                                    ${isActive
                                        ? "bg-[#33D097]/10 text-[#EDF0F4] border border-[#33D097]/20"
                                        : "text-[#646E7E] hover:text-[#EDF0F4] hover:bg-[#10141E] border border-transparent"
                                    }
                                `}
                            >
                                {/* Active left accent bar */}
                                {isActive && (
                                    <span
                                        className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full"
                                        style={{
                                            background:
                                                "linear-gradient(180deg, #33D097 0%, #38BDF8 100%)",
                                        }}
                                    />
                                )}
                                <span
                                    className={`shrink-0 transition-colors ${
                                        isActive
                                            ? "text-[#33D097]"
                                            : "text-[#646E7E] group-hover:text-[#EDF0F4]"
                                    }`}
                                >
                                    {item.icon}
                                </span>
                                {!collapsed && (
                                    <span className="truncate flex-1">{item.name}</span>
                                )}
                            </button>
                        );
                    })}
                </nav>

                {/* ── FOOTER / LOGOUT ───────────────────────────────────── */}
                <div className="p-3 border-t border-[#1E2535] shrink-0">
                    {/* Session status pill */}
                    {!collapsed && (
                        <div className="mb-3 flex items-center gap-2 px-3 py-2 rounded-xl bg-[#10141E] border border-[#1E2535]">
                            <span className="w-1.5 h-1.5 bg-[#33D097] rounded-full animate-pulse shrink-0" />
                            <span className="text-[10px] font-mono font-bold text-[#33D097] uppercase tracking-widest truncate">
                                Session Active
                            </span>
                        </div>
                    )}
                    <button
                        onClick={logout}
                        title={collapsed ? "Logout" : undefined}
                        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl font-semibold text-sm text-red-400 hover:text-red-300 hover:bg-red-950/20 border border-transparent hover:border-red-900/30 transition-all duration-150"
                    >
                        <svg
                            className="w-[18px] h-[18px] shrink-0"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                            strokeWidth="2"
                        >
                            <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                            />
                        </svg>
                        {!collapsed && <span className="truncate">Logout</span>}
                    </button>
                </div>
            </aside>
        </>
    );
}

export default Sidebar;
