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
- **Digital records & evidence integrity** (§12–13): private storage behind short-lived signed URLs. SHA-256 is computed on the device and verified on the server. Content-type sniffing, ClamAV malware scanning and thumbnails are included. Replacements and deletions are audited, approved evidence is locked, and retention is configurable (routine 1 year, incidents 3 years, files on a customer record kept until deleted).
- **Property Watch / inspections**: resident visit requests, inspection-point checklist, photos, an owner report, and one-click follow-up maintenance.
- **Properties & residents, assets with QR/NFC labels, complaints** (auto-linked to maintenance), **cleaning & gardening schedules**, **staff** (shifts, attendance, work history) and **vendors** (with performance).
- **Security**: visitors with resident approval and pre-approval, vehicle register and gate log, QR patrol routes, incidents, and SOS with escalation.
- **Billing**: per plot, unit, sq ft, fixed or custom plans; dues generated without duplicates; payments with idempotency keys; Razorpay-style signed webhooks processed once; receipts (PDF); reconciliation; defaulters; and basic expenses. Every maintenance job on a plot is billed to its owner when it is created; the supervisor sets or changes the charge until it is paid, the owner pays online or staff record cash/UPI, and the job closes only once the bill is paid or waived (jobs with no plot are the association's cost; set the tenant setting `job_payment_required` to false to turn this off).
- **Communication**: announcements, notices, alerts, events and outages to targeted audiences. In-app notifications, plus push, SMS, WhatsApp and email adapters.
- **Dashboards & reports, search, audit** (§22–23, §38): role dashboards, filterable reports with CSV export, and natural-language search ("Show all gate repairs for Plot 117 in the last 12 months"). Append-only audit logging covers every important action.
- **RBAC & multi-tenancy** (§24–25): seven roles, a permission matrix plus row-level scoping, and `tenant_id` on every record. Cross-tenant access returns 404.
- **Offline / PWA** (§30): installable app, service-worker app shell, and an IndexedDB queue (`QUEUED → SYNCING → SYNCED / FAILED / RETRY`) that replays to an idempotent `/sync` endpoint. Queued work covers visitors, vehicles, patrols, incidents, SOS, attendance, maintenance steps and photos.
- **Ratings & support**: after each job the plot's customer is asked to rate it from 1 to 5 with a comment (jobs from a service ticket are rated once, on the ticket). Any rating below 4 sends a "Low rating" alert to supervisors and admins. A WhatsApp chat button on every page uses the configured `GP_WHATSAPP_NUMBER`, and residents have a short **Report a problem** form (menu, top bar and the website) that raises a service ticket for the office to assign.
- **Public website** (§32): the existing page, plus the Proof of Work section, For Layouts, a Request Demo form (stored for the platform admin, with a WhatsApp fallback), Contact and a mobile menu.

### Integrations that need provider accounts

These are built behind adapters and need credentials or a provider choice (see §47 open questions):

- **Payments**: Razorpay orders, Checkout and webhooks are built in; set `GP_RAZORPAY_KEY_ID`, `GP_RAZORPAY_KEY_SECRET` and `GP_PAYMENT_WEBHOOK_SECRET` (below). Without keys the demo has a "simulate payment" button, which is disabled in production and whenever keys are set.
- **Notifications**: push goes to the mobile apps through Firebase once `GP_PUSH_PROVIDER=fcm` and `GP_FCM_SERVICE_ACCOUNT` are set (see *Mobile apps* below). Email sends over SMTP once `GP_SMTP_*` is set, SMS through MSG91 and WhatsApp through the Cloud API (below); each logs until it is configured.

### Mobile apps (Android and iPhone)

The apps use the same `/api/v1` API as the website. What they need is built in:

- **Sign-in**: `/auth/login` (or phone codes) returns an access token (30 minutes) and a refresh token (14 days) that `/auth/refresh` rotates. Each phone is its own session, listed at `/auth/sessions`.
- **Push notifications**: after sign-in the app sends its Firebase token to `POST /devices`. Pushes carry `kind`, `entity_type` and `entity_id` so a tap can open the right screen. Signing out, or signing out everywhere, stops that phone's pushes. One Firebase project covers both stores: create it, add the Android and iOS apps, upload the APNs key for iOS, then set `GP_PUSH_PROVIDER=fcm` and `GP_FCM_SERVICE_ACCOUNT` (the service-account JSON, or a path to it).
- **Start-up check**: `GET /app/config` (no sign-in) returns the minimum supported versions (`GP_APP_MIN_VERSION_ANDROID`, `GP_APP_MIN_VERSION_IOS`) and store links, so an old app can ask to update.
- **Data use**: responses are gzipped, JSON GETs carry an `ETag` (send `If-None-Match` to get a `304` when nothing changed), photos have a 480 px `thumbnail_url` and, when large, a 1600 px `preview_url`.
- **Errors**: every error has `detail` (as before), a stable `code` (`not_found`, `validation_error`, `mfa_setup_required`, ...) and a readable `message`.
- **Client code**: `/api/v1/openapi.json` has short operation ids (`tickets_list_tickets`) for OpenAPI generators.

Notifications are sent just after the change is saved, on a small thread pool, so a slow provider doesn't hold up the request; the worker sends anything left over after a restart.

### Payments (Razorpay)

1. In the Razorpay Dashboard, create API keys (test keys work before KYC is complete) and set `GP_RAZORPAY_KEY_ID` and `GP_RAZORPAY_KEY_SECRET`.
2. Add a webhook to `https://<your domain>/api/v1/payments/webhook` with the `payment.captured` and `payment.failed` events, and put its secret in `GP_PAYMENT_WEBHOOK_SECRET`.
3. "Pay" creates a Razorpay order and opens Razorpay Checkout in the browser. The payment is applied when the checkout's signed response is verified (the API also confirms it with Razorpay and captures it if needed) or when the webhook arrives, whichever comes first; both are processed once.

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

### One app, different views for customers and vendors

Everyone signs in at the same `/login`. The account's role decides the menu, the home screen and what the API allows. Under **Settings → Features**, the layout admin switches features on or off separately for **customers** (residents and owners) and **vendors**:

- **Customers:** service tickets, my property, maintenance history, Property Watch, complaints, visitors, vehicles, dues & payments, incidents, notices, SOS, records search.
- **Vendors:** service tickets, work orders, scan asset, proof-of-work reports, offline mode, records search.

A switched-off feature disappears from the menu and home screen, and its permissions are removed, so the API refuses it even by direct link. Dependencies are enforced: vendor service tickets need work orders. All features are on by default, and changes are audited. Office roles (admin, supervisor, staff, guard) aren't affected.

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

### Malware scanning

Every upload (photos, videos, PDFs) is scanned before it is accepted. In `docker compose` this uses a self-hosted **ClamAV** daemon (the `clamav` service), so no account or API key is needed and its virus signatures update themselves. An infected file is deleted, the person sees which threat was found, and the attempt is recorded in the audit log. If the scanner is down or still starting (it takes about a minute to load signatures after a restart), the upload is refused with "try again" and the file is kept, so finishing it later works without re-sending.

ClamAV needs about **1.1 GB of RAM** with signatures loaded, the most of any service on a 4 GB server. It is capped at 1.6 GB, and signature reloads are not run side by side, so they don't double memory. Outside Docker and production, the default scanner (`eicar`) only catches the EICAR test file; set `GP_MALWARE_SCANNER=clamav` and `GP_CLAMAV_HOST` to use a ClamAV you run yourself. Give that clamd the same limits as `docker-compose.yml` (`StreamMaxLength 110M`, `MaxFileSize 110M`, `MaxScanSize 400M`, `AlertExceedsMax yes`); with clamd's 25 MB default, larger videos are refused. With `GP_ENVIRONMENT=production` and no scanner set, ClamAV is used.

### Owner updates: photo proof, plot-due reminders and monthly reports

- **Photo proof when a job closes.** When a job on a plot is approved and closed with at least one after photo, the owner gets a message with a link to a page showing the before and after photos (`/proof/<token>`). The link is signed and expires with routine media retention. Owners who messaged the business number in the last 24 hours also get the two photos in the WhatsApp chat. Supervisors can resend it with `POST /api/v1/maintenance/{id}/send-proof`. Respects *resident evidence visibility*; turn it off with the tenant setting `job_proof_enabled: false`.
- **"Your plot is due" reminders.** For every recurring schedule on a plot that repeats every 14 days or longer, the owner is reminded once per visit, 7 days ahead by default (`plot_due_reminder_days`, 0 turns it off). If the plot has unpaid dues the message carries a one-tap pay link. The default link opens the bill in the app (`/billing?invoice=<id>`); a payment gateway can supply its own link with `owner_contact.set_pay_link_builder()` (for example a Razorpay Payment Link).
- **Monthly plot health report.** On the first worker run of each month, every plot with an owner gets last month's report: visits done (jobs and property-watch inspections), photos, issues spotted (inspection findings, incidents, complaints), next visit and dues, as a short message plus a PDF link. Owners also find them on their property page. Admins can rebuild and resend a month with `POST /api/v1/properties/{id}/plot-reports {"month": "2026-09"}`. Turn it off with `plot_report_enabled: false`.

These go to owners with an account through their notification channels (event kinds `job_proof`, `plot_due` and `plot_report`, default in-app + WhatsApp + email, changeable per tenant under notification channels). Owners recorded only by phone or email on the property get email and SMS. They use the same providers as everything else, so nothing extra is needed beyond `GP_WHATSAPP_*`, `GP_MSG91_*` and `GP_SMTP_*` above. Links point at the first `GP_CORS_ORIGINS` entry, and with local storage WhatsApp fetches photos from `GP_PUBLIC_BASE_URL`, so both must be reachable from the internet.

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
cd backend && pytest -q                                   # 87 tests on SQLite
GP_TEST_DATABASE_URL=postgresql+psycopg://greenplot:greenplot@localhost/greenplot_test pytest -q
ruff check app tests
GP_TEST_CLAMAV_HOST=localhost pytest -q tests/test_malware.py   # also scan against a real ClamAV on :3310

cd frontend && npm run typecheck && npm run build
# End-to-end (API seeded + `npm start` running):
npx playwright test
```

The backend suite covers the end-to-end Proof of Work flow (§49), evidence rules and integrity, rework, permissions and tenant isolation, security operations, billing and webhooks, offline sync idempotency and conflicts, search, reports and jobs. The Playwright suite opens every page for every role, runs the worker → supervisor proof-of-work flow in a real browser, syncs an offline visitor registration, and submits the website demo form.

## Legal pages

The public site has Terms & Conditions (`/terms`), Privacy Policy (`/privacy`), Refund & Cancellation (`/refund-policy`), Service Delivery (`/service-delivery`) and Contact (`/contact`) pages, linked from the site footer, login and registration. Razorpay checks for these before activating a live account. Business details (name, address, phone, emails, Grievance Officer) live in [`frontend/lib/legal.ts`](frontend/lib/legal.ts), and have the text reviewed by a lawyer. Registration requires ticking the Terms & Privacy box; the accepted `TERMS_VERSION` and IP are kept in the audit log.

## Configuration

All backend settings are environment variables prefixed `GP_` (see [`backend/app/core/config.py`](backend/app/core/config.py)). Per-layout settings are edited in the app under **Settings**: evidence requirements per task type, checklist templates, recurring schedules, resident evidence visibility, retention, SOS escalation and users/roles.
