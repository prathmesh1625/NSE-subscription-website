import React from "react";
import { Link } from "react-router-dom";

export function TermsOfService() {
    return (
        <div className="min-h-screen bg-[#0d0f14] text-[#e8eaf2] font-sans">
            <style>{`
                @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500&display=swap');

                *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

                :root {
                    --bg:          #0d0f14;
                    --bg-raised:   #13161e;
                    --bg-card:     #181c26;
                    --border:      #252a38;
                    --border-soft: #1e2333;
                    --ink:         #e8eaf2;
                    --ink-muted:   #8b90a7;
                    --ink-faint:   #4e5368;
                    --accent:      #4d7cfe;
                    --accent-soft: #1a2340;
                    --accent-text: #7ea4ff;
                    --green:       #34d399;
                    --green-soft:  #0a2218;
                    --green-text:  #6ee7b7;
                    --amber:       #fbbf24;
                    --amber-soft:  #221a08;
                    --amber-text:  #fcd34d;
                    --red:         #f87171;
                    --red-soft:    #200f0f;
                    --red-border:  #3d1515;
                    --radius:      10px;
                }

                html { scroll-behavior: smooth; }

                body {
                    font-family: 'DM Sans', sans-serif;
                    font-size: 15px; line-height: 1.75;
                    color: var(--ink); background: var(--bg);
                    -webkit-font-smoothing: antialiased;
                }

                nav {
                    position: sticky; top: 0; z-index: 100;
                    background: rgba(13,15,20,0.88);
                    backdrop-filter: blur(16px);
                    border-bottom: 1px solid var(--border);
                    padding: 0 2rem; height: 56px;
                    display: flex; align-items: center; justify-content: space-between;
                }
                .nav-logo { font-family: 'DM Serif Display', serif; font-size: 20px; color: var(--ink); text-decoration: none; }
                .nav-badge {
                    font-size: 11px; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase;
                    color: var(--amber-text); background: var(--amber-soft);
                    padding: 4px 10px; border-radius: 20px; border: 1px solid #3a2d10;
                }

                .disclaimer-bar {
                    background: var(--amber-soft); border-bottom: 1px solid #3a2d10;
                    padding: 10px 2rem; display: flex; align-items: flex-start; gap: 10px;
                    font-size: 13px; color: var(--amber-text); line-height: 1.5;
                }
                .disclaimer-bar strong { font-weight: 500; }
                .disclaimer-bar a {
                    margin-left: auto; white-space: nowrap; flex-shrink: 0;
                    color: var(--amber); text-decoration: none; font-weight: 500; font-size: 12px; padding-top: 1px;
                }
                .disclaimer-bar a:hover { text-decoration: underline; }
                .disclaimer-bar svg { color: var(--amber); flex-shrink: 0; margin-top: 1px; }

                .hero {
                    background: var(--bg-raised); border-bottom: 1px solid var(--border);
                    padding: 56px 2rem 48px; text-align: center;
                }
                .hero-eyebrow { font-size: 11px; font-weight: 500; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 14px; }
                .hero h1 { font-family: 'DM Serif Display', serif; font-size: clamp(32px, 5vw, 48px); font-weight: 400; color: var(--ink); letter-spacing: -0.5px; line-height: 1.15; margin-bottom: 16px; }
                .hero-sub { font-size: 15px; color: var(--ink-muted); max-width: 520px; margin: 0 auto 24px; }
                .hero-meta { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--ink-faint); border: 1px solid var(--border); border-radius: 20px; padding: 5px 14px; background: var(--bg-card); }

                .page-wrap { max-width: 1060px; margin: 0 auto; padding: 0 2rem; }
                .content-grid { display: grid; grid-template-columns: 220px 1fr; gap: 0; align-items: start; padding: 56px 0 80px; }

                .toc { position: sticky; top: 72px; padding-right: 40px; }
                .toc-label { font-size: 10px; font-weight: 500; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 14px; }
                .toc a { display: block; font-size: 13px; color: var(--ink-muted); text-decoration: none; padding: 5px 0 5px 14px; border-left: 2px solid var(--border); margin-bottom: 2px; transition: color 0.15s, border-color 0.15s; }
                .toc a:hover { color: var(--accent-text); border-left-color: var(--accent); }

                .doc-body { min-width: 0; }
                .section { padding: 0 0 40px; border-bottom: 1px solid var(--border); margin-bottom: 40px; }
                .section:last-child { border-bottom: none; margin-bottom: 0; }
                .section-tag { display: inline-block; font-size: 10px; font-weight: 500; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 10px; }

                h2 { font-family: 'DM Serif Display', serif; font-size: 24px; font-weight: 400; color: var(--ink); letter-spacing: -0.3px; margin-bottom: 16px; line-height: 1.25; }
                h3 { font-size: 14px; font-weight: 500; color: var(--ink); margin: 20px 0 8px; }
                p { color: var(--ink-muted); margin-bottom: 14px; font-size: 15px; }
                p:last-child { margin-bottom: 0; }
                a { color: var(--accent-text); text-decoration: none; }
                a:hover { text-decoration: underline; }

                .rule-list { list-style: none; margin: 16px 0; }
                .rule-list li { display: flex; align-items: flex-start; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--border-soft); font-size: 14px; color: var(--ink-muted); }
                .rule-list li:last-child { border-bottom: none; }
                .rule-list li::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); flex-shrink: 0; margin-top: 8px; }
                .rule-list.warn li::before { background: var(--red); }

                .summary-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 20px 0; }
                .summary-card { border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; background: var(--bg-card); }
                .s-icon { font-size: 20px; margin-bottom: 10px; display: block; }
                .summary-card strong { display: block; font-size: 13px; font-weight: 500; color: var(--ink); margin-bottom: 4px; }
                .summary-card p { font-size: 12px; color: var(--ink-muted); margin: 0; line-height: 1.5; }

                .notice {
                    border-left: 3px solid var(--amber); background: var(--amber-soft);
                    border-radius: 0 var(--radius) var(--radius) 0;
                    padding: 14px 18px; margin: 20px 0;
                }
                .notice p { font-size: 13px; color: var(--amber-text); margin: 0; line-height: 1.6; }
                .notice strong { font-weight: 500; }
                .notice.info { border-left-color: var(--accent); background: var(--accent-soft); }
                .notice.info p { color: var(--accent-text); }

                .plan-cards { display: flex; gap: 10px; margin: 16px 0; }
                .plan-card { flex: 1; border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; background: var(--bg-card); }
                .plan-card.featured { border-color: var(--accent); background: var(--accent-soft); }
                .plan-name { font-size: 11px; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 6px; }
                .plan-card.featured .plan-name { color: var(--accent-text); }
                .plan-card h3 { font-size: 16px; margin: 0 0 10px; color: var(--ink); }
                .plan-card ul { list-style: none; }
                .plan-card ul li { font-size: 12px; color: var(--ink-muted); padding: 3px 0; display: flex; gap: 6px; }
                .plan-card ul li::before { content: '✓'; color: var(--green); font-weight: 500; flex-shrink: 0; }

                .contact-box { display: flex; align-items: center; gap: 16px; border: 1px solid var(--border); border-radius: var(--radius); padding: 20px 24px; background: var(--bg-card); margin-top: 16px; }
                .contact-icon { width: 44px; height: 44px; border-radius: 10px; background: var(--accent-soft); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
                .contact-icon svg { width: 20px; height: 20px; color: var(--accent-text); }
                .contact-box p { margin: 0; font-size: 14px; color: var(--ink-muted); }

                footer { border-top: 1px solid var(--border); padding: 24px 2rem; display: flex; align-items: center; justify-content: space-between; max-width: 1060px; margin: 0 auto; }
                footer p { font-size: 12px; color: var(--ink-faint); margin: 0; }
                footer a { color: var(--ink-faint); text-decoration: none; }
                footer a:hover { color: var(--accent-text); }

                @media (max-width: 720px) {
                    .content-grid { grid-template-columns: 1fr; }
                    .toc { display: none; }
                    .summary-grid { grid-template-columns: repeat(2, 1fr); }
                    .plan-cards { flex-direction: column; }
                    footer { flex-direction: column; gap: 8px; text-align: center; }
                    .disclaimer-bar { flex-wrap: wrap; }
                    .disclaimer-bar a { margin-left: 0; }
                }
            `}</style>

            <nav>
                <Link to="/" className="nav-logo">EquityAlerts</Link>
                <span className="nav-badge">Terms of Service</span>
            </nav>

            <div className="disclaimer-bar">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" width="14" height="14">
                    <circle cx="8" cy="8" r="6" />
                    <path d="M8 5v3.5M8 10.5v.5" />
                </svg>
                <span><strong>Disclaimer:</strong> EquityAlerts is an information aggregation platform only. Nothing on this platform constitutes investment advice, a recommendation to buy or sell securities, or financial guidance of any kind. All trading decisions are made solely at your own risk.</span>
                <Link to="/disclaimer">Read full disclaimer →</Link>
            </div>

            <div className="hero">
                <div className="page-wrap">
                    <p className="hero-eyebrow">Legal</p>
                    <h1>Terms of Service</h1>
                    <p className="hero-sub">By using EquityAlerts, you agree to these terms. Please read them carefully before creating an account or using our services.</p>
                    <span className="hero-meta">
                        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="13" height="13">
                            <rect x="2" y="3" width="12" height="11" rx="1.5" />
                            <path d="M5 3V2a1 1 0 0 1 2 0v1M9 3V2a1 1 0 0 1 2 0v1M2 7h12" />
                        </svg>
                        Last updated: June 2025
                    </span>
                </div>
            </div>

            <div className="page-wrap">
                <div className="content-grid">
                    <aside className="toc">
                        <p className="toc-label">Contents</p>
                        <a href="#about">About EquityAlerts</a>
                        <a href="#eligibility">Eligibility</a>
                        <a href="#accounts">Accounts</a>
                        <a href="#subscriptions">Subscriptions</a>
                        <a href="#acceptable-use">Acceptable Use</a>
                        <a href="#whatsapp">WhatsApp Notifications</a>
                        <a href="#disclaimer">Disclaimer</a>
                        <a href="#liability">Liability</a>
                        <a href="#termination">Termination</a>
                        <a href="#governing-law">Governing Law</a>
                        <a href="#changes">Changes to Terms</a>
                        <a href="#contact">Contact</a>
                    </aside>

                    <main className="doc-body">

                        <div className="section">
                            <p>These Terms of Service ("Terms") govern your access to and use of EquityAlerts, a platform that aggregates BSE and NSE company filings, allows you to build a personal watchlist, and delivers real-time announcements to you via WhatsApp.</p>
                            <p><strong style={{ color: "var(--ink)" }}>EquityAlerts is a product of EagleSwift Global Advisors Private Limited</strong>, a company incorporated in India. "EquityAlerts" is the product name under which EagleSwift Global Advisors Private Limited operates this platform and its WhatsApp alerts service.</p>
                            <p>These Terms constitute a legally binding agreement between you and EagleSwift Global Advisors Private Limited (operating as EquityAlerts). If you do not agree, please do not use our platform.</p>
                            <div className="summary-grid">
                                <div className="summary-card">
                                    <span className="s-icon">📋</span>
                                    <strong>What we offer</strong>
                                    <p>Stock exchange filing aggregation, watchlist management, and WhatsApp-based alerts.</p>
                                </div>
                                <div className="summary-card">
                                    <span className="s-icon">⚠️</span>
                                    <strong>Not investment advice</strong>
                                    <p>EquityAlerts provides information only. Nothing here constitutes a recommendation to buy or sell securities.</p>
                                </div>
                                <div className="summary-card">
                                    <span className="s-icon">🇮🇳</span>
                                    <strong>Indian law applies</strong>
                                    <p>These Terms are governed by the laws of India. Disputes are subject to jurisdiction in Mumbai.</p>
                                </div>
                            </div>
                        </div>

                        <div className="section" id="about">
                            <span className="section-tag">01</span>
                            <h2>About EquityAlerts</h2>
                            <p>EquityAlerts is a product of <strong style={{ color: "var(--ink)" }}>EagleSwift Global Advisors Private Limited</strong>. All references to "we", "our", or "us" in these Terms mean EagleSwift Global Advisors Private Limited.</p>
                            <p>EquityAlerts is an information aggregation platform. We source publicly available exchange filings from the Bombay Stock Exchange (BSE) and National Stock Exchange (NSE) and present them in a structured, searchable format. Users can add companies to a watchlist and opt in to receive WhatsApp notifications when those companies make new filings or announcements.</p>
                            <p><strong style={{ color: "var(--ink)" }}>EquityAlerts is not a stockbroker, investment advisor, or portfolio manager.</strong> We are not registered with SEBI as an investment advisor. Nothing on this platform constitutes investment, financial, or legal advice.</p>
                        </div>

                        <div className="section" id="eligibility">
                            <span className="section-tag">02</span>
                            <h2>Eligibility</h2>
                            <p>To use EquityAlerts, you must:</p>
                            <ul className="rule-list">
                                <li>Be at least 18 years of age</li>
                                <li>Be a resident or citizen of India, or a person otherwise permitted by applicable law to use such a service</li>
                                <li>Have a valid Indian mobile number (SIM) that can receive SMS messages</li>
                                <li>Not be prohibited from receiving our services under any applicable laws</li>
                            </ul>
                            <p>By creating an account, you represent and warrant that you meet all eligibility requirements.</p>
                        </div>

                        <div className="section" id="accounts">
                            <span className="section-tag">03</span>
                            <h2>Accounts &amp; Registration</h2>
                            <p>You register on EquityAlerts using your mobile phone number, which is verified via a one-time password (OTP) delivered by SMS. You are responsible for:</p>
                            <ul className="rule-list">
                                <li>Keeping your account credentials confidential</li>
                                <li>All activity that occurs under your account</li>
                                <li>Notifying us immediately if you suspect unauthorised access</li>
                                <li>Ensuring the phone number registered is one you own — do not register on behalf of another person</li>
                            </ul>
                            <p>We reserve the right to suspend or terminate accounts that violate these Terms or are used for fraudulent purposes.</p>
                        </div>

                        <div className="section" id="subscriptions">
                            <span className="section-tag">04</span>
                            <h2>Subscriptions &amp; Payments</h2>
                            <div className="plan-cards">
                                <div className="plan-card">
                                    <p className="plan-name">Basic</p>
                                    <h3>Free</h3>
                                    <ul>
                                        <li>Browse company listings</li>
                                        <li>Search NSE/BSE filings</li>
                                        <li>Limited watchlist</li>
                                    </ul>
                                </div>
                                <div className="plan-card featured">
                                    <p className="plan-name">Pro</p>
                                    <h3>Paid subscription</h3>
                                    <ul>
                                        <li>Unlimited watchlist</li>
                                        <li>Real-time WhatsApp alerts</li>
                                        <li>PDF filing delivery</li>
                                        <li>Priority support</li>
                                    </ul>
                                </div>
                            </div>
                            <h3>Billing</h3>
                            <p>Paid subscriptions are processed via Razorpay. By subscribing, you authorise us to charge the applicable fee to your chosen payment method on a recurring basis as per your selected plan.</p>
                            <h3>Cancellation &amp; Refunds</h3>
                            <p>You may cancel your subscription at any time from your account settings. Cancellation takes effect at the end of your current billing period. We do not offer refunds for partially used subscription periods unless required by applicable law.</p>
                            <div className="notice">
                                <p><strong>Note:</strong> Subscription fees are exclusive of applicable taxes. GST or other taxes may be charged in addition to the listed price.</p>
                            </div>
                        </div>

                        <div className="section" id="acceptable-use">
                            <span className="section-tag">05</span>
                            <h2>Acceptable Use</h2>
                            <p>You agree to use EquityAlerts only for lawful purposes. The following are strictly prohibited:</p>
                            <ul className="rule-list warn">
                                <li>Scraping, crawling, or automatically harvesting data from EquityAlerts without our express written permission</li>
                                <li>Using EquityAlerts data to build competing products or services</li>
                                <li>Attempting to gain unauthorised access to our systems, servers, or databases</li>
                                <li>Transmitting malware, spam, or disruptive code through our platform</li>
                                <li>Sharing your account credentials with third parties or operating multiple accounts to circumvent subscription limits</li>
                                <li>Using our WhatsApp notification service to relay messages to other parties at scale</li>
                                <li>Misrepresenting your identity or affiliation when using EquityAlerts</li>
                            </ul>
                            <p>Violation of these rules may result in immediate account suspension and, where applicable, legal action.</p>
                        </div>

                        <div className="section" id="whatsapp">
                            <span className="section-tag">06</span>
                            <h2>WhatsApp Notification Service</h2>
                            <p>EquityAlerts delivers filing notifications via the WhatsApp Cloud API, operated by Meta Platforms, Inc. By opting in to WhatsApp notifications, you acknowledge and agree that:</p>
                            <ul className="rule-list">
                                <li>Notifications are delivered on a best-effort basis — we do not guarantee delivery times, especially during high-volume periods or platform outages</li>
                                <li>WhatsApp's 24-hour messaging window and Meta's policies may affect message delivery</li>
                                <li>You are responsible for maintaining a valid, active WhatsApp account to receive alerts</li>
                                <li>You can opt out of notifications at any time by contacting us or updating your account preferences</li>
                                <li>Standard data charges from your mobile carrier may apply</li>
                            </ul>
                            <div className="notice info">
                                <p><strong>Important:</strong> EquityAlerts filing alerts are informational only. We are not responsible for any trading decisions made on the basis of notifications received through our platform.</p>
                            </div>
                        </div>

                        <div className="section" id="disclaimer">
                            <span className="section-tag">07</span>
                            <h2>Disclaimer of Warranties</h2>
                            <p>EquityAlerts is provided on an "as is" and "as available" basis without warranties of any kind, express or implied. We do not warrant that:</p>
                            <ul className="rule-list">
                                <li>The platform will be uninterrupted, error-free, or free of viruses or harmful components</li>
                                <li>Filing data will be complete, accurate, or delivered in real time — exchange data is sourced from BSE/NSE feeds and may be subject to delays or inaccuracies</li>
                                <li>The platform will meet your specific requirements or expectations</li>
                            </ul>
                            <p>Use of EquityAlerts is entirely at your own risk. We expressly disclaim all warranties to the fullest extent permitted by law.</p>
                        </div>

                        <div className="section" id="liability">
                            <span className="section-tag">08</span>
                            <h2>Limitation of Liability</h2>
                            <p>To the maximum extent permitted by applicable Indian law, EquityAlerts, its directors, employees, and agents shall not be liable for any indirect, incidental, special, consequential, or punitive damages — including financial losses, loss of data, or loss of goodwill — arising out of or in connection with your use of the platform.</p>
                            <p>Our total liability to you for any claim arising under these Terms shall not exceed the amount paid by you to EquityAlerts in the three months preceding the claim.</p>
                            <div className="notice">
                                <p><strong>Reminder:</strong> EquityAlerts does not provide investment advice. Any financial decisions you make based on information from our platform are solely your responsibility.</p>
                            </div>
                        </div>

                        <div className="section" id="termination">
                            <span className="section-tag">09</span>
                            <h2>Termination</h2>
                            <p>Either party may terminate the relationship under these Terms at any time:</p>
                            <ul className="rule-list">
                                <li><strong style={{ color: "var(--ink)" }}>You</strong> may delete your account from settings. Deletion removes your personal data as described in our Privacy Policy, subject to legal retention obligations.</li>
                                <li><strong style={{ color: "var(--ink)" }}>We</strong> may suspend or terminate your account without notice if you breach these Terms, engage in fraudulent activity, or if we are required to do so by law.</li>
                            </ul>
                            <p>Upon termination, your right to use EquityAlerts ceases immediately. Provisions that by their nature should survive termination — including disclaimers, limitation of liability, and governing law — will continue to apply.</p>
                        </div>

                        <div className="section" id="governing-law">
                            <span className="section-tag">10</span>
                            <h2>Governing Law &amp; Disputes</h2>
                            <p>These Terms are governed by and construed in accordance with the laws of India, without regard to conflict of law principles. Any disputes arising from these Terms or your use of EquityAlerts shall be subject to the exclusive jurisdiction of the courts located in Mumbai, Maharashtra.</p>
                            <p>We encourage you to reach out to us first at <a href="mailto:support@equityalerts.ai">support@equityalerts.ai</a> before initiating any legal proceedings — most concerns can be resolved quickly and informally.</p>
                        </div>

                        <div className="section" id="changes">
                            <span className="section-tag">11</span>
                            <h2>Changes to These Terms</h2>
                            <p>We may update these Terms from time to time to reflect changes in our services, applicable law, or business practices. When we do, we will update the "Last updated" date at the top of this page and, for material changes, notify you via email or a prominent notice on the platform.</p>
                            <p>Your continued use of EquityAlerts after changes take effect constitutes your acceptance of the revised Terms.</p>
                        </div>

                        <div className="section" id="contact">
                            <span className="section-tag">12</span>
                            <h2>Contact Us</h2>
                            <p>Questions about these Terms, requests to exercise your rights, or general support — we're here to help.</p>
                            <div className="contact-box">
                                <div className="contact-icon">
                                    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
                                        <path d="M3 5h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z" />
                                        <path d="m2 6 8 5 8-5" />
                                    </svg>
                                </div>
                                <div>
                                    <p>Email us at <a href="mailto:support@equityalerts.ai">support@equityalerts.ai</a></p>
                                    <p style={{ fontSize: "12px", marginTop: "2px" }}>EquityAlerts, a product of EagleSwift Global Advisors Private Limited · Mumbai, Maharashtra, India</p>
                                </div>
                            </div>
                        </div>

                    </main>
                </div>
            </div>

            <footer>
                <p>© 2025 EagleSwift Global Advisors Private Limited. All rights reserved.</p>
                <p>EquityAlerts is a product of EagleSwift Global Advisors Private Limited.</p>
                <p>
                    <Link to="/privacy-policy">Privacy Policy</Link>
                    &nbsp;·&nbsp;
                    <Link to="/disclaimer">Disclaimer</Link>
                    &nbsp;·&nbsp;
                    <a href="#">Cookie Preferences</a>
                </p>
            </footer>

        </div>
    );
}

export default TermsOfService;