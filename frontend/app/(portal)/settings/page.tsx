"use client";

import { useState } from "react";
import { Badge, Dialog, ErrorBox, Field, PageHead, Select, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, label, roleLabel } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { invalidateLookups, useLookups } from "@/lib/lookups";
import type { Page, Tenant, User } from "@/lib/types";

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

function Users() {
  const act = useAction();
  const toast = useToast();
  const [role, setRole] = useState("");
  const { data, reload } = useApi<Page<User>>("/users", { role, limit: 500 });
  return (
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
                </td>
                <td className="row">
                  <button className="btn small ghost" onClick={() => act.run(() => api(`/users/${u.id}`, { method: "PATCH", body: { is_active: !u.is_active } })).then(reload)}>
                    {u.is_active ? "Disable" : "Enable"}
                  </button>
                  {!u.last_login_at ? (
                    <button
                      className="btn small ghost"
                      onClick={async () => {
                        const r = await act.run(() => api<{ invite_url: string }>(`/users/${u.id}/reinvite`, { method: "POST" }));
                        if (r) {
                          await navigator.clipboard?.writeText(r.invite_url).catch(() => {});
                          toast("New invite link copied");
                        }
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

export default function SettingsPage() {
  const [tab, setTab] = useState("general");
  return (
    <>
      <PageHead title="Settings" sub="Layout configuration, evidence rules, checklists, schedules and access." />
      <div className="tabs">
        {["general", "evidence", "checklists", "schedules", "users"].map((t) => (
          <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
            {label(t)}
          </button>
        ))}
      </div>
      {tab === "general" ? <General /> : null}
      {tab === "evidence" ? <Policies /> : null}
      {tab === "checklists" ? <Templates /> : null}
      {tab === "schedules" ? <Schedules /> : null}
      {tab === "users" ? <Users /> : null}
    </>
  );
}
