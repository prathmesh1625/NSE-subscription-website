import React from "react";
import { useNavigate } from "react-router-dom";
import LandingNavbar from "../layout/LandingNavbar";
import Footer from "../layout/Footer";

export default function Pricing() {
    const navigate = useNavigate();

    return (
        <div className="min-h-screen bg-[#07090F] text-white">

            <LandingNavbar/>

            {/* Hero */}
            <section className="pt-32 pb-24 border-b border-[#1E2535]">

                <div className="max-w-5xl mx-auto px-6 text-center">

                    <span className="text-[#33D097] uppercase tracking-[3px] font-bold text-sm">
                        Pricing
                    </span>

                    <h1 className="text-2xl font-bold mt-5">
                        Simple, Honest Pricing
                    </h1>

                    <p className="text-[#98A0AE] text-lg mt-6 max-w-3xl mx-auto leading-8">
                        Start completely free and upgrade only when your
                        portfolio grows.
                    </p>

                </div>

            </section>

            {/* Pricing Cards */}

            <section className="py-20">

                <div className="max-w-6xl mx-auto px-6">

                    <div className="grid md:grid-cols-2 gap-10">

                        {/* Free */}

                        <div className="bg-[#10141E] border border-[#1E2535] rounded-3xl p-10 flex flex-col">

                            <span className="uppercase text-sm tracking-widest text-[#98A0AE]">
                                Free
                            </span>

                            <h2 className="text-6xl font-bold mt-5">
                                ₹0
                            </h2>

                            <p className="text-[#98A0AE] mb-8">
                                Forever
                            </p>

                            <ul className="space-y-5 flex-1">

                                <li>✅ Access all 200+ companies</li>

                                <li>✅ Track up to <b>10 companies</b></li>

                                <li>✅ Real-time WhatsApp alerts</li>

                                <li>✅ Unlimited announcement history</li>

                                <li>✅ Email support</li>

                            </ul>

                            <button
                                onClick={() => navigate("/register")}
                                className="mt-10 border border-[#33D097] text-[#33D097] rounded-xl py-4 font-bold hover:bg-[#33D097] hover:text-black transition"
                            >
                                Get Started Free
                            </button>

                        </div>

                        {/* Premium */}

                        <div className="relative bg-gradient-to-b from-[#1B2E28] to-[#10141E] border-2 border-[#33D097] rounded-3xl p-10 flex flex-col">

                            <span className="absolute -top-4 left-1/2 -translate-x-1/2 bg-[#33D097] text-black font-bold px-5 py-2 rounded-full text-sm">
                                Most Popular
                            </span>

                            <span className="uppercase text-sm tracking-widest text-[#33D097]">
                                Premium
                            </span>

                            <h2 className="text-6xl font-bold mt-5">
                                ₹299
                            </h2>

                            <p className="text-[#98A0AE] mb-8">
                                Per Month
                            </p>

                            <ul className="space-y-5 flex-1">

                                <li>✅ Access all 200+ companies</li>

                                <li>✅ Track up to <b>25 companies</b></li>

                                <li>✅ Real-time WhatsApp alerts</li>

                                <li>✅ Priority alert delivery</li>

                                <li>✅ Premium customer support</li>

                                <li>✅ Early access to new features</li>

                            </ul>

                            <button
                                onClick={() => navigate("/register")}
                                className="mt-10 bg-[#33D097] text-black rounded-xl py-4 font-bold hover:scale-105 transition"
                            >
                                Go Premium →
                            </button>

                        </div>

                    </div>

                </div>

            </section>
            {/* FAQ */}

            <section className="py-20">

                <div className="max-w-4xl mx-auto px-6">

                    <h2 className="text-4xl font-bold text-center mb-12">
                        Pricing FAQ
                    </h2>

                    <details className="bg-[#10141E] border border-[#1E2535] rounded-xl mb-5 p-6">
                        <summary className="cursor-pointer font-bold">
                            Can I cancel anytime?
                        </summary>

                        <p className="mt-4 text-[#98A0AE]">
                            Yes. You can upgrade, downgrade or cancel your
                            Premium subscription at any time.
                        </p>
                    </details>

                    <details className="bg-[#10141E] border border-[#1E2535] rounded-xl mb-5 p-6">
                        <summary className="cursor-pointer font-bold">
                            Is the Free plan really free?
                        </summary>

                        <p className="mt-4 text-[#98A0AE]">
                            Yes. The Free plan has no expiry and allows you to
                            monitor up to 10 companies.
                        </p>
                    </details>

                    <details className="bg-[#10141E] border border-[#1E2535] rounded-xl p-6">
                        <summary className="cursor-pointer font-bold">
                            How do I pay?
                        </summary>

                        <p className="mt-4 text-[#98A0AE]">
                            You can pay securely using UPI, Debit Card,
                            Credit Card and Net Banking.
                        </p>
                    </details>

                </div>

            </section>

            <Footer />

        </div>
    );
}