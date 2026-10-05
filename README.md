# GreenPlot

**Property Management Made Simple** — one digital platform for layout associations, residents, guards, staff, supervisors and vendors in residential plotted layouts (initial scope: Bangalore).

The product requirements live in [`GreenPlot_Complete_Requirements.md`](GreenPlot_Complete_Requirements.md), the source of truth for everything here.

| Part | Path | Stack |
|---|---|---|
| Public website | [`index.html`](index.html) | Static HTML (served at `/` by the web app) |
| Web app / PWA | [`frontend/`](frontend) | Next.js 16, React 19, TypeScript |
| API | [`backend/`](backend) | FastAPI, SQLAlchemy 2, PostgreSQL (PostGIS image), Alembic |

```text
Browser / installed PWA ── Cloudflare (TLS) ── Next.js (site + app, proxies /api/v1)
                                                    │
                                              FastAPI /api/v1 ── PostgreSQL
                                                    ├── worker (schedules, reminders, SOS escalation, retention)
                                                    └── private media storage (local volume or S3 / R2)
```

## What's implemented

Every V1 module in the requirements:

- **Customer ticketing & vendor service management** ([`GreenPlot_Ticketing_System_Requirements.md`](GreenPlot_Ticketing_System_Requirements.md)): residents raise service tickets (`GP-TKT-2026-000001`) with photos from the portal or the public website's "Raise a ticket" link. The office reviews, prioritises and assigns each ticket to internal staff or an external vendor. The vendor accepts or rejects with a reason (a rejection returns the ticket to the office), then works it through a linked maintenance work order that carries the full Proof of Work rules. A supervisor verifies or requests rework, and the ticket is resolved. The customer confirms or reopens it and rates the service. Closing a ticket sends a mandatory closure notification, and every channel delivery is logged and retried. Tickets have configurable categories, per-priority and per-category response/resolution SLAs with at-risk warnings and breach escalation, auto-close, separate customer, vendor and internal comment visibility, a full timeline and audit trail, reports (volume, SLA, vendor performance, categories, properties, satisfaction), property history, search and offline creation.
- **Maintenance & Proof of Work** (§8–11, §31, §48): lifecycle `CREATED → ASSIGNED → ACCEPTED → STARTED → COMPLETED → APPROVED → CLOSED` with rework and reopen. Configurable evidence per task type: before/after photos, checklist, GPS, video, materials, invoice and QR/NFC scan. Failed or skipped checklist items need a reason. Missing evidence blocks submission unless the worker records an exception, which the supervisor then reviews. Workers cannot approve their own jobs. Evidence is kept per rework round, and a downloadable PDF Proof of Work report is available.
- **Digital records & evidence integrity** (§12–13): private storage behind short-lived signed URLs. SHA-256 is computed on the device and verified on the server. Content-type sniffing, a malware-scan hook and thumbnails are included. Replacements and deletions are audited, approved evidence is locked, and retention is configurable (routine 90 days, incidents longer).
- **Property Watch / inspections**: resident visit requests, inspection-point checklist, photos, an owner report, and one-click follow-up maintenance.
- **Properties & residents, assets with QR/NFC labels, complaints** (auto-linked to maintenance), **cleaning & gardening schedules**, **staff** (shifts, attendance, work history) and **vendors** (with performance).
- **Security**: visitors with resident approval and pre-approval, vehicle register and gate log, QR patrol routes, incidents, and SOS with escalation.
- **Billing**: per plot, unit, sq ft, fixed or custom plans; dues generated without duplicates; payments with idempotency keys; Razorpay-style signed webhooks processed once; receipts (PDF); reconciliation; defaulters; and basic expenses.
- **Communication**: announcements, notices, alerts, events and outages to targeted audiences. In-app notifications, plus push, SMS, WhatsApp and email adapters.
- **Dashboards & reports, search, audit** (§22–23, §38): role dashboards, filterable reports with CSV export, and natural-language search ("Show all gate repairs for Plot 117 in the last 12 months"). Append-only audit logging covers every important action.
- **RBAC & multi-tenancy** (§24–25): seven roles, a permission matrix plus row-level scoping, and `tenant_id` on every record. Cross-tenant access returns 404.
- **Offline / PWA** (§30): installable app, service-worker app shell, and an IndexedDB queue (`QUEUED → SYNCING → SYNCED / FAILED / RETRY`) that replays to an idempotent `/sync` endpoint. Queued work covers visitors, vehicles, patrols, incidents, SOS, attendance, maintenance steps and photos.
- **Public website** (§32): the existing page, plus the Proof of Work section, For Layouts, a Request Demo form (stored for the platform admin, with a WhatsApp fallback), Contact and a mobile menu.

