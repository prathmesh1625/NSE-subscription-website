import React from "react";
import { useNavigate } from "react-router-dom";
import LandingNavbar from "../layout/LandingNavbar";
import Footer from "../layout/Footer";

export default function FAQ() {
    const navigate = useNavigate();

    const faqs = [
        {
            question: "How fast do alerts arrive after an announcement?",
            answer:
                "Our engine monitors exchange filings continuously and dispatches WhatsApp alerts with sub-second processing latency — typically you'll have the announcement before it trends anywhere else.",
        },
        {
            question: "Do I need to install an app?",
            answer:
                "No. Alerts arrive directly on WhatsApp, and your watchlist is managed from this web portal. Nothing to install, nothing to keep open.",
        },
        {
            question: "What does the free plan include?",
            answer:
                "The free plan is free forever and lets you track up to 10 companies with full real-time WhatsApp alerts. Upgrade to Premium (₹299/month) to track up to 25 companies.",
        },
        {
            question: "Is this investment advice?",
            answer:
                "No. EquityAlerts provides informational alerts only and does not offer investment advice. Always do your own research before making investment decisions.",
        },
        {
            question: "Can I track multiple companies?",
            answer:
                "Yes. Free users can track up to 10 companies, while Premium users can track up to 25 companies simultaneously.",
        },
        {
            question: "Which exchanges are supported?",
            answer:
                "We currently monitor companies listed on both NSE and BSE and provide real-time updates from their official announcements.",
        },
    ];

    return (
        <div className="min-h-screen bg-[#07090F] text-white">

            <LandingNavbar />

            {/* Hero */}
            <section className="pt-32 pb-24 border-b border-[#1E2535]">
                <div className="max-w-5xl mx-auto px-6 text-center">

                    <span className="text-[#33D097] uppercase tracking-[3px] font-bold text-sm">
                        Frequently Asked Questions
                    </span>

                    <h1 className="text-5xl font-bold mt-5">
                        How can we help?
                    </h1>

                    <p className="text-[#98A0AE] text-lg mt-6 leading-8 max-w-3xl mx-auto">
                        Find answers to the most common questions about
                        EquityAlerts, pricing, monitoring, WhatsApp alerts,
                        and account management.
                    </p>

                </div>
            </section>

            {/* FAQ */}
            <section className="py-20">
                <div className="max-w-4xl mx-auto px-6">

                    {faqs.map((faq, index) => (

                        <details
                            key={index}
                            className="bg-[#10141E] border border-[#1E2535] rounded-2xl mb-5 overflow-hidden"
                            open={index === 0}
                        >

                            <summary className="cursor-pointer px-6 py-5 text-lg font-semibold text-white">
                                {faq.question}
                            </summary>

                            <div className="px-6 pb-6 text-[#98A0AE] leading-8">
                                {faq.answer}
                            </div>

                        </details>

                    ))}

                </div>
            </section>

            <Footer />

        </div>
    );
}