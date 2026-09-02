import React from "react";
import { Link } from "react-router-dom";

export function PrivacyPolicy() {
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
                    --radius:      10px;
                }

                html { scroll-behavior: smooth; }

                body {
                    font-family: 'DM Sans', sans-serif;
                    font-size: 15px;
                    line-height: 1.75;
                    color: var(--ink);
                    background: var(--bg);
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
                .nav-logo {
                    font-family: 'DM Serif Display', serif;
                    font-size: 20px; color: var(--ink);
                    text-decoration: none; letter-spacing: -0.3px;
                }
                .nav-badge {
                    font-size: 11px; font-weight: 500;
                    letter-spacing: 0.06em; text-transform: uppercase;
                    color: var(--accent-text); background: var(--accent-soft);
                    padding: 4px 10px; border-radius: 20px;
                    border: 1px solid #2a3560;
                }

                .disclaimer-bar {
                    background: var(--amber-soft);
                    border-bottom: 1px solid #3a2d10;
                    padding: 10px 2rem;
                    display: flex; align-items: flex-start; gap: 10px;
                    font-size: 13px; color: var(--amber-text); line-height: 1.5;
                }
                .disclaimer-bar strong { font-weight: 500; }
                .disclaimer-bar a {
                    margin-left: auto; white-space: nowrap; flex-shrink: 0;
                    color: var(--amber); text-decoration: none;
                    font-weight: 500; font-size: 12px; padding-top: 1px;
                }
                .disclaimer-bar a:hover { text-decoration: underline; }
                .disclaimer-bar svg { color: var(--amber); flex-shrink: 0; margin-top: 1px; }

                .hero {
                    background: var(--bg-raised);
                    border-bottom: 1px solid var(--border);
                    padding: 56px 2rem 48px; text-align: center;
                }
                .hero-eyebrow {
                    font-size: 11px; font-weight: 500;
                    letter-spacing: 0.1em; text-transform: uppercase;
                    color: var(--ink-faint); margin-bottom: 14px;
                }
                .hero h1 {
                    font-family: 'DM Serif Display', serif;
                    font-size: clamp(32px, 5vw, 48px); font-weight: 400;
                    color: var(--ink); letter-spacing: -0.5px;
                    line-height: 1.15; margin-bottom: 16px;
                }
                .hero-sub {
                    font-size: 15px; color: var(--ink-muted);
                    max-width: 480px; margin: 0 auto 24px;
                }
                .hero-meta {
                    display: inline-flex; align-items: center; gap: 6px;
                    font-size: 12px; color: var(--ink-faint);
                    border: 1px solid var(--border); border-radius: 20px;
                    padding: 5px 14px; background: var(--bg-card);
                }

                .page-wrap { max-width: 1060px; margin: 0 auto; padding: 0 2rem; }

                .content-grid {
                    display: grid; grid-template-columns: 220px 1fr;
                    gap: 0; align-items: start; padding: 56px 0 80px;
                }

                .toc { position: sticky; top: 72px; padding-right: 40px; }
                .toc-label {
                    font-size: 10px; font-weight: 500;
                    letter-spacing: 0.1em; text-transform: uppercase;
                    color: var(--ink-faint); margin-bottom: 14px;
                }
                .toc a {
                    display: block; font-size: 13px; color: var(--ink-muted);
                    text-decoration: none; padding: 5px 0 5px 14px;
                    border-left: 2px solid var(--border);
                    margin-bottom: 2px; transition: color 0.15s, border-color 0.15s;
                }
                .toc a:hover { color: var(--accent-text); border-left-color: var(--accent); }

                .doc-body { min-width: 0; }

                .section {
                    padding: 0 0 40px;
                    border-bottom: 1px solid var(--border);
                    margin-bottom: 40px;
                }
                .section:last-child { border-bottom: none; margin-bottom: 0; }

                .section-tag {
                    display: inline-block; font-size: 10px; font-weight: 500;
                    letter-spacing: 0.1em; text-transform: uppercase;
                    color: var(--ink-faint); margin-bottom: 10px;
                }
                h2 {
                    font-family: 'DM Serif Display', serif;
                    font-size: 24px; font-weight: 400; color: var(--ink);
                    letter-spacing: -0.3px; margin-bottom: 16px; line-height: 1.25;
                }
                p { color: var(--ink-muted); margin-bottom: 14px; font-size: 15px; }
                p:last-child { margin-bottom: 0; }
                a { color: var(--accent-text); text-decoration: none; }
                a:hover { text-decoration: underline; }

                .data-grid {
                    display: grid; grid-template-columns: repeat(2, 1fr);
                    gap: 12px; margin-top: 20px;
                }
                .data-card {
                    border: 1px solid var(--border); border-radius: var(--radius);
                    padding: 16px 18px; background: var(--bg-card);
                }
                .data-card-icon {
                    width: 32px; height: 32px; border-radius: 8px;
                    background: var(--accent-soft);
                    display: flex; align-items: center; justify-content: center;
                    margin-bottom: 10px;
                }
                .data-card-icon svg { width: 16px; height: 16px; color: var(--accent-text); }
                .data-card strong { display: block; font-size: 13px; font-weight: 500; color: var(--ink); margin-bottom: 4px; }
                .data-card span { font-size: 13px; color: var(--ink-muted); }

                .purpose-list { list-style: none; margin-top: 16px; }
                .purpose-list li {
                    display: flex; align-items: flex-start; gap: 10px;
                    padding: 10px 0; border-bottom: 1px solid var(--border-soft);
                    font-size: 14px; color: var(--ink-muted);
                }
                .purpose-list li:last-child { border-bottom: none; }
                .purpose-list li::before {
                    content: ''; width: 6px; height: 6px; border-radius: 50%;
                    background: var(--accent); flex-shrink: 0; margin-top: 8px;
                }

                .partner-list { margin-top: 20px; display: flex; flex-direction: column; gap: 10px; }
                .partner-row {
                    display: flex; align-items: flex-start; gap: 14px;
                    border: 1px solid var(--border); border-radius: var(--radius);
                    padding: 14px 16px; background: var(--bg-card);
                }
                .partner-logo {
                    width: 36px; height: 36px; border-radius: 8px; flex-shrink: 0;
                    display: flex; align-items: center; justify-content: center;
                    font-weight: 500; font-size: 12px; letter-spacing: 0.02em;
                }
                .partner-logo.razorpay { background: #1a2340; color: var(--accent-text); }
                .partner-logo.meta     { background: #101e3a; color: #7eb8ff; }
                .partner-logo.google   { background: #261510; color: #f87171; }
                .partner-logo.cs       { background: #221a08; color: var(--amber-text); }
                .partner-info strong   { display: block; font-size: 13px; font-weight: 500; color: var(--ink); margin-bottom: 2px; }
                .partner-info span     { font-size: 13px; color: var(--ink-muted); line-height: 1.5; }
                .consent-pill {
                    margin-left: auto; flex-shrink: 0;
                    font-size: 11px; font-weight: 500;
                    padding: 3px 10px; border-radius: 20px;
                }
                .consent-pill.always  { background: var(--green-soft); color: var(--green-text); border: 1px solid #174436; }
                .consent-pill.consent { background: var(--amber-soft); color: var(--amber-text); border: 1px solid #3a2d10; }

                .rights-grid {
                    display: grid; grid-template-columns: repeat(3, 1fr);
                    gap: 10px; margin-top: 20px;
                }
                .right-card {
                    border: 1px solid var(--border); border-radius: var(--radius);
                    padding: 16px; background: var(--bg-card);
                }
                .right-number {
                    font-family: 'DM Serif Display', serif; font-size: 28px;
                    color: var(--border); line-height: 1; margin-bottom: 8px;
                }
                .right-card strong { display: block; font-size: 13px; font-weight: 500; color: var(--ink); margin-bottom: 4px; }
                .right-card p { font-size: 12px; color: var(--ink-muted); margin: 0; line-height: 1.5; }

                .cookie-types { display: flex; flex-direction: column; gap: 8px; margin-top: 16px; }
                .cookie-row {
                    display: flex; align-items: center; justify-content: space-between; gap: 16px;
                    background: var(--bg-card); border: 1px solid var(--border);
                    border-radius: var(--radius); padding: 12px 16px;
                }
                .cookie-left strong { display: block; font-size: 13px; font-weight: 500; color: var(--ink); margin-bottom: 2px; }
                .cookie-left span   { font-size: 12px; color: var(--ink-muted); }
                .toggle-mock {
                    width: 36px; height: 20px; border-radius: 10px;
                    flex-shrink: 0; display: flex; align-items: center; padding: 2px;
                }
                .toggle-mock.on  { background: var(--green); justify-content: flex-end; }
                .toggle-mock.off { background: var(--border); justify-content: flex-start; }
                .toggle-mock .knob { width: 16px; height: 16px; border-radius: 50%; background: white; }

                .contact-box {
                    display: flex; align-items: center; gap: 16px;
                    border: 1px solid var(--border); border-radius: var(--radius);
                    padding: 20px 24px; background: var(--bg-card); margin-top: 16px;
                }
                .contact-icon {
                    width: 44px; height: 44px; border-radius: 10px;
                    background: var(--accent-soft);
                    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
                }
                .contact-icon svg { width: 20px; height: 20px; color: var(--accent-text); }
                .contact-box p { margin: 0; font-size: 14px; color: var(--ink-muted); }

                footer {
                    border-top: 1px solid var(--border);
                    padding: 24px 2rem;
                    display: flex; align-items: center; justify-content: space-between;
                    max-width: 1060px; margin: 0 auto;
                }
                footer p { font-size: 12px; color: var(--ink-faint); margin: 0; }
                footer a { color: var(--ink-faint); text-decoration: none; }
                footer a:hover { color: var(--accent-text); }

                @media (max-width: 720px) {
                    .content-grid { grid-template-columns: 1fr; }
                    .toc { display: none; }
                    .data-grid { grid-template-columns: 1fr; }
                    .rights-grid { grid-template-columns: repeat(2, 1fr); }
                    footer { flex-direction: column; gap: 8px; text-align: center; }
                    .disclaimer-bar { flex-wrap: wrap; }
                    .disclaimer-bar a { margin-left: 0; }
                }
            `}</style>

            <nav>
                <Link to="/" className="nav-logo">EquityAlerts</Link>
                <span className="nav-badge">Privacy Policy</span>
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
                    <h1>Privacy Policy</h1>
                    <p className="hero-sub">How we collect, use, and protect your personal data when you use EquityAlerts.</p>
                    <span className="hero-meta">
                        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" width="13" height="13">
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
                        <a href="#data-collect">Data We Collect</a>
                        <a href="#how-use">How We Use It</a>
                        <a href="#data-sharing">Data Sharing</a>
                        <a href="#rights">Your Rights</a>
                        <a href="#cookies">Cookies</a>
                        <a href="#security">Security</a>
                        <a href="#retention">Data Retention</a>
                        <a href="#contact">Contact Us</a>
                    </aside>

                    <main className="doc-body">

                        <div className="section">
                            <p><strong style={{ color: "var(--ink)" }}>EquityAlerts is a product of EagleSwift Global Advisors Private Limited</strong>, a company incorporated in India. EagleSwift Global Advisors Private Limited is the data fiduciary responsible for the personal data described in this policy.</p>
                            <p>EquityAlerts ("we", "our", or "us" — meaning EagleSwift Global Advisors Private Limited) operates a platform that lets you monitor listed company announcements from NSE and BSE, build a watchlist, and receive real-time notifications via WhatsApp. This Privacy Policy explains what personal data we collect, how we use it, who we share it with, and what rights you have under the <strong style={{ color: "var(--ink)" }}>Digital Personal Data Protection Act, 2023</strong> (DPDP Act).</p>
                            <p>By using EquityAlerts, you agree to the practices described in this policy.</p>
                        </div>

                        <div className="section" id="data-collect">
                            <span className="section-tag">01</span>
                            <h2>Data We Collect</h2>
                            <p>We collect only what is necessary to provide a reliable, personalised experience.</p>
                            <div className="data-grid">
                                <div className="data-card">
                                    <div className="data-card-icon">
                                        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
                                            <path d="M10 2a4 4 0 1 1 0 8 4 4 0 0 1 0-8zm-7 14c0-3.3 3.1-6 7-6s7 2.7 7 6" />
                                        </svg>
                                    </div>
                                    <strong>Phone number</strong>
                                    <span>Used for account authentication via SMS OTP (MSG91) and for delivering filing notifications via WhatsApp.</span>
                                </div>
                                <div className="data-card">
                                    <div className="data-card-icon">
                                        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
                                            <path d="M3 5h14a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z" />
                                            <path d="m2 6 8 5 8-5" />
                                        </svg>
                                    </div>
                                    <strong>Email address</strong>
                                    <span>Provided during subscription sign-up or when you contact our support team.</span>
                                </div>
                                <div className="data-card">
                                    <div className="data-card-icon">
                                        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
                                            <path d="M2 14 7 4l5 7 3-4 3 7H2z" />
                                        </svg>
                                    </div>
                                    <strong>Usage data</strong>
                                    <span>Pages visited, features used, watchlist activity, and search queries — collected through analytics tools.</span>
                                </div>
                                <div className="data-card">
                                    <div className="data-card-icon">
                                        <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
                                            <rect x="3" y="5" width="14" height="10" rx="1.5" />
                                            <path d="M7 18h6M10 15v3" />
                                        </svg>
                                    </div>
                                    <strong>Device information</strong>
                                    <span>Browser type, OS, screen resolution, and IP address — collected for security and analytics.</span>
                                </div>
                            </div>
                        </div>

                        <div className="section" id="how-use">
                            <span className="section-tag">02</span>
                            <h2>How We Use Your Data</h2>
                            <p>Your data is used solely to provide and improve EquityAlerts. We do not use it for purposes beyond what you would reasonably expect.</p>
                            <ul className="purpose-list">
                                <li>Authenticate your identity and manage your account securely</li>
                                <li>Process subscriptions and payments</li>
                                <li>Send SMS one-time passwords (OTPs) via MSG91 for authentication, transactional WhatsApp messages — payment confirmations and stock filing alerts — via Meta Cloud API</li>
                                <li>Analyse usage patterns to improve platform features and performance</li>
                                <li>Respond to support inquiries promptly</li>
                            </ul>
                        </div>

                        <div className="section" id="data-sharing">
                            <span className="section-tag">03</span>
                            <h2>Data Sharing</h2>
                            <p>We do not sell your personal data. We share data only with the service providers below, strictly for operational purposes.</p>
                            <div className="partner-list">
                                <div className="partner-row">
                                    <div className="partner-logo razorpay">Rpay</div>
                                    <div className="partner-info">
                                        <strong>Razorpay</strong>
                                        <span>Payment processing — name, email, phone number, and transaction details.</span>
                                    </div>
                                    <span className="consent-pill always">Always on</span>
                                </div>
                                <div className="partner-row">
                                    <div className="partner-logo meta">M91</div>
                                    <div className="partner-info">
                                        <strong>MSG91</strong>
                                        <span>SMS OTP delivery for account authentication via the MSG91 widget.</span>
                                    </div>
                                    <span className="consent-pill always">Always on</span>
                                </div>
                                <div className="partner-row">
                                    <div className="partner-logo meta">Meta</div>
                                    <div className="partner-info">
                                        <strong>WhatsApp / Meta</strong>
                                        <span>Transactional filing notifications via the WhatsApp Cloud API.</span>
                                    </div>
                                    <span className="consent-pill always">Always on</span>
                                </div>
                                <div className="partner-row">
                                    <div className="partner-logo google">GA</div>
                                    <div className="partner-info">
                                        <strong>Google Analytics</strong>
                                        <span>Anonymised usage analytics to understand how users interact with our platform.</span>
                                    </div>
                                    <span className="consent-pill consent">Consent required</span>
                                </div>
                                <div className="partner-row">
                                    <div className="partner-logo meta">Meta</div>
                                    <div className="partner-info">
                                        <strong>Meta (Facebook) Pixel</strong>
                                        <span>Ad campaign measurement and retargeting. Meta may use this data per their own <a href="https://www.facebook.com/privacy/policy/" target="_blank" rel="noopener">Data Policy</a>.</span>
                                    </div>
                                    <span className="consent-pill consent">Consent required</span>
                                </div>
                                <div className="partner-row">
                                    <div className="partner-logo cs">CS</div>
                                    <div className="partner-info">
                                        <strong>ContentSquare</strong>
                                        <span>Session replay and heatmap analytics to improve user experience. Only activated after cookie consent.</span>
                                    </div>
                                    <span className="consent-pill consent">Consent required</span>
                                </div>
                            </div>
                        </div>

                        <div className="section" id="rights">
                            <span className="section-tag">04</span>
                            <h2>Your Rights Under DPDP Act, 2023</h2>
                            <p>Under India's Digital Personal Data Protection Act, 2023, you have the following rights. To exercise any of them, contact us at <a href="mailto:support@equityalerts.ai">support@equityalerts.ai</a>.</p>
                            <div className="rights-grid">
                                <div className="right-card">
                                    <div className="right-number">01</div>
                                    <strong>Access</strong>
                                    <p>Request a summary of the personal data we hold about you.</p>
                                </div>
                                <div className="right-card">
                                    <div className="right-number">02</div>
                                    <strong>Correction</strong>
                                    <p>Request correction of inaccurate or incomplete data.</p>
                                </div>
                                <div className="right-card">
                                    <div className="right-number">03</div>
                                    <strong>Erasure</strong>
                                    <p>Request deletion of your data, subject to legal obligations.</p>
                                </div>
                                <div className="right-card">
                                    <div className="right-number">04</div>
                                    <strong>Grievance Redressal</strong>
                                    <p>Raise concerns about how your data is handled.</p>
                                </div>
                                <div className="right-card">
                                    <div className="right-number">05</div>
                                    <strong>Nominate</strong>
                                    <p>Nominate someone to exercise your rights in case of death or incapacity.</p>
                                </div>
                            </div>
                        </div>

                        <div className="section" id="cookies">
                            <span className="section-tag">05</span>
                            <h2>Cookies &amp; Tracking</h2>
                            <p>EquityAlerts uses cookies and similar technologies. A consent banner appears on your first visit — non-essential cookies are only activated after you explicitly accept them. You can change preferences at any time via the "Cookie Preferences" link in the footer.</p>
                            <div className="cookie-types">
                                <div className="cookie-row">
                                    <div className="cookie-left">
                                        <strong>Essential cookies</strong>
                                        <span>Session management, authentication state, and theme preferences.</span>
                                    </div>
                                    <div className="toggle-mock on"><div className="knob"></div></div>
                                </div>
                                <div className="cookie-row">
                                    <div className="cookie-left">
                                        <strong>Analytics cookies</strong>
                                        <span>Google Analytics and ContentSquare — measure site usage and performance.</span>
                                    </div>
                                    <div className="toggle-mock off"><div className="knob"></div></div>
                                </div>
                                <div className="cookie-row">
                                    <div className="cookie-left">
                                        <strong>Advertising cookies</strong>
                                        <span>Meta Pixel — advertising effectiveness and retargeting.</span>
                                    </div>
                                    <div className="toggle-mock off"><div className="knob"></div></div>
                                </div>
                            </div>
                        </div>

                        <div className="section" id="security">
                            <span className="section-tag">06</span>
                            <h2>Security</h2>
                            <p>We implement industry-standard security measures including encrypted connections (TLS/SSL), secure authentication flows, and strict access controls. No method of transmission or storage is 100% secure — we cannot guarantee absolute security but are committed to protecting your information to the best of our ability.</p>
                        </div>

                        <div className="section" id="retention">
                            <span className="section-tag">07</span>
                            <h2>Data Retention</h2>
                            <p>We retain your personal data only for as long as necessary:</p>
                            <ul className="purpose-list">
                                <li><strong style={{ color: "var(--ink)" }}>Account data</strong> — retained while your account is active and for a reasonable period after deletion to comply with legal obligations.</li>
                                <li><strong style={{ color: "var(--ink)" }}>Payment records</strong> — retained as required by applicable tax and financial regulations.</li>
                                <li><strong style={{ color: "var(--ink)" }}>Analytics data</strong> — aggregated and anonymised data may be retained indefinitely for product improvement.</li>
                            </ul>
                        </div>

                        <div className="section" id="contact">
                            <span className="section-tag">08</span>
                            <h2>Contact Us</h2>
                            <p>If you have questions about this Privacy Policy or wish to exercise your data rights, reach out to us. We respond to all legitimate requests within a reasonable timeframe.</p>
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
                    <Link to="/terms-of-service">Terms of Service</Link>
                    &nbsp;·&nbsp;
                    <Link to="/disclaimer">Disclaimer</Link>
                    &nbsp;·&nbsp;
                    <a href="#">Cookie Preferences</a>
                </p>
            </footer>

        </div>
    );
}

export default PrivacyPolicy;