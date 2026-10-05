# GreenPlot — Complete Product Requirements Specification

**Product:** GreenPlot  
**Tagline:** Property Management Made Simple  
**Positioning:** Property & layout management  
**Initial scope:** Bangalore  
**Platform:** Responsive web application / PWA  
**Version:** 1.0

---

## 1. Problem Statement

Residential plotted layouts often manage property care, security, maintenance, vendors, complaints, payments and records through WhatsApp, phone calls, spreadsheets and paper records.

GreenPlot provides one digital platform for layout associations, residents, guards, staff, supervisors and vendors.

### Core principle

> Every important layout activity should create a digital, searchable and auditable record.

### Standard workflow

`REQUEST → ASSIGN → VISIT PROPERTY → COMPLETE WORK → VERIFY & RECORD → SEARCHABLE HISTORY`

---

## 2. Goals

- Digitize day-to-day layout/property management.
- Create reliable property and maintenance history.
- Make maintenance work measurable and verifiable.
- Capture Proof of Work instead of relying only on completion text.
- Securely store photos, videos and documents.
- Provide role-based access.
- Support mobile-first field operations.
- Support offline-tolerant guard/staff workflows.
- Provide dashboards, reports and audit trails.

### Maintenance goals

A completed maintenance job should be able to contain:

- Job details
- Property/asset
- Assigned staff/vendor
- Start and completion information
- Checklist
- Work notes
- Before/after evidence
- Materials/spares
- Invoice/receipt/service report
- GPS/location where available
- QR/NFC asset identification where applicable
- Supervisor verification
- Audit history

---

## 3. Non-Goals / Out of Scope

V1 excludes:

- Full accounting/ERP
- Full GST accounting
- Payroll
- CCTV platform
- AI intrusion detection
- Face recognition
- ANPR
- Property title/legal verification
- Resident marketplace
- Elections/voting
- Full facility-management ERP
- Raw card/payment credential storage

Potential future phases:

- Native guard Android app
- Payroll
- CCTV/ANPR
- Advanced WhatsApp automation
- Vendor contracts
- Resident voting
- Advanced accounting/depreciation
- AI inspection
- Visual before/after comparison
- Damage/vegetation detection
- Anomaly detection
- Predictive maintenance
- Automated reports
- GIS/digital twin

---

## 4. Target Users

### Plot Owner / Resident
View property, maintenance history, complaints, dues, payments, notices, visitors, vehicles and permitted digital records.

### Guard
Visitor/vehicle entry, staff registration, patrols, incidents and SOS, including offline operation.

### Maintenance Staff
Assigned jobs, start/complete work, asset scan, evidence capture, checklist, notes, materials and submission.

### Supervisor
Assign work, review evidence, approve/reject, request rework and monitor operations.

### Vendor
Receive jobs, submit service details, Proof of Work and invoices/service reports.

### Layout Admin / Association
Manage properties, residents, security, maintenance, gardening, assets, staff, vendors, billing, complaints, records, notices and reports.

### Platform Super Admin
Manage tenants, subscriptions, configuration and platform operations.

---

## 5. Core Modules

1. Property Management
2. Property Watch / Inspections
3. Security & Access
4. Maintenance & Repairs
5. Cleaning & Compound Maintenance
6. Landscaping & Gardening
7. Complaints / Service Requests
8. Asset Management
9. Staff Management
10. Vendor Management
11. Billing & Dues
12. Communication
13. Digital Records / Media
14. Proof of Work
15. Dashboards & Reports
16. Search
17. Audit
18. Offline/PWA

---

# 6. Property Management

Each property should support:

- Property/plot ID
- Plot number
- Layout
- Address/location
- Owner
- Resident
- Status
- Associated assets
- Maintenance history
- Complaints
- Media
- Documents

Property history should provide a timeline of inspections, maintenance, complaints, incidents, gardening, security events and relevant records.

---

# 7. Property Watch / Inspection

Inspection points may include:

