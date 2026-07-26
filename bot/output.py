"""
EquityAlerts Result Bits - PDF Financial Extractor
================================================
Extracts key financial metrics from any investor presentation PDF
and formats them as an EquityAlerts-style WhatsApp message using LangChain.

Requirements:
    pip install langchain langchain-anthropic langchain-openai langchain-google-genai pdfplumber pypdf python-dotenv

Usage:
    python output.py --pdf path/to/presentation.pdf
    python output.py --url https://example.com/presentation.pdf
    python output.py --pdf path/to/presentation.pdf --provider google
    python output.py --pdf path/to/presentation.pdf --provider google --model gemini-2.5-flash
"""

# ── Load .env FIRST before anything else ─────────────────────────────────────
from dotenv import load_dotenv
from pathlib import Path
import os

# Works from any working directory — always finds .env next to this script
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

# ─────────────────────────────────────────────────────────────────────────────
import argparse
import json
import re
import sys
import urllib.request
import tempfile

# ── LangChain ────────────────────────────────────────────────────────────────
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

# ── PDF text extraction ───────────────────────────────────────────────────────
import pdfplumber


# ─────────────────────────────────────────────────────────────────────────────
# 1.  Pydantic schema – defines the structured output
# ─────────────────────────────────────────────────────────────────────────────

class PeriodMetric(BaseModel):
    """A single financial metric for one reporting period."""
    period_label: str = Field(description="E.g. 'Mar 2026', 'Dec 2025', 'Mar 2025'")
    value: str = Field(description="Formatted value with currency/unit, e.g. '₹934.17 Cr' or '17.08%'")


class MetricBlock(BaseModel):
    """Revenue, PAT, OPM or any other key metric."""
    name: str = Field(description="Full metric name, e.g. 'Revenue', 'Profit After Tax (PAT)'")
    short_name: str = Field(description="Short label, e.g. 'REV', 'PAT', 'OPM'")
    periods: list[PeriodMetric] = Field(
        description="List of [current_quarter, prev_quarter, same_quarter_last_year]"
    )
    qoq_change: str = Field(description="QoQ % change, e.g. '+62.18' or '-5.3'")
    yoy_change: str = Field(description="YoY % change, e.g. '+57.14' or '-10.2'")
    unit: str = Field(description="'crore' | 'percent' | 'lakh' | 'million' | 'billion' | 'other'")


