# ============================================================
#  preview.py — Testing tool: run one PDF through the REAL
#                summarisation + template-routing pipeline and
#                see exactly what subscribers would receive,
#                WITHOUT sending a WhatsApp message or writing to
#                bot_data.db / PostgreSQL.
#
#  Why this exists: a template/prompt change today can't be
#  judged until a matching real filing shows up and someone
#  manually checks the WhatsApp thread. This runs the same code
#  db_watcher.py uses (output.process_pdf, resolve_template_send,
#  config.render_template_body) against a PDF on disk instead.
#
#  Usage:
#      python preview.py --pdf path/to/filing.pdf
#      python preview.py --pdf path/to/filing.pdf --company "Tata Consultancy Services" --symbol TCS
# ============================================================
import argparse
import json
import os
import sys
from datetime import datetime

import config
import output
import whatsapp
import db_watcher


def _extract_once(pdf_path: str) -> tuple:
    """
    Extract the PDF text ONCE and report on it. Returns (text, report).

    Deliberately a single call: the diagnostics below and output.process_pdf
    all need this text, and re-parsing a 60k-char filing per section made a
    preview three times slower than the real pipeline for no reason.

    `production_drops` mirrors output.process_pdf's ACTUAL failure condition
    (`if not pdf_text.strip()`) rather than a threshold of our own — a
    preview that stopped at "<100 chars" would claim a filing is dropped
    that production happily summarises, which defeats the point of the tool.
    """
    report = {}
    try:
        text = output.extract_text_from_pdf_file(pdf_path, report=report)
    except Exception as e:
        return "", {
            "chars": 0,
            "production_drops": True,
            "extract_error": str(e),
            "note": "PDF could not be parsed at all (corrupt/encrypted?) — "
                    "this is NOT the same as a scanned PDF.",
        }
    chars = len(text.strip())
    report.update({
        "chars": chars,
        # Production only bails when there is NO text whatsoever.
        "production_drops": chars == 0,
        "sample": text.strip()[:300],
    })
    if chars == 0:
        report["note"] = ("No text layer AND no OCR output — an image-only PDF "
                          "with OCR disabled or unavailable (is the "
                          "tesseract-ocr binary installed?). "
                          "output.process_pdf raises here.")
    elif chars < 100:
        report["note"] = (f"Only {chars} chars of text — likely a scanned page "
                          "with a thin text layer. Production does NOT drop "
                          "this; it sends whatever the LLM makes of it.")
    elif report.get("ocr_pages"):
        report["note"] = (f"OCR supplied page(s) {report['ocr_pages']} "
                          f"({report['ocr_chars']:,} chars) — the numbers below "
                          f"come from glyph recognition, so spot-check them "
                          f"against the filing.")
    elif report.get("garbled_pages"):
        report["note"] = (f"Page(s) {report['garbled_pages']} have a broken text "
                          f"layer and were NOT recovered by OCR.")
    return text, report


def _results_detection_report(text: str) -> dict:
    """
    Why looks_like_financial_results() said yes or no — every signal it
    actually uses, including the dated-column layout that a
    newspaper-advertisement filing is recognised by (this report used to omit
    it, so it explained a detected filing as having no result phrase).
    """
    low = text.lower()
    has_phrase   = any(p in low for p in output._RESULT_PHRASES)
    has_dated_columns = (
        bool(output._DATE_COLUMNS_RE.search(text))
        and len(output._AUDIT_MARKER_RE.findall(text)) >= 2
    )
    keyword_hits = [k for k in output._METRIC_KEYWORDS if k in low]
    abbrev_hits  = sorted(set(output._METRIC_ABBREV_RE.findall(text)))
    term_count   = output.count_metric_terms(text)
    money_count  = len(output._MONEY_RE.findall(text))
    detected     = output.looks_like_financial_results(text)
    return {
        "detected_as_results": detected,
        "has_result_phrase": has_phrase,
        "has_dated_columns": has_dated_columns,
        "metric_keywords_found": keyword_hits,
        "metric_abbreviations_found": abbrev_hits,
        "money_figures_found": money_count,
        "document_scale": output.detect_document_scale(text),
        "reason": (
            "looks like a results document"
            if detected else
            f"needs (a result phrase OR dated result columns) AND >=2 metric "
            f"terms AND >=12 money figures — got phrase={has_phrase}, "
            f"dated_columns={has_dated_columns}, terms={term_count}, "
            f"money={money_count}"
        ),
    }


