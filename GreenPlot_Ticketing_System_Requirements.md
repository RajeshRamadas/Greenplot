# GreenPlot — Customer Ticketing & Vendor Service Management Requirements

**Product:** GreenPlot  
**Module:** Customer Ticketing & Vendor Service Management  
**Tagline:** Property Management Made Simple  
**Version:** 1.0  
**Initial scope:** Bangalore  
**Platform:** Responsive Web Application / PWA

## 1. Purpose

GreenPlot shall provide a complete ticketing system where a customer/resident raises a service request, an admin/supervisor reviews and assigns it to a vendor or staff member, the assignee performs and documents the work, the work is verified, the ticket is closed, and the customer is automatically notified.

### Primary workflow

`CUSTOMER RAISES TICKET → TICKET CREATED → ADMIN REVIEW → VENDOR/STAFF ASSIGNED → ACCEPTED → WORK IN PROGRESS → WORK COMPLETED + PROOF → SUPERVISOR VERIFICATION → TICKET CLOSED → CUSTOMER NOTIFIED`

The module integrates with Property Management, Maintenance, Vendors, Staff, Digital Records, Proof of Work, Notifications, Audit Trail and Reports.

## 2. Goals

- Give residents/customers an easy way to raise service tickets.
- Give every ticket a unique tracking ID.
- Allow admins/supervisors to review and assign tickets.
- Assign to internal staff or external vendors.
- Give vendors a dedicated accept/work/complete workflow.
- Capture Proof of Work.
- Provide customer status visibility.
- Automatically notify customers about important events, especially closure.
- Prevent tickets from being lost or forgotten.
- Maintain a complete audit history.
- Support SLA, priority and escalation.
- Connect completed tickets to property and maintenance history.

## 3. Non-Goals

V1 does not require full CRM, complex call-center/ITSM, payroll, full accounting, advanced AI ticket resolution, or property-title/legal verification.

## 4. Users

### Customer / Resident
Create tickets, attach evidence, track status, comment, receive notifications, view resolution, provide feedback and reopen according to policy.

### Layout Admin
View all tickets, categorize, prioritize, assign/reassign, set SLA, escalate, communicate, review proof, close/reopen and report.

### Supervisor
Review assignments, monitor SLA, review vendor work, approve/reject, request rework, resolve and close.

### Vendor
View assigned tickets, accept/reject, communicate, start work, upload proof, record materials and submit completion.

### Staff
Internal staff can follow the vendor workflow subject to permissions.

## 5. Ticket Categories

Configurable examples:

- Cleaning
- Gardening
- Plumbing
- Electrical
- Gate/Fence
- Security
- Water
- Drainage
- Streetlight
- Common Area
- Property Inspection
- Maintenance
- Vendor Service
- Other

Each category may define default priority, SLA, checklist, required evidence, preferred vendor type and escalation rule.

## 6. Ticket Creation

Customer flow:

`Create Ticket → Property/Plot → Category → Subcategory → Issue → Description → Priority (if allowed) → Photos/Video → Preferred Time → Submit`

Required: Ticket ID, tenant/layout, customer, property, category, description, created timestamp, status and priority.

Optional: subcategory, photos, video, documents, preferred time, additional contact details and location.

### Ticket number

Use a stable unique number such as `GP-TKT-2026-000001`.

## 7. Priority

Initial priorities:

- Low
- Medium
- High
- Critical

Priority may be selected within configured limits, assigned automatically from category, changed by admin or escalated by SLA. Changes must be audited.

## 8. Ticket Lifecycle

Recommended states:

`OPEN → UNDER_REVIEW → ASSIGNED → ACCEPTED → IN_PROGRESS → WAITING_FOR_CUSTOMER → WORK_COMPLETED → VERIFICATION → RESOLVED → CLOSED`

Alternative states: `REJECTED`, `CANCELLED`, `ON_HOLD`, `REOPENED`.

## 9. Assignment

Tickets may be assigned to internal staff, a vendor, a technician or a vendor team.

Store assignee type/ID, assigned by, assigned timestamp, due date, SLA and notes.

Reassignment must preserve previous assignee, new assignee, reason, actor and timestamp.

## 10. Vendor Acceptance

Vendor receives an assignment notification and may accept or reject.

A rejection requires a reason such as wrong category, outside service area, no availability or unavailable equipment. Rejection returns the ticket to admin/supervisor for reassignment and must not silently close the ticket.

## 11. Vendor Work Execution

