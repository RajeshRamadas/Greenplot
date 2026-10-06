export type UUID = string;

export type Role = "resident" | "guard" | "staff" | "supervisor" | "vendor" | "layout_admin" | "super_admin";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Me {
  id: UUID;
  tenant_id: UUID | null;
  email: string;
  phone: string | null;
  full_name: string;
  role: Role;
  vendor_id: UUID | null;
  permissions: string[];
  tenant_name: string | null;
  tenant_modules: string[];
  whatsapp_opt_in: boolean;
  phone_verified_at: string | null;
  totp_enabled: boolean;
  mfa_setup_required: boolean;
  recovery_codes_left: number;
  /** Enabled feature switches for residents/vendors; null for office roles. */
  features: string[] | null;
}

export interface User {
  id: UUID;
  email: string;
  full_name: string;
  phone: string | null;
  role: Role;
  is_active: boolean;
  vendor_id: UUID | null;
  last_login_at: string | null;
  totp_enabled?: boolean;
  locked_until?: string | null;
  phone_verified_at?: string | null;
}

export interface Property {
  id: UUID;
  layout_id: UUID;
  layout_name: string | null;
  code: string;
  plot_number: string;
  block: string | null;
  address: string | null;
  area_sqft: number | null;
  units: number;
  status: string;
  condition: string;
  owner_user_id: UUID | null;
  owner_name: string | null;
  owner_phone: string | null;
  owner_email: string | null;
  notes: string | null;
  latitude: number | null;
  longitude: number | null;
}

export interface Resident {
  id: UUID;
  property_id: UUID;
  user_id: UUID | null;
  name: string;
  phone: string | null;
  email: string | null;
  relation: string;
  is_primary: boolean;
  in_directory: boolean;
}

export interface TimelineEntry {
  at: string;
  kind: string;
  id: UUID;
  number: string | null;
  title: string;
  status: string | null;
}

export interface ChecklistItem {
  id: UUID;
  position: number;
  label: string;
  status: "pending" | "completed" | "failed" | "skipped";
  reason: string | null;
  checked_at: string | null;
}

export interface Material {
  id: UUID;
  name: string;
  quantity: number;
  unit: string;
  unit_cost: number | null;
  supplier: string | null;
  notes: string | null;
  created_at: string;
}

export interface Evidence {
  id: UUID;
  media_id: UUID;
  evidence_type: string;
  uploaded_by: UUID;
  uploaded_by_name: string | null;
  captured_at: string | null;
  uploaded_at: string;
  latitude: number | null;
  longitude: number | null;
  sha256: string;
  status: string;
  rework_round: number;
  caption: string | null;
  content_type: string | null;
  url: string | null;
  thumbnail_url: string | null;
}

export interface EvidenceException {
  id: UUID;
  requirement: string;
  reason_code: string;
  reason: string;
  review_status: string;
  created_at: string;
}

export interface Comment {
  id: UUID;
  author_name: string | null;
  body: string;
  kind: string;
  created_at: string;
}

export interface ProofRequirement {
  key: string;
  required: boolean;
  state: "satisfied" | "excepted" | "missing";
}

