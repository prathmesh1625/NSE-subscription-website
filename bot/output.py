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
import time
import urllib.request
import tempfile
from functools import lru_cache

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
    basis: str = Field(
        default="",
        description=(
            "Which statement the metrics were copied from: 'consolidated' when "
            "the group/total table was used, 'standalone' when the filing has "
            "only a standalone statement. Empty if it cannot be determined."
        ),
    )
    metrics: list[MetricBlock] = Field(description="List of key financial metrics extracted")
    insights_url: str = Field(
        default="",
        description="AI insights URL if present, else empty string"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2.  PDF text extraction helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_pages_pypdf(pdf_path: str) -> list | None:
    """Per-page text via pypdf (fast, doesn't stall on vector diagrams), or None."""
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception as e:
        print(f"⚠️ pypdf extraction failed: {e}. Falling back to pdfplumber...",
              file=sys.stderr)
        return None


def _extract_pages_pdfplumber(pdf_path: str) -> list:
    """Per-page text via pdfplumber, skipping the slow extract_tables() geometry."""
    print("⏳ Running pdfplumber fallback text extraction...", file=sys.stderr)
    with pdfplumber.open(pdf_path) as pdf:
        return [(page.extract_text() or "") for page in pdf.pages]


# ── OCR fallback for scanned filings and newspaper cuttings ──────────────────
# A "newspaper advertisement of results" filing is a covering letter plus a
# SCAN of the printed page, and an "Outcome of board meeting" is often a scan of
# the signed statement. Their pages carry either no text layer at all or a
# broken one that decodes to mojibake ("U3 a;Sjd Qp Q)IQ"), so the summary had
# nothing to work with and the filing went out with no figures — and, when the
# whole document was image-only, process_pdf raised and nothing was generated at
# all. OCR only those pages, and only when the text we already have can't yield
# a results table, so a normal text-layer filing pays nothing for this.

OCR_ENABLED = os.getenv("OCR_ENABLED", "true").strip().lower() not in ("false", "0", "no")
OCR_DPI     = int(os.getenv("OCR_DPI", "300"))          # 300 is tesseract's sweet spot for print
OCR_LANGS   = os.getenv("OCR_LANGS", "eng")             # e.g. "eng+hin" for Hindi editions
# Newspaper intimations run 1-4 pages; a fully scanned results statement more.
OCR_MAX_PAGES       = int(os.getenv("OCR_MAX_PAGES", "4"))
# Wall-clock ceiling for ALL OCR of one document. This runs INSIDE
# config.SUMMARY_TIMEOUT_SEC together with the two LLM calls, so it must leave
# room for them — see the budget note on SUMMARY_TIMEOUT_SEC in config.py.
OCR_TIME_BUDGET_SEC = int(os.getenv("OCR_TIME_BUDGET_SEC", "8"))

# ── LLM call budget (shared by every provider; kept short to prevent a single filing from monopolising a worker) ───────────────────────────────
# Retries are exponentially backed off by the provider SDK, so these ride out a
# short 429 burst rather than failing the filing. Worst case
# (LLM_TIMEOUT_SEC * (LLM_MAX_RETRIES + 1)) still has to fit inside
# config.SUMMARY_TIMEOUT_SEC, which hard-caps the whole summary.
LLM_TIMEOUT_SEC  = int(os.getenv("LLM_TIMEOUT_SEC", "15"))
LLM_MAX_RETRIES  = int(os.getenv("LLM_MAX_RETRIES", "0"))

# A page with less real text than this contributes nothing and is a scan.
_MIN_PAGE_CHARS = 40
# Below this much usable text in the WHOLE document, treat it as scanned.
_MIN_USABLE_CHARS = 600

_WORD_RE  = re.compile(r"[A-Za-z]{2,}")
_VOWEL_RE = re.compile(r"[aeiouyAEIOUY]")
# Thresholds calibrated on 109 real filing pages: the one page with a broken
# font encoding scored 0.38 on the vowel ratio and 0.112 on control characters,
# while all 108 legitimate pages scored >= 0.75 and EXACTLY 0.0 respectively.
_GARBLE_MIN_TOKENS   = 20      # fewer than this and the ratio isn't meaningful
_GARBLE_VOWEL_RATIO  = 0.60
_GARBLE_CTRL_RATIO   = 0.01

_ocr_unavailable = False       # set once, so a missing tesseract isn't retried


def text_looks_garbled(text: str) -> bool:
    """
    True when a page HAS text but it decoded to mojibake — a PDF whose embedded
    font carries a broken encoding, which is how scanned newspaper cuttings
    reach us. Such text is worse than no text: it passes every "is there text?"
    check and then poisons the summary.

    Two independent signals, either is enough:
      • C0 control characters in the body (a real text layer has none);
      • too few alphabetic tokens containing a vowel (real English words
        essentially all do).
    """
    if not text:
        return False
    ctrl = sum(1 for c in text if ord(c) < 32 and c not in "\t\n\r")
    if ctrl / len(text) > _GARBLE_CTRL_RATIO:
        return True
    tokens = _WORD_RE.findall(text)
    if len(tokens) < _GARBLE_MIN_TOKENS:
        return False               # too little to judge — not garbled, just thin
    voweled = sum(1 for w in tokens if _VOWEL_RE.search(w))
    return (voweled / len(tokens)) < _GARBLE_VOWEL_RATIO


def page_text_is_usable(text: str) -> bool:
    """True when a page's extracted text is worth feeding to the model."""
    return len((text or "").strip()) >= _MIN_PAGE_CHARS and not text_looks_garbled(text)


def _ocr_pages(pdf_path: str, page_indexes: list,
               require_image: bool = True) -> dict:
    """
    OCR the given 0-based page indexes and return {index: text}.

    Renders with PyMuPDF and reads with tesseract. Any missing dependency (no
    PyMuPDF wheel, no tesseract binary in the image) is logged ONCE and degrades
    to "no OCR" — never an exception, because this sits in the delivery path.

    With `require_image`, pages carrying no embedded image are skipped: a blank
    signature page has nothing to read and would only burn the time budget.
    Callers pass require_image=False when NO page yielded usable text, so a scan
    drawn as vectors rather than an image still gets rasterised and read.
    """
    global _ocr_unavailable
    if _ocr_unavailable or not page_indexes:
        return {}
    try:
        try:
            import pymupdf                      # PyMuPDF >= 1.24
        except ImportError:
            import fitz as pymupdf              # older name
        import pytesseract
        from PIL import Image
    except Exception as e:
        _ocr_unavailable = True
        print(f"⚠️ OCR unavailable ({e}) — scanned pages will be skipped. "
              f"Install pymupdf + pytesseract and the tesseract-ocr binary.",
              file=sys.stderr)
        return {}

    import io
    import time as _time

    out      = {}
    started  = _time.monotonic()
    doc      = None
    try:
        doc = pymupdf.open(pdf_path)
        for idx in page_indexes[:OCR_MAX_PAGES]:
            elapsed = _time.monotonic() - started
            if elapsed > OCR_TIME_BUDGET_SEC:
                print(f"⏱️  OCR budget ({OCR_TIME_BUDGET_SEC}s) reached after "
                      f"{len(out)} page(s); skipping the rest.", file=sys.stderr)
                break
            try:
                page = doc[idx]
                if require_image and not page.get_images():
                    continue                    # nothing scanned on this page
                pix = page.get_pixmap(dpi=OCR_DPI)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                txt = pytesseract.image_to_string(img, lang=OCR_LANGS) or ""
                if txt.strip():
                    out[idx] = txt
            except pytesseract.TesseractNotFoundError:
                _ocr_unavailable = True
                print("⚠️ tesseract binary not found — install the "
                      "tesseract-ocr package in the image.", file=sys.stderr)
                break
            except Exception as e:
                print(f"⚠️ OCR failed on page {idx + 1}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"⚠️ OCR could not open {os.path.basename(pdf_path)}: {e}",
              file=sys.stderr)
    finally:
        if doc is not None:
            try:
                doc.close()
            except Exception:
                pass

    if out:
        print(f"🔍 OCR recovered {sum(len(t) for t in out.values()):,} chars from "
              f"{len(out)} scanned page(s) at {OCR_DPI} DPI ({OCR_LANGS}).",
              file=sys.stderr)
    return out


def extract_text_from_pdf_file(pdf_path: str, report: dict | None = None) -> str:
    """
    All text from a PDF: the embedded text layer, with OCR filling in pages that
    have none or whose layer decoded to mojibake.

    Pass `report` to receive extraction diagnostics (page counts, which pages
    were OCR'd and why) without parsing stderr — bot/preview.py uses this.
    """
    pages = _extract_pages_pypdf(pdf_path)
    if pages is None:
        pages = _extract_pages_pdfplumber(pdf_path)
    elif len("".join(pages).strip()) <= 100:
        # pypdf found next to nothing — pdfplumber sometimes does better on the
        # same file, so try it before paying for OCR.
        try:
            plumbed = _extract_pages_pdfplumber(pdf_path)
            if len("".join(plumbed).strip()) > len("".join(pages).strip()):
                pages = plumbed
        except Exception as e:
            print(f"⚠️ pdfplumber extraction failed: {e}", file=sys.stderr)
    else:
        print("⚡ Extracted text using fast pypdf parser.", file=sys.stderr)

    usable       = [t for t in pages if page_text_is_usable(t)]
    usable_text  = "\n".join(usable)
    bad_indexes  = [i for i, t in enumerate(pages) if not page_text_is_usable(t)]
    garbled_seen = any(text_looks_garbled(t) for t in pages)

    if report is not None:
        report.update({
            "pages": len(pages),
            "usable_pages": len(usable),
            "garbled_pages": [i + 1 for i, t in enumerate(pages)
                              if text_looks_garbled(t)],
            "text_layer_chars": len(usable_text.strip()),
            "ocr_pages": [],
            "ocr_chars": 0,
        })

    # Only pay for OCR when the text layer can't already do the job: a broken
    # layer, almost no text at all, or no results table in what we have. A
    # normal filing whose statement extracted cleanly skips this entirely.
    needs_ocr = bad_indexes and OCR_ENABLED and (
        garbled_seen
        or len(usable_text.strip()) < _MIN_USABLE_CHARS
        or not looks_like_financial_results(usable_text)
    )
    if not needs_ocr:
        return usable_text if usable else "\n".join(pages)

    ocr_text = _ocr_pages(pdf_path, bad_indexes, require_image=bool(usable))
    if report is not None:
        report["ocr_pages"] = [i + 1 for i in sorted(ocr_text)]
        report["ocr_chars"] = sum(len(t) for t in ocr_text.values())

    # Rebuild in page order: OCR replaces an unusable page, a usable text layer
    # always wins over OCR (it is exact, where OCR guesses glyphs).
    merged = []
    for i, t in enumerate(pages):
        if page_text_is_usable(t):
            merged.append(t)
        elif i in ocr_text:
            merged.append(ocr_text[i])
    if not merged:
        # Image-only document and OCR produced nothing. Returning "" (rather
        # than the mojibake) makes process_pdf raise, so db_watcher sends the
        # degraded alert that names the filing and links to it — better than a
        # summary written from garbage.
        print(f"⚠️ No usable text in {os.path.basename(pdf_path)} "
              f"({len(pages)} page(s)) and OCR recovered nothing.",
              file=sys.stderr)
    return "\n".join(merged)


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

WHICH STATEMENT TO READ — DO THIS BEFORE ANYTHING ELSE.
A single Indian results filing usually contains TWO complete results tables:
a STANDALONE statement (the parent company alone) and a CONSOLIDATED statement
(the parent PLUS all its subsidiaries — the group TOTAL). The standalone table
is almost always printed FIRST, so the first table you meet is typically the
WRONG one to report.

  - If the document contains a CONSOLIDATED statement, extract EVERY metric
    from the CONSOLIDATED table and set basis = "consolidated".
  - Use the STANDALONE table ONLY when the document has no consolidated
    statement at all (common for companies with no subsidiaries), and then set
    basis = "standalone".
  - NEVER mix the two. Every number in your output must come from the SAME
    statement — a revenue taken from the consolidated table alongside a profit
    taken from the standalone table is a serious error.
  - A consolidated table that is present but carries no figures (blank, "NA",
    "Not Applicable", or a note that consolidated results are not applicable)
    does NOT count — fall back to standalone and set basis = "standalone".

Recognise the consolidated table by its OWN heading — "Consolidated Statement
of Standalone and Consolidated Financial Results", "Consolidated Financial
Results", "Statement of Consolidated Results", or a column group headed
"Consolidated" — and not by its position in the document. Some filings place
the two side by side as column groups under one heading ("STANDALONE" columns
then "CONSOLIDATED" columns); there, read the CONSOLIDATED column group and
be careful to take the period columns from that group only.

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

8. SCANNED / OCR'd FILINGS — the column headers may not line up with the numbers.
   Many exchange filings are scans. In their extracted text the period headers
   ("30.06.2026 31.03.2026 30.06.2025") are often in a DIFFERENT order from the
   numeric columns they label, the audited/unaudited markers are shuffled with
   them, and every row NAME can appear as one block ABOVE all the numbers.
   Before you attach a period label to a value, cross-check it against any
   press release, "Financial Performance" or highlights section in the SAME
   document — those state the current quarter's figures in words (e.g. "Net
   Sales at Rs 10,521.4 crore (+17.9%)") and are the reliable anchor for which
   column is the current quarter. If you cannot establish with confidence which
   period a number belongs to, OMIT that metric rather than guess.

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


# Seconds allowed for the RESULTS extraction call (build_chain, below). It is
# by far the heaviest LLM call in the bot — a 46-page results filing sends up to
# 80k chars plus the JSON schema, where summarize_content sends 8k — so it needs
# its own, longer budget than the 25s the plain summary uses.
#
# Retries are OFF for it on purpose. db_watcher.generate_pdf_summary caps the
# WHOLE summary at config.SUMMARY_TIMEOUT_SEC, and process_pdf falls back to
# summarize_content when extraction fails; a retry of a call this size just
# burns the rest of that budget, so the fallback never got to run and the
# filing went out with an EMPTY body. Extraction must fail FAST and leave room.
RESULT_EXTRACT_TIMEOUT_SEC = int(os.getenv("RESULT_EXTRACT_TIMEOUT_SEC", "18"))


# ── Provider → default model mapping ─────────────────────────────────────────
def _perf_log(stage: str, started: float, **details) -> None:
    """Structured timing log for production diagnosis."""
    elapsed = time.monotonic() - started
    extra = " ".join(f"{k}={v}" for k, v in details.items())
    suffix = f" | {extra}" if extra else ""
    print(f"[timing] {stage}: {elapsed:.2f}s{suffix}", file=sys.stderr)


PROVIDER_DEFAULTS = {
    "anthropic": "claude-opus-4-6",
    "openai":    "gpt-4o-mini",
    "google":    "gemini-2.5-flash",
    "gemini":    "gemini-2.5-flash",   # alias for google
    "groq":      "llama-3.3-70b-versatile",
}


@lru_cache(maxsize=8)
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
                         timeout=RESULT_EXTRACT_TIMEOUT_SEC, max_retries=0)

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

    # Limit text size to keep result-day LLM calls bounded.
    # 32k is enough for the financial tables while substantially reducing
    # prompt size/latency versus the old 50k default.
    max_chars = int(os.getenv("RESULT_MAX_CHARS", "32000")) if provider != "groq" else 18000
    input_text = consolidated_first(pdf_text)[:max_chars]

    _llm_started = time.monotonic()
    print(
        f"[timing] financial_llm START provider={provider} model={model or PROVIDER_DEFAULTS.get(provider)} "
        f"input_chars={len(input_text)}",
        file=sys.stderr,
    )

    # We report the CONSOLIDATED (group) statement, but filings print the
    # standalone one first — on a long filing the consolidated table would be
    # cut off by max_chars below and the model would have nothing but
    # standalone to read. Move it to the front so it survives the cap.
    try:
        result = chain.invoke({
            "schema":   schema_str,
            "pdf_text": input_text,
        })
    except Exception as exc:
        _perf_log("financial_llm FAIL", _llm_started, error=type(exc).__name__)
        raise
    else:
        _perf_log("financial_llm DONE", _llm_started, output_type=type(result).__name__)

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
    # Highlight the actual AI summary body. Keep the impact hashtag outside the
    # bold span so WhatsApp renders the summary as the primary readable block.
    highlighted_body = f"*{body.strip()}*" if body and body.strip() else "*Summary unavailable.*"
    lines.append(f"🤖 {highlighted_body}{_impact_hashtag(impact)}")
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