- Boundary
- Gate
- Fencing
- Vegetation
- Garden
- Water/utilities
- Streetlights
- Drainage
- Security
- Common infrastructure

Inspection record:

- Inspection ID
- Property
- Inspector
- Date/time
- Checklist
- Condition
- Findings
- Photos/videos
- Location where available
- Follow-up issue
- Generated maintenance task

Inspection findings can create maintenance jobs.

---

# 8. Maintenance Management

### Maintenance types

- Cleaning
- Compound maintenance
- Gate/fence
- Plumbing
- Electrical
- Civil
- Painting
- Gardening
- Landscaping
- Repairs
- Preventive maintenance
- Asset servicing
- Other configured services

### Task lifecycle

`CREATED → ASSIGNED → ACCEPTED → STARTED → COMPLETED → APPROVED → CLOSED`

Rework:

`COMPLETED → REWORK REQUIRED → STARTED → COMPLETED`

---

# 9. Maintenance Proof of Work

Proof of Work is a core GreenPlot capability.

It should answer:

> What was done, where, when, by whom, what evidence supports it, what materials/documents were involved, and who verified it?

## 9.1 Evidence types

### Before photos
For visual work, capture the original condition and link it to the job.

### After photos
Capture the completed condition and link it to the job.

### Checklist
Each item supports completed, failed or skipped. Failed/skipped items require a reason.

### Completion notes
Record work performed, issue found, outcome and observations.

### Worker identity
Store staff/vendor account, user ID, role and submission time.

### Timestamps
Record creation, assignment, acceptance, start, evidence upload, completion, review, approval/rejection and closure.

### GPS/location
Capture coordinates where available and permitted. GPS should be supporting evidence, not absolute proof of quality/completion.

### Video
Allow short videos where they provide stronger evidence, such as equipment operation, gate operation or repair completion.

### Materials/spares
Record material, quantity, unit, optional cost, supplier and notes.

### Invoice/receipt/service report
Allow attachments for invoices, receipts, vendor reports, warranty documents and purchase documents.

### QR/NFC asset scan
For maintainable assets:

`SCAN ASSET → CONFIRM ASSET → CREATE/EXECUTE MAINTENANCE`

### Supervisor approval
Supervisor can approve, reject, request rework and add comments/evidence.

### Audit trail
Record creation, assignment, start, evidence upload, checklist changes, submission, approval, rejection, reopening and closure.

---

# 10. Evidence Requirements

Evidence requirements must be configurable by task type.

Example:

| Task | Before | After | Checklist | GPS | Supervisor |
|---|---|---|---|---|---|
| Cleaning | Optional/Required | Required | Required | Optional | Configurable |
| Gate repair | Required | Required | Required | Optional | Required |
| Gardening | Required | Required | Required | Optional | Configurable |
| Electrical | Required | Required | Required | Optional | Required |
| Inspection | Required | Required | Required | Optional | Required |

If required evidence cannot be captured:

- Worker selects an exception.
- Worker enters a reason.
- Supervisor reviews it.
- Exception is recorded in the audit trail.
- The system must not silently treat missing required evidence as complete.

---

# 11. Maintenance Record

Example record:

```text
GP-MNT-2026-00418
Green Valley Layout
Main Entrance Gate

Task:
Gate hinge lubrication and alignment

Assigned:
Maintenance Staff

Completed:
26 Sep 2026, 10:42 AM

Proof:
- Before photos
- After photos
- Checklist
- Work notes
- Materials
- Optional GPS
- Invoice/service document

Supervisor:
Approved
26 Sep 2026, 11:15 AM

Audit:
Created → Assigned → Started → Evidence Submitted
→ Approved → Closed
```

---

# 12. Digital Records / Media

Media may be attached to:

- Property
- Visitor
- Vehicle
- Patrol
- Maintenance task
- Complaint
- Incident
- Asset
- Vendor job
- Inspection

Metadata:

- Media ID
- Tenant ID
- Entity type/ID
- Evidence type/stage
- Uploaded by
- Captured timestamp where available
- Uploaded timestamp
- GPS where available
- Storage key
- Thumbnail
- File size/type
- SHA-256
- Processing status

