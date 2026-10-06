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
- **Notifications**: the push adapter logs until a push provider is added. Email sends over SMTP once `GP_SMTP_*` is set, SMS through MSG91 and WhatsApp through the Cloud API (below); each logs until it is configured.
- **Malware scanning**: plug ClamAV or a provider into `scan_for_malware`.

### SMS (MSG91)

SMS goes through **MSG91's Flow API**. Indian SMS must use **DLT-registered templates**, so GreenPlot sends three kinds:

| Template | Variables | Used for | Example text |
|---|---|---|---|
| `GP_MSG91_OTP_TEMPLATE_ID` | `##otp##` | sign-in, password-reset and registration codes when WhatsApp isn't available | `##otp## is your GreenPlot code. Valid 10 minutes. Do not share. -GreenPlot` |
| `GP_MSG91_NOTIFY_TEMPLATE_ID` | `##title##` `##body##` | notifications whose channels include SMS (e.g. dues reminders, SOS) | `GreenPlot: ##title## ##body##` |
| `GP_MSG91_LINK_TEMPLATE_ID` | `##title##` `##link##` | invites, account alerts | `GreenPlot: ##title## Open: ##link##` |

DLT limits each variable (usually 30 characters), so `title` and `body` are trimmed to `GP_MSG91_VAR_MAX`; links are sent in full. Each send's MSG91 request id is stored in the delivery log. Delivery reports posted to `/api/v1/webhooks/msg91?token=<GP_MSG91_WEBHOOK_TOKEN>` mark it delivered or failed (with the reason, e.g. NDNC). Failures are retried by the worker.

To go live:

1. In MSG91, add your DLT entity and sender ID, then create the three templates with the variables above, linked to their DLT template IDs.
2. Set `GP_SMS_PROVIDER=msg91`, `GP_MSG91_AUTHKEY`, the template IDs, and optionally `GP_MSG91_SENDER`.
3. Set the delivery-report webhook in MSG91 to `https://<your-domain>/api/v1/webhooks/msg91?token=<GP_MSG91_WEBHOOK_TOKEN>`.
4. Check it under **Settings → Notifications → SMS (MSG91)** with *Send test SMS*.

### Sign-in & accounts

- **Ways to sign in:** email and password, or **mobile number + one-time code** (sent by WhatsApp, else SMS). Codes are 6 digits, valid for 10 minutes, limited to 5 attempts and 5 sends per hour, and stored only as hashes.
- **2-step verification:** works with any authenticator app (TOTP, RFC 6238), with 10 single-use recovery codes. The secret is encrypted at rest. `GP_MFA_REQUIRED_ROLES` makes it mandatory per role: until they enrol, those users can only reach their profile. Admins can reset it for someone who lost their phone.
- **Forgot password:** self-service, with a code sent to the account's email or mobile. Every other session is signed out. Responses never reveal whether an account exists.
- **Lockout:** after 5 failed sign-ins (password or 2-step code), the account is locked for 15 minutes. It's stored in the database, so it works across API processes. The user gets an email alert, and an admin can unlock early.
- **Sessions:** Profile lists the signed-in devices; sign out one, or all of them. A device that's signed out loses access at once, not when its token expires.
- **Invites are sent automatically** by email and WhatsApp/SMS whenever an admin adds a user, resident or layout, or re-invites someone. The link is also copied, as a fallback.
- **Self-registration** (`/register`): residents and vendors find their layout and confirm their mobile with a code. The layout office then approves the request in **Settings → Users**, linking it to a plot or a vendor company (a new vendor is created if needed), and the invite goes out. Rejected applicants are told why.
- **Phone numbers changed by the user** must be confirmed with a code, since they are also used to sign in.
- **Outside production**, code responses include `dev_code`, so these flows work without SMS, WhatsApp or email providers (`GP_DEV_SHOW_CODES`).

### WhatsApp (two-way)

GreenPlot uses the official **WhatsApp Business Cloud API**. Ticket updates (created, assigned, accepted, work started, completed, resolved, **closed**), new-assignment alerts for vendors and announcements are sent to people who **opted in** (Profile → *WhatsApp updates*, or by messaging START to the business number). Residents can **reply to an update** — or send a ticket number — and the message is added to the ticket's conversation. STATUS returns the ticket status, and STOP opts out. Every send and its sent → delivered → read / failed receipt is shown in the ticket's notification delivery log. Failed sends are retried. Admins choose the channels per event and can send a test message under **Settings → Notifications**.

To go live:

1. In Meta Business Manager, create a WhatsApp Business app and register your number. Note the **phone number ID**, create a **System User access token** with `whatsapp_business_messaging`, and copy the **app secret**.
2. Create and get approved a *Utility* message template named `greenplot_update` (language `en`), with the body `{{1}}` + newline + `{{2}}` — for example, “*{{1}}*  {{2}}  Reply to this message to talk to the layout office.” It is used for messages sent outside WhatsApp's 24-hour reply window. Inside that window, plain text is sent.
3. Set `GP_WHATSAPP_PROVIDER=meta` and the `GP_WHATSAPP_*` variables (see `.env.example`).
4. In the app's WhatsApp → Configuration, set the callback URL to `https://<your-domain>/api/v1/webhooks/whatsapp`, use the same verify token, and subscribe to **messages**.

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
cd backend && pytest -q                                   # 83 tests on SQLite
GP_TEST_DATABASE_URL=postgresql+psycopg://greenplot:greenplot@localhost/greenplot_test pytest -q
ruff check app tests

cd frontend && npm run typecheck && npm run build
# End-to-end (API seeded + `npm start` running):
npx playwright test
```

The backend suite covers the end-to-end Proof of Work flow (§49), evidence rules and integrity, rework, permissions and tenant isolation, security operations, billing and webhooks, offline sync idempotency and conflicts, search, reports and jobs. The Playwright suite opens every page for every role, runs the worker → supervisor proof-of-work flow in a real browser, syncs an offline visitor registration, and submits the website demo form.

## Configuration

All backend settings are environment variables prefixed `GP_` (see [`backend/app/core/config.py`](backend/app/core/config.py)). Per-layout settings are edited in the app under **Settings**: evidence requirements per task type, checklist templates, recurring schedules, resident evidence visibility, retention, SOS escalation and users/roles.