`Assigned → Accept → Start Work → Before Evidence → Work → Checklist → Materials → After Evidence → Completion Notes → Submit Completion`

## 12. Proof of Work

Reuse GreenPlot's Proof of Work model.

Possible evidence:

- Before photos
- After photos
- Video
- Checklist
- Work notes
- Materials
- Invoice
- Receipt
- Service report
- Warranty document
- GPS/location
- QR/NFC asset scan

Evidence requirements are configurable by category.

Example:

| Category | Before | After | Checklist | Supervisor |
|---|---|---|---|---|
| Cleaning | Optional | Required | Required | Configurable |
| Plumbing | Required | Required | Required | Required |
| Electrical | Required | Required | Required | Required |
| Gardening | Required | Required | Required | Configurable |
| Gate repair | Required | Required | Required | Required |

## 13. Customer Communication

Every ticket has a customer-visible timeline/conversation. Customers can add comments, answer questions, upload additional evidence and view permitted status/vendor messages.

Internal notes are separate from customer-visible comments and must never be exposed accidentally.

## 14. Ticket Timeline

The timeline records ticket creation, review, assignment, vendor acceptance, work start, evidence upload, completion, verification, closure and notifications.

Example:

`Created → Reviewed → Assigned → Accepted → Started → Evidence Submitted → Approved → Closed → Customer Notified`

## 15. SLA

Each category can define response and resolution SLAs. Example planning values:

| Priority | Response SLA | Resolution SLA |
|---|---:|---:|
| Critical | 15 min | 4 hrs |
| High | 1 hr | 24 hrs |
| Medium | 4 hrs | 48 hrs |
| Low | 24 hrs | 5 days |

Actual values are configurable by layout.

Track created, first response, assignment, acceptance, start, resolution, closure and SLA breach times.

## 16. SLA Escalation

Approaching SLA: notify assignee and supervisor.  
SLA breach: notify supervisor/admin and optionally escalate further.

Rules must be configurable.

## 17. Customer Notifications

Notify customers for events such as:

- Ticket created
- Assigned
- Vendor accepted
- Work started
- Waiting for customer
- Work completed
- Resolved
- Closed
- Reopened

### Mandatory closure notification

When a valid ticket reaches `CLOSED`:

1. Store closure timestamp and closing actor.
2. Generate closure event.
3. Create customer notification.
4. Send through configured channel(s).
5. Log delivery result.
6. Show notification in customer portal.
7. Update ticket/property history.

Example:

> **GreenPlot Ticket Closed** — Your service request **GP-TKT-2026-000001** has been completed and closed. [View Ticket]

## 18. Notification Channels

Support:

- In-app
- Push
- WhatsApp
- SMS
- Email

V1 should prioritize in-app/push and the configured WhatsApp/SMS channel.

Notification delivery must be logged.

## 19. Closure Confirmation

Two supported patterns:

### Recommended
`Supervisor approves → RESOLVED → Customer notified → optional acknowledgement → CLOSED`

Customer may select `Resolved` or `Still an issue`. "Still an issue" creates `REOPENED` and sends the ticket back for action.

## 20. Reopening

Reopening requires reason, actor and timestamp. Customer reopening can be limited to a configurable period; admin can reopen according to policy. All reopenings are audited.

## 21. Attachments

Tickets support photos, videos, PDFs, invoices, receipts, service reports and other approved documents.

Use GreenPlot's private media architecture with signed upload URLs and private S3/R2 storage.

Store file ID, ticket ID, uploader, type, timestamp, size, hash and processing state.

## 22. Security & Permissions

Customers access only their permitted tickets/properties. Vendors access only assigned/permitted tickets. Internal notes are hidden from customers/vendors. Tenant isolation is mandatory. Customer/vendor contact details are exposed only when required and permitted.

## 23. Database Model

### Ticket

```text
id
ticket_number
tenant_id
property_id
customer_id
category_id
subcategory_id
title
description
priority
status
source
assigned_to_type
assigned_to_id
sla_policy_id
due_at
first_response_at
accepted_at
started_at
completed_at
resolved_at
closed_at
reopened_at
created_at
updated_at
```

### TicketComment

```text
id
ticket_id
tenant_id
author_id
comment_type
visibility
message
created_at
updated_at
```

Visibility: `CUSTOMER`, `INTERNAL`, `VENDOR`, `SUPERVISOR`.

### TicketAssignment

```text
id
ticket_id
assignee_type
assignee_id
assigned_by
assigned_at
accepted_at
rejected_at
rejection_reason
unassigned_at
created_at
```