def preview_pdf(
    pdf_path: str,
    provider: str | None = None,
    model: str | None = None,
    company: str | None = None,
    symbol: str = "N/A",
    filing_type: str = "Investor Filing",
    download_url: str = "https://equityalerts.in/sample-filing.pdf",
    exchange_time: str | None = None,
) -> dict:
    """
    Run `pdf_path` through the real pipeline and return every stage's output.
    Pure with respect to the outside world: no WhatsApp send, no bot_data.db
    write, no PostgreSQL. The only network calls are to the configured LLM
    provider (needed to actually generate the summary).
    """
    provider = provider or getattr(config, "SUMMARY_PROVIDER", "openai")
    model    = model or getattr(config, "SUMMARY_MODEL", "gpt-4o-mini")
    exchange_time = exchange_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    company_name  = company or "Unknown Company"

    pdf_text, extraction = _extract_once(pdf_path)
    report = {
        "pdf_path": pdf_path,
        "provider": provider,
        "model": model,
        "extraction": extraction,
        "results_detection": _results_detection_report(pdf_text),
    }

    # ── The AI summary — or the reason there isn't one. ──────────────────
    # Either way we still render what subscribers receive: when the summary
    # fails, db_watcher._build_caption() falls back to a bare caption and
    # SENDS IT ANYWAY. Stopping here (as this tool first did) hid the
    # message people actually get on exactly the scanned-PDF filings we're
    # trying to diagnose.
    ai_body = None
    if extraction["production_drops"]:
        report["summary_status"] = (
            extraction.get("extract_error")
            or "No text extracted — output.process_pdf raises; production "
               "falls back to the bare caption below."
        )
    else:
        try:
            ai_body = output.process_pdf(
                pdf_path,
                provider=provider,
                model=model,
                company_hint=company,
                filing_type=filing_type,
                download_url=download_url,
            )
            marker = ai_body.find("📢")
            if marker != -1:
                ai_body = ai_body[marker:]
            report["ai_body"] = ai_body
            report["summary_status"] = "ok"
        except Exception as e:
            ai_body = None
            report["summary_status"] = (
                f"process_pdf failed: {e} — production falls back to the "
                f"bare caption below."
            )

    if ai_body:
        body = ai_body
        report["used_fallback_caption"] = False
    else:
        # Exactly db_watcher._full_caption()'s fallback string.
        body = (f"📄 *{company_name}* — {filing_type}\n"
                f"🏦 Symbol: {symbol}")
        report["used_fallback_caption"] = True

    # ── Open-window (free-form text) message — exactly what db_watcher's
    # _caption_with_time() produces before it's handed to whatsapp.send_text
    # / send_cta_url_button.
    open_window_message = db_watcher._caption_with_time(
        body, company_name, symbol, exchange_time
    )
    report["open_window_message"] = open_window_message

    # ── Closed-window (approved template) message — the SAME routing
    # decision db_watcher._try_send() makes, via the pure function it calls.
    decision = db_watcher.resolve_template_send(open_window_message)
    rendered = config.render_template_body(decision["template_name"], decision["params"])
    # Meta rejects an empty variable, so whatsapp._sanitize_template_param
    # substitutes "NSE filing" — show the params as they'd ACTUALLY go out.
    sent_params = [whatsapp._sanitize_template_param(p) for p in decision["params"]]
    sent_render = config.render_template_body(decision["template_name"], sent_params)
    report["closed_window"] = {
        "route": decision["route"],
        "template_name": decision["template_name"] or "(none configured)",
        "param_count": len(decision["params"]),
        "params": sent_params,
        "rendered_message": sent_render if sent_render is not None else rendered,
        "render_warning": (
            None if (sent_render or rendered) is not None else
            "Template body unknown or param count mismatch — see "
            "config.TEMPLATE_BODIES. Would likely be REJECTED by Meta."
        ),
    }
    return report


def _print_report(report: dict):
    sep = "=" * 70
    print(sep)
    print(f"PDF: {report['pdf_path']}")
    print(sep)

    ext = report["extraction"]
    print(f"\n[Text extraction] {ext['chars']} chars"
          + (f" — {ext['usable_pages']}/{ext['pages']} pages had a usable text "
             f"layer, {len(ext.get('ocr_pages') or [])} OCR'd"
             if "pages" in ext else ""))
    if ext.get("note"):
        print(f"    {ext['note']}")

    rd = report["results_detection"]
    print(f"\n[Results detection] {rd['reason']}")

    print(f"\n[AI summary] {report.get('summary_status', 'n/a')}")
    if report.get("used_fallback_caption"):
        print("    ⚠️  NO AI SUMMARY — the messages below are the bare "
              "fallback caption\n        that subscribers actually receive.")

    print(f"\n{sep}\nOPEN-WINDOW MESSAGE (free-form text, window open)\n{sep}")
    print(report["open_window_message"])

    cw = report["closed_window"]
    print(f"\n{sep}\nCLOSED-WINDOW MESSAGE (approved template: {cw['template_name']}, "
          f"route={cw['route']}, {cw['param_count']} params)\n{sep}")
    if cw["rendered_message"]:
        print(cw["rendered_message"])
    else:
        print(f"⚠️  {cw['render_warning']}")
        print("Raw params:")
        for i, p in enumerate(cw["params"], 1):
            print(f"  {{{{{i}}}}} = {p!r}")


def main():
    ap = argparse.ArgumentParser(
        description="Preview the WhatsApp message(s) a PDF would generate, "
                     "without sending anything or touching the database."
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pdf", help="Local path to a filing PDF")
    src.add_argument("--url", help="URL of a filing PDF (e.g. an nseindia.com link)")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--company", default=None)
    ap.add_argument("--symbol", default="N/A")
    ap.add_argument("--filing-type", default="Investor Filing")
    ap.add_argument("--download-url", default=None,
                    help="Link shown in the message's download line "
                         "(defaults to --url itself, when given)")
    ap.add_argument("--json", action="store_true", help="Print raw JSON instead of a formatted report")
    args = ap.parse_args()

    tmp_path = None
    pdf_path = args.pdf
    if args.url:
        print(f"Downloading {args.url} ...", file=sys.stderr)
        tmp_path = output.download_pdf(args.url)
        pdf_path = tmp_path

    try:
        report = preview_pdf(
            pdf_path,
            provider=args.provider,
            model=args.model,
            company=args.company,
            symbol=args.symbol,
            filing_type=args.filing_type,
            download_url=args.download_url or args.url or "https://equityalerts.in/sample-filing.pdf",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if args.url:
        report["pdf_path"] = args.url

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_report(report)


if __name__ == "__main__":
    main()
