import React, { useState, useEffect, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";

// Premium animated counter component using IntersectionObserver and RequestAnimationFrame
function AnimatedCounter({ end, duration = 1200 }) {
    const [count, setCount] = useState(0);
    const countRef = useRef(null);

    useEffect(() => {
        let observer;
        let animationFrameId;

        if (countRef.current) {
            observer = new IntersectionObserver(
                (entries) => {
                    entries.forEach((entry) => {
                        if (entry.isIntersecting) {
                            let startTimestamp = null;
                            const step = (timestamp) => {
                                if (!startTimestamp) startTimestamp = timestamp;
                                const progress = Math.min((timestamp - startTimestamp) / duration, 1);
                                // Ease out cubic formula
                                const easedProgress = 1 - Math.pow(1 - progress, 3);
                                setCount(Math.round(easedProgress * end));
                                if (progress < 1) {
                                    animationFrameId = requestAnimationFrame(step);
                                }
                            };
                            animationFrameId = requestAnimationFrame(step);
                            observer.unobserve(entry.target);
                        }
                    });
                },
                { threshold: 0.5 }
            );
            observer.observe(countRef.current);
        }

        return () => {
            if (observer) observer.disconnect();
            if (animationFrameId) cancelAnimationFrame(animationFrameId);
        };
    }, [end, duration]);

    return <span ref={countRef}>{count}</span>;
}

function LandingPage() {
    const navigate = useNavigate();

    // Setup scroll reveal animation hook
    useEffect(() => {
        const io = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add("in");
                        io.unobserve(entry.target);
                    }
                });
            },
            { threshold: 0.12 }
        );

        const els = document.querySelectorAll(".reveal");
        els.forEach((el) => io.observe(el));

        return () => {
            els.forEach((el) => io.unobserve(el));
            io.disconnect();
        };
    }, []);

    return (
        <div className="min-h-screen bg-[#07090F] text-[#EDF0F4] font-sans relative overflow-x-hidden antialiased selection:bg-[#33D097]/30">
            {/* Aurora Background and Grid */}
            <div className="aurora-glow fixed inset-0 z-0 pointer-events-none" />
            <div className="bg-grid-pattern fixed inset-0 z-0 pointer-events-none" />

            {/* TICKER */}
            <div className="relative z-10 bg-[#0B0E16]/90 border-b border-[#1E2535] overflow-hidden py-2 font-mono text-[11px]">
                <div className="animate-marquee flex gap-0 whitespace-nowrap">
                    {[...Array(2)].map((_, rIdx) => (
                        <React.Fragment key={rIdx}>
                            {[
                                { symbol: "RELIANCE", change: "1.24%", up: true },
                                { symbol: "TCS", change: "0.42%", up: false },
                                { symbol: "INFY", change: "0.87%", up: true },
                                { symbol: "HDFCBANK", change: "0.31%", up: true },
                                { symbol: "ICICIBANK", change: "0.18%", up: false },
                                { symbol: "BHARTIARTL", change: "2.05%", up: true },
                                { symbol: "SBIN", change: "0.66%", up: true },
                                { symbol: "LICI", change: "0.74%", up: false },
                                { symbol: "ITC", change: "0.12%", up: true },
                                { symbol: "KOTAKBANK", change: "1.48%", up: true }
                            ].map((item, idx) => (
                                <span key={`${rIdx}-${idx}`} className="inline-flex items-center gap-[7px] px-[22px] border-r border-[#1E2535]/60">
                                    <b className="text-[#EDF0F4] font-bold tracking-[0.5px]">{item.symbol}</b>
                                    <span className={item.up ? "text-[#33D097]" : "text-[#F87171]"}>
                                        {item.up ? "▲" : "▼"} {item.change}
                                    </span>
                                </span>
                            ))}
                        </React.Fragment>
                    ))}
                </div>
            </div>

            {/* NAV */}
            <nav className="sticky top-0 z-50 bg-[#07090F]/72 backdrop-blur-[18px] border-b border-[#1E2535]/70">
                <div className="max-w-[1180px] mx-auto px-6 h-[68px] flex items-center justify-between">
                    <div className="flex items-center gap-[11px]">
                        <div className="w-[38px] h-[38px] rounded-[11px] bg-brand-grad flex items-center justify-center shadow-[0_4px_24px_rgba(51,208,151,0.35)]">
                            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none">
                                <path d="M3 17l5-6 4 4 6-8 3 3" stroke="#04130C" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"/>
                            </svg>
                        </div>
                        <span className="font-display font-bold text-[18px] tracking-[-0.3px] text-[#EDF0F4]">
                            EquityAlerts
                        </span>
                    </div>

                    <div className="hidden md:flex gap-[34px] text-[13.5px] font-semibold text-[#98A0AE]">
                    <Link to="/pricing" className="hover:text-[#EDF0F4] transition duration-200 relative group py-1">
                            Pricing
                            <span className="absolute left-0 bottom-0 w-0 h-[2px] bg-brand-grad rounded-[2px] transition-all duration-250 group-hover:w-full" />
                    </Link>
                        <Link to="/features" className="hover:text-[#EDF0F4] transition duration-200 relative group py-1">
                            Features
                            <span className="absolute left-0 bottom-0 w-0 h-[2px] bg-brand-grad rounded-[2px] transition-all duration-250 group-hover:w-full" />
                        </Link>
                        <Link to="/Coverage" className="hover:text-[#EDF0F4] transition duration-200 relative group py-1">
                            Coverage
                            <span className="absolute left-0 bottom-0 w-0 h-[2px] bg-brand-grad rounded-[2px] transition-all duration-250 group-hover:w-full" />
                        </Link>
                        <Link to="/HowItWorks" className="hover:text-[#EDF0F4] transition duration-200 relative group py-1">
                            How It Works
                            <span className="absolute left-0 bottom-0 w-0 h-[2px] bg-brand-grad rounded-[2px] transition-all duration-250 group-hover:w-full" />
                        </Link>
                        <Link to="/faq" className="hover:text-[#EDF0F4] transition duration-200 relative group py-1">
                            FAQ
                            <span className="absolute left-0 bottom-0 w-0 h-[2px] bg-brand-grad rounded-[2px] transition-all duration-250 group-hover:w-full" />
                        </Link>
                    </div>

                    <div className="flex items-center gap-[14px]">
                        <Link to="/login"className="px-6 py-2.5 rounded-full bg-[#1E2635] border border-[#2E3A50] text-white font-bold text-sm hover:bg-[#2A3446] hover:border-[#3DD9A4] transition-all duration-300 shadow-md" >
                        Log In
                        </Link>    
                    </div>
                </div>
            </nav>

            {/* HERO */}
            <header className="max-w-[1180px] mx-auto px-6 relative z-10 pt-[84px] pb-10 grid grid-cols-1 lg:grid-cols-[1.12fr_0.88fr] gap-[56px] items-center text-center lg:text-left">
                <div>
                    <span className="inline-flex items-center gap-2 bg-[#33D097]/[0.07] border border-[#33D097]/22 text-[#33D097] text-xs font-bold px-[14px] py-[7px] rounded-full tracking-[0.3px]">
                        <span className="w-[7px] h-[7px] rounded-full bg-[#33D097] pulse-dot" />
                        893 analysts tracking announcements live
                    </span>

                    <h1 className="font-display text-[38px] md:text-[60px] leading-[1.06] tracking-[-1.8px] font-bold mt-[26px] mb-[22px] text-[#EDF0F4]">
                        Never miss a <span className="grad-text">company announcement</span> again.
                    </h1>

                    <p className="text-[#98A0AE] text-[16.5px] leading-[1.7] max-w-[520px] mx-auto lg:mx-0 font-medium">
                        Track NSE &amp; BSE companies and get instant WhatsApp alerts for earnings, dividends, board meetings, acquisitions and regulatory filings — the moment they're published.
                    </p>

                    <div className="flex gap-[14px] mt-[34px] flex-wrap justify-center lg:justify-start">
                        <button
                            onClick={() => navigate("/register")}
                            className="inline-flex items-center justify-center gap-2 font-sans font-bold text-[14.5px] rounded-[14px] px-[30px] h-[52px] cursor-pointer bg-brand-grad text-[#04130C] shadow-[0_6px_28px_rgba(51,208,151,0.32)] hover:shadow-[0_10px_36px_rgba(51,208,151,0.45)] hover:-translate-y-[2px] active:scale-[0.97] transition-all duration-180"
                        >
                            Start Tracking Free
                        </button>
                        <Link to="/pricing"
                            className="inline-flex items-center justify-center gap-2 font-sans font-bold text-[14.5px] rounded-[14px] px-[30px] h-[52px] cursor-pointer bg-transparent text-[#EDF0F4] border border-[#1E2535] hover:border-[#33D097] hover:text-[#33D097] hover:-translate-y-[2px] active:scale-[0.97] transition-all duration-180"
                        >
                            View Plans
                        </Link>
                    </div>

                    <div className="flex gap-[44px] mt-[46px] pt-[30px] border-t border-[#1E2535] justify-center lg:justify-start">
                        <div className="text-center lg:text-left">
                            <div className="font-display text-[30px] font-bold tracking-[-1px] text-[#EDF0F4]">
                                <span className="text-[#33D097]"><AnimatedCounter end={5000} /></span>+
                            </div>
                            <div className="text-[12px] text-[#646E7E] font-semibold mt-1 tracking-[0.3px] uppercase">Companies</div>
                        </div>
                        <div className="text-center lg:text-left">
                            <div className="font-display text-[30px] font-bold tracking-[-1px] text-[#EDF0F4]">
                                <span className="text-[#33D097]">&lt;1</span>s
                            </div>
                            <div className="text-[12px] text-[#646E7E] font-semibold mt-1 tracking-[0.3px] uppercase">Alert Latency</div>
                        </div>
                        <div className="text-center lg:text-left">
                            <div className="font-display text-[30px] font-bold tracking-[-1px] text-[#EDF0F4]">
                                <span className="text-[#33D097]"><AnimatedCounter end={24} /></span>/7
                            </div>
                            <div className="text-[12px] text-[#646E7E] font-semibold mt-1 tracking-[0.3px] uppercase">Monitoring</div>
                        </div>
                        <div className="text-center lg:text-left">
                            <div className="font-display text-[30px] font-bold tracking-[-1px] text-[#EDF0F4]">
                                <span className="text-[#33D097]">₹0</span>
                            </div>
                            <div className="text-[12px] text-[#646E7E] font-semibold mt-1 tracking-[0.3px] uppercase">To Start</div>
                        </div>
                    </div>
                </div>

                <div className="relative flex justify-center">
                    <div className="absolute bg-[#10141E]/92 backdrop-blur-[10px] border border-[#1E2535] rounded-[14px] px-4 py-3 z-[3] shadow-[0_16px_50px_rgba(0,0,0,0.5)] top-[46px] left-0 lg:-left-[30px] float-card-1 text-left">
                        <div className="text-[9.5px] font-black text-[#646E7E] tracking-[1px] uppercase">NSE Feed</div>
                        <div className="font-display text-[17px] font-bold mt-[3px] text-[#33D097]">● CONNECTED</div>
                    </div>
                    <div className="absolute bg-[#10141E]/92 backdrop-blur-[10px] border border-[#1E2535] rounded-[14px] px-4 py-3 z-[3] shadow-[0_16px_50px_rgba(0,0,0,0.5)] bottom-[70px] right-0 lg:-right-[26px] float-card-2 text-left">
                        <div className="text-[9.5px] font-black text-[#646E7E] tracking-[1px] uppercase">Alerts today</div>
                        <div className="font-display text-[17px] font-bold mt-[3px] text-[#33D097]">+1,284</div>
                    </div>

                    <div className="w-[300px] rounded-[38px] bg-[#0D1119] border border-[#232C3F] shadow-[0_40px_90px_rgba(0,0,0,0.6),0_0_80px_rgba(51,208,151,0.07)] p-3 relative z-[2] phone-float text-left">
                        <div className="rounded-[28px] bg-[#0A0E0B] overflow-hidden h-[540px] flex flex-col">
                            <div className="bg-[#15211B] px-4 py-3.5 flex items-center gap-[11px] border-b border-[#33D097]/10">
                                <div className="w-9 h-9 rounded-full bg-brand-grad flex items-center justify-center font-black text-[13px] text-[#04130C]">EA</div>
                                <div>
                                    <div className="text-[13.5px] font-bold text-[#EDF0F4]">EquityAlerts</div>
                                    <div className="text-[10.5px] text-[#33D097]">● online</div>
                                </div>
                            </div>
                            <div 
                                className="flex-1 px-3 py-3.5 flex flex-col gap-[11px] overflow-hidden"
                                style={{
                                    backgroundImage: "radial-gradient(rgba(51, 208, 151, 0.04) 1px, transparent 1px)",
                                    backgroundSize: "22px 22px"
                                }}
                            >
                                <div className="wa-msg bg-[#121E17] border border-[#33D097]/12 rounded-[4px_14px_14px_14px] px-[13px] py-[11px] max-w-[94%]">
                                    <span className="inline-block text-[9px] font-black tracking-[0.8px] px-2 py-[3px] rounded-[5px] mb-[7px] uppercase bg-[#33D097]/14 text-[#33D097]">
                                        Earnings
                                    </span>
                                    <b className="text-[12.5px] block mb-[3px] text-[#EDF0F4]">RELIANCE — Q4 Results Out</b>
                                    <span className="text-[11px] text-[#98A0AE] leading-[1.5] block">
                                        Consolidated net profit ₹18,951 Cr. Full filing PDF attached.
                                    </span>
                                    <div className="text-[9px] text-[#646E7E] text-right mt-[6px]">09:42 ✓✓</div>
                                </div>
                                <div className="wa-msg bg-[#121E17] border border-[#33D097]/12 rounded-[4px_14px_14px_14px] px-[13px] py-[11px] max-w-[94%]">
                                    <span className="inline-block text-[9px] font-black tracking-[0.8px] px-2 py-[3px] rounded-[5px] mb-[7px] uppercase bg-[#38BDF8]/14 text-[#38BDF8]">
                                        Dividend
                                    </span>
                                    <b className="text-[12.5px] block mb-[3px] text-[#EDF0F4]">TCS — Dividend Declared</b>
                                    <span className="text-[11px] text-[#98A0AE] leading-[1.5] block">
                                        Interim dividend of ₹10/share. Record date: 16 Jun 2026.
                                    </span>
                                    <div className="text-[9px] text-[#646E7E] text-right mt-[6px]">10:15 ✓✓</div>
                                </div>
                                <div className="wa-msg bg-[#121E17] border border-[#33D097]/12 rounded-[4px_14px_14px_14px] px-[13px] py-[11px] max-w-[94%]">
                                    <span className="inline-block text-[9px] font-black tracking-[0.8px] px-2 py-[3px] rounded-[5px] mb-[7px] uppercase bg-[#FBBF24]/14 text-[#FBBF24]">
                                        Board Meeting
                                    </span>
                                    <b className="text-[12.5px] block mb-[3px] text-[#EDF0F4]">HDFCBANK — Board Meeting</b>
                                    <span className="text-[11px] text-[#98A0AE] leading-[1.5] block">
                                        Board meeting scheduled 19 Jun to consider fund raising.
                                    </span>
                                    <div className="text-[9px] text-[#646E7E] text-right mt-[6px]">11:03 ✓✓</div>
                                </div>
                                <div className="wa-msg bg-[#121E17] border border-[#33D097]/12 rounded-[4px_14px_14px_14px] px-[13px] py-[11px] max-w-[94%]">
                                    <span className="inline-block text-[9px] font-black tracking-[0.8px] px-2 py-[3px] rounded-[5px] mb-[7px] uppercase bg-[#F87171]/14 text-[#F87171]">
                                        Acquisition
                                    </span>
                                    <b className="text-[12.5px] block mb-[3px] text-[#EDF0F4]">INFY — Acquisition Update</b>
                                    <span className="text-[11px] text-[#98A0AE] leading-[1.5] block">
                                        Completes acquisition of EU-based consulting firm.
                                    </span>
                                    <div className="text-[9px] text-[#646E7E] text-right mt-[6px]">11:40 ✓✓</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </header>

            {/* TRUST STRIP */}
            <div className="relative z-10 border-y border-[#1E2535] bg-[#0B0E16]/50 py-[22px] mt-[60px]">
                <div className="max-w-[1180px] mx-auto px-6 flex justify-between gap-[18px] flex-wrap">
                    {[
                        "5000 Companies",
                        "WhatsApp Alerts",
                        "Free Forever Plan",
                        "NSE & BSE Coverage",
                        "Real-Time Monitoring"
                    ].map((text, idx) => (
                        <div key={idx} className="flex items-center gap-[9px] text-[13px] font-semibold text-[#98A0AE]">
                            <svg className="w-[17px] h-[17px] shrink-0" viewBox="0 0 24 24" fill="none">
                                <circle cx="12" cy="12" r="10" stroke="#33D097" strokeWidth="2"/>
                                <path d="M8 12l3 3 5-6" stroke="#33D097" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                            </svg>
                            {text}
                        </div>
                    ))}
                </div>
            </div>



            {/* FOOTER */}
            <footer className="border-t border-[#1E2535] bg-[#07090F]/85 py-[60px] pb-8 relative z-10 text-left">
                <div className="max-w-[1180px] mx-auto px-6">
                    <div className="grid grid-cols-2 md:grid-cols-[1.4fr_1fr_1fr_1fr] gap-10 mb-[48px]">
                        <div>
                            <div className="flex items-center gap-[11px]">
                                <div className="w-8 h-8 rounded-[9px] bg-brand-grad flex items-center justify-center">
                                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none">
                                        <path d="M3 17l5-6 4 4 6-8 3 3" stroke="#04130C" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"/>
                                    </svg>
                                </div>
                                <span className="font-display font-bold text-[16px] text-[#EDF0F4]">EquityAlerts</span>
                            </div>
                            <p className="text-[#646E7E] text-[12.5px] leading-[1.7] mt-3.5 max-w-[260px]">
                                Company announcement monitoring for NSE &amp; BSE. Informational alerts only — not investment advice.
                            </p>
                            {/* Ownership disclosure — EquityAlerts is the product name;
                                the legal entity behind it is EagleSwift Global Advisors
                                Private Limited. Stated here and on every legal page so
                                the relationship is verifiable by users and reviewers. */}
                            <p className="text-[#98A0AE] text-[12.5px] leading-[1.7] mt-3.5 max-w-[260px]">
                                EquityAlerts is a product of{" "}
                                <span className="font-semibold text-[#C7CDD8]">EagleSwift Global Advisors Private Limited</span>.
                            </p>
                        </div>
                        
                    
                        <div>
                            <h5 className="text-[11px] font-black tracking-[1.8px] uppercase text-[#646E7E] mb-[18px]">Support</h5>
                            <a href="mailto:support@equityalerts.ai" className="block text-[13.5px] text-[#98A0AE] font-semibold mb-3 hover:text-[#33D097] transition duration-150">Contact</a>
                            <a href="#faq" className="block text-[13.5px] text-[#98A0AE] font-semibold mb-3 hover:text-[#33D097] transition duration-150">FAQ</a>
                        </div>
                        <div>
                            <h5 className="text-[11px] font-black tracking-[1.8px] uppercase text-[#646E7E] mb-[18px]">Legal</h5>
                            <Link to="/privacy-policy" className="block text-[13.5px] text-[#98A0AE] font-semibold mb-3 hover:text-[#33D097] transition duration-150">Privacy Policy</Link>
                            <Link to="/terms-of-service" className="block text-[13.5px] text-[#98A0AE] font-semibold mb-3 hover:text-[#33D097] transition duration-150">Terms of Service</Link>
                            <Link to="/disclaimer" className="block text-[13.5px] text-[#98A0AE] font-semibold mb-3 hover:text-[#33D097] transition duration-150">Disclaimer</Link>
                        </div>
                    </div>
                    <div className="border-t border-[#1E2535] pt-[26px] flex justify-between items-center gap-4 flex-wrap text-[11.5px] text-[#646E7E]">
                        <span>© 2026 EagleSwift Global Advisors Private Limited. All rights reserved. EquityAlerts is a product of EagleSwift Global Advisors Private Limited.</span>
                        <div className="flex gap-5">
                            <Link to="/privacy-policy" className="hover:text-[#33D097] transition-colors">Privacy Policy</Link>
                            <Link to="/terms-of-service" className="hover:text-[#33D097] transition-colors">Terms of Service</Link>
                            <Link to="/disclaimer" className="hover:text-[#33D097] transition-colors">Disclaimer</Link>
                        </div>
                    </div>
                </div>
            </footer>
        </div>
    );
}

export default LandingPage;