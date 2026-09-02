import { Link } from "react-router-dom";

export default function Footer() {
    return (
        <footer className="border-t border-[#1E2535] bg-[#07090F]/85 py-[60px] pb-8 text-left">
            <div className="max-w-[1180px] mx-auto px-6">

                {/* Top Footer */}
                <div className="grid grid-cols-2 md:grid-cols-[1.4fr_1fr_1fr_1fr_1fr] gap-10 mb-12">

                    {/* Logo */}
                    <div>
                        <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-lg bg-gradient-to-r from-[#33D097] to-[#26B97F] flex items-center justify-center">
                                <svg
                                    className="w-4 h-4"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                >
                                    <path
                                        d="M3 17l5-6 4 4 6-8 3 3"
                                        stroke="#04130C"
                                        strokeWidth="2.5"
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                    />
                                </svg>
                            </div>

                            <span className="text-white font-bold text-lg">
                                EquityAlerts
                            </span>
                        </div>

                        <p className="text-[#646E7E] text-sm mt-4 leading-6">
                            Company announcement monitoring for NSE & BSE.
                            Informational alerts only — not investment advice.
                        </p>

                        {/* Ownership disclosure — EquityAlerts is the product
                            name; the legal entity behind it is EagleSwift
                            Global Advisors Private Limited. Stated here (and on
                            every legal page) so the relationship is verifiable
                            by users and by platform reviewers. */}
                        <p className="text-[#98A0AE] text-sm mt-4 leading-6">
                            EquityAlerts is a product of{" "}
                            <span className="font-semibold text-[#C7CDD8]">
                                EagleSwift Global Advisors Private Limited
                            </span>
                            .
                        </p>
                    </div>
                    
                    {/* Support */}
                    <div>
                        <h4 className="text-xs uppercase tracking-wider text-[#646E7E] font-bold mb-4">
                            Support
                        </h4>

                        <div className="space-y-3">
                            <a
                                href="mailto:support@equityalerts.ai"
                                className="block text-[#98A0AE] hover:text-[#33D097]"
                            >
                                Contact
                            </a>

                            <Link
                                to="/faq"
                                className="block text-[#98A0AE] hover:text-[#33D097]"
                            >
                                FAQ
                            </Link>
                        </div>
                    </div>

                    {/* Legal */}
                    <div>
                        <h4 className="text-xs uppercase tracking-wider text-[#646E7E] font-bold mb-4">
                            Legal
                        </h4>

                        <div className="space-y-3">
                            <Link
                                to="/privacy-policy"
                                className="block text-[#98A0AE] hover:text-[#33D097]"
                            >
                                Privacy Policy
                            </Link>

                            <Link
                                to="/terms-of-service"
                                className="block text-[#98A0AE] hover:text-[#33D097]"
                            >
                                Terms of Service
                            </Link>

                            <Link
                                to="/disclaimer"
                                className="block text-[#98A0AE] hover:text-[#33D097]"
                            >
                                Disclaimer
                            </Link>
                        </div>
                    </div>
                </div>

                {/* Bottom Footer */}
                <div className="border-t border-[#1E2535] pt-6 flex flex-col md:flex-row justify-between items-center gap-4">

                    <p className="text-[#646E7E] text-sm text-center md:text-left">
                        © {new Date().getFullYear()} EagleSwift Global Advisors
                        Private Limited. All rights reserved. EquityAlerts is a
                        product of EagleSwift Global Advisors Private Limited.
                    </p>

                    <div className="flex flex-wrap justify-center items-center gap-x-4 gap-y-2 text-[#9298A0]">

                        <Link
                            to="/privacy-policy"
                            className="hover:text-[#33D097] transition"
                        >
                            Privacy Policy
                        </Link>

                        <span className="hidden sm:inline">|</span>

                        <Link
                            to="/terms-of-service"
                            className="hover:text-[#33D097] transition"
                        >
                            Terms of Service
                        </Link>

                        <span className="hidden sm:inline">|</span>

                        <Link
                            to="/disclaimer"
                            className="hover:text-[#33D097] transition"
                        >
                            Disclaimer
                        </Link>

                    </div>

                </div>

            </div>
        </footer>
    );
}