class FinancialSummary(BaseModel):
    """Complete structured output for one quarterly result."""
    company_name: str = Field(description="Full company name")
    reporting_period: str = Field(description="E.g. 'Mar 2026'")
    metrics: list[MetricBlock] = Field(description="List of key financial metrics extracted")
    insights_url: str = Field(
        default="",
        description="AI insights URL if present, else empty string"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2.  PDF text extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_text_from_pdf_file(pdf_path: str) -> str:
    """Extract all text from a PDF file using pypdf for speed, with a fallback to pdfplumber."""
    # Try pypdf first (extremely fast and doesn't get stuck on vector diagrams)
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        text_parts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
        full_text = "\n".join(text_parts)
        if len(full_text.strip()) > 100:
            print("⚡ Extracted text using fast pypdf parser.", file=sys.stderr)
            return full_text
    except Exception as e:
        print(f"⚠️ pypdf extraction failed: {e}. Falling back to pdfplumber...", file=sys.stderr)

    # Fallback to pdfplumber without the slow extract_tables() layout geometry analysis
    print("⏳ Running pdfplumber fallback text extraction...", file=sys.stderr)
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    return "\n".join(text_parts)


def download_pdf(url: str) -> str:
    """Download a PDF from URL to a temp file, return local path."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        tmp.write(response.read())
    tmp.close()
    return tmp.name


# ─────────────────────────────────────────────────────────────────────────────
# 3.  LangChain extraction chain
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a financial analyst AI that extracts structured data
from quarterly investor presentation PDFs of Indian listed companies.

Your task:
1. Identify the company name and reporting quarter/year.
2. Extract the following metrics (if present) for THREE periods:
   - Current Quarter (most recent, e.g. Mar 2026)
   - Previous Quarter (e.g. Dec 2025)
   - Same Quarter Last Year (e.g. Mar 2025)
3. Metrics to extract (extract ALL that are present):
   - Revenue / Net Revenue / Total Income  → short_name: REV
   - EBITDA / Operating Profit             → short_name: EBITDA
   - Operating Profit Margin (OPM/EBITDA%) → short_name: OPM
   - Profit After Tax (PAT / Net Profit)   → short_name: PAT
   - Earnings Per Share (EPS)              → short_name: EPS
   - Net Debt                              → short_name: DEBT (optional)
   - Order Book / Backlog                  → short_name: ORDERBOOK (optional)
4. Calculate QoQ and YoY percentage changes:
   - QoQ = ((current - prev_quarter) / |prev_quarter|) * 100
   - YoY = ((current - same_qtr_last_year) / |same_qtr_last_year|) * 100
   - Round to 2 decimal places, include sign (+/-)
5. UNITS — READ THE TABLE HEADING BEFORE COPYING ANY NUMBER.
   Indian results tables state their denomination in a heading such as
   "(₹ in lakhs)", "(Rs. in Crore)", "(₹ in Millions)". You MUST use the
   denomination that the table you copied from actually states:
     - table says lakhs   → unit = "lakh"    and suffix the value "Lakh"
     - table says crore   → unit = "crore"   and suffix the value "Cr"
     - table says million → unit = "million" and suffix the value "Mn"
     - table says billion → unit = "billion" and suffix the value "Bn"
   Do NOT relabel a lakhs figure as crore. A value of 1,07,496 in a table
   headed "(₹ in lakhs)" is ₹1,07,496 Lakh (= ₹1,074.96 Cr) — writing it as
   "₹1,07,496 Cr" overstates it 100x and is a serious error.
   Do NOT convert between denominations yourself — copy the number exactly as
   printed and label it with the table's own denomination.
   For margins (OPM, EBITDA%), unit = "percent".
6. Format monetary values with the Rs symbol and the denomination suffix from
   rule 5, matching what the source table states.
7. Format percentage values with % suffix.

CRITICAL ANTI-HALLUCINATION RULES (read carefully):
- Return an EMPTY "metrics" array UNLESS the document is an actual quarterly or
  annual FINANCIAL RESULTS statement that contains a real results table with
  reported figures. Board-meeting notices, intimations, trading-window closures,
  newspaper publications, presentations without a results table, and any
  document that merely mentions the word "results" WITHOUT real reported numbers
  must return an empty metrics array.
- NEVER fabricate, infer, estimate, guess, or carry over the example values
  shown in this prompt or the schema. Those examples are formatting hints ONLY.
- Every number you output MUST appear verbatim in the PDF TEXT below. If you
  cannot find a metric's number literally in the text, do not output that metric.
- If a metric is not found, skip it entirely.
- Use exact numbers from the PDF — do not round or approximate.
- Return ONLY valid JSON matching the schema. No markdown fences, no explanation.
"""

EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", (
        "Extract financial data from the following PDF text and return JSON "
        "matching the FinancialSummary schema.\n\n"
        "Schema:\n{schema}\n\n"
        "PDF TEXT:\n{pdf_text}"
    )),
])


# ── Provider → default model mapping ─────────────────────────────────────────
PROVIDER_DEFAULTS = {
    "anthropic": "claude-opus-4-6",
    "openai":    "gpt-4o-mini",
    "google":    "gemini-2.5-flash",
    "gemini":    "gemini-2.5-flash",   # alias for google
    "groq":      "llama-3.3-70b-versatile",
}


def build_chain(provider: str = "google", model: str | None = None):
    """Build the LangChain extraction chain for the given LLM provider."""
    _model = model or PROVIDER_DEFAULTS.get(provider)

    if provider in ("google", "gemini"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        # Prefer GEMINI_API_KEY; fall back to GOOGLE_API_KEY
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "No Gemini API key found. "
                "Add GOOGLE_API_KEY or GEMINI_API_KEY to your .env file."
            )
        # Force the library to use this key (it reads GOOGLE_API_KEY from env internally)
        os.environ["GOOGLE_API_KEY"] = api_key
        llm = ChatGoogleGenerativeAI(
            model=_model,
            google_api_key=api_key,
            temperature=0,
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=_model, temperature=0, max_tokens=2048)

    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=_model, temperature=0, max_tokens=2048,
                         timeout=25, max_retries=1)

    elif provider == "groq":
        from langchain_groq import ChatGroq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "No Groq API key found. "
                "Add GROQ_API_KEY to your env/system variables."
            )
        llm = ChatGroq(model=_model, groq_api_key=api_key, temperature=0, max_retries=2)

    else:
        raise ValueError(
            f"Unsupported provider: '{provider}'. "
            f"Choose from: {list(PROVIDER_DEFAULTS.keys())}"
        )

    parser = JsonOutputParser(pydantic_object=FinancialSummary)
    chain  = EXTRACTION_PROMPT | llm | parser
    return chain, parser


