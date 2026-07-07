# NSE Announcement Monitoring & PDF Ingestion System

A production-oriented backend system that continuously monitors NSE (National Stock Exchange) corporate announcements for hundreds of companies, downloads associated PDFs, and delivers structured data to downstream services.

---

## Table of Contents

- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [Goals](#goals)
- [Architecture](#architecture)
- [Worker Architecture](#worker-architecture)
- [Persistent Queue](#persistent-queue)
- [Retry & Failure Recovery](#retry--failure-recovery)
- [Circuit Breaker](#circuit-breaker)
- [Heartbeats & Supervision](#heartbeats--supervision)
- [Market-Hours Logic](#market-hours-logic)
- [Database Schema](#database-schema)
- [File Structure](#file-structure)
- [Installation](#installation)
- [PostgreSQL Setup](#postgresql-setup)
- [Environment Variables](#environment-variables)
- [Running the Services](#running-the-services)
- [Scaling Strategy](#scaling-strategy)
- [Monitoring](#monitoring)
- [Current Limitations](#current-limitations)
- [Production Deployment](#production-deployment)
- [Future Improvements](#future-improvements)

---

## Overview

This system is the ingestion and monitoring backend for a financial data pipeline. It polls the NSE API continuously during market hours, detects new corporate announcements, downloads PDF filings, and stores both metadata and raw files in a reliable, recoverable way.

The project evolved from a simple polling script into a resilient, queue-driven, stateful ingestion architecture capable of monitoring 200+ companies in production and architecturally designed to scale to 500.

**This project does not include:** frontend, dashboards, public API, or user management. It is purely the ingestion layer.

---

## Problem Statement

Corporate announcements on NSE are time-sensitive. Delays in detection or download failures mean downstream services (WhatsApp notifications, search indexes, subscription delivery) miss filings. Early versions of this system suffered from:

- Duplicate downloads due to no deduplication
- Queue loss on restart (in-memory queue)
- No recovery from transient NSE/network failures
- Single-worker bottleneck with no horizontal scaling
- No visibility into worker health or queue state

---

## Goals

1. Monitor hundreds of NSE companies simultaneously during market hours
2. Detect new announcements quickly with minimal polling delay
3. Download associated PDFs reliably with automatic retry
4. Store announcement metadata permanently in PostgreSQL
5. Never lose queued work across restarts or crashes
6. Scale toward 500 companies without architectural changes
7. Provide operational visibility for debugging and alerting

---

## Architecture

```
NSE API
  │
  ▼
Market Hours Guard (08:00–18:00 IST)
  │
  ▼
Request Limiter (burst control)
  │
  ▼
Watcher Service
  ├── Deduplication (company_state timestamps + DB constraints)
  ├── Announcement metadata → PostgreSQL (announcements table)
  ├── Download jobs → PostgreSQL (download_jobs queue)
  └── Circuit breaker (pause if queue exceeds threshold)
  │
  ▼
download_jobs Queue (PostgreSQL — persistent, distributed-safe)
  │
  ▼
Download Workers (N parallel, atomic job claiming via FOR UPDATE SKIP LOCKED)
  ├── Mark job PROCESSING
  ├── Download PDF → local filesystem
  ├── Mark DOWNLOADED or FAILED
  └── Update announcement status
  │
  ├──[FAILED]──▶ failed_jobs table
  │                   │
  │               Recovery Worker
  │               (requeues to download_jobs)
  │
  └──[SUCCESS]──▶ Downstream systems
                  (WhatsApp · search · analytics)
  │
Supervisor Worker
  └── Checks worker_heartbeats, detects dead workers, releases stuck jobs
```

---

## Worker Architecture

The system runs three independent worker types:

### Download Worker (`workers/downloadWorker.js`)

The primary workhorse. Runs in a loop:

1. Claims a pending job atomically from `download_jobs` using `FOR UPDATE SKIP LOCKED`
2. Sets job status to `PROCESSING`
3. Downloads the PDF via `services/downloadPdf.js`
4. Updates job and announcement status to `DOWNLOADED` or `FAILED`
5. Writes a heartbeat timestamp to `worker_heartbeats`
6. Uses adaptive polling — backs off during quiet periods to reduce DB load

Multiple download worker instances can run safely in parallel. The `FOR UPDATE SKIP LOCKED` pattern ensures no two workers ever claim the same job, even without a Redis or message broker.

### Supervisor Worker (`workers/supervisorWorker.js`)

Monitors worker liveness:

1. Polls `worker_heartbeats` on a configurable interval
2. Detects workers whose `last_seen` is stale beyond a threshold
3. Releases jobs held by dead workers back to `PENDING` (stuck-job recovery)

### Recovery Worker (`scheduler/recoveryWorker.js`)

Handles persistent failures:

1. Polls `failed_jobs` for retryable entries
2. Reinserts them into `download_jobs`
3. Removes recovered entries from `failed_jobs`

---

## Persistent Queue

All download jobs are stored in PostgreSQL's `download_jobs` table rather than in-memory. This means:

- Jobs survive process restarts and crashes
- Multiple workers can safely consume jobs without coordination overhead
- Queue state is inspectable with standard SQL queries
- Backpressure is enforceable via `MAX_QUEUE_SIZE` and `MAX_PENDING_JOBS` configuration

**Atomic job claiming** uses PostgreSQL advisory locking:

```sql
SELECT * FROM download_jobs
WHERE status = 'PENDING'
ORDER BY created_at ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

This is the core of distributed-safe worker operation. Workers that hit a locked row skip it immediately rather than waiting, so N workers can all run full-speed without contention.

---

## Retry & Failure Recovery

The system has three layers of retry:

**Layer 1 — HTTP retry (`services/retry.js`):** Individual NSE fetch requests are retried with configurable delay on transient network errors.

**Layer 2 — Job-level retry (`workers/downloadWorker.js`):** If a PDF download fails, the job is marked `FAILED` in `download_jobs` and a record is inserted into `failed_jobs`. The retry count is tracked.

**Layer 3 — Recovery worker (`scheduler/recoveryWorker.js`):** Periodically scans `failed_jobs` and requeues jobs that haven't exceeded the maximum retry limit. This handles longer-term failures (NSE downtime, rate limits) without manual intervention.

---

## Circuit Breaker

The watcher service monitors queue depth before inserting new jobs. If `download_jobs` has more than `MAX_PENDING_JOBS` rows in `PENDING` state, the watcher pauses ingestion for the current cycle. This prevents:

- Queue table growth without bound
- Download workers being overwhelmed
- Cascading failures when NSE is slow or unavailable

The circuit breaker resets automatically when queue depth drops below the threshold.

---

## Heartbeats & Supervision

Every download worker writes a `last_seen` timestamp to `worker_heartbeats` at a fixed interval (every few seconds). The supervisor worker checks these timestamps and flags any worker that hasn't updated within a configurable staleness window.

When a dead worker is detected:

1. Its `PROCESSING` jobs are identified (jobs claimed but never completed)
2. Those jobs are reset to `PENDING`
3. Live workers pick them up on the next poll cycle

This prevents jobs from being permanently stuck in `PROCESSING` state after a worker crash.

---

## Market-Hours Logic

The watcher loop is gated by `services/isMarketOpen.js`. Polling only runs between **08:00 and 18:00 IST**, which covers pre-market through post-market activity with a buffer.

Outside these hours, the watcher loop sleeps without making any NSE requests. Download workers continue processing the queue outside market hours if jobs remain.

The window is configurable via the `MARKET_START` and `MARKET_END` environment variables.

---

## Database Schema

### `announcements`

Permanent business data. One row per unique announcement.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID / serial | Primary key |
| `symbol` | VARCHAR | Company ticker |
| `title` | TEXT | Announcement title |
| `pdf_url` | TEXT | NSE PDF link |
| `local_path` | TEXT | Downloaded file path |
| `announced_at` | TIMESTAMP | NSE announcement timestamp |
| `download_status` | VARCHAR | `PENDING` / `DOWNLOADING` / `DOWNLOADED` / `FAILED` |
| `created_at` | TIMESTAMP | Row insertion time |

Unique constraint on `(symbol, pdf_url)` prevents duplicate entries.

---

### `company_state`

Tracks the latest processed announcement timestamp per company. On restart, the watcher reads this table and skips all historical announcements — only new ones are processed.

| Column | Type | Notes |
|---|---|---|
| `symbol` | VARCHAR | Primary key |
| `last_seen_at` | TIMESTAMP | Latest processed announcement time |

---

### `download_jobs`

Operational queue. Rows are created by the watcher and consumed by download workers.

| Column | Type | Notes |
|---|---|---|
| `id` | Serial | Primary key |
| `announcement_id` | FK | References `announcements` |
| `pdf_url` | TEXT | Target URL |
| `status` | VARCHAR | `PENDING` / `PROCESSING` / `DONE` / `FAILED` |
| `retry_count` | INTEGER | Number of attempts |
| `claimed_by` | VARCHAR | Worker ID (prevents double-claim) |
| `created_at` | TIMESTAMP | Queue insertion time |
| `updated_at` | TIMESTAMP | Last status change |

---

### `failed_jobs`

Permanent record of jobs that exhausted retries or failed with non-transient errors.

| Column | Type | Notes |
|---|---|---|
| `id` | Serial | Primary key |
| `announcement_id` | FK | Source announcement |
| `pdf_url` | TEXT | Failed URL |
| `error_message` | TEXT | Last error |
| `retry_count` | INTEGER | Attempts made |
| `created_at` | TIMESTAMP | Failure time |

---

### `worker_heartbeats`

Liveness tracking for download workers.

| Column | Type | Notes |
|---|---|---|
| `worker_id` | VARCHAR | Unique worker identifier |
| `last_seen` | TIMESTAMP | Most recent heartbeat |
| `status` | VARCHAR | `ACTIVE` / `DEAD` |

---

## File Structure

```
nse-announcement-downloader/
│
├── db/
│   └── connection.js           # PostgreSQL connection pool
│
├── repositories/
│   ├── announcementRepository.js    # Announcement CRUD + dedup
│   ├── companyStateRepository.js    # Per-company timestamp tracking
│   ├── downloadJobRepository.js     # Queue management + atomic claiming
│   ├── failedJobRepository.js       # Failed job storage + retrieval
│   └── workerHeartbeatRepository.js # Liveness tracking
│
├── scheduler/
│   ├── watcher.js              # Core ingestion engine
│   ├── recoveryWorker.js       # Failed job requeue loop
│   └── cleanupWorker.js        # Optional queue housekeeping
│
├── services/
│   ├── batchSaver.js           # Bulk DB insert utility
│   ├── chunkArray.js           # Split symbols into worker batches
│   ├── config.js               # Central configuration
│   ├── downloadPdf.js          # HTTP download + filesystem write
│   ├── downloadQueue.js        # Queue orchestration layer
│   ├── failedQueue.js          # Failed queue management
│   ├── fetchAnnouncements.js   # NSE API client with retry
│   ├── isMarketOpen.js         # Market-hours guard
│   ├── metrics.js              # Runtime operational counters
│   ├── requestLimiter.js       # Concurrent request throttle
│   └── retry.js                # Generic retry utility
│
├── workers/
│   ├── downloadWorker.js       # PDF download service
│   └── supervisorWorker.js     # Worker liveness monitor
│
├── storage/
│   └── pdf/                    # Downloaded PDF files
│
├── .env                        # Environment configuration
├── package.json
└── server.js                   # Main entry point
```

---

## Installation

**Requirements:** Node.js 18+, PostgreSQL 14+

```bash
git clone <repo-url>
cd nse-announcement-downloader
npm install
```

---

## PostgreSQL Setup

```sql
-- Create database
CREATE DATABASE nse_monitor;

-- announcements
CREATE TABLE announcements (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  title TEXT,
  pdf_url TEXT NOT NULL,
  local_path TEXT,
  announced_at TIMESTAMP,
  download_status VARCHAR(20) DEFAULT 'PENDING',
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(symbol, pdf_url)
);

-- company_state
CREATE TABLE company_state (
  symbol VARCHAR(20) PRIMARY KEY,
  last_seen_at TIMESTAMP NOT NULL
);

-- download_jobs
CREATE TABLE download_jobs (
  id SERIAL PRIMARY KEY,
  announcement_id INTEGER REFERENCES announcements(id),
  pdf_url TEXT NOT NULL,
  status VARCHAR(20) DEFAULT 'PENDING',
  retry_count INTEGER DEFAULT 0,
  claimed_by VARCHAR(100),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_download_jobs_status ON download_jobs(status);

-- failed_jobs
CREATE TABLE failed_jobs (
  id SERIAL PRIMARY KEY,
  announcement_id INTEGER REFERENCES announcements(id),
  pdf_url TEXT,
  error_message TEXT,
  retry_count INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW()
);

-- worker_heartbeats
CREATE TABLE worker_heartbeats (
  worker_id VARCHAR(100) PRIMARY KEY,
  last_seen TIMESTAMP NOT NULL,
  status VARCHAR(20) DEFAULT 'ACTIVE'
);
```

---

## Environment Variables

Create a `.env` file in the project root:

```env
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=nse_monitor
DB_USER=postgres
DB_PASSWORD=your_password

# Watcher
SYMBOLS=RELIANCE,TCS,INFY,HDFCBANK,WIPRO   # comma-separated NSE tickers
INTERVAL=30000                               # poll interval in ms
MAX_RECORDS=10                               # announcements per fetch
REQUEST_LIMIT=5                              # max concurrent NSE requests

# Workers
DOWNLOAD_WORKERS=3                           # parallel download workers
MAX_QUEUE_SIZE=500                           # max total queue rows
MAX_PENDING_JOBS=100                         # circuit breaker threshold

# Market hours (24h IST)
MARKET_START=8
MARKET_END=18

# Storage
PDF_STORAGE_PATH=./storage/pdf
```

---

## Running the Services

Start all services together:

```bash
node server.js
```

Or run each service independently for development:

```bash
# Watcher only
node scheduler/watcher.js

# Download workers
node workers/downloadWorker.js

# Supervisor
node workers/supervisorWorker.js

# Recovery worker
node scheduler/recoveryWorker.js
```

---

## Scaling Strategy

| Target | Approach |
|---|---|
| 50–100 companies | Default config, single machine |
| 100–200 companies | Increase `DOWNLOAD_WORKERS` to 5–8, tune `REQUEST_LIMIT` |
| 200–500 companies | Multiple watcher processes with symbol partitioning, larger PostgreSQL instance |
| 500–1000 companies | Distributed workers across multiple machines, S3 for PDF storage, Redis for queue |
| 1000+ | Kafka-based queue, multi-region deployment |

The current architecture bottleneck at scale is the single PostgreSQL instance and local filesystem. Both are replaceable without changing the application logic layer.

---

## Monitoring

The `services/metrics.js` module tracks in-process counters:

- `cycles` — total watcher cycles completed
- `companies` — companies successfully polled
- `downloads` — PDFs downloaded successfully
- `errors` — failed operations
- `uptime` — process uptime in seconds

Query operational state directly via SQL:

```sql
-- Queue depth by status
SELECT status, COUNT(*) FROM download_jobs GROUP BY status;

-- Recent failures
SELECT symbol, error_message, created_at FROM failed_jobs ORDER BY created_at DESC LIMIT 20;

-- Worker liveness
SELECT worker_id, last_seen, status FROM worker_heartbeats ORDER BY last_seen DESC;

-- Download success rate (last 24h)
SELECT download_status, COUNT(*) FROM announcements
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY download_status;
```

---

## Current Limitations

These are infrastructure constraints, not architectural flaws:

- **Single PostgreSQL instance** — no read replicas or connection pooling middleware (PgBouncer)
- **Local filesystem** — PDFs stored on the same machine, no cloud object storage
- **Single machine deployment** — no multi-server worker distribution
- **No centralized logging** — stdout only, no log aggregation
- **No Docker** — manual process management
- **No process supervisor** — no PM2 or systemd integration yet
- **No alerting** — metrics are in-process, not exported to Prometheus/Grafana

---

## Production Deployment

### Recommended minimum setup (VPS)

```bash
# Install PM2
npm install -g pm2

# Start with PM2
pm2 start server.js --name nse-watcher
pm2 start workers/downloadWorker.js --name nse-downloader -i 3
pm2 start workers/supervisorWorker.js --name nse-supervisor
pm2 start scheduler/recoveryWorker.js --name nse-recovery

# Save and enable auto-restart on reboot
pm2 save
pm2 startup
```

### Recommended VPS spec for 200 companies

- 2 vCPU, 4 GB RAM
- 50 GB SSD (PDF accumulates quickly — plan for growth)
- PostgreSQL on same machine or managed DB service

### Environment hardening

- Use a dedicated PostgreSQL user with minimal permissions
- Store `.env` outside the repo or use a secrets manager
- Rotate credentials regularly
- Set up daily PostgreSQL backups

---

## Future Improvements

### Infrastructure
- Dockerize all services with `docker-compose`
- PM2 ecosystem file for coordinated process management
- S3 or MinIO for PDF object storage (replace local filesystem)
- Managed PostgreSQL (RDS, Supabase, Neon) for reliability

### Observability
- Export metrics to Prometheus
- Grafana dashboards for queue depth, download rate, error rate
- Alerting on circuit breaker activations and dead workers
- Centralized logging via Loki or CloudWatch

### Reliability
- PDF checksum validation after download
- PDF corruption detection (validate file header)
- Exponential backoff on retry (currently fixed delay)
- Multi-region failover for NSE API resilience

### Scaling
- Redis or BullMQ as queue backend (drop-in for PostgreSQL queue)
- Kafka for high-throughput announcement streaming
- Distributed workers via Docker Swarm or Kubernetes
- Symbol partitioning across multiple watcher instances

---

## Project Status

**Stage:** Production-oriented ingestion system

**Architecture completeness:** ~75–80% of stated scope

**Key achievement:** Transitioned from a single-process in-memory polling script to a stateful, distributed-safe, queue-driven ingestion architecture with full failure recovery and operational visibility.