def _basis_suffix(basis: str) -> str:
    """
    " (Consolidated)" / " (Standalone)" for the company line, "" when the
    extraction couldn't tell which statement it read.

    This rides in the COMPANY slot, BEFORE the "|", on purpose. The results
    template's period-dedup key is everything AFTER the "|"
    (db_watcher._result_period_key), and NSE/BSE publish the standalone and
    consolidated statements of one quarter as separate filings — putting the
    basis after the "|" would give them different period keys and send a
    subscriber two alerts for the same quarter.
    """
    b = (basis or "").strip().lower()
    if b.startswith("consolidat"):  return " (Consolidated)"
    if b.startswith("standalone"):  return " (Standalone)"
    return ""


def _build_results_takeaway(summary: FinancialSummary) -> str:
    """Build a short deterministic takeaway from extracted metrics.

    This is intentionally not another LLM call: it keeps Result Bits fast and
    guarantees that the message contains an actual highlighted summary.
    """
    if not summary or not summary.metrics:
        return ""

    # Prefer PAT/profit and revenue when present, otherwise use the first metric.
    preferred = None
    for metric in summary.metrics:
        name = (metric.name or "").lower()
        if "profit after tax" in name or name == "pat" or "net profit" in name:
            preferred = metric
            break
    if preferred is None:
        for metric in summary.metrics:
            if "revenue" in (metric.name or "").lower() or "sales" in (metric.name or "").lower():
                preferred = metric
                break
    if preferred is None:
        preferred = summary.metrics[0]

    q = (preferred.qoq_change or "").strip()
    y = (preferred.yoy_change or "").strip()
    label = preferred.name or preferred.short_name or "Key metric"
    parts = [label]
    if q:
        parts.append(f"{q}% QoQ")
    if y:
        parts.append(f"{y}% YoY")
    return " — ".join([parts[0], ", ".join(parts[1:])]) if len(parts) > 1 else parts[0]


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
    lines.append(
        f"💼 {summary.company_name}{_basis_suffix(summary.basis)} "
        f"| {summary.reporting_period} Results Out"
    )
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

    # Keep a visible, highlighted takeaway even when the structured results
    # extractor did not return a separate prose insight. This avoids a Result Bits
    # message looking like it has "no summary" while adding no second LLM call.
    takeaway = _build_results_takeaway(summary)
    lines.append("")
    lines.append("🤖 *Key Insights:*" )
    if takeaway:
        lines.append(f"*{takeaway}*")
    lines.append(f"🔗 {summary.insights_url or download_url or short_url or equisense_url}")
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

    # Build a plain LLM (no structured output / JSON parser).
    #
    # Every provider gets the SAME retry/timeout budget. A results-day burst
    # sends several summaries at once (SUMMARY_WORKERS) and a results filing
    # alone costs ~20k tokens via extract_financials, which is enough to reach
    # a 200k TPM account limit — so 429s arrive in clusters, not one at a time.
    # At high retry settings, multiple attempts a few
    # seconds apart can land inside the same rate-limited window and the
    # filing went out with no summary at all, permanently. The retries are
    # exponentially backed off by each SDK, so this rides out a short burst.
    # Well inside config.SUMMARY_TIMEOUT_SEC (25s), which still hard-caps it.
    if provider in ("google", "gemini"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        # Assigning None to os.environ raises an opaque TypeError; say what is
        # actually wrong instead.
        if not api_key:
            raise ValueError(
                "SUMMARY_PROVIDER is google/gemini but neither GEMINI_API_KEY "
                "nor GOOGLE_API_KEY is set."
            )
        os.environ["GOOGLE_API_KEY"] = api_key
        llm = ChatGoogleGenerativeAI(model=_model, google_api_key=api_key,
                                     temperature=0, timeout=LLM_TIMEOUT_SEC,
                                     max_retries=LLM_MAX_RETRIES)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        llm = ChatAnthropic(model=_model, temperature=0, max_tokens=512,
                            timeout=LLM_TIMEOUT_SEC, max_retries=LLM_MAX_RETRIES)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=_model, temperature=0, max_tokens=512,
                         timeout=LLM_TIMEOUT_SEC, max_retries=LLM_MAX_RETRIES)
    elif provider == "groq":
        from langchain_groq import ChatGroq
        llm = ChatGroq(model=_model, groq_api_key=os.getenv("GROQ_API_KEY"),
                       temperature=0, timeout=LLM_TIMEOUT_SEC,
                       max_retries=LLM_MAX_RETRIES)
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

    _summary_started = time.monotonic()
    summary_input = pdf_text[:6000]
    print(
        f"[timing] content_summary START provider={provider} model={_model} "
        f"input_chars={len(summary_input)} filing_type={filing_type or 'N/A'!r}",
        file=sys.stderr,
    )
    try:
        result = (prompt | llm).invoke({
            "pdf_text": summary_input,
            "filing_type": filing_type or "N/A",
        })
    except Exception as exc:
        _perf_log("content_summary FAIL", _summary_started, error=type(exc).__name__)
        raise

    raw = result.content.strip() if hasattr(result, "content") else str(result).strip()
    _perf_log("content_summary DONE", _summary_started, output_chars=len(raw))
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

