"use client";

import { useState } from "react";
import { Badge, Dialog, ErrorBox, Field, PageHead, Select, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, label, minutes, roleLabel } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { invalidateLookups, useLookups } from "@/lib/lookups";
import { announceInvite } from "@/lib/invites";
import type { Page, Property, Tenant, TicketCategory, User, Vendor } from "@/lib/types";

const POLICY_FIELDS = ["before_photo", "after_photo", "checklist", "gps", "video", "materials", "invoice", "qr_scan", "supervisor_approval", "resident_acknowledgement"] as const;
type Policy = { category: string } & Record<(typeof POLICY_FIELDS)[number], boolean>;
type Template = { id: string; name: string; category: string; items: string[]; is_default: boolean };
type Schedule = { id: string; title: string; category: string; interval_days: number; next_run_on: string; is_active: boolean; assigned_staff_id: string | null };

function Policies() {
  const act = useAction();
  const { data, setData } = useApi<Policy[]>("/maintenance/policies");
  async function toggle(p: Policy, k: (typeof POLICY_FIELDS)[number]) {
    const r = await act.run(() => api<Policy>(`/maintenance/policies/${p.category}`, { method: "PATCH", body: { [k]: !p[k] } }));
    if (r && data) setData(data.map((x) => (x.category === r.category ? r : x)));
  }
  return (
    <div className="card">
      <h2>Evidence requirements by task type</h2>
      <p className="small muted" style={{ marginBottom: 12 }}>
        Required evidence must be captured, or an exception recorded for supervisor review, before work can be submitted.
      </p>
      <ErrorBox error={act.error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Task type</th>
              {POLICY_FIELDS.map((k) => (
                <th key={k} style={{ textAlign: "center" }}>
                  {label(k).replace("Resident Acknowledgement", "Resident ack")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data?.map((p) => (
              <tr key={p.category}>
                <td>
                  <b>{label(p.category)}</b>
                </td>
                {POLICY_FIELDS.map((k) => (
                  <td key={k} style={{ textAlign: "center" }}>
                    <input type="checkbox" checked={p[k]} onChange={() => toggle(p, k)} aria-label={`${label(p.category)} ${label(k)}`} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Templates() {
  const { meta } = useAuth();
  const act = useAction();
  const { data, reload } = useApi<Template[]>("/maintenance/templates");
  const [edit, setEdit] = useState<Template | "new" | null>(null);
  const [f, setF] = useState({ name: "", category: "cleaning", items: "" });
  return (
    <div className="card">
      <div className="card-head">
        <h2>Checklist templates</h2>
        <button className="btn small primary" onClick={() => (setF({ name: "", category: "cleaning", items: "" }), setEdit("new"))}>
          New template
        </button>
      </div>
      <div className="grid three">
        {data?.map((t) => (
          <div key={t.id} className="stat" style={{ cursor: "pointer" }} onClick={() => (setF({ name: t.name, category: t.category, items: t.items.join("\n") }), setEdit(t))}>
            <small>{label(t.category)}</small>
            <div style={{ fontWeight: 700 }}>{t.name}</div>
            <div className="small muted">{t.items.length} items</div>
          </div>
        ))}
      </div>
      <Dialog title={edit === "new" ? "New checklist template" : "Edit template"} open={!!edit} onClose={() => setEdit(null)}>
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            const body = { name: f.name, category: f.category, items: f.items.split("\n").map((s) => s.trim()).filter(Boolean), is_default: true };
            const ok = await act.run(() => (edit === "new" ? api("/maintenance/templates", { body }) : api(`/maintenance/templates/${(edit as Template).id}`, { method: "PUT", body })));
            if (ok) {
              setEdit(null);
              reload();
            }
          }}
        >
          <Field label="Name">
            <input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field label="Task type">
            <Select value={f.category} onChange={(v) => setF({ ...f, category: v })} options={meta?.task_categories ?? []} />
          </Field>
          <Field label="Items (one per line)">
            <textarea required rows={8} value={f.items} onChange={(e) => setF({ ...f, items: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            {edit !== "new" && edit ? (
              <button type="button" className="btn danger" onClick={() => act.run(() => api(`/maintenance/templates/${edit.id}`, { method: "DELETE" })).then(() => (setEdit(null), reload()))}>
                Delete
              </button>
            ) : null}
            <button className="btn primary">Save</button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

function Schedules() {
  const { meta } = useAuth();
  const lookups = useLookups();
  const toast = useToast();
  const act = useAction();
  const { data, reload } = useApi<Schedule[]>("/maintenance/schedules");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<Record<string, string>>({ category: "cleaning", interval_days: "7", next_run_on: new Date().toISOString().slice(0, 10) });
  return (
    <div className="card" id="schedules">
      <div className="card-head">
        <h2>Recurring schedules</h2>
        <div className="row">
          <button
            className="btn small"
            onClick={async () => {
              const r = await act.run(() => api<{ created: string[] }>("/maintenance/schedules/run", { method: "POST" }));
              if (r) toast(r.created.length ? `Created ${r.created.join(", ")}` : "Nothing due today");
            }}
          >
            Generate due tasks now
          </button>
          <button className="btn small primary" onClick={() => setOpen(true)}>
            New schedule
          </button>
        </div>
      </div>
      <ErrorBox error={act.error} />
      {data?.map((s) => (
        <div key={s.id} className="list-item">
          <div>
            <div className="title">{s.title}</div>
            <div className="small muted">
              {label(s.category)} · every {s.interval_days} days · next {fmtDate(s.next_run_on)}
            </div>
          </div>
          <div className="row">
            <Badge status={s.is_active ? "good" : "cancelled"} text={s.is_active ? "Active" : "Paused"} />
            <button className="btn small ghost" onClick={() => act.run(() => api(`/maintenance/schedules/${s.id}`, { method: "PATCH", body: { is_active: !s.is_active } })).then(reload)}>
              {s.is_active ? "Pause" : "Resume"}
            </button>
          </div>
        </div>
      ))}
      <Dialog title="New recurring schedule" open={open} onClose={() => setOpen(false)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const body = {
              title: f.title, category: f.category, interval_days: Number(f.interval_days), next_run_on: f.next_run_on, location_note: f.location || null,
              property_id: f.property || null, assigned_staff_id: f.staff || null, vendor_id: f.vendor || null,
            };
            if (await act.run(() => api("/maintenance/schedules", { body }))) {
              setOpen(false);
              reload();
            }
          }}
        >
          <Field label="Title" full>
            <input required value={f.title || ""} onChange={(e) => setF({ ...f, title: e.target.value })} />
          </Field>
          <Field label="Task type">
            <Select value={f.category} onChange={(v) => setF({ ...f, category: v })} options={meta?.task_categories ?? []} />
          </Field>
          <Field label="Every (days)">
            <input type="number" min="1" value={f.interval_days} onChange={(e) => setF({ ...f, interval_days: e.target.value })} />
          </Field>
          <Field label="First run">
            <input type="date" value={f.next_run_on} onChange={(e) => setF({ ...f, next_run_on: e.target.value })} />
          </Field>
          <Field label="Location">
            <input value={f.location || ""} onChange={(e) => setF({ ...f, location: e.target.value })} />
          </Field>
          <Field label="Property">
            <Select value={f.property || ""} onChange={(v) => setF({ ...f, property: v })} placeholder="Common area" options={lookups.properties.map((p) => ({ value: p.id, label: `Plot ${p.plot_number}` }))} />
          </Field>
          <Field label="Assign staff">
            <Select value={f.staff || ""} onChange={(v) => setF({ ...f, staff: v })} placeholder="—" options={lookups.staff.map((u) => ({ value: u.id, label: u.full_name }))} />
          </Field>
          <Field label="or vendor" full>
            <Select value={f.vendor || ""} onChange={(v) => setF({ ...f, vendor: v })} placeholder="—" options={lookups.vendors.map((v) => ({ value: v.id, label: v.name }))} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary">Create</button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

type Signup = {
  id: string;
  kind: "resident" | "vendor";
  full_name: string;
  email: string;
  phone: string;
  plot_number: string | null;
  relation: string | null;
  company_name: string | null;
  service_categories: string[];
  message: string | null;
  created_at: string;
  suggested_property_id: string | null;
  suggested_vendor_id: string | null;
};

/** Residents and vendors who asked to join from the registration page. */
function SignupRequests({ onApproved }: { onApproved: () => void }) {
  const act = useAction();
  const toast = useToast();
  const { data, reload } = useApi<Page<Signup>>("/signups");
  const props = useApi<Page<Property>>("/properties", { limit: 500 });
  const vendors = useApi<Page<Vendor>>("/vendors", { limit: 500 });
  const [choice, setChoice] = useState<Record<string, string>>({});
  if (!data?.items.length) return null;
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h2>Registration requests ({data.total})</h2>
      <p className="small muted">The applicant&apos;s mobile number was verified with a code. Approving creates the account and sends them a link to set a password.</p>
      <ErrorBox error={act.error} />
      <div className="list">
        {data.items.map((r) => {
          const pick = choice[r.id] ?? (r.kind === "resident" ? r.suggested_property_id : r.suggested_vendor_id) ?? "";
          return (
            <div key={r.id} className="list-item" style={{ alignItems: "flex-start", flexWrap: "wrap", gap: 10 }}>
              <div style={{ minWidth: 220, flex: 1 }}>
                <div className="title">
                  {r.full_name} <Badge status="pending" text={r.kind === "resident" ? `Resident · plot ${r.plot_number} (${r.relation})` : `Vendor · ${r.company_name}`} />
                </div>
                <div className="small muted">
                  {r.email} · {r.phone} · {fmtDate(r.created_at)}
                  {r.service_categories.length ? ` · ${r.service_categories.join(", ")}` : ""}
                </div>
                {r.message ? <div className="small">“{r.message}”</div> : null}
              </div>
              <div className="row" style={{ flexWrap: "wrap" }}>
                {r.kind === "resident" ? (
                  <Select
                    aria-label="Property"
                    value={pick}
                    onChange={(v) => setChoice({ ...choice, [r.id]: v })}
                    placeholder="Choose property…"
                    options={(props.data?.items ?? []).map((p) => ({ value: p.id, label: `Plot ${p.plot_number}${p.owner_name ? ` · ${p.owner_name}` : ""}` }))}
                    style={{ width: "auto" }}
                  />
                ) : (
                  <Select
                    aria-label="Vendor"
                    value={pick}
                    onChange={(v) => setChoice({ ...choice, [r.id]: v })}
                    placeholder={`New vendor: ${r.company_name}`}
                    options={(vendors.data?.items ?? []).map((v) => ({ value: v.id, label: v.name }))}
                    style={{ width: "auto" }}
                  />
                )}
                <button
                  className="btn small primary"
                  disabled={act.pending || (r.kind === "resident" && !pick)}
                  onClick={async () => {
                    const body = r.kind === "resident" ? { property_id: pick } : { vendor_id: pick || null };
                    const out = await act.run(() => api<{ invite_url: string; sent_via: string[] }>(`/signups/${r.id}/approve`, { body }));
                    if (out) {
                      await announceInvite(out, toast, `${r.full_name} approved. Invite`);
                      reload();
                      onApproved();
                    }
                  }}
                >
                  Approve
                </button>
                <button
                  className="btn small danger"
                  disabled={act.pending}
                  onClick={async () => {
                    const reason = prompt(`Why can't ${r.full_name} be approved? (they will be told)`);
                    if (reason && (await act.run(() => api(`/signups/${r.id}/reject`, { body: { reason } })))) reload();
                  }}
                >
                  Reject
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Users() {
  const act = useAction();
  const toast = useToast();
  const [role, setRole] = useState("");
  const { data, reload } = useApi<Page<User>>("/users", { role, limit: 500 });
  return (
    <>
    <SignupRequests onApproved={reload} />
    <div className="card">
      <div className="card-head">
        <h2>Users & roles</h2>
        <Select value={role} onChange={setRole} placeholder="All roles" options={Object.keys(roleLabel).filter((r) => r !== "super_admin").map((r) => ({ value: r, label: roleLabel[r] }))} style={{ width: "auto" }} />
      </div>
      <ErrorBox error={act.error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Role</th>
              <th>Last login</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((u) => (
              <tr key={u.id}>
                <td>
                  <b>{u.full_name}</b>
                  <div className="small muted">{u.email}</div>
                </td>
                <td>
                  <select
                    value={u.role}
                    onChange={async (e) => {
                      if (await act.run(() => api(`/users/${u.id}`, { method: "PATCH", body: { role: e.target.value } }))) {
                        invalidateLookups();
                        reload();
                      }
                    }}
                    style={{ width: "auto" }}
                  >
                    {Object.keys(roleLabel)
                      .filter((r) => r !== "super_admin")
                      .map((r) => (
                        <option key={r} value={r}>
                          {roleLabel[r]}
                        </option>
                      ))}
                  </select>
                </td>
                <td className="small">{u.last_login_at ? fmtDate(u.last_login_at) : "Never"}</td>
                <td>
                  <Badge status={u.is_active ? "good" : "cancelled"} text={u.is_active ? "Active" : "Disabled"} />
                  {u.locked_until && new Date(u.locked_until) > new Date() ? <Badge status="failed" text="Locked" /> : null}
                  {u.totp_enabled ? <Badge status="completed" text="2-step" /> : null}
                </td>
                <td className="row">
                  <button className="btn small ghost" onClick={() => act.run(() => api(`/users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } })).then(reload)}>
                    {u.is_active ? "Disable" : "Enable"}
                  </button>
                  {u.locked_until && new Date(u.locked_until) > new Date() ? (
                    <button className="btn small ghost" onClick={() => act.run(() => api(`/users/${u.id}/unlock`, { method: "POST" })).then(() => (reload(), toast("Unlocked")))}>
                      Unlock
                    </button>
                  ) : null}
                  {u.totp_enabled ? (
                    <button
                      className="btn small ghost"
                      onClick={() => {
                        if (confirm(`Turn off 2-step verification for ${u.full_name}? Use this if they lost their phone.`))
                          act.run(() => api(`/users/${u.id}/reset-2fa`, { method: "POST" })).then(() => (reload(), toast("2-step verification reset")));
                      }}
                    >
                      Reset 2-step
                    </button>
                  ) : null}
                  {!u.last_login_at ? (
                    <button
                      className="btn small ghost"
                      onClick={async () => {
                        const r = await act.run(() => api<{ invite_url: string; sent_via: string[] }>(`/users/${u.id}/reinvite`, { method: "POST" }));
                        await announceInvite(r, toast, "New invite");
                      }}
                    >
                      Re-invite
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
    </>
  );
}

function General() {
  const act = useAction();
  const toast = useToast();
  const { data, setData } = useApi<Tenant>("/settings");
  if (!data) return null;
  const s = data.settings as Record<string, unknown>;
  async function save(patch: Record<string, unknown>) {
    const r = await act.run(() => api<Tenant>("/settings", { method: "PATCH", body: patch }));
    if (r) {
      setData(r);
      toast("Saved");
    }
  }
  return (
    <div className="card">
      <h2>{data.name}</h2>
      <ErrorBox error={act.error} />
      <div className="form two">
        <Field label="Close tasks automatically on approval">
          <Select value={String(s.auto_close_on_approval ?? true)} onChange={(v) => save({ auto_close_on_approval: v === "true" })} options={[{ value: "true", label: "Yes" }, { value: "false", label: "No — close manually" }]} />
        </Field>
        <Field label="Residents can see evidence">
          <Select value={String(s.resident_evidence_visibility ?? "after_approval")} onChange={(v) => save({ resident_evidence_visibility: v })} options={[{ value: "after_approval", label: "After approval" }, { value: "all", label: "Always" }, { value: "none", label: "Never" }]} />
        </Field>
        <Field label="Routine media retention (days)" hint="Initial planning value: 90 days">
          <input type="number" min="7" defaultValue={Number(s.routine_media_retention_days ?? 90)} onBlur={(e) => save({ routine_media_retention_days: Number(e.target.value) })} />
        </Field>
        <Field label="Incident media retention (days)">
          <input type="number" min="30" defaultValue={Number(s.incident_media_retention_days ?? 1095)} onBlur={(e) => save({ incident_media_retention_days: Number(e.target.value) })} />
        </Field>
        <Field label="Escalate unanswered SOS after (minutes)">
          <input type="number" min="1" defaultValue={Number(s.sos_escalation_minutes ?? 3)} onBlur={(e) => save({ sos_escalation_minutes: Number(e.target.value) })} />
        </Field>
        <Field label="Background jobs">
          <button className="btn" type="button" onClick={async () => { const r = await act.run(() => api<Record<string, number>>("/jobs/run", { method: "POST" })); if (r) toast(Object.entries(r).map(([k, v]) => `${label(k)}: ${v}`).join(" · ")); }}>
            Run reminders, schedules & retention now
          </button>
        </Field>
      </div>
    </div>
  );
}

type TicketConfig = { sla: Record<string, { response_minutes: number; resolution_minutes: number }> } & Record<string, unknown>;

/** Ticket categories, SLA targets and customer policy (ticketing requirements §5, §15, §42). */
function Tickets() {
  const { meta } = useAuth();
  const act = useAction();
  const toast = useToast();
  const cats = useApi<TicketCategory[]>("/tickets/categories", { include_inactive: true });
  const cfg = useApi<TicketConfig>("/tickets/config");
  const [adding, setAdding] = useState(false);
  const [nc, setNc] = useState<Record<string, string>>({ default_priority: "medium", task_category: "repairs" });

  async function saveSettings(patch: Record<string, unknown>) {
    if (await act.run(() => api("/settings", { method: "PATCH", body: patch }))) {
      cfg.reload();
      toast("Saved");
    }
  }
  async function saveCat(c: TicketCategory, patch: Partial<TicketCategory>) {
    if (await act.run(() => api(`/tickets/categories/${c.id}`, { method: "PATCH", body: patch }))) {
      cats.reload();
      toast("Saved");
    }
  }
  const num = (v: string) => (v.trim() === "" ? null : Number(v));
  const slug = (v?: string) => (v || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 40);
  const c = cfg.data;
  return (
    <div className="stack" style={{ gap: 16 }}>
      <ErrorBox error={act.error} />
      {c ? (
        <div className="card">
          <h2>Service levels by priority</h2>
          <p className="small muted">Targets for the first response and for resolution. A category can set its own, below.</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Priority</th>
                  <th>Response (minutes)</th>
                  <th>Resolution (minutes)</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(c.sla).map(([p, v]) => (
                  <tr key={p}>
                    <td>
                      <Badge status={p} />
                    </td>
                    {(["response_minutes", "resolution_minutes"] as const).map((k) => (
                      <td key={k}>
                        <input
                          type="number"
                          min="1"
                          aria-label={`${p} ${k}`}
                          defaultValue={v[k]}
                          onBlur={(e) => Number(e.target.value) !== v[k] && saveSettings({ ticket_sla: { ...c.sla, [p]: { ...v, [k]: Number(e.target.value) } } })}
                          style={{ maxWidth: 120 }}
                        />{" "}
                        <span className="small muted">{minutes(v[k])}</span>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="divider" />
          <h2>Customer & vendor policy</h2>
          <div className="form two">
            <Field label="Highest priority a customer can choose">
              <Select value={String(c.ticket_customer_max_priority)} onChange={(v) => saveSettings({ ticket_customer_max_priority: v })} options={["low", "medium", "high", "critical"]} />
            </Field>
            <Field label="Customers can reopen closed tickets for (days)">
              <input type="number" min="0" defaultValue={Number(c.ticket_reopen_days)} onBlur={(e) => saveSettings({ ticket_reopen_days: Number(e.target.value) })} />
            </Field>
            <Field label="Close resolved tickets automatically after (days)" hint="0 = wait for the customer or the office">
              <input type="number" min="0" defaultValue={Number(c.ticket_auto_close_days)} onBlur={(e) => saveSettings({ ticket_auto_close_days: Number(e.target.value) })} />
            </Field>
            <Field label="Warn when this much of the SLA has passed (%)">
              <input type="number" min="10" max="99" defaultValue={Number(c.ticket_sla_at_risk_percent)} onBlur={(e) => saveSettings({ ticket_sla_at_risk_percent: Number(e.target.value) })} />
            </Field>
            <Field label="Re-escalate an unresolved breach every (hours)">
              <input type="number" min="1" defaultValue={Number(c.ticket_escalate_every_hours)} onBlur={(e) => saveSettings({ ticket_escalate_every_hours: Number(e.target.value) })} />
            </Field>
            <Field label="Vendors can message customers">
              <Select value={String(c.ticket_assignee_customer_chat)} onChange={(v) => saveSettings({ ticket_assignee_customer_chat: v === "true" })} options={[{ value: "true", label: "Yes" }, { value: "false", label: "No — through the office" }]} />
            </Field>
            <Field label="Vendors see the customer's phone number">
              <Select value={String(c.ticket_share_customer_contact)} onChange={(v) => saveSettings({ ticket_share_customer_contact: v === "true" })} options={[{ value: "false", label: "No" }, { value: "true", label: "Yes" }]} />
            </Field>
            <Field label="Customers see the vendor's phone number">
              <Select value={String(c.ticket_share_vendor_contact)} onChange={(v) => saveSettings({ ticket_share_vendor_contact: v === "true" })} options={[{ value: "false", label: "No" }, { value: "true", label: "Yes" }]} />
            </Field>
          </div>
        </div>
      ) : null}
      <div className="card">
        <div className="card-head">
          <h2>Ticket categories</h2>
          <button className="btn small" onClick={() => setAdding(true)}>
            Add category
          </button>
        </div>
        <p className="small muted">The work type decides the proof-of-work checklist and evidence rules (see the Evidence tab) for the vendor&apos;s job.</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Category</th>
                <th>Default priority</th>
                <th>Work type</th>
                <th>Response / resolution SLA (min)</th>
                <th>Customer picks priority</th>
                <th>Active</th>
              </tr>
            </thead>
            <tbody>
              {cats.data?.map((x) => (
                <tr key={x.id}>
                  <td>
                    <b>{x.name}</b>
                    <div className="small muted">{x.subcategories.join(", ") || "—"}</div>
                  </td>
                  <td>
                    <Select value={x.default_priority} onChange={(v) => saveCat(x, { default_priority: v })} options={["low", "medium", "high", "critical"]} aria-label={`${x.name} default priority`} />
                  </td>
                  <td>
                    <Select value={x.task_category} onChange={(v) => saveCat(x, { task_category: v })} options={meta?.task_categories ?? [x.task_category]} aria-label={`${x.name} work type`} />
                  </td>
                  <td>
                    <div className="row" style={{ flexWrap: "nowrap" }}>
                      <input type="number" min="1" placeholder={String(x.effective_response_minutes)} defaultValue={x.response_sla_minutes ?? ""} onBlur={(e) => num(e.target.value) !== x.response_sla_minutes && saveCat(x, { response_sla_minutes: num(e.target.value) })} style={{ width: 90 }} aria-label={`${x.name} response SLA`} />
                      <input type="number" min="1" placeholder={String(x.effective_resolution_minutes)} defaultValue={x.resolution_sla_minutes ?? ""} onBlur={(e) => num(e.target.value) !== x.resolution_sla_minutes && saveCat(x, { resolution_sla_minutes: num(e.target.value) })} style={{ width: 90 }} aria-label={`${x.name} resolution SLA`} />
                    </div>
                  </td>
                  <td>
                    <input type="checkbox" checked={x.customer_sets_priority} onChange={(e) => saveCat(x, { customer_sets_priority: e.target.checked })} aria-label={`${x.name}: customer picks priority`} />
                  </td>
                  <td>
                    <input type="checkbox" checked={x.is_active} onChange={(e) => saveCat(x, { is_active: e.target.checked })} aria-label={`${x.name} active`} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <Dialog title="Add ticket category" open={adding} onClose={() => setAdding(false)}>
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            const body = {
              code: nc.code ?? slug(nc.name),
              name: nc.name,
              default_priority: nc.default_priority,
              task_category: nc.task_category,
              subcategories: (nc.subs || "").split("\n").map((x) => x.trim()).filter(Boolean),
            };
            if (await act.run(() => api("/tickets/categories", { body }))) {
              setAdding(false);
              setNc({ default_priority: "medium", task_category: "repairs" });
              cats.reload();
            }
          }}
        >
          <Field label="Name">
            <input required value={nc.name || ""} onChange={(e) => setNc({ ...nc, name: e.target.value })} />
          </Field>
          <Field label="Code" hint="Lowercase letters, digits and underscores">
            <input required pattern="[a-z0-9_]{2,40}" value={nc.code ?? slug(nc.name)} onChange={(e) => setNc({ ...nc, code: e.target.value })} />
          </Field>
          <Field label="Default priority">
            <Select value={nc.default_priority} onChange={(v) => setNc({ ...nc, default_priority: v })} options={["low", "medium", "high", "critical"]} />
          </Field>
          <Field label="Work type">
            <Select value={nc.task_category} onChange={(v) => setNc({ ...nc, task_category: v })} options={meta?.task_categories ?? ["repairs"]} />
          </Field>
          <Field label="Issue types (one per line)">
            <textarea value={nc.subs || ""} onChange={(e) => setNc({ ...nc, subs: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            <button className="btn primary" disabled={act.pending}>
              Add
            </button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

type WaStatus = {
  provider: string;
  live: boolean;
  configured: boolean;
  webhook_secured: boolean;
  phone_number_id: string | null;
  template: string;
  template_language: string;
  business_number: string;
  opted_in_users: number;
  webhook_path: string;
  events: Record<string, string[]>;
  recent: { at: string; direction: string; user_name: string | null; phone: string; body: string | null; status: string; error: string | null; ticket_id: string | null }[];
};
const CHANNELS = ["push", "whatsapp", "sms", "email"] as const;
const CHANNEL_NAMES: Record<string, string> = { push: "Push", whatsapp: "WhatsApp", sms: "SMS", email: "Email" };

type SmsStatus = { provider: string; live: boolean; configured: boolean; sender: string | null; templates: Record<"otp" | "notify" | "link", boolean>; webhook_secured: boolean; webhook_path: string; var_max: number };

/** MSG91 SMS: DLT templates, delivery reports and a test send. */
function SmsCard() {
  const act = useAction();
  const toast = useToast();
  const { data } = useApi<SmsStatus>("/sms/status");
  const [phone, setPhone] = useState("");
  if (!data) return null;
  const names = { otp: "One-time codes (##otp##)", notify: "Notifications (##title## ##body##)", link: "Invites & links (##title## ##link##)" } as const;
  return (
    <div className="card">
      <div className="card-head">
        <h2>SMS (MSG91)</h2>
        <Badge status={data.live ? "completed" : "pending"} text={data.live ? "Live" : "Logging only"} />
      </div>
      {!data.live ? (
        <div className="alert warn" style={{ marginBottom: 12 }}>
          SMS is only logged. Set <span className="mono">GP_SMS_PROVIDER=msg91</span>, the MSG91 auth key and the three DLT template IDs (see the README) to send real SMS.
        </div>
      ) : null}
      <dl className="kv">
        <dt>Sender ID</dt>
        <dd className="mono">{data.sender || "From template"}</dd>
        {(Object.keys(names) as (keyof typeof names)[]).map((k) => (
          <span key={k} style={{ display: "contents" }}>
            <dt>{names[k]}</dt>
            <dd>
              <Badge status={data.templates[k] ? "completed" : "pending"} text={data.templates[k] ? "Template set" : "Not set"} />
            </dd>
          </span>
        ))}
        <dt>Delivery reports</dt>
        <dd>
          <span className="mono">{typeof window !== "undefined" ? window.location.origin : ""}{data.webhook_path}</span>{" "}
          {data.webhook_secured ? <Badge status="completed" text="Token set" /> : <Badge status="pending" text="No token" />}
        </dd>
      </dl>
      <p className="small muted">Text variables are trimmed to {data.var_max} characters to fit DLT rules; links are sent in full.</p>
      <div className="row" style={{ marginTop: 8 }}>
        <input type="tel" placeholder="Mobile (blank = your number)" value={phone} onChange={(e) => setPhone(e.target.value)} style={{ maxWidth: 240 }} aria-label="Test mobile number" />
        <button
          className="btn"
          disabled={act.pending}
          onClick={async () => {
            const r = await act.run(() => api<{ result: string }>("/sms/test", { body: { phone: phone || null } }));
            if (r) toast(r.result === "sent" ? "Test SMS sent" : `Not sent: ${r.result}`, r.result === "sent" ? "ok" : "error");
          }}
        >
          Send test SMS
        </button>
      </div>
      <ErrorBox error={act.error} />
    </div>
  );
}

/** WhatsApp channel status and which channels each notification uses (ticketing §18). */
function Notifications() {
  const act = useAction();
  const toast = useToast();
  const { data, reload } = useApi<WaStatus>("/whatsapp/status");
  if (!data) return null;
  async function toggle(kind: string, ch: string, on: boolean) {
    const next: Record<string, string[]> = {};
    for (const [k, v] of Object.entries(data!.events)) next[k] = v.filter((c) => c !== "in_app");
    next[kind] = on ? [...next[kind], ch] : next[kind].filter((c) => c !== ch);
    if (await act.run(() => api("/settings", { method: "PATCH", body: { notification_channels: next } }))) {
      reload();
      toast("Saved");
    }
  }
  async function test() {
    const r = await act.run(() => api<{ result: string }>("/whatsapp/test", { body: {} }));
    if (r) toast(r.result === "sent" ? "Test message sent to your WhatsApp" : `Not sent: ${label(r.result.replace(":", " — "))}`, r.result === "sent" ? "ok" : "error");
  }
  return (
    <div className="stack" style={{ gap: 16 }}>
      <ErrorBox error={act.error} />
      <div className="card">
        <div className="card-head">
          <h2>WhatsApp Business</h2>
          <Badge status={data.live ? "completed" : "pending"} text={data.live ? "Live" : "Logging only"} />
        </div>
        {!data.live ? (
          <div className="alert warn" style={{ marginBottom: 12 }}>
            Messages are only logged. To send real WhatsApp messages, set <span className="mono">GP_WHATSAPP_PROVIDER=meta</span> with the access token, phone number
            ID, app secret and verify token from Meta, and create the approved template described in the README.
          </div>
        ) : null}
        <dl className="kv">
          <dt>Provider</dt>
          <dd>{data.provider === "meta" ? "WhatsApp Cloud API (Meta)" : "Log only"}</dd>
          <dt>Phone number ID</dt>
          <dd className="mono">{data.phone_number_id || "—"}</dd>
          <dt>Template</dt>
          <dd>
            <span className="mono">{data.template}</span> ({data.template_language}) — used outside the 24-hour reply window
          </dd>
          <dt>Webhook</dt>
          <dd>
            <span className="mono">{typeof window !== "undefined" ? window.location.origin : ""}{data.webhook_path}</span>
            {data.webhook_secured ? <Badge status="completed" text="Signed" /> : <Badge status="pending" text="No app secret" />}
          </dd>
          <dt>Opted-in users</dt>
          <dd>{data.opted_in_users}</dd>
        </dl>
        <div className="row" style={{ marginTop: 12 }}>
          <button className="btn" disabled={act.pending} onClick={test}>
            Send me a test message
          </button>
          <span className="small muted">Turn on WhatsApp updates in your Profile first.</span>
        </div>
      </div>
      <SmsCard />
      <div className="card">
        <h2>Channels per notification</h2>
        <p className="small muted">In-app is always on. WhatsApp goes only to people who opted in; SMS needs a phone number.</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Notification</th>
                {CHANNELS.map((c) => (
                  <th key={c}>{CHANNEL_NAMES[c]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.events).map(([kind, chans]) => (
                <tr key={kind}>
                  <td>{label(kind)}</td>
                  {CHANNELS.map((c) => (
                    <td key={c}>
                      <input type="checkbox" aria-label={`${label(kind)} via ${CHANNEL_NAMES[c]}`} checked={chans.includes(c)} disabled={act.pending} onChange={(e) => toggle(kind, c, e.target.checked)} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="card">
        <h2>Recent WhatsApp conversations</h2>
        {!data.recent.length ? <p className="small muted">No messages yet. Residents&apos; replies to ticket updates appear here and on the ticket.</p> : null}
        <div className="list">
          {data.recent.map((m, i) => (
            <div key={i} className="list-item" style={{ alignItems: "flex-start" }}>
              <div style={{ minWidth: 0 }}>
                <div className="title">
                  {m.direction === "in" ? "From" : "To"} {m.user_name || m.phone}{" "}
                  {m.ticket_id ? (
                    <a href={`/tickets/${m.ticket_id}`} className="small">
                      ticket
                    </a>
                  ) : null}
                </div>
                <div className="small" style={{ whiteSpace: "pre-wrap" }}>
                  {m.body}
                </div>
                {m.error ? <div className="small muted">{m.error}</div> : null}
              </div>
              <div style={{ textAlign: "right" }}>
                <Badge status={["failed"].includes(m.status) ? "failed" : m.status === "ignored" ? "pending" : "completed"} text={label(m.status)} />
                <div className="small muted">{fmtDate(m.at)}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const [tab, setTab] = useState("general");
  return (
    <>
      <PageHead title="Settings" sub="Layout configuration, service tickets, evidence rules, checklists, schedules and access." />
      <div className="tabs">
        {["general", "tickets", "notifications", "evidence", "checklists", "schedules", "users"].map((t) => (
          <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
            {label(t)}
          </button>
        ))}
      </div>
      {tab === "general" ? <General /> : null}
      {tab === "tickets" ? <Tickets /> : null}
      {tab === "notifications" ? <Notifications /> : null}
      {tab === "evidence" ? <Policies /> : null}
      {tab === "checklists" ? <Templates /> : null}
      {tab === "schedules" ? <Schedules /> : null}
      {tab === "users" ? <Users /> : null}
    </>
  );
}