States:

`PENDING → UPLOADING → PROCESSING → READY / FAILED → DELETED`

### Storage

Use private S3-compatible object storage such as S3/R2. Do not store large media directly in PostgreSQL.

Use signed upload URLs and signed access URLs.

### Security

- Private buckets
- Signed URLs
- Authorization checks
- Tenant isolation
- No permanent public media URLs
- Appropriate access logging

### Retention

Initial planning value: 90 days for routine media, configurable. Incident/legal records may require longer retention according to policy and applicable requirements.

---

# 13. Evidence Integrity

For uploaded evidence:

- Generate SHA-256 hash.
- Preserve original object.
- Store upload metadata.
- Track processing.
- Audit replacement/deletion where permitted.
- Preserve approval/rework history.

The system should answer:

- Who uploaded it?
- When?
- Which job?
- Was it approved?
- Was it subsequently replaced/deleted?

---

# 14. Cleaning & Compound Maintenance

Support:

- Plot cleaning
- Common-area cleaning
- Compound cleaning
- Waste removal
- Gate/fence cleaning
- Drain cleaning
- Recurring schedules
- Assignment
- Checklist
- Before/after evidence
- Supervisor verification
- History

---

# 15. Landscaping & Gardening

Support:

- Mowing
- Trimming
- Weeding
- Planting
- Pruning
- Watering
- Seasonal maintenance
- Recurring schedules
- Checklist
- Before/after evidence
- Materials
- Supervisor verification
- History

---

# 16. Complaints / Service Requests

Lifecycle:

`OPEN → ASSIGNED → IN PROGRESS → RESOLVED → CLOSED`

Support:

- Property
- Category
- Priority
- Description
- Photo/video
- Assigned staff/vendor
- Comments
- Maintenance linkage
- Resolution evidence
- Closure information

---

# 17. Asset Management

Assets may include:

- Gates
- Pumps
- Motors
- Streetlights
- Electrical equipment
- Water equipment
- Security equipment
- Common infrastructure

Asset fields:

- Asset ID
- QR code
- Optional NFC ID
- Name/category
- Location
- Installation date
- Vendor
- Warranty
- Condition
- Maintenance schedule
- History
- Documents
- Media

Workflow:

`SCAN QR/NFC → OPEN ASSET → VIEW HISTORY → CREATE MAINTENANCE → CAPTURE PROOF → APPROVAL → HISTORY`

---

# 18. Security & Access

### Visitor management

- Name
- Photo where applicable
- Phone
- Purpose
- Host/property
- Entry
- Exit
- Approval

### Vehicles

- Vehicle number
- Owner/resident
- Entry/exit
- Visitor vehicle
- Optional photo

### Patrol

- Route
- Checkpoints
- QR/NFC
- Timestamp
- Optional photo
- Exceptions

### Incidents

`OPEN → ACKNOWLEDGED → INVESTIGATING → RESOLVED → CLOSED`

Incident evidence can include photos, video, notes, time and location.

### SOS

- SOS activation
- Emergency notification
- Escalation
- Incident linkage
- Audit record

---

# 19. Billing & Dues

Support:

- Recurring periods
- Per plot/unit/sqft/fixed/custom
- Dues
- Receipts
- Defaulters
- Basic expenses

Payment gateway may use an approved Indian provider.

Requirements:

- Webhook verification
- Idempotency
- Reconciliation
- Receipts
- No raw card storage

Full accounting/GST is outside V1.

---

# 20. Communication

Support:

- Announcements
- Notices
- Alerts
- Events
- Outages
- Optional resident directory

Channels:

- In-app
- Push
- SMS
- WhatsApp
- Email optional

---

# 21. Staff & Vendor Management

### Staff

- Profiles
- Roles
- Shifts
- Attendance
- Assigned tasks
- Work history

### Vendors

- Profile
- Contact
- Service category
- Assigned jobs
- Documents
- Service history
- Performance