### TicketSLA

```text
id
ticket_id
response_due_at
resolution_due_at
first_response_at
resolved_at
response_breached
resolution_breached
```

### TicketStatusHistory

```text
id
ticket_id
old_status
new_status
changed_by
reason
created_at
```

### TicketEvidence

Reuse GreenPlot Digital Records/Media entities with `ticket_id`, `media_id`, `evidence_type`, `uploaded_by` and `created_at`.

## 24. API Requirements

Base path: `/api/v1`

```http
POST   /tickets
GET    /tickets
GET    /tickets/{id}
PATCH  /tickets/{id}
POST   /tickets/{id}/assign
POST   /tickets/{id}/accept
POST   /tickets/{id}/reject
POST   /tickets/{id}/start
POST   /tickets/{id}/comments
POST   /tickets/{id}/evidence
POST   /tickets/{id}/complete
POST   /tickets/{id}/verify
POST   /tickets/{id}/resolve
POST   /tickets/{id}/close
POST   /tickets/{id}/reopen
GET    /tickets/{id}/timeline
GET    /tickets/{id}/history
GET    /tickets/{id}/sla
GET    /tickets/{id}/evidence
```

## 25. Customer Frontend

Ticket list: ID, title, category, status, priority, created date, assigned vendor/staff and last update.

Filters: Open, In Progress, Resolved, Closed, Reopened.

Create ticket: property, category, issue, description, photos/video, preferred time and submit.

Ticket details: ticket number, status, priority, vendor, SLA, timeline, comments, attachments, proof, resolution and acknowledgement.

## 26. Vendor Frontend

Dashboard sections:

- New Assignments
- Accepted
- In Progress
- Awaiting Verification
- Completed
- Rejected

Ticket screen includes customer issue, permitted property/location, category, priority, SLA, instructions, attachments, comments, Start Work, Evidence, Checklist, Materials and Complete Work.

## 27. Admin/Supervisor Frontend

Dashboard:

- New tickets
- Unassigned
- Assigned
- In progress
- SLA at risk
- SLA breached
- Awaiting verification
- Resolved
- Reopened

Actions: assign, reassign, priority, internal note, customer/vendor communication, approve, reject, rework, resolve, close and reopen.

## 28. Automatic Assignment

V1 can use manual assignment. Future recommendation can consider category, location/service area, availability, workload, performance, SLA and historical completion time.

## 29. Vendor Performance

Track assigned, accepted, rejected, completed, reopened, response time, resolution time, SLA breaches, ratings and rework rate.

## 30. Customer Feedback

After resolution, customer can provide rating, comment and `Resolved`/`Still an issue` response. Feedback is linked to the ticket and vendor performance.

## 31. Notification Architecture

```text
Ticket Event
   ↓
Notification Service
   ↓
Preference Check
   ↓
Channel Selection
   ├── In-App
   ├── Push
   ├── WhatsApp
   ├── SMS
   └── Email
   ↓
Delivery Log
```

Notification fields: notification ID, tenant ID, user ID, ticket ID, event type, channel, status, sent/delivered time and failure reason.

## 32. Integration With Maintenance

Ticketing and maintenance must remain connected:

`Customer Ticket → Maintenance Task → Proof of Work → Verification → Ticket Resolution → Customer Notification → Property History`

A ticket may create one or more maintenance tasks. A maintenance task may be linked to one or more tickets if configured.

## 33. Property History

Closed tickets should create a relevant property timeline entry.

Example:

```text
Property 117
Oct 05 — Plumbing Ticket
Oct 05 — Vendor Assigned
Oct 05 — Repair Completed
Oct 05 — Supervisor Approved
Oct 05 — Ticket Closed
```

## 34. Reports

### Ticket volume
- Created
- Closed
- Open
- Overdue

### SLA
- Met
- Breached
- Average response time
- Average resolution time

### Vendor
- Tickets by vendor
- Completion time
- Rework
- Reopen rate
- Ratings

### Category
- Most common issues
- Recurring problems
- Average resolution by category

### Customer
- Tickets by property
- Repeat complaints
- Satisfaction

## 35. Dashboard KPIs

Recommended cards:

```text
Open Tickets | In Progress | SLA At Risk
Resolved Today | Closed Today | SLA Breached
```

## 36. Offline Support

Vendor/staff PWA can cache assigned tickets and queue notes, photos, checklist completion and completion actions for later synchronization.

`Local Queue → Sync → Server Validation → Conflict Handling → Synced`

