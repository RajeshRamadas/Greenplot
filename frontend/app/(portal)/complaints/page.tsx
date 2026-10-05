"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { CaptureButton } from "@/components/Capture";
import { Badge, Dialog, Empty, ErrorBox, Field, Loading, PageHead, Pager, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, label } from "@/lib/format";
import { useAction, useApi, useOnline } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import { enqueue } from "@/lib/offline";
import type { Complaint, Page } from "@/lib/types";

export default function ComplaintsPage() {
  const { can, meta, me } = useAuth();
  const router = useRouter();
  const lookups = useLookups();
  const online = useOnline();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState(false);
  const [created, setCreated] = useState<Complaint | null>(null);
  const [f, setF] = useState<Record<string, string>>({ category: "other", priority: "medium" });
  const act = useAction();
  const { data, error, loading, reload } = useApi<Page<Complaint>>("/complaints", { status, q, limit: 50, offset });

  return (
    <>
      <PageHead title="Complaints & service requests" sub="OPEN → ASSIGNED → IN PROGRESS → RESOLVED → CLOSED">
        {can("complaints.create") ? (
          <button className="btn primary" onClick={() => (setOpen(true), setCreated(null))}>
            Raise complaint
          </button>
        ) : null}
      </PageHead>
      <div className="filters">
        <input type="search" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select value={status} onChange={setStatus} placeholder="Any status" options={["open", "assigned", "in_progress", "resolved", "closed"]} />
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data && !data.items.length ? (
        <div className="card">
          <Empty title="No complaints" />
        </div>
      ) : null}
      {data?.items.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Complaint</th>
                <th>Title</th>
                <th>Property</th>
                <th>Raised</th>
                <th>Linked job</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr key={c.id} className="clickable" onClick={() => router.push(`/complaints/${c.id}`)}>
                  <td className="mono">{c.number}</td>
                  <td>
                    <b>{c.title}</b>
                    <div className="small muted">
                      {label(c.category)} · {label(c.priority)}
                    </div>
                  </td>
                  <td>{c.property_label || "—"}</td>
                  <td>
                    {fmtDate(c.created_at)}
                    <div className="small muted">{c.raised_by_name}</div>
                  </td>
                  <td>{c.task_number ? <span className="mono">{c.task_number}</span> : "—"}</td>
                  <td>
                    <Badge status={c.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {data ? <Pager total={data.total} limit={data.limit} offset={offset} onChange={setOffset} /> : null}

      <Dialog title={created ? "Complaint raised" : "Raise a complaint"} open={open} onClose={() => (setOpen(false), reload())}>
        {created ? (
          <div className="stack">
            <div className="alert ok">
              {created.number} raised. You can add photos or video of the problem.
            </div>
            <CaptureButton entityType="complaint" entityId={created.id} text="Add photo / video" />
            <div className="actions">
              <button className="btn primary" onClick={() => router.push(`/complaints/${created.id}`)}>
                View complaint
              </button>
            </div>
          </div>
        ) : (
          <form
            className="form two"
            onSubmit={async (e) => {
              e.preventDefault();
              const body = { title: f.title, description: f.description || null, category: f.category, priority: f.priority, property_id: f.property_id || null };
              if (!online && me) {
                await enqueue(me.id, "complaint", "create", body, `Complaint: ${f.title}`);
                setOpen(false);
                return;
              }
              const c = await act.run(() => api<Complaint>("/complaints", { body }));
              if (c) setCreated(c);
            }}
          >
            <Field label="What's wrong?" full>
              <input required minLength={3} value={f.title || ""} onChange={(e) => setF({ ...f, title: e.target.value })} />
            </Field>
            <Field label="Category">
              <Select value={f.category} onChange={(v) => setF({ ...f, category: v })} options={meta?.complaint_categories ?? ["other"]} />
            </Field>
            <Field label="Priority">
              <Select value={f.priority} onChange={(v) => setF({ ...f, priority: v })} options={meta?.priorities ?? ["medium"]} />
            </Field>
            {lookups.properties.length ? (
              <Field label="Property" full>
                <Select
                  value={f.property_id || ""}
                  onChange={(v) => setF({ ...f, property_id: v })}
                  placeholder={me?.role === "resident" ? "My property" : "Common area"}
                  options={lookups.properties.map((p) => ({ value: p.id, label: `Plot ${p.plot_number}` }))}
                />
              </Field>
            ) : null}
            <Field label="Details" full>
              <textarea value={f.description || ""} onChange={(e) => setF({ ...f, description: e.target.value })} />
            </Field>
            <div className="full">
              <ErrorBox error={act.error} />
            </div>
            <div className="actions full">
              <button className="btn primary" disabled={act.pending}>
                Submit
              </button>
            </div>
          </form>
        )}
      </Dialog>
    </>
  );
}