Vendor workflow:

`CREATED → ASSIGNED → ACCEPTED → STARTED → COMPLETED → APPROVED → CLOSED`

Vendor jobs use the Proof of Work model where applicable.

---

# 22. Reports & Dashboard

Admin dashboard:

- Open complaints
- Active maintenance
- Overdue tasks
- Completed tasks
- Pending approvals
- Maintenance cost
- Vendor activity
- Staff activity
- Security incidents
- Inspections
- Billing status

Maintenance reports filter by:

- Date
- Layout
- Property
- Asset
- Category
- Staff
- Vendor
- Status
- Approval status

Reports:

- Maintenance history
- Pending work
- Completed work
- Rework
- Vendor performance
- Maintenance cost
- Asset maintenance history
- Proof-of-work records

Authorized users can generate a downloadable maintenance proof report.

---

# 23. Search

Search/filter:

- Property
- Plot
- Maintenance ID
- Complaint ID
- Asset
- Vendor
- Staff
- Date
- Category
- Status

Example:

> Show all gate repairs for Plot 117 in the last 12 months.

---

# 24. Role-Based Access Control

Roles:

- Resident
- Guard
- Staff
- Supervisor
- Vendor
- Layout Admin
- Platform Super Admin

Permissions must be tenant-aware.

Residents only see permitted property records. Staff see assigned jobs. Supervisors approve permitted jobs. Admins manage the layout. Super Admin manages the platform.

---

# 25. Multi-Tenant Architecture

Every tenant-owned record uses `tenant_id`.

Tenant isolation applies to:

- Users
- Properties
- Maintenance
- Media
- Assets
- Complaints
- Billing
- Vendors
- Staff
- Reports
- Audit logs

Cross-tenant access must be prevented.

---

# 26. Technical Architecture

```text
Internet
   ↓
Cloudflare / Reverse Proxy
   ↓
Next.js / React PWA
   ↓
FastAPI REST API
   ↓
PostgreSQL + PostGIS
   ├── Redis (optional)
   ├── Background Workers (optional)
   └── Private S3/R2 Object Storage
```

Use a modular monolith for V1 and scale components as required.

---

# 27. Technology Stack

### Frontend
- React / Next.js
- TypeScript
- Mobile-first responsive UI
- PWA
- Camera
- IndexedDB
- Offline queue
- Push notifications

### Backend
- Python
- FastAPI
- REST JSON
- Background workers

### Database
- PostgreSQL
- PostGIS

### Storage
- S3-compatible object storage
- S3/R2

### Infrastructure
- Cloudflare
- Containerized deployment
- Single VPS/cloud VM initially

---

# 28. API Requirements

Base:

`/api/v1`

Core resources:

```text
/auth
/tenants
/users
/properties
/residents
/visitors
/vehicles
/patrol
/incidents
/sos
/tasks
/maintenance
/media
/complaints
/assets
/gardening
/staff
/vendors
/billing
/payments
/notices
/records/search
/reports
/dashboard
/sync
```

Maintenance APIs:

```http
POST   /api/v1/maintenance
GET    /api/v1/maintenance/{id}
PATCH  /api/v1/maintenance/{id}
POST   /api/v1/maintenance/{id}/assign
POST   /api/v1/maintenance/{id}/start
POST   /api/v1/maintenance/{id}/evidence
POST   /api/v1/maintenance/{id}/complete
POST   /api/v1/maintenance/{id}/approve
POST   /api/v1/maintenance/{id}/reject
POST   /api/v1/maintenance/{id}/reopen
```

Media:

```http
POST   /api/v1/media/upload-url
POST   /api/v1/media/complete
GET    /api/v1/media/{id}
DELETE /api/v1/media/{id}
```

Use signed URLs for large uploads where practical.

---

# 29. Database Requirements

Use:

- UUID primary keys
- Foreign keys
- `tenant_id`
- UTC timestamps
- Indexes
- PostGIS geography when required
- Soft deletes where appropriate
- Audit records