### Integrations that need provider accounts

These are built behind adapters and need credentials or a provider choice (see §47 open questions):

- **Payments**: a real Razorpay (or other) order call and checkout. The demo has a "simulate payment" button that is disabled in production.
- **Notifications**: push, SMS, WhatsApp and email adapters currently log the message.
- **Malware scanning**: plug ClamAV or a provider into `scan_for_malware`.

## Run it locally

Requirements: Python 3.11+, Node 22+, PostgreSQL 16 (or SQLite for a quick look).

```bash
# API
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export GP_DATABASE_URL=postgresql+psycopg://greenplot:greenplot@localhost/greenplot   # omit to use SQLite
alembic upgrade head
python -m app.seed          # demo layout: one login per role, password GreenPlot@2026
uvicorn app.main:app --reload --port 8000     # docs at http://localhost:8000/api/v1/docs

# Web app (new terminal)
cd frontend
npm install
npm run dev                 # http://localhost:3000 (website) and /login (app)
```

Demo logins (password `GreenPlot@2026`): `admin@`, `supervisor@`, `staff@`, `gardener@`, `guard@`, `vendor@`, `resident@greenvalley.example`, and `platform@greenplot.in` (super admin).

Background jobs (recurring schedules, due/overdue reminders, SOS escalation, dues reminders, media retention) run with `python -m app.worker`. Use `--once` for cron, or set `GP_WORKER_ENABLED=true` to run them inside the API.

## Deploy (single VPS, §27)

```bash
cp .env.example .env    # set POSTGRES_PASSWORD, GP_SECRET_KEY, GP_PUBLIC_BASE_URL, ...
docker compose up -d --build
docker compose exec api python -m app.seed   # optional demo data
```

Put Cloudflare or another TLS reverse proxy in front of port 3000. For large video uploads, route `/api/v1/*` straight to the `api` service at the proxy. For S3 / Cloudflare R2 media storage, set `GP_STORAGE_BACKEND=s3` and the `GP_S3_*` variables; the bucket must stay private.

## Tests

```bash
cd backend && pytest -q                                   # 53 tests on SQLite
GP_TEST_DATABASE_URL=postgresql+psycopg://greenplot:greenplot@localhost/greenplot_test pytest -q
ruff check app tests

cd frontend && npm run typecheck && npm run build
# End-to-end (API seeded + `npm start` running):
npx playwright test
```

The backend suite covers the end-to-end Proof of Work flow (§49), evidence rules and integrity, rework, permissions and tenant isolation, security operations, billing and webhooks, offline sync idempotency and conflicts, search, reports and jobs. The Playwright suite opens every page for every role, runs the worker → supervisor proof-of-work flow in a real browser, syncs an offline visitor registration, and submits the website demo form.

## Configuration

All backend settings are environment variables prefixed `GP_` (see [`backend/app/core/config.py`](backend/app/core/config.py)). Per-layout settings are edited in the app under **Settings**: evidence requirements per task type, checklist templates, recurring schedules, resident evidence visibility, retention, SOS escalation and users/roles.
