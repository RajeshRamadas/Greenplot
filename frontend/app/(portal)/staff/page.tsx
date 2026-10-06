"use client";

import { useState } from "react";
import { Badge, Dialog, Empty, ErrorBox, Field, PageHead, Select, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtTime, roleLabel } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { invalidateLookups } from "@/lib/lookups";
import type { Staff, TaskSummary } from "@/lib/types";
import { announceInvite } from "@/lib/invites";

interface History {
  name: string;
  assigned: number;
  completed: number;
  rework: number;
  tasks: TaskSummary[];
}

export default function StaffPage() {
  const { can } = useAuth();
  const toast = useToast();
  const act = useAction();
  const staff = useApi<Staff[]>("/staff");
  const onDuty = useApi<{ user_id: string; name: string; role: string; since: string }[]>("/staff/on-duty");
  const [selected, setSelected] = useState<string | null>(null);
  const history = useApi<History>(selected ? `/staff/${selected}/work-history` : null);
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState<Staff | null>(null);
  const [f, setF] = useState<Record<string, string>>({ role: "staff" });

  return (
    <>
      <PageHead title="Staff" sub="Profiles, roles, shifts, attendance and work history.">
        {can("users.manage") ? (
          <button className="btn primary" onClick={() => setOpen(true)}>
            Add staff member
          </button>
        ) : null}
      </PageHead>
      <ErrorBox error={staff.error || act.error} />
      <div className="grid side">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Role</th>
                <th>Shift</th>
                <th>Skills</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {staff.data?.map((s) => (
                <tr key={s.id} className="clickable" onClick={() => setSelected(s.user_id)}>
                  <td>
                    <b>{s.full_name}</b>
                    <div className="small muted">
                      {s.designation} {s.phone ? `· ${s.phone}` : ""}
                    </div>
                  </td>
                  <td>{roleLabel[s.role || ""] || s.role}</td>
                  <td>{s.shift_name ? `${s.shift_name} ${s.shift_start ?? ""}–${s.shift_end ?? ""}` : "—"}</td>
                  <td className="small">{s.skills.join(", ") || "—"}</td>
                  <td>
                    <Badge status={s.is_active ? "good" : "cancelled"} text={s.is_active ? "Active" : "Inactive"} />
                    {can("staff.manage") ? (
                      <button className="btn small ghost" onClick={(e) => (e.stopPropagation(), setEdit(s), setF({ designation: s.designation || "", shift_name: s.shift_name || "", shift_start: s.shift_start || "", shift_end: s.shift_end || "", skills: s.skills.join(", ") }))}>
                        Edit
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <h2>On duty now</h2>
            {!onDuty.data?.length ? <Empty title="Nobody checked in" /> : null}
            {onDuty.data?.map((d) => (
              <div key={d.user_id} className="list-item">
                <span>
                  {d.name} <span className="small muted">· {roleLabel[d.role]}</span>
                </span>
                <span className="small muted">since {fmtTime(d.since)}</span>
              </div>
            ))}
          </div>
          {history.data ? (
            <div className="card">
              <h2>{history.data.name}</h2>
              <div className="stats" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
                <div className="stat">
                  <small>Assigned</small>
                  <b>{history.data.assigned}</b>
                </div>
                <div className="stat">
                  <small>Completed</small>
                  <b>{history.data.completed}</b>
                </div>
                <div className="stat">
                  <small>Rework</small>
                  <b>{history.data.rework}</b>
                </div>
              </div>
              {history.data.tasks.slice(0, 10).map((t) => (
                <a key={t.id} href={`/maintenance/${t.id}`} className="list-item">
                  <span className="small">{t.title}</span>
                  <Badge status={t.status} />
                </a>
              ))}
            </div>
          ) : null}
        </div>
      </div>
      <Dialog title="Add staff member" open={open} onClose={() => setOpen(false)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const r = await act.run(() => api<{ invite_url: string | null; sent_via?: string[] }>("/users", { body: { email: f.email, full_name: f.name, phone: f.phone || null, role: f.role } }));
            if (r) {
              setOpen(false);
              invalidateLookups();
              staff.reload();
              await announceInvite(r, toast, "Invite");
            }
          }}
        >
          <Field label="Full name" full>
            <input required value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field label="Email">
            <input required type="email" value={f.email || ""} onChange={(e) => setF({ ...f, email: e.target.value })} />
          </Field>
          <Field label="Phone">
            <input value={f.phone || ""} onChange={(e) => setF({ ...f, phone: e.target.value })} />
          </Field>
          <Field label="Role" full>
            <Select value={f.role} onChange={(v) => setF({ ...f, role: v })} options={[{ value: "staff", label: "Maintenance staff" }, { value: "guard", label: "Guard" }, { value: "supervisor", label: "Supervisor" }]} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary">Create & invite</button>
          </div>
        </form>
      </Dialog>
      <Dialog title={`Edit ${edit?.full_name}`} open={!!edit} onClose={() => setEdit(null)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!edit) return;
            const body = {
              designation: f.designation || null, shift_name: f.shift_name || null, shift_start: f.shift_start || null, shift_end: f.shift_end || null,
              skills: (f.skills || "").split(",").map((s) => s.trim()).filter(Boolean),
            };
            if (await act.run(() => api(`/staff/${edit.id}`, { method: "PATCH", body }))) {
              setEdit(null);
              staff.reload();
            }
          }}
        >
          <Field label="Designation" full>
            <input value={f.designation} onChange={(e) => setF({ ...f, designation: e.target.value })} />
          </Field>
          <Field label="Shift name">
            <input value={f.shift_name} onChange={(e) => setF({ ...f, shift_name: e.target.value })} />
          </Field>
          <Field label="Skills (comma separated)">
            <input value={f.skills} onChange={(e) => setF({ ...f, skills: e.target.value })} />
          </Field>
          <Field label="Shift start">
            <input type="time" value={f.shift_start} onChange={(e) => setF({ ...f, shift_start: e.target.value })} />
          </Field>
          <Field label="Shift end">
            <input type="time" value={f.shift_end} onChange={(e) => setF({ ...f, shift_end: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary">Save</button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