Core entities:

```text
Tenant
User
Role
Property
Resident
Asset
MaintenanceTask
MaintenanceChecklist
MaintenanceEvidence
Complaint
Inspection
Staff
Vendor
Invoice
Payment
Notification
Incident
Patrol
AuditLog
```

Suggested evidence fields:

```text
id
tenant_id
maintenance_id
entity_type
entity_id
media_id
evidence_type
uploaded_by
captured_at
uploaded_at
latitude
longitude
sha256
status
created_at
updated_at
```

---

# 30. Offline/PWA

Guard/staff PWA should support offline-tolerant:

- Visitor entries
- Vehicle entries
- Patrols
- Incidents
- Maintenance tasks
- Evidence capture

Offline queue fields:

- Local operation ID
- Timestamp
- User
- Entity
- Payload
- Sync state

States:

`QUEUED → SYNCING → SYNCED / FAILED / RETRY`

Operations should be idempotent.

---

# 31. End-to-End Maintenance Proof Flow

```text
Worker opens task
        ↓
Start Work
        ↓
Optional QR/NFC Asset Scan
        ↓
Before Photo
        ↓
Perform Work
        ↓
Checklist
        ↓
Work Notes
        ↓
Materials
        ↓
After Photo/Video
        ↓
Invoice/Receipt
        ↓
Submit
        ↓
Supervisor Review
        ↓
APPROVED → CLOSED
        │
        └→ REWORK REQUIRED → Worker fixes → Resubmits
```

---

# 32. Frontend Requirements

## Public website

Include:

- GreenPlot wordmark
- Tagline: Property Management Made Simple
- Hero
- Services
- Property Watch
- Maintenance Records / Proof of Work
- Digital Records
- How It Works
- For Layouts
- Request Demo
- Contact
- Footer
- WhatsApp contact

### WhatsApp

Configured number:

`+91 8105568225`

Provide a click-to-chat action with a prefilled enquiry message.

## Public maintenance feature section

### Every maintenance task. Documented and verified.

Suggested copy:

> Know what was done, when it was done, and who completed it. GreenPlot keeps maintenance activities organized with photo evidence, task checklists, work notes, and supervisor verification—all connected to the property’s digital history.

The public website should show only sample/demo records, never real tenant data.

---

# 33. Staff Maintenance Portal

Flow:

`Login → My Tasks → Task Details → Start Work → Evidence → Checklist → Materials → Notes → Submit`

Mobile-first priorities:

- Large action buttons
- Camera
- Checklist
- Upload progress
- Offline state
- Sync status

---

# 34. Supervisor Portal

Screens:

- Dashboard
- Pending approvals
- Task details
- Evidence viewer
- Checklist
- Work notes
- Materials
- Invoice
- Approve
- Reject
- Request rework
- History

---

# 35. Resident Portal

Screens:

- Dashboard
- Property
- Property Watch
- Maintenance history
- Complaints
- Visitors
- Vehicles
- Dues
- Payments
- Notices
- SOS
- Profile

Evidence visibility follows configured privacy rules.

---

# 36. Admin Portal

Screens:

- Dashboard
- Residents
- Properties
- Security
- Maintenance
- Gardening
- Assets
- Vendors
- Staff
- Billing
- Complaints
- Digital Records
- Announcements
- Reports
- Settings

---

# 37. Security & Privacy

Requirements:

- HTTPS
- Secure authentication
- Role-based authorization
- Tenant isolation
- Private object storage
- Signed media URLs
- Password hashing
- Session/token security
- Audit logging
- Input validation
- Rate limiting
- Secure upload validation
- Malware/file scanning where applicable
- Backup strategy
- Data retention configuration

Sensitive media must never be publicly accessible.

---

# 38. Audit

Audit important actions:

- User creation
- Role changes
- Property changes
- Maintenance assignment
- Completion
- Evidence upload
- Evidence deletion/replacement
- Approval/rejection
- Billing changes
- Payment status
- Incident changes
- Configuration changes

