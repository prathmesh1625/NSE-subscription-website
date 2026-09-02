import React from "react";
import { Link } from "react-router-dom";

export function Disclamer() {
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
                    --green-border:#174436;
                    --amber:       #fbbf24;
                    --amber-soft:  #221a08;
                    --amber-text:  #fcd34d;
                    --amber-border:#3a2d10;
                    --red:         #f87171;
                    --red-soft:    #200f0f;
                    --red-border:  #3d1515;
                    --red-text:    #fca5a5;
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
                    background: rgba(13,15,20,0.88); backdrop-filter: blur(16px);
                    border-bottom: 1px solid var(--border);
                    padding: 0 2rem; height: 56px;
                    display: flex; align-items: center; justify-content: space-between;
                }
                .nav-logo { font-family: 'DM Serif Display', serif; font-size: 20px; color: var(--ink); text-decoration: none; }
                .nav-badge { font-size: 11px; font-weight: 500; letter-spacing: 0.06em; text-transform: uppercase; color: var(--red-text); background: var(--red-soft); padding: 4px 10px; border-radius: 20px; border: 1px solid var(--red-border); }

                .hero {
                    background: var(--amber-soft); border-bottom: 1px solid var(--amber-border);
                    padding: 56px 2rem 48px; text-align: center;
                }
                .hero-eyebrow { font-size: 11px; font-weight: 500; letter-spacing: 0.1em; text-transform: uppercase; color: var(--amber); margin-bottom: 14px; }
                .hero h1 { font-family: 'DM Serif Display', serif; font-size: clamp(32px, 5vw, 48px); font-weight: 400; color: var(--amber-text); letter-spacing: -0.5px; line-height: 1.15; margin-bottom: 16px; }
                .hero-sub { font-size: 15px; color: #c2944a; max-width: 540px; margin: 0 auto 24px; }
                .hero-meta { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--amber); border: 1px solid var(--amber-border); border-radius: 20px; padding: 5px 14px; background: var(--bg-card); }

                .key-callout {
                    background: var(--red-soft); border: 1px solid var(--red-border);
                    border-radius: var(--radius); padding: 20px 24px;
                    display: flex; gap: 16px; align-items: flex-start; margin-bottom: 40px;
                }
                .callout-icon { width: 40px; height: 40px; border-radius: 10px; background: #2d1010; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
                .callout-icon svg { width: 20px; height: 20px; color: var(--red); }
                .key-callout p { font-size: 14px; color: var(--red-text); line-height: 1.65; margin: 0; }
                .key-callout strong { font-weight: 500; display: block; margin-bottom: 4px; font-size: 15px; color: var(--red); }

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
                p { color: var(--ink-muted); margin-bottom: 14px; font-size: 15px; }
                p:last-child { margin-bottom: 0; }
                a { color: var(--accent-text); text-decoration: none; }
                a:hover { text-decoration: underline; }

                .point-list { list-style: none; margin: 16px 0; }
                .point-list li { display: flex; align-items: flex-start; gap: 12px; padding: 11px 0; border-bottom: 1px solid var(--border-soft); font-size: 14px; color: var(--ink-muted); line-height: 1.6; }
                .point-list li:last-child { border-bottom: none; }
                .point-list .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--amber); flex-shrink: 0; margin-top: 8px; }

                .summary-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 20px 0; }
                .s-box { border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; background: var(--bg-card); }
                .s-box .s-top { font-size: 11px; font-weight: 500; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-faint); margin-bottom: 8px; }
                .s-box p { font-size: 13px; color: var(--ink-muted); margin: 0; line-height: 1.55; }
                .s-box.warn { border-color: var(--amber-border); background: var(--amber-soft); }
                .s-box.warn .s-top { color: var(--amber); }
                .s-box.warn p { color: var(--amber-text); }
                .s-box.safe { border-color: var(--green-border); background: var(--green-soft); }
                .s-box.safe .s-top { color: var(--green); }
                .s-box.safe p { color: var(--green-text); }

                .notice { border-left: 3px solid var(--amber); background: var(--amber-soft); border-radius: 0 var(--radius) var(--radius) 0; padding: 14px 18px; margin: 20px 0; }
                .notice p { font-size: 13px; color: var(--amber-text); margin: 0; line-height: 1.6; }
                .notice strong { font-weight: 500; }

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
                    .summary-row { grid-template-columns: 1fr; }
                    footer { flex-direction: column; gap: 8px; text-align: center; }
                }
            `}</style>

            <nav>
                <Link to="/" className="nav-logo">EquityAlerts</Link>
                <span className="nav-badge">Disclaimer</span>
            </nav>

            <div className="hero">
                <div className="page-wrap">
                    <p className="hero-eyebrow">Legal</p>
                    <h1>Disclaimer</h1>
                    <p className="hero-sub">Please read this disclaimer carefully before using EquityAlerts. It defines the nature and limits of the information we provide.</p>
                    <span className="hero-meta">
                        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" width="13" height="13">
                            <circle cx="8" cy="8" r="6" />
                            <path d="M8 5v3.5M8 10.5v.5" />
                        </svg>
                        Last updated: June 2025
                    </span>
                </div>
            </div>

            <div className="page-wrap">
                <div className="content-grid">

                    <aside className="toc">
                        <p className="toc-label">Contents</p>
                        <a href="#not-advice">Not Investment Advice</a>
                        <a href="#no-sebi">Not SEBI Registered</a>
                        <a href="#data-accuracy">Data Accuracy</a>
                        <a href="#whatsapp-alerts">WhatsApp Alerts</a>
                        <a href="#past-performance">Past Performance</a>
                        <a href="#third-party">Third-Party Links</a>
                        <a href="#user-risk">Your Risk</a>
                        <a href="#no-liability">No Liability</a>
                        <a href="#jurisdiction">Jurisdiction</a>
                        <a href="#contact">Contact</a>
                    </aside>

                    <main className="doc-body">

                        <div className="key-callout">
                            <div className="callout-icon">
                                <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
                                    <path d="M10 2L2 17h16L10 2z" />
                                    <path d="M10 8v4M10 14v1" />
                                </svg>
                            </div>
                            <div>
                                <strong>EquityAlerts does not provide investment advice.</strong>
                                All content on this platform — including company filings, watchlist data, announcements, and WhatsApp notifications — is provided for informational purposes only. Nothing here should be construed as a recommendation, solicitation, or offer to buy or sell any security, financial product, or instrument.
                            </div>
                        </div>

                        <div className="section" id="not-advice">
                            <span className="section-tag">01</span>
                            <h2>Not Investment Advice</h2>
                            <p><strong style={{ color: "var(--ink)" }}>EquityAlerts is a product of EagleSwift Global Advisors Private Limited</strong>, a company incorporated in India. References to "we", "our", or "us" in this Disclaimer mean EagleSwift Global Advisors Private Limited.</p>
                            <p>EquityAlerts aggregates publicly available regulatory filings from the Bombay Stock Exchange (BSE) and National Stock Exchange (NSE) and delivers them to users via a web platform and WhatsApp notifications. This service is purely informational.</p>
                            <div className="summary-row">
                                <div className="s-box safe">
                                    <p className="s-top">What we are</p>
                                    <p>A filing aggregation and notification platform. We organise public exchange data and deliver it to you faster.</p>
                                </div>
                                <div className="s-box warn">
                                    <p class="s-top">What we are not</p>
                                    <p>An investment advisor, broker, analyst, portfolio manager, or research entity of any kind.</p>
                                </div>
                                <div className="s-box">
                                    <p className="s-top">Your responsibility</p>
                                    <p>Any decision to buy, hold, or sell a security based on information from EquityAlerts is entirely your own.</p>
                                </div>
                            </div>
                            <p>The information provided should not be used as the sole basis for any investment decision. You should consult a qualified and SEBI-registered financial advisor before making investment decisions.</p>
                        </div>

                        <div className="section" id="no-sebi">
                            <span className="section-tag">02</span>
                            <h2>Not Registered with SEBI</h2>
                            <p>EquityAlerts is not registered with the Securities and Exchange Board of India (SEBI) as an Investment Adviser, Research Analyst, Stock Broker, Sub-Broker, Portfolio Manager, or in any other regulated capacity under the SEBI Act, 1992 or its regulations.</p>
                            <p>We do not publish research reports, target prices, buy/sell ratings, or recommendations of any kind. Any resemblance of our filing summaries to investment research is coincidental — we present facts from exchange filings, not opinions or analysis.</p>
                            <div className="notice">
                                <p><strong>If you are looking for personalised investment advice,</strong> please consult a SEBI-registered investment adviser. You can verify registration status on the <a href="https://www.sebi.gov.in" target="_blank" rel="noopener" style={{ color: "var(--amber)", fontWeight: 500 }}>SEBI website</a>.</p>
                            </div>
                        </div>

                        <div className="section" id="data-accuracy">
                            <span className="section-tag">03</span>
                            <h2>Data Accuracy &amp; Completeness</h2>
                            <p>While we make every effort to present accurate and timely information, EquityAlerts cannot guarantee the completeness, accuracy, timeliness, or reliability of any data displayed on the platform.</p>
                            <ul className="point-list">
                                <li><span className="dot"></span>Exchange filings are sourced from BSE and NSE data feeds. Errors or delays in those feeds may be reflected on our platform.</li>
                                <li><span class="dot"></span>Filing PDFs are reproduced as delivered by the exchanges. We do not verify, edit, or endorse the contents of any company disclosure.</li>
                                <li><span className="dot"></span>Data may be delayed, incomplete, or occasionally unavailable due to technical issues, exchange outages, or maintenance windows.</li>
                                <li><span className="dot"></span>Company names, ISIN codes, and sector classifications are derived from exchange data and may not always reflect the most current corporate actions.</li>
                            </ul>
                            <p>Always verify critical information directly from the official BSE or NSE websites before acting on it.</p>
                        </div>

                        <div className="section" id="whatsapp-alerts">
                            <span className="section-tag">04</span>
                            <h2>WhatsApp Alerts — Informational Only</h2>
                            <p>EquityAlerts delivers company filing notifications via WhatsApp. These notifications are designed to inform you that a filing has been made — they are not trading signals, alerts to buy or sell, or commentary on the significance of the filing.</p>
                            <ul className="point-list">
                                <li><span className="dot"></span>Notification delivery is best-effort and may be subject to delays or failures due to WhatsApp platform constraints, the 24-hour messaging window, or network issues.</li>
                                <li><span className="dot"></span>A received notification does not imply that a filing is material, price-sensitive, or actionable.</li>
                                <li><span className="dot"></span>You are solely responsible for reading, interpreting, and acting (or not acting) on any filing notified to you.</li>
                                <li><span className="dot"></span>EquityAlerts is not liable for any financial outcome arising from a notification — whether delivered, delayed, or missed.</li>
                            </ul>
                        </div>

                        <div className="section" id="past-performance">
                            <span className="section-tag">05</span>
                            <h2>Past Performance</h2>
                            <p>Any historical data, statistics, or company performance figures displayed on EquityAlerts are provided for informational and contextual purposes only. Past performance of any company, index, or security is not a reliable indicator of future results.</p>
                            <p>Equity markets are subject to market risk. The value of investments may go up or down, and you may receive less than the amount you originally invest. EquityAlerts accepts no responsibility for any investment losses incurred.</p>
                        </div>

                        <div className="section" id="third-party">
                            <span className="section-tag">06</span>
                            <h2>Third-Party Links &amp; Content</h2>
                            <p>Our platform may contain links to third-party websites, including exchange portals, company websites, and news sources. These links are provided for convenience only. EquityAlerts does not endorse, control, or take responsibility for the content, accuracy, or practices of any linked third-party site.</p>
                            <p>Filing documents published by companies are the sole responsibility of the respective companies. EquityAlerts makes no representations regarding the accuracy or completeness of any company disclosure.</p>
                        </div>

                        <div className="section" id="user-risk">
                            <span className="section-tag">07</span>
                            <h2>Use at Your Own Risk</h2>
                            <p>Your use of EquityAlerts — including reliance on any information, notification, or filing data available through our platform — is entirely at your own risk. Before making any investment decision, you should:</p>
                            <ul className="point-list">
                                <li><span className="dot"></span>Conduct your own independent due diligence on any company or security</li>
                                <li><span className="dot"></span>Consult a qualified, SEBI-registered investment adviser or financial professional</li>
                                <li><span className="dot"></span>Consider your own financial situation, investment objectives, and risk tolerance</li>
                                <li><span className="dot"></span>Verify all material information directly from official exchange sources</li>
                            </ul>
                        </div>

                        <div className="section" id="no-liability">
                            <span className="section-tag">08</span>
                            <h2>No Liability</h2>
                            <p>To the maximum extent permitted by applicable law, EquityAlerts, its founders, directors, employees, and agents shall not be liable for any direct, indirect, incidental, consequential, or punitive loss or damage — including financial losses, loss of opportunity, or loss of data — arising from:</p>
                            <ul className="point-list">
                                <li><span className="dot"></span>Your reliance on any information or notification provided by EquityAlerts</li>
                                <li><span className="dot"></span>Delayed, inaccurate, or missing filing data</li>
                                <li><span className="dot"></span>Failure to receive a WhatsApp notification for any reason</li>
                                <li><span className="dot"></span>Any action or inaction taken on the basis of content available on our platform</li>
                                <li><span className="dot"></span>Interruptions, errors, or unavailability of the EquityAlerts platform</li>
                            </ul>
                            <div className="notice">
                                <p><strong>This disclaimer does not limit liability</strong> that cannot be excluded under Indian law, including liability for fraud, willful misconduct, or personal injury caused by negligence.</p>
                            </div>
                        </div>

                        <div className="section" id="jurisdiction">
                            <span className="section-tag">09</span>
                            <h2>Jurisdiction</h2>
                            <p>This Disclaimer is governed by and construed in accordance with the laws of India. Any disputes relating to this Disclaimer or your use of EquityAlerts shall be subject to the exclusive jurisdiction of the courts in Mumbai, Maharashtra, India.</p>
                            <p>By using EquityAlerts, you agree that this Disclaimer forms part of our <Link to="/terms-of-service">Terms of Service</Link> and is incorporated by reference.</p>
                        </div>

                        <div className="section" id="contact">
                            <span className="section-tag">10</span>
                            <h2>Questions</h2>
                            <p>If you have questions about this Disclaimer or need clarification on the nature of our services, please reach out to us.</p>
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
                    <Link to="/privacy-policy">Privacy Policy</Link> &nbsp;·&nbsp;
                    <Link to="/terms-of-service">Terms of Service</Link> &nbsp;·&nbsp;
                    <a href="#">Cookie Preferences</a>
                </p>
            </footer>

        </div>
    );
}

export default Disclamer;