# "Newspaper advertisement of results" filings carry the standard 4-column
# results layout (this quarter / prior quarter / year-ago quarter / full year)
# as bare DATE headers instead of a "quarter ended" PHRASE — 3+ dd.mm.yyyy
# dates in a row next to "(Unaudited)"/"(Audited)" markers is the layout
# signature. Missing this sent a genuine UltraTech Cement results filing out
# as a generic notice because none of _RESULT_PHRASES appeared verbatim.
_DATE_COLUMNS_RE = re.compile(r"(?:\d{2}\.\d{2}\.\d{4}\s*){3,}")
_AUDIT_MARKER_RE = re.compile(r"\(\s*(?:un)?audited\s*\)", re.IGNORECASE)

# P&L line-item names, as an INVESTOR PRESENTATION or a press release writes
# them — not just as the statutory results statement does. A deck reports
# "Net Sales", "Gross Contribution" and "PBDIT" where the filed statement says
# "Revenue from operations" and "Profit before tax": Asian Paints' Q1FY27
# investor presentation carried Net Sales / PBDIT / PBT / PAT for two periods
# and matched exactly ONE term ("revenue") of the original list, so it failed
# the >=2 gate and went out as a generic notice with no figures at all.
_METRIC_KEYWORDS = (
    "revenue", "total income", "total revenue", "profit before tax",
    "profit after tax", "net profit", "ebitda", "operating profit",
    "earnings per share", "total expenses", "total comprehensive income",
    "net sales", "income from operations", "profit for the period",
    "gross contribution", "gross margin", "operating margin",
)