export interface TaskSummary {
  id: UUID;
  number: string;
  title: string;
  category: string;
  priority: string;
  status: string;
  source: string;
  property_id: UUID | null;
  asset_id: UUID | null;
  complaint_id: UUID | null;
  assigned_staff_id: UUID | null;
  vendor_id: UUID | null;
  supervisor_id: UUID | null;
  due_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  approved_at: string | null;
  closed_at: string | null;
  rework_count: number;
  review_decision: string | null;
  overdue: boolean;
  property_label: string | null;
  assignee_name: string | null;
  vendor_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskDetail extends TaskSummary {
  description: string | null;
  location_note: string | null;
  inspection_id: UUID | null;
  assigned_at: string | null;
  accepted_at: string | null;
  reviewed_at: string | null;
  start_latitude: number | null;
  start_longitude: number | null;
  complete_latitude: number | null;
  complete_longitude: number | null;
  gps_accuracy_m: number | null;
  asset_scanned_at: string | null;
  asset_scan_method: string | null;
  work_notes: string | null;
  issue_found: string | null;
  outcome: string | null;
  observations: string | null;
  review_comment: string | null;
  estimated_cost: number | null;
  resident_ack_at: string | null;
  resident_ack_note: string | null;
  checklist: ChecklistItem[];
  materials: Material[];
  evidence: Evidence[];
  exceptions: EvidenceException[];
  comments: Comment[];
  proof: { policy: Record<string, boolean>; requirements: ProofRequirement[]; missing: string[]; pending_checklist: string[] } | null;
  allowed_actions: string[];
  asset_label: string | null;
  supervisor_name: string | null;
  completed_by_name: string | null;
  reviewed_by_name: string | null;
  materials_cost: number;
}

export interface Complaint {
  id: UUID;
  number: string;
  property_id: UUID | null;
  category: string;
  priority: string;
  title: string;
  description: string | null;
  status: string;
  raised_by: UUID;
  raised_by_name: string | null;
  assigned_staff_id: UUID | null;
  vendor_id: UUID | null;
  maintenance_task_id: UUID | null;
  resolution: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  property_label: string | null;
  task_number: string | null;
  task_status: string | null;
  created_at: string;
  comments: { id: UUID; author_name: string | null; body: string; internal: boolean; created_at: string }[] | null;
}

export interface MediaItem {
  id: UUID;
  entity_type: string;
  evidence_type: string | null;
  content_type: string;
  original_filename: string | null;
  sha256: string | null;
  status: string;
  url: string | null;
  thumbnail_url: string | null;
  uploaded_at: string | null;
  captured_at: string | null;
  legal_hold: boolean;
}

export interface Inspection {
  id: UUID;
  number: string;
  property_id: UUID;
  inspector_id: UUID | null;
  inspector_name: string | null;
  property_label: string | null;
  is_property_watch: boolean;
  status: string;
  scheduled_for: string | null;
  started_at: string | null;
  completed_at: string | null;
  overall_condition: string | null;
  findings: string | null;
  items: { id: UUID; position: number; point: string; condition: string | null; notes: string | null; follow_up_task_id: UUID | null }[];
  media: MediaItem[] | null;
  created_at: string;
}

export interface Asset {
  id: UUID;
  code: string;
  qr_code: string;
  nfc_id: string | null;
  name: string;
  category: string;
  property_id: UUID | null;
  location: string | null;
  installed_on: string | null;
  vendor_id: UUID | null;
  warranty_until: string | null;
  condition: string;
  service_interval_days: number | null;
  next_service_due: string | null;
  notes: string | null;
}

export interface Vendor {
  id: UUID;
  name: string;
  contact_person: string | null;
  phone: string | null;
  email: string | null;
  service_categories: string[];
  address: string | null;
  is_active: boolean;
  notes: string | null;
}

export interface Staff {
  id: UUID;
  user_id: UUID;
  full_name: string | null;
  role: string | null;
  phone: string | null;
  employee_code: string | null;
  designation: string | null;
  skills: string[];
  shift_name: string | null;
  shift_start: string | null;
  shift_end: string | null;
  is_active: boolean;
}

export interface Visitor {
  id: UUID;
  name: string;
  phone: string | null;
  purpose: string;
  property_id: UUID | null;
  property_label: string | null;
  host_name: string | null;
  vehicle_number: string | null;
  status: string;
  pre_approved: boolean;
  entry_at: string | null;
  exit_at: string | null;
  created_at: string;
}

export interface Vehicle {
  id: UUID;
  number: string;
  property_id: UUID | null;
  owner_name: string | null;
  vehicle_type: string;
  make_model: string | null;
}

export interface VehicleLog {
  id: UUID;
  vehicle_number: string;
  is_visitor: boolean;
  direction: string;
  at: string;
  notes: string | null;
}

export interface PatrolRoute {
  id: UUID;
  name: string;
  description: string | null;
  is_active: boolean;
  checkpoints: { id: UUID; name: string; position: number; qr_code: string; nfc_id: string | null }[];
}

export interface PatrolRun {
  id: UUID;
  route_id: UUID;
  route_name: string | null;
  guard_name: string | null;
  started_at: string;
  completed_at: string | null;
  status: string;
  notes: string | null;
  checkpoints_total: number;
  scans: { id: UUID; checkpoint_id: UUID; scanned_at: string; method: string; exception: string | null }[];
}

export interface Incident {
  id: UUID;
  number: string;
  title: string;
  description: string | null;
  category: string;
  severity: string;
  status: string;
  property_id: UUID | null;
  location: string | null;
  latitude: number | null;
  longitude: number | null;
  occurred_at: string;
  reported_by_name: string | null;
  resolution: string | null;
  sos_id: UUID | null;
  updates: { id: UUID; author_name: string | null; body: string; status_change: string | null; created_at: string }[] | null;
}

export interface Sos {
  id: UUID;
  raised_by_name: string | null;
  property_id: UUID | null;
  latitude: number | null;
  longitude: number | null;
  message: string | null;
  status: string;
  escalation_level: number;
  incident_id: UUID | null;
  created_at: string;
}

export interface Invoice {
  id: UUID;
  number: string;
  property_id: UUID;
  property_label: string | null;
  description: string;
  period_start: string | null;
  period_end: string | null;
  amount: number;
  amount_paid: number;
  due_date: string;
  status: string;
  overdue: boolean;
}

export interface Payment {
  id: UUID;
  invoice_id: UUID;
  amount: number;
  method: string;
  status: string;
  receipt_number: string | null;
  paid_at: string | null;
  provider_order_id: string | null;
  reference: string | null;
  created_at: string;
  checkout: { provider: string; order_id: string; amount_paise: number; note: string } | null;
}

export interface Plan {
  id: UUID;
  name: string;
  basis: string;
  rate: number;
  frequency_months: number;
  due_days: number;
  is_active: boolean;
}

export interface Notice {
  id: UUID;
  kind: string;
  title: string;
  body: string;
  audience: string;
  channels: string[];
  pinned: boolean;
  published_at: string;
  ends_at: string | null;
}

export interface Notification {
  id: UUID;
  kind: string;
  title: string;
  body: string | null;
  entity_type: string | null;
  entity_id: UUID | null;
  read_at: string | null;
  created_at: string;
}

export interface AuditEntry {
  id: UUID;
  actor_name: string | null;
  actor_role: string | null;
  action: string;
  entity_type: string;
  entity_id: UUID | null;
  timestamp: string;
  old_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  ip: string | null;
}

export interface SearchHit {
  type: string;
  id: UUID;
  number: string | null;
  title: string;
  status: string | null;
  category: string | null;
  property_label: string | null;
  date: string | null;
}

export interface Meta {
  task_categories: string[];
  task_statuses: string[];
  priorities: string[];
  evidence_types: string[];
  requirement_keys: string[];
  inspection_points: string[];
  asset_categories: string[];
  complaint_categories: string[];
  exception_reasons: string[];
  ticket_statuses: string[];
  ticket_priorities: string[];
  ticket_reject_reasons: string[];
}

export interface Tenant {
  id: UUID;
  name: string;
  slug: string;
  city: string;
  status: string;
  plan: string;
  modules: string[];
  settings: Record<string, unknown>;
  contact_email: string | null;
}

// ------------------------------------------------------------------ customer tickets

export interface TicketCategory {
  id: UUID;
  code: string;
  name: string;
  subcategories: string[];
  default_priority: string;
  task_category: string;
  preferred_vendor_type: string | null;
  response_sla_minutes: number | null;
  resolution_sla_minutes: number | null;
  customer_sets_priority: boolean;
  is_active: boolean;
  position: number;
  effective_response_minutes: number | null;
  effective_resolution_minutes: number | null;
}

export interface TicketSummary {
  id: UUID;
  number: string;
  title: string;
  category_id: UUID;
  category_code: string | null;
  category_name: string | null;
  subcategory: string | null;
  priority: string;
  status: string;
  source: string;
  property_id: UUID | null;
  property_label: string | null;
  customer_id: UUID;
  customer_name: string | null;
  assigned_to_type: "staff" | "vendor" | null;
  assigned_to_id: UUID | null;
  assignee_name: string | null;
  maintenance_task_id: UUID | null;
  due_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  reopen_count: number;
  rating: number | null;
  sla_state: "on_track" | "at_risk" | "breached" | "met" | null;
  created_at: string;
  updated_at: string;
}

export interface TicketSla {
  response_due_at: string;
  resolution_due_at: string;
  first_response_at: string | null;
  resolved_at: string | null;
  response_breached: boolean;
  resolution_breached: boolean;
  escalation_level: number;
  state: string | null;
}

export interface TicketComment {
  id: UUID;
  author_id: UUID | null;
  author_name: string | null;
  author_role: string | null;
  comment_type: string;
  visibility: string;
  message: string;
  created_at: string;
}

export interface TicketAttachment {
  id: UUID;
  media_id: UUID;
  source: "ticket" | "work";
  evidence_type: string;
  caption: string | null;
  uploaded_by_name: string | null;
  uploaded_at: string | null;
  content_type: string | null;
  filename: string | null;
  sha256: string | null;
  url: string | null;
  thumbnail_url: string | null;
}

export interface TicketTimelineItem {
  at: string;
  kind: string;
  title: string;
  detail: string | null;
  actor_name: string | null;
  status: string | null;
}

export interface WorkOrder {
  id: UUID;
  number: string;
  status: string;
  category: string;
  assignee_name: string | null;
  rework_count: number;
  due_at: string | null;
  completed_at: string | null;
  approved_at: string | null;
  missing: string[];
  pending_checklist: string[];
  checklist_total: number;
  checklist_done: number;
  evidence_count: number;
  materials_count: number;
}

export interface TicketDetail extends TicketSummary {
  description: string;
  location: string | null;
  preferred_time: string | null;
  contact_phone: string | null;
  created_by: UUID;
  first_response_at: string | null;
  assigned_at: string | null;
  accepted_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  verified_at: string | null;
  reopened_at: string | null;
  rework_count: number;
  resolution: string | null;
  feedback: string | null;
  feedback_at: string | null;
  customer_confirmation: string | null;
  customer_phone: string | null;
  assignee_phone: string | null;
  sla: TicketSla | null;
  work_order: WorkOrder | null;
  work_orders: WorkOrder[];
  comments: TicketComment[];
  attachments: TicketAttachment[];
  timeline: TicketTimelineItem[];
  allowed_actions: string[];
  comment_visibilities: string[];
  reopen_until: string | null;
}

export interface TicketDashboard {
  by_status: Record<string, number>;
  kpis: Record<"open" | "in_progress" | "sla_at_risk" | "resolved_today" | "closed_today" | "sla_breached", number>;
  buckets?: Record<string, number>;
  sections?: Record<string, number>;
  rejected?: { ticket_id: UUID; number: string | null; title: string | null; rejected_at: string; reason: string | null }[];
  tabs?: Record<string, number>;
}