def extract_financials(
    pdf_text: str,
    provider: str = "google",
    model: str | None = None,
) -> FinancialSummary:
    """Run LangChain chain to extract financials from PDF text."""
    chain, _ = build_chain(provider=provider, model=model)
    schema_str = json.dumps(FinancialSummary.model_json_schema(), indent=2)

    # Limit text size to prevent exceeding context or free rate limits (e.g. Groq TPM is small)
    max_chars = 20000 if provider == "groq" else 80000
    
    result = chain.invoke({
        "schema":   schema_str,
        "pdf_text": pdf_text[:max_chars],   # stay within context limits
    })

    if isinstance(result, dict):
        return FinancialSummary(**result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 4.  WhatsApp message formatter
# ─────────────────────────────────────────────────────────────────────────────

def _trend_emoji(change_str: str) -> str:
    """Return emoji based on direction and magnitude of change."""
    try:
        val = float(change_str.replace("+", "").replace("%", ""))
    except ValueError:
        return "➡️"
    if val > 20:   return "🚀"
    if val > 0:    return "🟢"
    if val < -20:  return "🔴"
    if val < 0:    return "🔻"
    return "➡️"


def _format_change(change_str: str) -> str:
    """Format '62.18' → '+62.18%', '-5.3' → '-5.3%'."""
    try:
        val  = float(change_str.replace("+", "").replace("%", ""))
        sign = "+" if val >= 0 else ""
        return f"{sign}{val:.2f}%"
    except ValueError:
        return change_str


# PureFrameLabs promo appended to every PDF filing alert.
PUREFRAME_AD = (
    "━━━━━━━━━━━━━━\n"
    "*📢 We are PureFrameLabs* — we build similar products & custom tools.\n"
    "For any query or product, contact us: *8459625508*"
)

BRAND_NAME = "EquityAlerts"


def _impact_hashtag(impact: str) -> str:
    """'low' → ' #LowImpact'. Empty/unknown → ''."""
    imp = (impact or "").strip().lower()
    if imp.startswith("high"):  return " #HighImpact"
    if imp.startswith("med"):   return " #MediumImpact"
    if imp.startswith("low"):   return " #LowImpact"
    return ""


def _parse_event_impact_summary(text: str, fallback_event: str = ""):
    """
    Pull EVENT / IMPACT / SUMMARY out of the LLM output. Robust to the model
    dropping a label — if no SUMMARY label is found the whole text is treated
    as the summary.
    """
    event = impact = summary = ""
    m = re.search(r"EVENT:\s*(.+)", text, re.IGNORECASE)
    if m:
        event = m.group(1).strip().splitlines()[0].strip()
    m = re.search(r"IMPACT:\s*([A-Za-z]+)", text, re.IGNORECASE)
    if m:
        impact = m.group(1).strip()
    m = re.search(r"SUMMARY:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    if m:
        summary = m.group(1).strip()
    if not summary:
        summary = text.strip()
    if not event:
        event = (fallback_event or "").strip()
    return event, impact, summary


def _build_stock_bits_message(
    company_name: str,
    event: str,
    body: str,
    impact: str = "",
    brand_url: str = "https://equityalerts.in/portal",
    short_url: str = "",
    download_url: str = "",
) -> str:
    """
    Assemble the EquiSense-style 'Stock Bits' WhatsApp message:

        📢 *EquityAlerts Stock Bits!!*

        🏢 <company>

        ⚡ <event type>

        🤖 <summary> #Impact

        🔗 <insights/short link>
        📎 Download filing: <pdf url>

        You are receiving this stock update per your request on <brand>
        Disclaimer: <brand>

    The long download URL is intentional — it widens the WhatsApp bubble to the
    full-width look of the reference message.
    """
    lines = [f"📢 *{BRAND_NAME} Stock Bits!!*", ""]
    lines.append(f"🏢 {company_name}")
    lines.append("")
    if event:
        lines.append(f"⚡ {event}")
        lines.append("")
    lines.append(f"🤖 {body}{_impact_hashtag(impact)}")
    lines.append("")

    link_added = False
    if short_url:
        lines.append(f"🔗 {short_url}")
        link_added = True
    if download_url:
        lines.append(f"📎 Download filing: {download_url}")
        link_added = True
    if link_added:
        lines.append("")

    lines.append(f"You are receiving this stock update per your request on {brand_url}")
    lines.append(f"Disclaimer: {brand_url}/disclaimer")
    return "\n".join(lines)


# Abbreviations the model gets wrong often enough to correct on sight, as
# (name substrings, correct abbreviation). It routinely tags a "Profit before
# tax" block short_name="PAT" — rendering the self-contradicting heading
# "Profit before tax (PAT):" and, downstream, letting a pre-tax figure fill
# the results template's fixed "Profit After Tax" slot.
_SHORT_FIXUPS = (
    (("before tax", "before exceptional", "pre-tax"), "PBT"),
)


def _canonical_short(name: str, short: str) -> str:
    """Correct an abbreviation that contradicts the metric's own name."""
    low = (name or "").lower()
    for needles, correct in _SHORT_FIXUPS:
        if any(n in low for n in needles):
            return correct
    return short


def _metric_label(name: str, short: str) -> str:
    """
    "Revenue", "REV" -> "Revenue (REV):".

    The model often already carries the abbreviation inside the name
    ("Basic Earnings Per Share (EPS)"), which naively appending short_name
    turned into "Basic Earnings Per Share (EPS) (EPS):". Strip a trailing
    parenthetical that just repeats the abbreviation, correct an abbreviation
    that contradicts the name, and drop the suffix entirely when there is no
    abbreviation to add.
    """
    name  = (name or "").strip()
    short = (short or "").strip()
    if short:
        name = re.sub(r"\s*\(\s*" + re.escape(short) + r"\s*\)\s*$", "",
                      name, flags=re.IGNORECASE).strip()
    short = _canonical_short(name, short)
    return f"{name} ({short}):" if short else f"{name}:"


def format_whatsapp_message(
    summary: FinancialSummary,
    equisense_url: str = "https://equityalerts.in/portal",
    short_url: str = "",
    download_url: str = "",
) -> str:
    """
    STRUCTURED 'Result Bits' message for quarterly/annual results — a proper
    metrics table (Revenue / PAT / OPM …, three periods each, QoQ & YoY), instead
    of a flat summary paragraph. Layout:

        📢 *EquityAlerts Result Bits!!*

        💼 <company> | <period> Results Out

        📊 Key Metrics

        Revenue (REV):
        🗓️ Mar 2026: ₹205.55 Cr
        ...
        🚀 +25.38% QoQ, 🚀 +31.47% YoY

        🤖 Key Insights:
         <link>

        You are receiving ...
    """
    lines = [f"📢 *{BRAND_NAME} Result Bits!!*", ""]
    lines.append(f"💼 {summary.company_name} | {summary.reporting_period} Results Out")
    lines.append("")
    lines.append("📊 Key Metrics")
    for m in summary.metrics:
        lines.append("")
        lines.append(_metric_label(m.name, m.short_name))
        for p in m.periods:
            lines.append(f"🗓️ {p.period_label}: {p.value}")
        lines.append(
            f"{_trend_emoji(m.qoq_change)} {_format_change(m.qoq_change)} QoQ, "
            f"{_trend_emoji(m.yoy_change)} {_format_change(m.yoy_change)} YoY"
        )

    lines.append("")
    lines.append("🤖 Key Insights:")
    lines.append(f" {summary.insights_url or download_url or short_url or equisense_url}")
    lines.append("")
    lines.append(f"You are receiving this stock update per your request on {equisense_url}")
    lines.append(f"Disclaimer: {equisense_url}/disclaimer")
    return "\n".join(lines)


def summarize_content(
    pdf_text: str,
    company_name: str,
    provider: str = "openai",
    model: str | None = None,
    equisense_url: str = "https://equityalerts.in/portal",
    filing_type: str = "",
    download_url: str = "",
    short_url: str = "",
) -> str:
    """
    EquiSense-style 'Stock Bits' alert for filings with no financial tables.
    Asks the LLM for a short event category, an impact level and a plain
    summary, then lays them out like the reference message.
    """
    _model = model or PROVIDER_DEFAULTS.get(provider)

    # Build a plain LLM (no structured output / JSON parser)
    if provider in ("google", "gemini"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        os.environ["GOOGLE_API_KEY"] = api_key
        llm = ChatGoogleGenerativeAI(model=_model, google_api_key=api_key, temperature=0)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=_model, temperature=0, max_tokens=512)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=_model, temperature=0, max_tokens=512,
                         timeout=25, max_retries=1)
    elif provider == "groq":
        from langchain_groq import ChatGroq
        llm = ChatGroq(model=_model, groq_api_key=os.getenv("GROQ_API_KEY"), temperature=0)
    else:
        raise ValueError(f"Unsupported provider: '{provider}'")

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You summarise Indian stock-exchange (NSE/BSE) filings for retail investors.\n"
         "Return EXACTLY these three labelled lines and nothing else:\n"
         "EVENT: <2-5 word category of the filing, e.g. 'Investor Conference Participation', "
         "'Board Meeting Intimation', 'Dividend Declaration', 'Order Win'>\n"
         "IMPACT: <one word — High, Medium or Low — how price-sensitive this filing is>\n"
         "SUMMARY: <2-4 sentence plain-English summary: what the company is doing, why it "
         "matters, and any key dates or amounts. No bullet points, no headers, no markdown.>"),
        ("human", "Filing title: {filing_type}\n\nFiling content:\n\n{pdf_text}"),
    ])

    result = (prompt | llm).invoke({
        "pdf_text": pdf_text[:8000],
        "filing_type": filing_type or "N/A",
    })
    raw = result.content.strip() if hasattr(result, "content") else str(result).strip()
    event, impact, body = _parse_event_impact_summary(raw, fallback_event=filing_type)

    return _build_stock_bits_message(
        company_name, event, body, impact=impact,
        brand_url=equisense_url, short_url=short_url, download_url=download_url,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 5.  Main pipeline
# ─────────────────────────────────────────────────────────────────────────────

# ── Anti-hallucination guards ────────────────────────────────────────────────

_RESULT_PHRASES = (
    "financial results", "statement of profit and loss", "profit and loss",
    "quarter ended", "period ended", "year ended", "half year ended",
    "audited financial", "unaudited financial",
)

_METRIC_KEYWORDS = (
    "revenue", "total income", "total revenue", "profit before tax",
    "profit after tax", "net profit", "ebitda", "operating profit",
    "earnings per share", "total expenses", "total comprehensive income",
)

# Monetary-looking figures: "1,234.56", "12,34,567" (Indian grouping) or "934.17".
_MONEY_RE = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+\.\d{2}")


def looks_like_financial_results(pdf_text: str) -> bool:
    """
    Only treat a PDF as a quarterly/annual RESULTS document (and run financial
    metric extraction) when it really looks like one.

    Most exchange filings — board-meeting notices, trading-window closures,
    Reg 30 disclosures, newspaper ads, presentations without a results table —
    are NOT results statements and have no financial table. Running metric
    extraction on them just makes the model invent numbers. We require a results
    phrase, at least two distinct metric terms, AND a table's worth of monetary
    figures (which a mere notice/intimation will not have).
    """
    if not pdf_text:
        return False
    low = pdf_text.lower()
    has_phrase   = any(p in low for p in _RESULT_PHRASES)
    keyword_hits = sum(1 for k in _METRIC_KEYWORDS if k in low)
    money_count  = len(_MONEY_RE.findall(pdf_text))
    return has_phrase and keyword_hits >= 2 and money_count >= 12


def verify_metrics_against_text(summary: "FinancialSummary", pdf_text: str) -> int:
    """
    Drop any metric whose numbers never appear in the source text — a strong
    sign the model fabricated them. Conservative: a metric is kept if ANY of its
    period values matches the text. Returns the number of metrics kept.
    """
    text_digits = re.sub(r"[,\s]", "", pdf_text or "")
    kept = []
    for m in summary.metrics:
        for p in m.periods:
            num = re.search(r"-?\d[\d,]*\.?\d*", p.value or "")
            if not num:
                continue
            core     = num.group(0).replace(",", "").rstrip(".")
            int_part = core.split(".")[0]
            # Match the full number, or at least a 3+ digit integer part, in the
            # comma-stripped source text.
            if (core and core in text_digits) or (len(int_part) >= 3 and int_part in text_digits):
                kept.append(m)
                break
    summary.metrics = kept
    return len(kept)


_VALUE_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")

# Multiply a figure in <scale> by this to get crore.
_SCALE_TO_CRORE = {"lakh": 0.01, "crore": 1.0, "million": 0.1, "billion": 100.0}

# The denomination heading Indian results tables carry: "(₹ in lakhs)",
# "(Rs. in Crore)", "(₹ in Millions)", "Amount in Lakhs", ... We deliberately
# require the "in <unit>" phrasing — a bare "Cr" appears all over a document as
# a value suffix and would make detection meaningless.
_DOC_SCALE_RE = re.compile(
    r"(?:rs\.?|inr|₹|amount|figures)?\s*(?:are\s+)?in\s+"
    r"(lakhs?|lacs?|crores?|millions?|billions?)\b",
    re.IGNORECASE,
)
_SCALE_ALIASES = {
    "lakh": "lakh", "lakhs": "lakh", "lac": "lakh", "lacs": "lakh",
    "crore": "crore", "crores": "crore",
    "million": "million", "millions": "million",
    "billion": "billion", "billions": "billion",
}


def detect_document_scale(pdf_text: str) -> str | None:
    """
    The denomination the source table is printed in ("lakh" / "crore" /
    "million" / "billion"), read from its own heading — or None when the
    document never states one.

    This is the ground truth for reconcile_metric_units(). Models routinely
    copy a figure verbatim off a lakhs-denominated table and then label it
    "Cr" (a silent 100x overstatement) — a bank PAT of ₹1,07,496 lakh was
    shipped as "₹1,07,496 Cr" in production. The document's own heading is a
    far more reliable signal than anything the model reports about units.
    """
    if not pdf_text:
        return None
    counts = {}
    for m in _DOC_SCALE_RE.finditer(pdf_text):
        scale = _SCALE_ALIASES.get(m.group(1).lower())
        if scale:
            counts[scale] = counts.get(scale, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _stated_scale(value: str, unit: str) -> str | None:
    """The denomination a metric VALUE claims, from its own suffix first
    ("₹1,075 Cr" → crore), falling back to the block's declared `unit`."""
    low = (value or "").lower()
    if re.search(r"\blakhs?\b|\blacs?\b", low):
        return "lakh"
    if re.search(r"\bmn\b|\bmillions?\b", low):
        return "million"
    if re.search(r"\bbn\b|\bbillions?\b", low):
        return "billion"
    if re.search(r"\bcr\b|\bcrores?\b", low):
        return "crore"
    return _SCALE_ALIASES.get((unit or "").lower())


def _format_crore(v: float) -> str:
    """Render a crore figure the way the rest of the message does."""
    return f"₹{v:,.2f} Cr" if abs(v) < 1000 else f"₹{v:,.0f} Cr"


# Metrics quoted PER SHARE (EPS, DPS, book value …). They are printed in the
# same table as the crore figures but are NOT denominated in it, so the
# reconciliation below must leave them alone: an EPS of ₹12.11 per share was
# being relabelled "₹12.11 Cr" off a crore table and — worse — RESCALED to
# "₹0.12 Cr" off a lakhs one, destroying the value outright.
_PER_SHARE_RE = re.compile(r"per\s+share|\beps\b|\bdps\b|book\s+value",
                           re.IGNORECASE)


def _is_per_share(name: str, short: str) -> bool:
    """True for per-share metrics, which carry no crore/lakh denomination."""
    return bool(_PER_SHARE_RE.search(f"{name or ''} {short or ''}"))


def reconcile_metric_units(summary: "FinancialSummary", pdf_text: str,
                           doc_scale: str | None) -> int:
    """
    Re-label (and convert to crore) any metric value that was copied VERBATIM
    off the source table but tagged with the wrong denomination.

    The verbatim check is what makes this safe: if the digits the model emitted
    appear as-is in the PDF, it transcribed the printed figure rather than
    converting it — so the figure's true denomination MUST be the table's
    (`doc_scale`), whatever the model labelled it. When the digits do NOT
    appear verbatim the model did its own conversion, and we leave it alone
    rather than risk double-converting a correct value.

    Returns the number of period values corrected.
    """
    if not doc_scale or doc_scale not in _SCALE_TO_CRORE:
        return 0
    text_digits = re.sub(r"[,\s]", "", pdf_text or "")
    fixed = 0
    for m in summary.metrics:
        # A per-share figure is not in the table's denomination — converting
        # it to crore is always wrong, however verbatim the digits are.
        if _is_per_share(m.name, m.short_name):
            continue
        touched = False
        for p in m.periods:
            if not p.value or "%" in p.value:
                continue
            num = _VALUE_NUM_RE.search(p.value)
            if not num:
                continue
            core = num.group(0).replace(",", "").rstrip(".")
            # Only trust figures transcribed straight from the document.
            if not core or core not in text_digits:
                continue
            if _stated_scale(p.value, m.unit) == doc_scale:
                continue                      # already labelled correctly
            p.value = _format_crore(float(core) * _SCALE_TO_CRORE[doc_scale])
            touched = True
            fixed += 1
        if touched:
            m.unit = "crore"
    return fixed


# Absolute plausibility cap for a QUARTERLY figure of a single Indian listed
# company, expressed in crore. ₹5,00,000 Cr (~$60B) comfortably covers even
# Reliance/TCS-scale quarters, so genuine numbers never approach it. Guards
# against the extraction picking up a BALANCE-SHEET total (assets, deposits,
# advances) instead of a P&L line — observed in production as a bank's
# "Revenue" metric coming back at ₹13,36,052 Cr, ~2.5x India's entire
# quarterly GDP.
_MAX_PLAUSIBLE_CRORE   = 500_000
# Percent-denominated metrics (margins, ratios) shouldn't realistically exceed this.
_MAX_PLAUSIBLE_PERCENT = 1000


def _value_to_crore(value: str, unit: str) -> float | None:
    """
    Best-effort magnitude of a metric period VALUE, normalised to crore.
    Sniffs the unit from the value string itself first ("Rs. 858.67 Cr",
    "$12.3 Mn") since the model's declared per-metric `unit` field is not
    always consistent with what it actually wrote. Returns None when no
    number/currency unit can be parsed — callers should then SKIP the
    plausibility check rather than risk a false-positive drop.
    """
    if not value or "%" in value:
        return None
    m = _VALUE_NUM_RE.search(value)
    if not m:
        return None
    num = float(m.group(0).replace(",", ""))
    low = value.lower()
    if "lakh" in low:
        return num / 100
    if re.search(r"\bmn\b|million", low):
        return num / 10
    if re.search(r"\bbn\b|billion", low):
        return num * 100
    if "cr" in low:
        return num
    # No unit token in the value text itself — fall back to the block's
    # declared unit field.
    unit = (unit or "").lower()
    if unit == "lakh":
        return num / 100
    if unit == "million":
        return num / 10
    if unit == "billion":
        return num * 100
    if unit == "crore":
        return num
    return None


def _period_magnitude(value: str, unit: str) -> float | None:
    """
    Comparable magnitude for one period value. Percent metrics compare as
    plain numbers; money metrics normalise to crore so a QoQ isn't computed
    across two different denominations. None when nothing parses.
    """
    if not value:
        return None
    if "%" in value:
        m = _VALUE_NUM_RE.search(value)
        return float(m.group(0).replace(",", "")) if m else None
    crore = _value_to_crore(value, unit)
    if crore is not None:
        return crore
    m = _VALUE_NUM_RE.search(value)
    return float(m.group(0).replace(",", "")) if m else None


def recompute_changes(summary: "FinancialSummary") -> int:
    """
    Derive QoQ / YoY from the extracted period values instead of trusting the
    model's own arithmetic.

    The model's numbers were neither correct nor stable: the same filing run
    twice reported OPM (18.5% → 21.2%) as "+1.27% QoQ" and then "+14.86% QoQ",
    when the change is +14.59%. Periods are [current, prev quarter, year-ago],
    so QoQ compares [0] vs [1] and YoY [0] vs [2].

    A zero or negative base is left alone — percent change off a loss or a nil
    period is meaningless, and inventing one would be worse than the model's
    guess. Returns the number of values corrected.
    """
    fixed = 0
    for m in summary.metrics:
        vals = [_period_magnitude(p.value, m.unit) for p in m.periods]
        if not vals or vals[0] is None:
            continue
        current = vals[0]
        for idx, attr in ((1, "qoq_change"), (2, "yoy_change")):
            base = vals[idx] if len(vals) > idx else None
            if base is None or base <= 0:
                continue
            computed = f"{(current - base) / base * 100:+.2f}"
            if getattr(m, attr, None) != computed:
                setattr(m, attr, computed)
                fixed += 1
    return fixed


def drop_implausible_metrics(summary: "FinancialSummary") -> int:
    """
    Drop any metric with a period value whose magnitude is implausible for a
    single quarter (see _MAX_PLAUSIBLE_CRORE/_PERCENT above).

    Complements verify_metrics_against_text: that guard only checks the
    digits appear SOMEWHERE in the source PDF, which a balance-sheet total
    passes just as easily as the correct P&L figure — this catches those by
    scale instead of provenance. Returns the number of metrics kept.
    """
    kept = []
    for m in summary.metrics:
        implausible = False
        for p in m.periods:
            if "%" in (p.value or ""):
                num = _VALUE_NUM_RE.search(p.value)
                if num and abs(float(num.group(0).replace(",", ""))) > _MAX_PLAUSIBLE_PERCENT:
                    implausible = True
                    break
                continue
            crore = _value_to_crore(p.value, m.unit)
            if crore is not None and abs(crore) > _MAX_PLAUSIBLE_CRORE:
                implausible = True
                break
        if not implausible:
            kept.append(m)
    summary.metrics = kept
    return len(kept)


def process_pdf(
    pdf_source: str,
    provider: str = "google",
    model: str | None = None,
    equisense_url: str = "https://equityalerts.in/portal",
    short_url: str = "",
    save_json: bool = False,
    company_hint: str | None = None,
    filing_type: str = "",
    download_url: str = "",
) -> str:
    """
    End-to-end pipeline: PDF → text → LangChain extraction → formatted message.
    If no financial metrics are found, falls back to a plain content summary.
    """
    # Step 1: Get PDF text
    print(f"[1/3] Loading PDF: {pdf_source}", file=sys.stderr)
    tmp_path = None

    if pdf_source.startswith("http://") or pdf_source.startswith("https://"):
        print("      Downloading...", file=sys.stderr)
        tmp_path = download_pdf(pdf_source)
        pdf_path = tmp_path
    else:
        pdf_path = pdf_source

    try:
        pdf_text = extract_text_from_pdf_file(pdf_path)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not pdf_text.strip():
        raise ValueError(
            "No text extracted from PDF — it may be scanned/image-based. "
            "Try a text-layer PDF."
        )
    print(f"      Extracted {len(pdf_text):,} characters.", file=sys.stderr)

    # Step 2: LLM financial extraction — ONLY for genuine results documents.
    _model_name = model or PROVIDER_DEFAULTS.get(provider, "default")
    summary     = None
    company     = company_hint or "Unknown Company"

    if looks_like_financial_results(pdf_text):
        print(f"[2/3] Results document detected — extracting financials via "
              f"{provider} / {_model_name} ...", file=sys.stderr)
        try:
            summary = extract_financials(pdf_text, provider=provider, model=model)
            # Prefer the extracted name; fall back to the caller's known company.
            company = summary.company_name or company_hint or "Unknown Company"
            summary.company_name = company
            # Defence in depth, in THIS order — each step depends on the last:
            #  1. verify: drop metrics whose digits aren't in the PDF at all.
            #     Must run BEFORE reconciliation, which rewrites values into
            #     crore and would then no longer match the source text.
            verified = verify_metrics_against_text(summary, pdf_text)
            print(f"      Kept {verified} metric(s) verified against source text.", file=sys.stderr)
            #  2. reconcile: fix figures transcribed off a lakhs/millions table
            #     but labelled "Cr" (the 100x error class).
            doc_scale = detect_document_scale(pdf_text)
            if doc_scale:
                corrected = reconcile_metric_units(summary, pdf_text, doc_scale)
                if corrected:
                    print(f"      Document is denominated in {doc_scale} — "
                          f"re-scaled {corrected} mislabelled value(s) to Cr.", file=sys.stderr)
            #  3. plausibility: drop what's still absurd for a quarterly figure
            #     (e.g. a balance-sheet total misread as Revenue/PAT).
            plausible = drop_implausible_metrics(summary)
            if plausible != verified:
                print(f"      Dropped {verified - plausible} metric(s) with "
                      f"implausible magnitude.", file=sys.stderr)
            #  4. changes: recompute QoQ/YoY from the (now verified, correctly
            #     scaled) period values. Must run LAST — reconciliation rewrites
            #     values, and a change computed before that would describe the
            #     pre-correction numbers.
            recomputed = recompute_changes(summary)
            if recomputed:
                print(f"      Recomputed {recomputed} QoQ/YoY value(s) from the "
                      f"extracted figures.", file=sys.stderr)
        except Exception as e:
            print(f"      Financial extraction failed ({e}) — will use content summary.", file=sys.stderr)
    else:
        print("[2/3] Not a financial-results document — skipping metric extraction "
              "to avoid fabricated numbers; using a plain content summary.", file=sys.stderr)

    if save_json and summary:
        json_path = Path(pdf_source).stem + "_financials.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary.dict(), f, indent=2, ensure_ascii=False)
        print(f"      JSON saved → {json_path}", file=sys.stderr)

    # Step 3: Format — use financial summary if metrics found, else plain content summary
    print("[3/3] Formatting WhatsApp message...", file=sys.stderr)
    if summary and summary.metrics:
        return format_whatsapp_message(summary, equisense_url=equisense_url,
                                       short_url=short_url, download_url=download_url)

    print("      No financial metrics — generating content summary instead.", file=sys.stderr)
    return summarize_content(pdf_text, company_name=company, provider=provider,
                             model=model, equisense_url=equisense_url,
                             filing_type=filing_type, download_url=download_url,
                             short_url=short_url)


# ─────────────────────────────────────────────────────────────────────────────
# 6.  CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Investor PDF → EquityAlerts WhatsApp message"
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", help="Local path to investor presentation PDF")
    src.add_argument("--url", help="URL of investor presentation PDF")

    ap.add_argument(
        "--provider",
        choices=list(PROVIDER_DEFAULTS.keys()),
        default="google",
        help="LLM provider (default: google)",
    )
    ap.add_argument("--model",        default=None, help="Override model name")
    ap.add_argument("--short-url",    default="",   help="Short URL for AI insights section")
    ap.add_argument("--equisense-url",default="https://equityalerts.in/portal")
    ap.add_argument("--save-json",    action="store_true", help="Save intermediate JSON")
    ap.add_argument("--output",       default=None, help="Save message to file")
    ap.add_argument("--raw",          action="store_true", help="Print raw WhatsApp message without borders")

    args = ap.parse_args()

    try:
        message = process_pdf(
            pdf_source    = args.pdf or args.url,
            provider      = args.provider,
            model         = args.model,
            equisense_url = args.equisense_url,
            short_url     = args.short_url,
            save_json     = args.save_json,
        )
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(message)
        print(f"\n✅ Saved → {args.output}")
    elif args.raw:
        print(message)
    else:
        print("\n" + "═" * 60)
        print(message)
        print("═" * 60)


if __name__ == "__main__":
    main()