Audit fields:

```text
audit_id
tenant_id
actor_id
action
entity_type
entity_id
timestamp
old_value/reference
new_value/reference
IP/device metadata where appropriate
```

---

# 39. Notifications

Triggers:

- Task assignment
- Due/overdue task
- Maintenance completion
- Approval
- Rejection/rework
- Complaint update
- Payment due/success
- Incident
- SOS
- Announcement

Channels are configurable.

---

# 40. Maintenance Proof Report

A downloadable report should contain:

```text
GreenPlot
Maintenance Proof of Work

Record ID
Property
Asset
Task
Category
Priority

Assigned Staff/Vendor
Start Time
Completion Time

Checklist

Before Evidence

After Evidence

Work Notes

Materials

Invoice/Service Documents

GPS information if available

Supervisor Decision

Approval Timestamp

Audit Summary
```

---

# 41. Testing

### Unit
- State transitions
- Permissions
- Evidence validation
- Checklist rules
- Billing calculations
- Audit generation
- Tenant isolation

### API
- Authentication
- Authorization
- CRUD
- Upload flow
- Approval/rejection
- Idempotency
- Offline sync

### UI
- Mobile
- Desktop
- Camera
- Upload
- Offline mode
- Sync
- Approval

### Security
- Cross-tenant access
- Unauthorized media access
- Broken authorization
- File upload security
- Token/session security
- Rate limiting

### Evidence integrity
- Original preservation
- Hash generation
- Correct job association
- Replacement/deletion audit
- Approval/rework history

---

# 42. Acceptance Criteria

A maintenance implementation is accepted when:

- Task can be created and assigned.
- Worker can accept/start it.
- Configured checklist can be completed.
- Required evidence can be captured/uploaded.
- Evidence is linked to the correct task.
- Worker identity is stored.
- Timestamps are stored.
- GPS is stored where configured and available.
- Materials can be recorded.
- Documents can be attached.
- Supervisor can approve/reject.
- Rework can be requested.
- Audit history is retained.
- Authorized users can view the final record.
- Unauthorized users cannot access evidence.
- Record is searchable.

---

# 43. Success Metrics

- Percentage of maintenance tasks completed digitally
- Percentage with required proof
- Percentage approved without rework
- Average completion time
- Average approval time
- Overdue tasks
- Repeat complaints
- Evidence upload success rate
- Offline synchronization success rate
- Resident adoption
- Layout/admin adoption

---

# 44. Delivery Roadmap

### Phase 1 — Foundation
Authentication, tenants, users/roles, properties, database, API and frontend foundation.

### Phase 2 — Maintenance MVP
Tasks, assignment, staff workflow, checklists, before/after photos, notes, approval and history.

### Phase 3 — Digital Evidence
Private storage, signed uploads, video, documents, hashing, metadata, thumbnails, audit and integrity.

### Phase 4 — Property Operations
Property Watch, complaints, assets, QR/NFC, gardening, cleaning, vendors and staff.

### Phase 5 — Security
Visitors, vehicles, patrols, incidents and SOS.

### Phase 6 — Finance & Communication
Billing, dues, payments, receipts, notifications and WhatsApp/SMS/push.

### Phase 7 — Offline/PWA
IndexedDB queue, background sync, retry and installable PWA.

### Phase 8 — Reports & Scale
Dashboards, reports, proof reports, advanced search, tenant administration and monitoring.

---

# 45. Future AI

Potential later features:

- Before/after image comparison
- Visible damage detection
- Vegetation analysis
- Maintenance anomaly detection
- Predictive maintenance
- Automatic maintenance summaries
- Property condition reports
- Missing-evidence detection
- Checklist suggestions
- Cost prediction
- Resident-friendly reports

AI output must be treated as recommendations, not authoritative proof.

---

# 46. SaaS Model

GreenPlot is designed as a multi-tenant SaaS.

Possible pricing dimensions:

- Per layout
- Per property/plot
- Number of residents
- Number of staff/guards
- Storage
- Premium modules
- Advanced reporting

