# BSE Announcement Scraper

A standalone service that polls BSE's corporate-announcements feed, stores new
filings for subscribed companies, and downloads their PDFs.

## Why it is separate from `scraper/`

BSE disseminates a large share of filings **before** the same document appears
on NSE. Capturing that head start needs a loop that is free to run fast, and
previously BSE was scraped inside the NSE scraper's process — chained into the
same 20-second cycle with `Promise.all`, sharing its circuit breaker, its
download queue and its restarts. Any NSE backlog became a BSE delay, which
threw the head start away.

So this service:

- polls on its **own interval** (default 8s vs the NSE scraper's 20s),
- owns **private job tables** (`bse_download_jobs`, `bse_failed_jobs`) so its
  downloads never queue behind NSE's,
- runs in its **own container**, so it deploys and restarts independently.

It writes to the **same** `announcements` table the NSE scraper writes to,
because that is what the bot reads. Rows are stamped `exchange = 'BSE'`.

`scraper/server.js` no longer calls its `bseWatcher` — this service replaces it.
The old files under `scraper/` are left in place but unused.

## Pipeline

```
BSE announcements API
        │  (single-day feed, newest first, 50/page)
        ▼
scheduler/bseWatcher.js ── filters to subscribed scrip codes
        │
        ├─► announcements            (shared with the NSE scraper; bot reads this)
        └─► bse_download_jobs        (private queue)
                │
                ▼
        workers/downloadWorker.js ── writes storage/pdf/BSE_*.pdf
                │                     then flips download_status to DOWNLOADED
                ▼
        bot/db_watcher.py ─────────► WhatsApp
```

## Feed quirks worth knowing

These were all found the hard way; the endpoint returns a bare `{}` rather than
an error when any of them is violated.

| Constraint | Consequence if ignored |
|---|---|
| `pageno` is **mandatory** | empty `{}` response |
| With `strScrip` empty (all companies), `strPrevDate` **must equal** `strToDate` | empty `{}` — a multi-day range returns nothing |
| Request must look like it came from `www.bseindia.com` (Origin/Referer/UA) | empty body |
| Node's strict HTTP parser rejects BSE's response headers | `Parse Error: Unexpected whitespace after header value` |

The last one is subtle: setting `insecureHTTPParser` on the *agent* is not
enough, because axios always writes an explicit `options.insecureHTTPParser`
from its own config and overrides it. It has to be set on the axios instance —
see `services/httpClient.js`.

Dates are computed in **Asia/Kolkata**, not the container's UTC clock. Between
18:30 and 24:00 UTC it is already tomorrow in India, so a UTC-derived date would
query the wrong day every evening and quietly return nothing.

## Cost of polling fast

The feed is newest-first, and the watcher keeps a high-water mark of the newest
filing timestamp it has already scanned. Once a page contains nothing past that
mark, paging stops. In the steady state that is **one request per cycle**;
extra pages are only walked after a restart or a burst.

Duplicate work is harmless anyway — `announcements.pdf_url` is unique, so a
re-scan inserts nothing and notifies nobody.

## Cross-exchange duplicates

The same filing arrives from both scrapers as two rows with different
`pdf_url`s, so upstream dedup cannot see they are one document. The bot
suppresses the second copy (`_cross_exchange_key` in `bot/db_watcher.py`):
matching symbol + normalised subject, within 90 minutes. Whichever exchange
landed first wins — usually BSE, which is the point.

## Configuration

Everything is optional; defaults are in `services/config.js`.

| Variable | Default | Meaning |
|---|---|---|
| `BSE_INTERVAL` | `8000` | Poll interval (ms) |
| `BSE_MAX_PAGES` | `6` | Max pages (50 filings each) per cycle |
| `BSE_REQUEST_LIMIT` | `4` | Concurrent requests to BSE |
| `BSE_DOWNLOAD_CONCURRENCY` | `8` | PDFs downloaded in parallel |
| `BSE_DOWNLOAD_BATCH` | `20` | Jobs claimed per worker tick |
| `BSE_MAX_DOWNLOAD_RETRIES` | `8` | Attempts before a PDF is given up on |
| `PDF_STORAGE_PATH` | `../storage/pdf` | Must be the volume the bot reads |
| `DB_*`, `SUB_DB_*` | — | Ingestion and subscription databases |

Like the NSE scraper, this service is **subscription-driven**: it only stores
filings for companies that currently have at least one active subscription, and
only for those with a BSE scrip code in `config/bseCompanies.js`.

## Checking it without the database

`scripts/probeFeed.js` hits the live feed and prints exactly what the watcher
would have persisted — useful for diagnosing a feed change without running the
service.

```bash
node scripts/probeFeed.js                     # today, feed shape only
node scripts/probeFeed.js RELIANCE,TCS        # what those symbols would queue
node scripts/probeFeed.js RELIANCE 20260731   # a specific day
```

## Refreshing the scrip-code map

`config/bseCompanies.js` maps ticker → BSE scrip code (currently 4,882
entries), generated from BSE's active-equity master. Regenerate it with
`scripts/generateBseCompanies.js` when newly-listed companies are missing —
the startup log lists any subscribed symbol it could not map.