Operations must be idempotent.

## 37. Testing

### Customer
- Ticket creation
- Tracking
- Comments
- Evidence
- Closure notification
- Reopen

### Vendor
- Assignment
- Accept/reject
- Start
- Evidence
- Completion
- Rework

### Admin
- Assignment/reassignment
- Approval
- SLA
- Escalation
- Closure

### Notifications
- In-app
- Push
- WhatsApp/SMS/email when enabled
- Retry
- Failure handling

### Security
- Cross-tenant access
- Unauthorized evidence
- Internal note exposure
- Customer/vendor separation

### Offline
- Queue
- Sync
- Duplicate prevention
- Conflict handling

## 38. Acceptance Criteria

The module is accepted when:

1. Customer can create a ticket.
2. Unique ticket ID is generated.
3. Authorized admin/supervisor can see it.
4. Admin can categorize and prioritize.
5. Admin can assign vendor/staff.
6. Vendor receives assignment notification.
7. Vendor can accept/reject with reason.
8. Vendor can start work.
9. Vendor can upload required evidence.
10. Vendor can complete checklist.
11. Vendor can submit completion.
12. Supervisor can verify.
13. Supervisor can request rework.
14. Supervisor can approve.
15. Ticket can be resolved/closed.
16. Customer receives closure notification.
17. Notification delivery is logged.
18. Customer can view completed ticket.
19. Customer can provide feedback.
20. Customer can reopen according to policy.
21. Ticket appears in property history.
22. Audit history is retained.
23. Unauthorized users cannot access ticket/evidence.
24. SLA is tracked.
25. SLA breaches can trigger escalation.

## 39. Recommended V1 Scope

### Customer
- Create ticket
- Attach photos
- Track status
- Comment
- Notifications
- View resolution
- Reopen/feedback

### Admin/Supervisor
- Ticket dashboard
- Categorize
- Prioritize
- Assign/reassign
- SLA
- Approve/reject
- Close/reopen
- Reports

### Vendor
- Assigned tickets
- Accept/reject
- Start work
- Checklist
- Before/after photos
- Work notes
- Completion submission

### Platform
- Notifications
- Audit
- Private media
- Property history
- Search
- Tenant isolation

## 40. Future Enhancements

- Automatic vendor assignment
- Vendor availability calendar
- Vendor bidding
- Appointment scheduling
- WhatsApp two-way ticket creation
- Voice ticket creation
- AI ticket categorization
- AI priority recommendation
- AI vendor recommendation
- Duplicate-ticket detection
- Predictive SLA breach
- Sentiment analysis
- Automated ticket summaries
- Advanced customer satisfaction analytics

## 41. Product Principle

GreenPlot's ticketing system should provide a complete chain of accountability:

`CUSTOMER ISSUE → TRACKABLE TICKET → RESPONSIBLE ASSIGNEE → WORK → PROOF → VERIFICATION → RESOLUTION → CUSTOMER NOTIFICATION → FEEDBACK → PROPERTY HISTORY`

The customer should always be able to understand who is handling the issue, what is happening, what has been done, what proof exists, who verified it and whether it is closed.

## 42. Open Decisions

1. Should customers be allowed to set priority?
2. Which categories launch in V1?
3. Which categories require mandatory photos?
4. Which categories require supervisor approval?
5. Should customer confirmation be mandatory for closure?
6. How long can a customer reopen a closed ticket?
7. Default SLAs?
8. Can vendors see customer phone numbers?
9. Can customers see vendor phone numbers?
10. Should vendors communicate directly with customers?
11. Which notification channels launch in V1?
12. WhatsApp provider/API configuration?
13. SMS provider?
14. Push provider?
15. Maximum attachment sizes?
16. Maximum video duration?
17. Evidence retention?
18. Vendor rejection rules?
19. Automatic assignment?
20. Customer rating model?
21. One ticket to multiple maintenance tasks?
22. One maintenance task to multiple tickets?
23. Closure approval hierarchy?
24. SLA escalation hierarchy?
25. Notification language/localization?
26. Offline conflict policy?
27. Ticket export/PDF format?
28. Vendor performance visibility?
29. Resident access to vendor details?
30. Pricing impact of ticket volume/storage?

## 43. Source-of-Truth Rule

This document is the product-level source of truth for the GreenPlot Ticketing & Vendor Service Management module. Frontend, backend, API, database, notification and testing requirements derive from it. Conflicts with other implementation documents must be explicitly identified and resolved.