# The same line items as the ABBREVIATIONS a deck labels its bar charts with.
# Matched case-SENSITIVELY and whole-word: these are always printed uppercase,
# and a case-insensitive "pat"/"eps" would fire on ordinary prose ("patent",
# "pattern") and hand a board-meeting notice to the metric extractor.
_METRIC_ABBREV_RE = re.compile(
    r"\b(?:PAT|PBT|PBDIT|PBILDT|EBITDA|EBIT|OPM|EPS)\b"
)

# Monetary-looking figures: "1,234.56", "12,34,567" (Indian grouping) or "934.17".
_MONEY_RE = re.compile(r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+\.\d{2}")


# An earnings-CALL TRANSCRIPT discusses the quarter that was just reported, so
# it names every metric, quotes figures for them and says "quarter ended" —
# it passes every results test while containing no results TABLE at all. The
# figures in it are spoken: rounded ("859 crores"), partial, and quoted for
# whichever periods the speaker felt like comparing. Shipped as a results alert
# it produced Shakti Pumps' "Jun 2026 Results Out" with Mar 2026 and Jun 2025
# carrying identical values, because the model padded a third period that was
# never discussed.
#
# Each marker carries the count that makes it conclusive, so a REAL results
# filing mentioning its upcoming call once ("...conference call will be held")
# cannot trip it — Asian Paints' results filing says "conference call" exactly
# once, below the threshold of 2. Measured across the corpus: the transcript
# matched 6 markers, every genuine filing matched 0.
_TRANSCRIPT_MARKERS = (
    (re.compile(r"\bmoderator\b", re.IGNORECASE), 3),        # dialogue turns
    (re.compile(r"\bnext question\b", re.IGNORECASE), 2),
    (re.compile(r"ladies and gentlemen", re.IGNORECASE), 1),
    (re.compile(r"question[\s\-]?and[\s\-]?answer session", re.IGNORECASE), 1),
    (re.compile(r"\bearnings (?:conference )?call\b", re.IGNORECASE), 2),
    (re.compile(r"\bconference call\b", re.IGNORECASE), 2),
)

# Document types whose TITLE alone rules out a results table. The exchange's
# own title is authoritative where our text heuristics are inference, so it is
# worth checking on its own.
_NON_RESULTS_TITLE_RE = re.compile(
    r"transcript|audio recording|earnings call|analyst meet|investor meet",
    re.IGNORECASE,
)


def looks_like_call_transcript(pdf_text: str, filing_type: str = "") -> bool:
    """
    True for an earnings-call transcript — a document that reads like a results
    filing to every keyword test but contains only spoken figures.

    Two independent routes: the exchange's own filing title, and the dialogue
    shape of the document itself (two markers must clear their thresholds, so a
    single passing mention of a call cannot trigger it).
    """
    if filing_type and _NON_RESULTS_TITLE_RE.search(filing_type):
        return True
    if not pdf_text:
        return False
    score = sum(1 for rx, threshold in _TRANSCRIPT_MARKERS
                if len(rx.findall(pdf_text)) >= threshold)
    return score >= 2


def count_metric_terms(pdf_text: str) -> int:
    """
    How many DISTINCT P&L line items the text names, counting both the spelled
    out form and the uppercase abbreviation a presentation uses for it.
    """
    low = (pdf_text or "").lower()
    hits = sum(1 for k in _METRIC_KEYWORDS if k in low)
    return hits + len(set(_METRIC_ABBREV_RE.findall(pdf_text or "")))


def looks_like_financial_results(pdf_text: str) -> bool:
    """
    Only treat a PDF as a quarterly/annual RESULTS document (and run financial
    metric extraction) when it really looks like one.

    Most exchange filings — board-meeting notices, trading-window closures,
    Reg 30 disclosures, newspaper ads, presentations without a results table —
    are NOT results statements and have no financial table. Running metric
    extraction on them just makes the model invent numbers. We require
    (a results phrase OR a dated 4-column results layout), at least two
    distinct metric terms, AND a table's worth of monetary figures (which a
    mere notice/intimation will not have).

    The monetary-figure floor is what keeps the widened metric vocabulary safe:
    a newspaper-publication INTIMATION names the results in its subject line
    but carries no table, so it still cannot reach 12 figures.

    An earnings-call TRANSCRIPT is excluded outright: it clears every test above
    while containing no table — see looks_like_call_transcript.
    """
    if not pdf_text:
        return False
    if looks_like_call_transcript(pdf_text):
        return False
    low = pdf_text.lower()
    has_phrase   = any(p in low for p in _RESULT_PHRASES)
    has_dated_columns = (
        bool(_DATE_COLUMNS_RE.search(pdf_text))
        and len(_AUDIT_MARKER_RE.findall(pdf_text)) >= 2
    )
    keyword_hits = count_metric_terms(pdf_text)
    money_count  = len(_MONEY_RE.findall(pdf_text))
    return (has_phrase or has_dated_columns) and keyword_hits >= 2 and money_count >= 12


# A heading that introduces the CONSOLIDATED results statement, e.g.
# "STATEMENT OF UNAUDITED CONSOLIDATED FINANCIAL RESULTS FOR THE QUARTER ENDED".
# Anchored on a heading-shaped line (short, names both "consolidated" and
# "results") so the many passing mentions in the NOTES below a table — "the
# consolidated financial results include the results of ..." — don't win.
_CONSOL_HEADING_RE = re.compile(
    r"(?im)^[^\n]{0,160}?\bconsolidated\b[^\n]{0,80}?\bresults?\b[^\n]{0,80}$"
)

# The same, for the standalone statement — used only to bound the consolidated
# section when standalone happens to be printed after it.
_STANDALONE_HEADING_RE = re.compile(
    r"(?im)^[^\n]{0,160}?\bstandalone\b[^\n]{0,80}?\bresults?\b[^\n]{0,80}$"
)


def _consolidated_heading_pos(pdf_text: str) -> int | None:
    """
    Character offset of the CONSOLIDATED results heading, or None when the
    document has no consolidated statement (a company with no subsidiaries).

    A combined heading ("Statement of Standalone and Consolidated Financial
    Results") names both and matches here too — correctly, since such a
    document does carry consolidated columns.
    """
    for m in _CONSOL_HEADING_RE.finditer(pdf_text or ""):
        line = m.group(0)
        # "Consolidated" inside a sentence is prose from the notes, not a
        # heading. Real headings don't run on into a full sentence.
        if line.rstrip().endswith("."):
            continue
        return m.start()
    return None


def has_consolidated_statement(pdf_text: str) -> bool:
    """True when the filing carries a consolidated (group) results statement."""
    return _consolidated_heading_pos(pdf_text) is not None


def consolidated_first(pdf_text: str) -> str:
    """
    The same text with the CONSOLIDATED statement moved to the front.

    Indian filings print the STANDALONE statement first, so on a long filing
    the consolidated table can sit past extract_financials' character cap and
    never reach the model at all — which no prompt wording can fix, because
    the table simply isn't in the window. Nothing is dropped here, only
    reordered, so every number the model may cite is still present for
    verify_metrics_against_text to check afterwards.

    Returns the text unchanged when there is no consolidated statement, or
    when it already comes first.
    """
    start = _consolidated_heading_pos(pdf_text)
    if not start:                      # None (absent) or 0 (already first)
        return pdf_text
    return pdf_text[start:] + "\n\n" + pdf_text[:start]


def reconcile_basis(summary: "FinancialSummary", pdf_text: str) -> str:
    """
    Settle which statement the metrics actually came from, and never let the
    alert claim more than we can show.

    The model self-reports `basis`, and it is exactly the field it has the
    least reason to get right — so it is checked, not trusted:

      - No consolidated statement in the document → the numbers can only be
        standalone, whatever the model said.
      - The document HAS one → decide by WHERE the headline revenue figure
        appears. Found only inside the consolidated section → consolidated;
        only inside the standalone section → standalone, even if the model
        claimed otherwise. Found in both (the statements agree on that line)
        or in neither, the position proves nothing, so the model's claim
        stands only when it is "consolidated" — the basis we asked for.
      - Both statements share one region (the combined column-group layout)
        → undetermined, since no figure can be attributed by position.

    Returns the settled basis; "" means undetermined, and _basis_suffix then
    prints no label at all rather than a wrong one.
    """
    claimed = (summary.basis or "").strip().lower()
    consol_start = _consolidated_heading_pos(pdf_text)

    if consol_start is None:
        summary.basis = "standalone" if summary.metrics else ""
        return summary.basis

    # Text belonging to the standalone statement: everything before the
    # consolidated heading (plus any standalone section printed after it).
    #
    # The search for that trailing standalone section starts past the END of
    # the consolidated heading line, and ignores any heading that names
    # "consolidated" as well. A COMBINED heading ("Statement of Standalone and
    # Consolidated Financial Results", the layout where the two appear as
    # column groups of ONE table) matches both patterns at the same offset —
    # taking it as the start of a standalone section collapsed the
    # consolidated region to the empty string, and every consolidated figure
    # then looked standalone.
    text = pdf_text or ""
    line_end = text.find("\n", consol_start)
    scan_from = line_end + 1 if line_end != -1 else len(text)
    sa_start = None
    for sa in _STANDALONE_HEADING_RE.finditer(text, scan_from):
        if "consolidated" in sa.group(0).lower():
            continue
        sa_start = sa.start()
        break

    standalone_region = text[:consol_start]
    if sa_start is not None:
        standalone_region += text[sa_start:]
    consol_region = text[consol_start:sa_start]

    # Combined layout: ONE table whose columns are grouped "STANDALONE" then
    # "CONSOLIDATED", under a single heading naming both, with no separate
    # standalone statement anywhere. Both column groups sit in the SAME text
    # region, so matching a figure to a region proves nothing about which
    # group it came from — every standalone figure would "verify" as
    # consolidated. Report undetermined and let _basis_suffix print no label,
    # rather than stamp a confident wrong one on the alert.
    heading_line = text[consol_start:line_end if line_end != -1 else None]
    if sa_start is None and "standalone" in heading_line.lower():
        summary.basis = ""
        return summary.basis

    rev = next((m for m in summary.metrics
                if (m.short_name or "").upper() == "REV"), None)
    rev = rev or (summary.metrics[0] if summary.metrics else None)
    if rev is None:
        summary.basis = ""
        return summary.basis

    head = next((p.value for p in rev.periods if p.value), "")
    num  = re.search(r"-?\d[\d,]*\.?\d*", head or "")
    if not num:
        summary.basis = claimed if claimed.startswith("consolidat") else ""
        return summary.basis

    core = num.group(0).replace(",", "").lstrip("-").rstrip(".")
    in_consol     = core in re.sub(r"[,\s]", "", consol_region)
    in_standalone = core in re.sub(r"[,\s]", "", standalone_region)

    if in_consol and not in_standalone:
        summary.basis = "consolidated"
    elif in_standalone and not in_consol:
        summary.basis = "standalone"
    else:
        # Present in both (the two statements agree on this line) or in
        # neither — nothing here distinguishes them, so keep the model's own
        # claim only when it is the one we asked for.
        summary.basis = "consolidated" if claimed.startswith("consolidat") else ""
    return summary.basis


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
            # Sign stripped: this is a FABRICATION check, and a loss the
            # document prints "(20.00)" reaches us as "-₹20.00 Cr" (or the
            # reverse), which would never match on the sign character.
            core     = num.group(0).replace(",", "").lstrip("-").rstrip(".")
            int_part = core.split(".")[0]
            # Match the full number, or at least a 3+ digit integer part, in the
            # comma-stripped source text.
            if (core and core in text_digits) or (len(int_part) >= 3 and int_part in text_digits):
                kept.append(m)
                break
    summary.metrics = kept
    return len(kept)


_VALUE_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")

# A minus that sits BEFORE the currency symbol ("-₹20.00 Cr") or an accounting
# bracket ("₹(20.00) Cr", "(20.00)") — the two ways an Indian results table
# prints a LOSS. _VALUE_NUM_RE matches neither: its optional "-" has to sit
# immediately left of a digit. Both forms therefore parsed as +20.00, so a
# ₹20 Cr LOSS shipped as a ₹20 Cr PROFIT, the QoQ off it came out "+150.00%"
# instead of a loss-to-profit swing, and recompute_changes' "base <= 0" guard
# could never fire.
_NEG_PREFIX_RE = re.compile(r"[-−–(]\s*(?:rs\.?|inr|₹|\$)?\s*$",
                            re.IGNORECASE)


def _signed_number(value: str) -> float | None:
    """The number inside a metric VALUE *with its sign*, or None if there is
    no number. Use this instead of _VALUE_NUM_RE wherever the magnitude is
    used arithmetically — see _NEG_PREFIX_RE for why."""
    if not value:
        return None
    m = _VALUE_NUM_RE.search(value)
    if not m:
        return None
    num = float(m.group(0).replace(",", ""))
    if num > 0 and _NEG_PREFIX_RE.search(value[:m.start()]):
        return -num
    return num


# Multiply a figure in <scale> by this to get crore.
_SCALE_TO_CRORE = {"lakh": 0.01, "crore": 1.0, "million": 0.1, "billion": 100.0}

# The denomination heading Indian results tables carry: "(₹ in lakhs)",
# "(Rs. in Crore)", "(₹ in Millions)", "Amount in Lakhs", ... We deliberately
# require the "in <unit>" phrasing — a bare "Cr" appears all over a document as
# a value suffix and would make detection meaningless.
#
# The trailing [a-z]{0,2} on `long` absorbs OCR noise on the unit itself. A
# scanned filing's "(₹ in Crores)" reaches us as "(f in Crorea)" — the currency
# glyph is already optional here, but the mangled final letter made the whole
# heading invisible, so detect_document_scale() returned None and every figure
# went out with no denomination at all ("🗓️ Jun 2026: 10,521.44").
#
# `short` covers the abbreviated heading an investor DECK uses ("Note: Figures
# in columns in ₹ cr"), where the currency symbol sits between "in" and the
# unit. It gets no OCR tolerance: "cr" plus two free letters would also match
# "in crop", and the whole point of requiring "in " is that a bare "Cr" is
# meaningless as a signal.
_DOC_SCALE_RE = re.compile(
    r"(?:rs\.?|inr|₹|amount|figures)?\s*(?:are\s+)?in\s+"
    r"(?:(?:rs\.?|inr|₹)\s*)?"
    r"(?:(?P<long>lakhs?|lacs?|crores?|millions?|billions?)[a-z]{0,2}"
    r"|(?P<short>crs?|mns?|bns?))\b",
    re.IGNORECASE,
)
_SCALE_ALIASES = {
    "lakh": "lakh", "lakhs": "lakh", "lac": "lakh", "lacs": "lakh",
    "crore": "crore", "crores": "crore", "cr": "crore", "crs": "crore",
    "million": "million", "millions": "million", "mn": "million", "mns": "million",
    "billion": "billion", "billions": "billion", "bn": "billion", "bns": "billion",
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

    When a document states SEVERAL denominations — a P&L "(Rs. in Crore)" plus
    notes or a shareholding table "in lakhs" — the heading printed NEAREST the
    results table wins, not the most frequent one. A plain majority vote picked
    "lakh" for a crore-denominated P&L carrying two lakhs notes, which would
    have divided every correct figure by 100.
    """
    if not pdf_text:
        return None
    matches = []
    for m in _DOC_SCALE_RE.finditer(pdf_text):
        unit  = m.group("long") or m.group("short") or ""
        scale = _SCALE_ALIASES.get(unit.lower())
        if scale:
            matches.append((m.start(), scale))
    if not matches:
        return None

    # The results table itself is the anchor: a denomination heading sits
    # directly above the table it applies to.
    low    = pdf_text.lower()
    anchors = [low.find(k) for k in _METRIC_KEYWORDS if k in low]
    anchors += [m.start() for m in _METRIC_ABBREV_RE.finditer(pdf_text)]
    if anchors:
        anchor = min(anchors)
        return min(matches, key=lambda sm: abs(sm[0] - anchor))[1]

    counts = {}
    for _, scale in matches:
        counts[scale] = counts.get(scale, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def _value_suffix_scale(value: str) -> str | None:
    """
    The denomination the VALUE ITSELF spells out ("₹1,075 Cr" → crore), or None
    when it carries no suffix.

    Deliberately ignores the block's `unit` field: this is the only signal
    strong enough to RESCALE on. `unit` says what table the model read, not
    what it wrote — trusting it would divide an already-converted "₹1,074.96"
    labelled unit="lakh" by 100 all over again.
    """
    low = (value or "").lower()
    if re.search(r"\blakhs?\b|\blacs?\b", low):
        return "lakh"
    if re.search(r"\bmn\b|\bmillions?\b", low):
        return "million"
    if re.search(r"\bbn\b|\bbillions?\b", low):
        return "billion"
    if re.search(r"\bcr\b|\bcrores?\b", low):
        return "crore"
    return None


def _format_crore(v: float) -> str:
    """
    Render a crore figure the way the rest of the message does.

    Always two decimals. The old "drop the decimals above ₹1,000 Cr" rule
    rendered a ₹1,07,496 lakh figure as "₹1,075 Cr" rather than the exact
    "₹1,074.96 Cr" — a ₹4 lakh discrepancy against a filing the subscriber
    can open and check line by line.

    A loss reads "-₹20.00 Cr", not "₹-20.00 Cr".
    """
    return f"{'-' if v < 0 else ''}₹{abs(v):,.2f} Cr"


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
    off the source table but tagged with the wrong denomination — or with no
    denomination at all.

    The verbatim check is what makes this safe: if the digits the model emitted
    appear as-is in the PDF, it transcribed the printed figure rather than
    converting it — so the figure's true denomination MUST be the table's
    (`doc_scale`), whatever the model labelled it. When the digits do NOT
    appear verbatim the model did its own conversion, and we leave it alone
    rather than risk double-converting a correct value.

    Only an EXPLICIT suffix on the value counts as "already labelled" — the
    block's `unit` field does not. A model that emitted a bare "858.67" off a
    crore table had unit="crore", which matched doc_scale, so this skipped it
    and the subscriber received "🗓️ Jun 2026: 858.67" with no currency and no
    denomination at all. The verbatim gate is what makes trusting doc_scale
    over `unit` safe here: a value the model had already converted itself
    ("₹1,074.96" off a lakhs table) does not appear verbatim, so it is skipped.

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
            # Digits only for the verbatim check — the sign is carried
            # separately, since the document may print a loss in brackets
            # ("(2,000)") where the value says "-2,000" or vice versa.
            core = num.group(0).replace(",", "").lstrip("-").rstrip(".")
            # Only trust figures transcribed straight from the document.
            if not core or core not in text_digits:
                continue
            if _value_suffix_scale(p.value) == doc_scale:
                continue        # already labelled correctly, and explicitly so
            signed = _signed_number(p.value)
            if signed is None:
                continue
            p.value = _format_crore(signed * _SCALE_TO_CRORE[doc_scale])
            touched = True
            fixed += 1
        if touched:
            m.unit = "crore"
    return fixed


def normalize_metric_units(summary: "FinancialSummary") -> int:
    """
    Convert every monetary value that spells out a NON-crore denomination into
    crore, so one alert never mixes denominations and every alert is comparable
    with the next.

    reconcile_metric_units() above only rewrites values the model MISLABELLED.
    A value the model labelled CORRECTLY off a lakhs table — "₹1,07,496 Lakh",
    exactly what SYSTEM_PROMPT rule 5 asks it to produce — matched its
    doc_scale and was left alone, so subscribers received "₹1,07,496 Lakh" for
    one company and "₹858.67 Cr" for the next. Worse, a filing whose revenue
    was transcribed verbatim (and so rescaled) alongside a PAT that wasn't
    mixed BOTH denominations inside a single message.

    Only an explicit suffix on the value triggers a conversion — see
    _value_suffix_scale — and per-share metrics carry no denomination at all,
    so they are skipped exactly as in reconcile_metric_units(). Idempotent: a
    converted value states "Cr".

    Returns the number of period values converted.
    """
    fixed = 0
    for m in summary.metrics:
        if _is_per_share(m.name, m.short_name):
            continue
        touched = False
        for p in m.periods:
            if not p.value or "%" in p.value:
                continue
            scale = _value_suffix_scale(p.value)
            if scale is None or scale == "crore":
                continue
            num = _signed_number(p.value)
            if num is None:
                continue
            p.value = _format_crore(num * _SCALE_TO_CRORE[scale])
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
    num = _signed_number(value)
    if num is None:
        return None
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
        return _signed_number(value)
    crore = _value_to_crore(value, unit)
    if crore is not None:
        return crore
    return _signed_number(value)


# Month names as they appear in a period label, and the two label shapes the
# extractor produces: "Jun 2026" / "March 2026" / "Jun'25", and the raw column
# header "30.06.2026".
_MONTH_NUM = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_LABEL_DMY_RE   = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b")
_LABEL_MONTH_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*'?(\d{2,4})\b",
    re.IGNORECASE,
)


def _period_order_key(label: str):
    """
    (year, month, day) for a period label — "Jun 2026", "30.06.2026", "Jun'25".
    None when the label carries no parsable month+year ("Q1 FY27", "FY 2025-26"),
    which is the signal to leave the periods in the order the model emitted them.
    """
    if not label:
        return None
    m = _LABEL_DMY_RE.search(label)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12:
            return (year, month, day)
    m = _LABEL_MONTH_RE.search(label)
    if m:
        year = int(m.group(2))
        if year < 100:
            year += 2000
        return (year, _MONTH_NUM[m.group(1)[:3].lower()], 0)
    return None


def order_periods(summary: "FinancialSummary") -> int:
    """
    Sort every metric's periods NEWEST FIRST.

    recompute_changes() and both result templates assume
    [current quarter, previous quarter, year-ago quarter]. SYSTEM_PROMPT asks
    for that order but nothing enforced it, and a model that echoed the
    table's own left-to-right order (oldest first) produced a QoQ of -27.43%
    where the truth was +0.10% — correct figures, inverted change, and a 🔴
    beside a quarter that actually grew.

    Only reorders when EVERY label parses to a DISTINCT month+year: an
    unparsable or duplicated label means we cannot be sure which period is
    which, and the model's own ordering is then the better guess. Returns the
    number of metrics reordered.
    """
    fixed = 0
    for m in summary.metrics:
        keys = [_period_order_key(p.period_label) for p in m.periods]
        if len(keys) < 2 or any(k is None for k in keys) or len(set(keys)) != len(keys):
            continue
        ordered = sorted(m.periods, reverse=True,
                         key=lambda p: _period_order_key(p.period_label))
        if ordered != m.periods:
            m.periods = ordered
            fixed += 1
    return fixed


def recompute_changes(summary: "FinancialSummary") -> int:
    """
    Derive QoQ / YoY from the extracted period values instead of trusting the
    model's own arithmetic.

    The model's numbers were neither correct nor stable: the same filing run
    twice reported OPM (18.5% → 21.2%) as "+1.27% QoQ" and then "+14.86% QoQ",
    when the change is +14.59%. Periods are [current, prev quarter, year-ago],
    so QoQ compares [0] vs [1] and YoY [0] vs [2].

    A zero or negative base reports "n/a": percent change off a loss or a nil
    period is meaningless. This branch used to `continue`, keeping whatever the
    model had invented — and now that _signed_number() actually detects a loss
    printed as "(20.00)" or "-₹20.00 Cr", it is reachable, so a loss-to-profit
    swing would otherwise ship the model's fabricated "+999%".
    Returns the number of values corrected.
    """
    fixed = 0
    for m in summary.metrics:
        vals = [_period_magnitude(p.value, m.unit) for p in m.periods]
        if not vals or vals[0] is None:
            continue
        current = vals[0]
        for idx, attr in ((1, "qoq_change"), (2, "yoy_change")):
            base = vals[idx] if len(vals) > idx else None
            if base is None:
                continue
            if base <= 0:
                if getattr(m, attr, None) != "n/a":
                    setattr(m, attr, "n/a")
                    fixed += 1
                continue
            computed = f"{(current - base) / base * 100:+.2f}"
            if getattr(m, attr, None) != computed:
                setattr(m, attr, computed)
                fixed += 1
    return fixed


def drop_duplicate_period_metrics(summary: "FinancialSummary") -> int:
    """
    Drop any metric that quotes the SAME value for two different periods —
    the signature of the model padding out periods the document never reported.

    A results TABLE always prints three distinct columns. A transcript, a press
    release or a two-period investor deck gives the model fewer, and rather than
    return two periods it repeats one to fill the third: Shakti Pumps' earnings
    call went out with revenue "Jun 2026: ₹859 Cr / Mar 2026: ₹623 Cr /
    Jun 2025: ₹623 Cr" and, inevitably, a QoQ identical to the YoY.

    Dropping the whole metric is deliberate. Which of the two duplicated columns
    is the invented one is not knowable, and removing one would silently shift
    the remaining periods under headings that mean something else — a YoY change
    rendered as QoQ. Losing a row is recoverable; publishing a fabricated
    quarter under a real company's name is not. A genuinely flat metric (a
    margin identical two quarters running) is the accepted cost.

    Returns the number of metrics kept.
    """
    kept = []
    for m in summary.metrics:
        seen, duplicate = [], False
        for p in m.periods:
            mag = _period_magnitude(p.value, m.unit)
            if mag is None:
                continue
            if any(abs(mag - s) < 1e-9 for s in seen):
                duplicate = True
                break
            seen.append(mag)
        if not duplicate:
            kept.append(m)
    summary.metrics = kept
    return len(kept)


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
                num = _signed_number(p.value)
                if num is not None and abs(num) > _MAX_PLAUSIBLE_PERCENT:
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


_LEGAL_SUFFIX_RE = re.compile(
    r"\b(limited|ltd\.?|private|pvt\.?|inc\.?|plc|corporation|corp\.?)\b",
    re.IGNORECASE,
)


def _normalize_company_name(name: str) -> str:
    name = _LEGAL_SUFFIX_RE.sub(" ", name or "")
    name = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def _names_plausibly_match(hint: str, extracted: str) -> bool:
    """
    Loose sanity check that `extracted` (the LLM's own read of the company
    name off the PDF) is plausibly the SAME company as `hint` (the exchange's
    own record for this filing/symbol — authoritative, not LLM-derived).

    Exists to catch page-bleed: a "newspaper advertisement" filing can be a
    scan of a full newspaper PAGE carrying several companies' notices side by
    side. Widening looks_like_financial_results() to catch these (the dated
    4-column layout) means the extractor can now lock onto a NEIGHBOURING
    company's results table on the same page — real numbers, correctly
    verified against the source text, attached to the wrong company. Seen in
    production: a filing under symbol ULTRACEMCO whose extracted metrics were
    actually CG Power and Industrial Solutions', a different company whose
    ad shared the same scanned page.

    One shared significant word is enough to pass — this only needs to catch
    a clean mismatch (a different company name entirely), not police naming
    variants precisely.

    An NSE SYMBOL counts as a match for the name it is an abbreviation of. The
    hint is the exchange's record for the filing, which is the bare symbol
    whenever the company isn't in config.COMPANY_LIST and the portal name
    lookup misses or errors — and a symbol is one squashed token, so word
    intersection could never match it: "TATAPOWER" vs "The Tata Power Company
    Limited" shares no WORD with the name it abbreviates, and every metric of a
    correctly-extracted Tata Power results filing was being discarded as
    another company's. Comparing the space-stripped forms catches those
    (tatapower ⊂ thetatapowercompany) while still rejecting a genuinely
    different company (cgpowerandindustrialsolutions vs ultracemco).
    """
    h, e = _normalize_company_name(hint), _normalize_company_name(extracted)
    if not h or not e:
        return True  # nothing to compare against — don't block on missing data
    h_words = {w for w in h.split() if len(w) > 3}
    e_words = {w for w in e.split() if len(w) > 3}
    if h_words & e_words:
        return True
    h_squashed, e_squashed = h.replace(" ", ""), e.replace(" ", "")
    if len(h_squashed) < 4 or len(e_squashed) < 4:
        return True                     # too short to judge — don't block
    return h_squashed in e_squashed or e_squashed in h_squashed


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
    print(
        f"[perf] process_pdf START file={os.path.basename(str(pdf_source))} "
        f"provider={provider} model={model or PROVIDER_DEFAULTS.get(provider)} "
        f"filing_type={filing_type or 'N/A'!r}",
        file=sys.stderr,
    )
    print(f"[1/3] Loading PDF: {pdf_source}", file=sys.stderr)
    tmp_path = None

    if pdf_source.startswith("http://") or pdf_source.startswith("https://"):
        print("      Downloading...", file=sys.stderr)
        tmp_path = download_pdf(pdf_source)
        pdf_path = tmp_path
    else:
        pdf_path = pdf_source

    import time as _time
    _pipeline_started = _time.monotonic()
    try:
        _extract_started = _time.monotonic()
        pdf_text = extract_text_from_pdf_file(pdf_path)
        print(f"      ⏱ PDF extraction: {_time.monotonic() - _extract_started:.2f}s", file=sys.stderr)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not pdf_text.strip():
        raise ValueError(
            "No text extracted from PDF — it may be scanned/image-based. "
            "Try a text-layer PDF."
        )
    print(
        f"[perf] PDF_TEXT chars={len(pdf_text):,} "
        f"provider={provider} file={os.path.basename(str(pdf_source))}",
        file=sys.stderr,
    )

    # Step 2: LLM financial extraction — ONLY for genuine results documents.
    _model_name = model or PROVIDER_DEFAULTS.get(provider, "default")
    summary     = None
    company     = company_hint or "Unknown Company"

    if looks_like_call_transcript(pdf_text, filing_type):
        # Checked separately from looks_like_financial_results so the reason is
        # visible in the log, and so the exchange's own filing TITLE counts —
        # looks_like_financial_results only ever sees the text.
        print("[2/3] Earnings-call transcript / recording — no results table to "
              "extract; using a plain content summary.", file=sys.stderr)
    elif looks_like_financial_results(pdf_text):
        print(f"[2/3] Results document detected — extracting financials via "
              f"{provider} / {_model_name} ...", file=sys.stderr)
        try:
            _llm_started = _time.monotonic()
            summary = extract_financials(pdf_text, provider=provider, model=model)
            print(f"      ⏱ Financial LLM: {_time.monotonic() - _llm_started:.2f}s", file=sys.stderr)
            print(
                f"[perf] financial_result metrics={len(summary.metrics) if summary else 0}",
                file=sys.stderr,
            )
            extracted_name = summary.company_name or ""
            if (company_hint and extracted_name
                    and not _names_plausibly_match(company_hint, extracted_name)):
                # The metrics almost certainly belong to a DIFFERENT company
                # sharing this scanned page — see _names_plausibly_match.
                # Discard them entirely rather than risk shipping a real
                # profit figure under the wrong public company's name.
                print(f"      Extracted company '{extracted_name}' does not match "
                      f"expected '{company_hint}' — likely a different company's "
                      f"table on a shared newspaper page; discarding metrics.",
                      file=sys.stderr)
                summary = None
                raise ValueError("company identity mismatch")
            # company_hint is the exchange's OWN record for this filing/symbol
            # (ground truth) — always prefer it over the LLM's own reading of
            # the name off the page, which the identity check above doesn't
            # otherwise use.
            company = company_hint or extracted_name or "Unknown Company"
            summary.company_name = company
            # Defence in depth, in THIS order — each step depends on the last:
            #  1. verify: drop metrics whose digits aren't in the PDF at all.
            #     Must run BEFORE reconciliation, which rewrites values into
            #     crore and would then no longer match the source text.
            verified = verify_metrics_against_text(summary, pdf_text)
            print(f"      Kept {verified} metric(s) verified against source text.", file=sys.stderr)
            #  1b. basis: settle standalone vs consolidated and correct the
            #     model's own claim. Must run BEFORE the unit steps below —
            #     it matches the extracted figure against the source text, and
            #     those steps rewrite values into Cr, after which nothing would
            #     match the document any more (same reason as step 1).
            basis = reconcile_basis(summary, pdf_text)
            print(f"      Statement basis: {basis or 'undetermined'}"
                  f"{'' if basis else ' (no label will be shown)'}.", file=sys.stderr)
            #  2. reconcile: fix figures transcribed off a lakhs/millions table
            #     but labelled "Cr" (the 100x error class).
            doc_scale = detect_document_scale(pdf_text)
            if doc_scale:
                corrected = reconcile_metric_units(summary, pdf_text, doc_scale)
                if corrected:
                    print(f"      Document is denominated in {doc_scale} — "
                          f"re-scaled {corrected} mislabelled value(s) to Cr.", file=sys.stderr)
            #  3. normalise: convert values CORRECTLY labelled in a non-crore
            #     denomination ("₹1,07,496 Lakh") to Cr too, so no message
            #     mixes denominations. Must run AFTER reconciliation, which
            #     depends on the model's original labels being intact.
            normalised = normalize_metric_units(summary)
            if normalised:
                print(f"      Converted {normalised} value(s) from lakh/million/"
                      f"billion to Cr.", file=sys.stderr)
            #  4. plausibility: drop what's still absurd for a quarterly figure
            #     (e.g. a balance-sheet total misread as Revenue/PAT).
            plausible = drop_implausible_metrics(summary)
            if plausible != verified:
                print(f"      Dropped {verified - plausible} metric(s) with "
                      f"implausible magnitude.", file=sys.stderr)
            #  4b. padding: drop metrics repeating one value across two periods,
            #     which means the document reported fewer periods than the model
            #     emitted. Runs after the unit steps so the comparison is on
            #     final, like-for-like magnitudes.
            distinct = drop_duplicate_period_metrics(summary)
            if distinct != plausible:
                print(f"      Dropped {plausible - distinct} metric(s) repeating "
                      f"one value across periods (padded).", file=sys.stderr)
            #  5. order: put each metric's periods newest-first, so the change
            #     below compares the right pair and the rows read in the order
            #     the template's headings imply.
            reordered = order_periods(summary)
            if reordered:
                print(f"      Re-ordered periods newest-first for {reordered} "
                      f"metric(s).", file=sys.stderr)
            #  6. changes: recompute QoQ/YoY from the (now verified, correctly
            #     scaled, correctly ordered) period values. Must run LAST —
            #     the steps above rewrite values and their order, and a change
            #     computed before them would describe the pre-correction numbers.
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
        print(f"      ⏱ Total PDF pipeline: {_time.monotonic() - _pipeline_started:.2f}s", file=sys.stderr)
        return format_whatsapp_message(summary, equisense_url=equisense_url,
                                       short_url=short_url, download_url=download_url)

    print("      No financial metrics — generating content summary instead.", file=sys.stderr)
    _content_started = _time.monotonic()
    try:
        result_message = summarize_content(
            pdf_text,
            company_name=company,
            provider=provider,
            model=model,
            equisense_url=equisense_url,
            filing_type=filing_type,
            download_url=download_url,
            short_url=short_url,
        )
    except Exception as exc:
        _perf_log(
            "process_pdf CONTENT_SUMMARY_FAIL",
            _content_started,
            company=company,
            error=type(exc).__name__,
        )
        raise

    _perf_log(
        "process_pdf CONTENT_SUMMARY_DONE",
        _content_started,
        company=company,
        output_chars=len(result_message or ""),
    )
    _perf_log(
        "process_pdf TOTAL",
        _pipeline_started,
        company=company,
        chars=len(pdf_text),
        result="content_summary",
    )
    return result_message


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
