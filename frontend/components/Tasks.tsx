"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Dialog, Empty, ErrorBox, Field, Loading, Pager, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import type { Page, TaskDetail, TaskSummary } from "@/lib/types";

export function TaskCard({ t }: { t: TaskSummary }) {
  return (
    <Link href={`/maintenance/${t.id}`} className="task-card">
      <div className="row between">
        <b>{t.title}</b>
        <Badge status={t.status} text={t.status === "completed" ? "Awaiting review" : undefined} />
      </div>
      <div className="meta">
        <span className="mono">{t.number}</span>
        <span>{label(t.category)}</span>
        {t.property_label ? <span>{t.property_label}</span> : null}
        {t.due_at ? <span>Due {fmtDateTime(t.due_at)}</span> : null}
        {t.overdue ? <Badge status="urgent" text="Overdue" /> : null}
        {t.priority === "high" || t.priority === "urgent" ? <Badge status={t.priority} /> : null}
        {t.rework_count ? <Badge status="rework_required" text={`Rework ×${t.rework_count}`} /> : null}
      </div>
    </Link>
  );
}

export function TaskTable({ query, empty = "No tasks" }: { query: Record<string, string | number | boolean | string[] | undefined>; empty?: string }) {
  const router = useRouter();
  const [offset, setOffset] = useState(0);
  const { data, error, loading } = useApi<Page<TaskSummary>>("/maintenance", { ...query, limit: 50, offset });
  return (
    <>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data && !data.items.length ? (
        <div className="card">
          <Empty title={empty} />
        </div>
      ) : null}
      {data?.items.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Record</th>
                <th>Task</th>
                <th>Property / location</th>
                <th>Assigned</th>
                <th>Due</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((t) => (
                <tr key={t.id} className="clickable" onClick={() => router.push(`/maintenance/${t.id}`)}>
                  <td className="mono">{t.number}</td>
                  <td>
                    <Link href={`/maintenance/${t.id}`} onClick={(e) => e.stopPropagation()}>
                      <b>{t.title}</b>
                    </Link>
                    <div className="small muted">{label(t.category)}</div>
                  </td>
                  <td>{t.property_label || "—"}</td>
                  <td>{[t.assignee_name, t.vendor_name].filter(Boolean).join(" / ") || <span className="muted">Unassigned</span>}</td>
                  <td>
                    {fmtDate(t.due_at)} {t.overdue ? <Badge status="urgent" text="Overdue" /> : null}
                  </td>
                  <td>
                    <Badge status={t.status} text={t.status === "completed" ? "Awaiting review" : undefined} />
                    {t.rework_count ? <div className="small muted">Rework ×{t.rework_count}</div> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {data ? <Pager total={data.total} limit={data.limit} offset={offset} onChange={setOffset} /> : null}
    </>
  );
}

export function NewTaskDialog({ open, onClose, preset }: { open: boolean; onClose: () => void; preset?: Partial<Record<string, string>> }) {
  const { meta } = useAuth();
  const lookups = useLookups();
  const router = useRouter();
  const act = useAction();
  const [f, setF] = useState<Record<string, string>>({ category: "cleaning", priority: "medium", ...preset });
  const set = (k: string, v: string) => setF((x) => ({ ...x, [k]: v }));
  return (
    <Dialog title="New maintenance task" open={open} onClose={onClose}>
      <form
        className="form two"
        onSubmit={async (e) => {
          e.preventDefault();
          const body = {
            title: f.title,
            description: f.description || null,
            category: f.category,
            priority: f.priority,
            property_id: f.property_id || null,
            asset_id: f.asset_id || null,
            location_note: f.location_note || null,
            assigned_staff_id: f.staff || null,
            vendor_id: f.vendor || null,
            due_at: f.due ? new Date(f.due).toISOString() : null,
            checklist_items: f.checklist ? f.checklist.split("\n").map((s) => s.trim()).filter(Boolean) : null,
          };
          const t = await act.run(() => api<TaskDetail>("/maintenance", { body }));
          if (t) router.push(`/maintenance/${t.id}`);
        }}
      >
        <Field label="Title" full>
          <input required minLength={3} value={f.title || ""} onChange={(e) => set("title", e.target.value)} />
        </Field>
        <Field label="Category">
          <Select value={f.category} onChange={(v) => set("category", v)} options={meta?.task_categories ?? []} />
        </Field>
        <Field label="Priority">
          <Select value={f.priority} onChange={(v) => set("priority", v)} options={meta?.priorities ?? []} />
        </Field>
        <Field label="Property">
          <Select value={f.property_id || ""} onChange={(v) => set("property_id", v)} placeholder="Common area / none" options={lookups.properties.map((p) => ({ value: p.id, label: `Plot ${p.plot_number} (${p.code})` }))} />
        </Field>
        <Field label="Location note">
          <input placeholder="e.g. Park A, main gate" value={f.location_note || ""} onChange={(e) => set("location_note", e.target.value)} />
        </Field>
        <Field label="Assign staff">
          <Select value={f.staff || ""} onChange={(v) => set("staff", v)} placeholder="—" options={lookups.staff.map((u) => ({ value: u.id, label: u.full_name }))} />
        </Field>
        <Field label="or vendor">
          <Select value={f.vendor || ""} onChange={(v) => set("vendor", v)} placeholder="—" options={lookups.vendors.map((v) => ({ value: v.id, label: v.name }))} />
        </Field>
        <Field label="Due">
          <input type="datetime-local" value={f.due || ""} onChange={(e) => set("due", e.target.value)} />
        </Field>
        <Field label="Description" full>
          <textarea value={f.description || ""} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <Field label="Custom checklist (one item per line)" hint="Leave empty to use the category's checklist template" full>
          <textarea value={f.checklist || ""} onChange={(e) => set("checklist", e.target.value)} />
        </Field>
        <div className="full">
          <ErrorBox error={act.error} />
        </div>
        <div className="actions full">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" disabled={act.pending}>
            Create task
          </button>
        </div>
      </form>
    </Dialog>
  );
}
