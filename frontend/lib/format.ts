const IST: Intl.DateTimeFormatOptions = { timeZone: "Asia/Kolkata" };

export function fmtDateTime(v?: string | null) {
  if (!v) return "—";
  return new Date(v).toLocaleString("en-IN", { ...IST, day: "2-digit", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
}

export function fmtDate(v?: string | null) {
  if (!v) return "—";
  const d = v.length === 10 ? new Date(`${v}T00:00:00+05:30`) : new Date(v);
  return d.toLocaleDateString("en-IN", { ...IST, day: "2-digit", month: "short", year: "numeric" });
}

export function fmtTime(v?: string | null) {
  if (!v) return "—";
  return new Date(v).toLocaleTimeString("en-IN", { ...IST, hour: "numeric", minute: "2-digit" });
}

export function ago(v?: string | null) {
  if (!v) return "";
  const s = (Date.now() - new Date(v).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export const inr = (n?: number | null) =>
  n == null ? "—" : `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;

export const label = (v?: string | null) => (v ? v.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : "—");

export const roleLabel: Record<string, string> = {
  resident: "Resident",
  guard: "Guard",
  staff: "Maintenance Staff",
  supervisor: "Supervisor",
  vendor: "Vendor",
  layout_admin: "Layout Admin",
  super_admin: "Platform Super Admin",
};

/** Map a status to a badge tone. */
export function tone(status?: string | null): "green" | "amber" | "red" | "blue" | "grey" {
  switch (status) {
    case "approved":
    case "closed":
    case "resolved":
    case "paid":
    case "completed":
    case "synced":
    case "good":
    case "ready":
    case "exited":
    case "satisfied":
    case "accepted":
    case "met":
    case "on_track":
      return "green";
    case "rework_required":
    case "attention":
    case "partial":
    case "pending_approval":
    case "acknowledged":
    case "investigating":
    case "excepted":
    case "retry":
    case "incomplete":
    case "pending":
    case "verification":
    case "work_completed":
    case "waiting_for_customer":
    case "on_hold":
    case "at_risk":
      return "amber";
    case "issue":
    case "failed":
    case "unpaid":
    case "open":
    case "active":
    case "denied":
    case "missing":
    case "conflict":
    case "critical":
    case "high":
    case "urgent":
    case "cancelled":
    case "reopened":
    case "rejected":
    case "breached":
      return "red";
    case "assigned":
    case "started":
    case "in_progress":
    case "scheduled":
    case "inside":
    case "syncing":
    case "queued":
    case "under_review":
      return "blue";
    default:
      return "grey";
  }
}

/** Minutes as a short duration: 15 min, 4 h, 2 d. */
export function minutes(m?: number | null) {
  if (m == null) return "—";
  if (m < 60) return `${m} min`;
  if (m < 60 * 24 || m % (60 * 24)) return `${+(m / 60).toFixed(1)} h`;
  return `${m / 60 / 24} d`;
}

/** Time left until (or past) a deadline, e.g. "in 3 h" / "5 h overdue". */
export function until(v?: string | null) {
  if (!v) return "—";
  const s = (new Date(v).getTime() - Date.now()) / 1000;
  const a = Math.abs(s);
  const t = a < 3600 ? `${Math.max(1, Math.round(a / 60))} min` : a < 86400 ? `${Math.round(a / 3600)} h` : `${Math.round(a / 86400)} d`;
  return s >= 0 ? `in ${t}` : `${t} overdue`;
}