Possible modules:

- Core Property Management
- Security
- Maintenance
- Digital Records
- Billing
- Vendor Management
- Advanced Reports

Final pricing remains a business decision.

---

# 47. Open Questions / Decisions

1. Exact V1 launch scope.
2. Layout/property hierarchy.
3. Multiple owners/residents per property.
4. Role/permission matrix.
5. Authentication.
6. Resident invitation.
7. Staff/vendor onboarding.
8. Maintenance categories.
9. Checklist template management.
10. Task types requiring before photos.
11. Task types requiring after photos.
12. Task types requiring approval.
13. Evidence size limits.
14. Maximum photos/task.
15. Maximum video duration.
16. Accepted documents.
17. GPS privacy/accuracy policy.
18. QR/NFC hardware approach.
19. Evidence retention.
20. Incident/legal retention.
21. Storage provider.
22. Media processing provider.
23. Payment gateway.
24. WhatsApp integration scope.
25. SMS provider.
26. Push provider.
27. Offline conflict resolution.
28. Device-loss handling.
29. PDF/report format.
30. Resident access to evidence.
31. Vendor access duration.
32. Resident acknowledgement.
33. Single/multiple approval levels.
34. Maintenance cost approval.
35. Invoice approval.
36. Audit retention.
37. Backup policy.
38. Data export.
39. Tenant deletion.
40. Subscription/package structure.

---

# 48. V1 Proof-of-Work Minimum

### Required
- Maintenance ID
- Property/asset
- Task description
- Assigned staff/vendor
- Start/completion timestamps
- Completion notes
- Checklist
- After photo for visual work
- Supervisor approval
- Audit trail

### Configurable
- Before photo
- GPS
- Video
- QR/NFC
- Materials
- Invoice
- Resident acknowledgement

### Recommended
Before/after evidence for visual maintenance tasks.

---

# 49. End-to-End Example

```text
Resident reports:
"Gate is difficult to close."
        ↓
Complaint GP-CMP-001
        ↓
Maintenance GP-MNT-00418
        ↓
Assigned to staff
        ↓
Worker accepts
        ↓
Gate QR scanned
        ↓
Before photo
        ↓
Repair/alignment
        ↓
Checklist completed
        ↓
After photos
        ↓
Work notes + material
        ↓
Submit
        ↓
Supervisor review
        ├── APPROVED → CLOSED
        └── REWORK → Fix → Resubmit
        ↓
Searchable property history
```

---

# 50. Product Principle

GreenPlot should not merely answer:

> "Was the maintenance completed?"

It should provide a structured answer to:

> **What was done, where, when, by whom, what evidence supports it, what materials/documents were involved, and who verified the work?**

This Proof of Work model is a key GreenPlot differentiator.

---

# 51. Source-of-Truth Rule

This document is the product-level source of truth.

Detailed frontend, backend, API, database, testing and deployment specifications derive from this document.

If another implementation document conflicts with this specification:

1. Identify the conflict.
2. Record the decision.
3. Update the affected requirement.
4. Keep the final decision explicit.

---

# 52. Glossary

**GreenPlot:** Property and layout management platform.

**Tenant:** Layout/association using GreenPlot.

**Property:** Individual plot/property managed in GreenPlot.

**Asset:** Maintainable physical item/infrastructure.

**Maintenance Task:** Work item created to maintain or repair a property/asset.

**Proof of Work:** Structured evidence demonstrating what maintenance work was performed.

**Evidence:** Photo, video, document, checklist, location or other record associated with a task.

**Before Evidence:** Evidence showing condition before work.

**After Evidence:** Evidence showing condition after work.

**Supervisor Approval:** Review and acceptance of completed work.

**Rework:** Work returned for correction before approval.

**Digital Record:** Searchable operational record and associated evidence.

**PWA:** Progressive Web Application.

**QR/NFC Asset Scan:** Physical asset identification mechanism.

**Audit Trail:** Historical record of important system actions.
