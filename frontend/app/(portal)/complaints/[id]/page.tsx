"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { CaptureButton } from "@/components/Capture";
import { MediaGallery } from "@/components/MediaGallery";
import { Badge, Dialog, ErrorBox, Field, Loading, PageHead, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import type { Complaint } from "@/lib/types";

export default function ComplaintPage() {
  const { id } = useParams<{ id: string }>();
  const { me, can, meta } = useAuth();
  const lookups = useLookups();
  const { data: c, error, loading, setData, reload } = useApi<Complaint>(`/complaints/${id}`);
  const act = useAction();
  const [dialog, setDialog] = useState<null | "assign" | "status">(null);
  const [f, setF] = useState<Record<string, string>>({});
  const [comment, setComment] = useState("");
  const [internal, setInternal] = useState(false);
  const [mediaKey, setMediaKey] = useState(0);

  if (loading && !c) return <Loading />;
  if (!c || !me) return <ErrorBox error={error || "Not found"} />;
  const manage = can("complaints.manage");
  const isRaiser = c.raised_by === me.id;

  async function setStatus(status: string, resolution?: string) {
    const r = await act.run(() => api<Complaint>(`/complaints/${c!.id}/status`, { body: { status, resolution: resolution || null } }));
    if (r) {
      setData(r);
      setDialog(null);
    }
  }

  return (
    <>
      <PageHead title={c.title} sub={<><span className="mono">{c.number}</span> · {label(c.category)} · {c.property_label || "Common area"}</>}>
        <Badge status={c.status} />
      </PageHead>
      <ErrorBox error={act.error} />
      <div className="grid side">
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <h2>Details</h2>
            <p style={{ whiteSpace: "pre-wrap" }}>{c.description || <span className="muted">No description.</span>}</p>
            <div className="divider" />
            <h3 style={{ marginBottom: 8 }}>Photos & video</h3>
            <MediaGallery entityType="complaint" entityId={c.id} refreshKey={mediaKey} />
            {isRaiser || manage ? (
              <div style={{ marginTop: 10, maxWidth: 260 }}>
                <CaptureButton entityType="complaint" entityId={c.id} text="Add photo / video" onDone={() => setMediaKey((k) => k + 1)} />
              </div>
            ) : null}
          </div>
          <div className="card">
            <h2>Conversation</h2>
            <ul className="timeline">
              <li>
                <b>{c.raised_by_name}</b> raised this complaint
                <small>{fmtDateTime(c.created_at)}</small>
              </li>
              {c.comments?.map((x) => (
                <li key={x.id}>
                  <b>{x.author_name}</b> {x.internal ? <Badge status="pending" text="Internal" /> : null}
                  <div>{x.body}</div>
                  <small>{fmtDateTime(x.created_at)}</small>
                </li>
              ))}
              {c.resolution ? (
                <li>
                  <b>Resolution</b>
                  <div>{c.resolution}</div>
                  <small>{fmtDateTime(c.resolved_at)}</small>
                </li>
              ) : null}
            </ul>
            <form
              className="stack"
              onSubmit={async (e) => {
                e.preventDefault();
                if (!comment.trim()) return;
                if (await act.run(() => api(`/complaints/${c.id}/comments`, { body: { body: comment, internal } }))) {
                  setComment("");
                  reload();
                }
              }}
            >
              <textarea placeholder="Write a comment" value={comment} onChange={(e) => setComment(e.target.value)} />
              <div className="row between">
                {manage ? (
                  <label className="row small">
                    <input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Internal note (hidden from resident)
                  </label>
                ) : (
                  <span />
                )}
                <button className="btn">Post</button>
              </div>
            </form>
          </div>
        </div>
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <h2>Status</h2>
            <dl className="kv" style={{ gridTemplateColumns: "100px 1fr" }}>
              <dt>Priority</dt>
              <dd>{label(c.priority)}</dd>
              <dt>Raised</dt>
              <dd>{fmtDateTime(c.created_at)}</dd>
              <dt>Resolved</dt>
              <dd>{fmtDateTime(c.resolved_at)}</dd>
              <dt>Closed</dt>
              <dd>{fmtDateTime(c.closed_at)}</dd>
              <dt>Maintenance</dt>
              <dd>
                {c.maintenance_task_id ? (
                  <Link href={`/maintenance/${c.maintenance_task_id}`}>
                    {c.task_number} · {label(c.task_status)}
                  </Link>
                ) : (
                  "—"
                )}
              </dd>
            </dl>
            <div className="row" style={{ marginTop: 14 }}>
              {manage && !["resolved", "closed"].includes(c.status) ? (
                <button className="btn primary" onClick={() => setDialog("assign")}>
                  {c.maintenance_task_id ? "Reassign" : "Assign & create job"}
                </button>
              ) : null}
              {manage ? (
                <button className="btn" onClick={() => setDialog("status")}>
                  Change status
                </button>
              ) : null}
              {isRaiser && c.status === "resolved" ? (
                <>
                  <button className="btn primary" onClick={() => setStatus("closed")}>
                    Confirm & close
                  </button>
                  <button className="btn" onClick={() => setStatus("in_progress", "Issue persists")}>
                    Still a problem
                  </button>
                </>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      <Dialog title="Assign complaint" open={dialog === "assign"} onClose={() => setDialog(null)}>
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            const r = await act.run(() =>
              api<Complaint>(`/complaints/${c.id}/assign`, {
                body: { assigned_staff_id: f.staff || null, vendor_id: f.vendor || null, task_category: f.category || null, create_task: true, due_at: f.due ? new Date(f.due).toISOString() : null },
              }),
            );
            if (r) {
              setData(r);
              setDialog(null);
            }
          }}
        >
          <p className="small muted">A linked maintenance job is created so the fix carries full proof of work.</p>
          <Field label="Staff member">
            <Select value={f.staff || ""} onChange={(v) => setF({ ...f, staff: v })} placeholder="—" options={lookups.staff.map((u) => ({ value: u.id, label: u.full_name }))} />
          </Field>
          <Field label="or vendor">
            <Select value={f.vendor || ""} onChange={(v) => setF({ ...f, vendor: v })} placeholder="—" options={lookups.vendors.map((v) => ({ value: v.id, label: v.name }))} />
          </Field>
          <Field label="Maintenance category">
            <Select value={f.category || ""} onChange={(v) => setF({ ...f, category: v })} placeholder="Infer from complaint" options={meta?.task_categories ?? []} />
          </Field>
          <Field label="Due">
            <input type="datetime-local" value={f.due || ""} onChange={(e) => setF({ ...f, due: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            <button className="btn primary" disabled={act.pending}>
              Assign
            </button>
          </div>
        </form>
      </Dialog>
      <Dialog title="Change status" open={dialog === "status"} onClose={() => setDialog(null)}>
        <form className="form" onSubmit={(e) => (e.preventDefault(), setStatus(f.status || "resolved", f.resolution))}>
          <Field label="New status">
            <Select value={f.status || "resolved"} onChange={(v) => setF({ ...f, status: v })} options={["open", "assigned", "in_progress", "resolved", "closed"]} />
          </Field>
          <Field label="Resolution / note">
            <textarea value={f.resolution || ""} onChange={(e) => setF({ ...f, resolution: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            <button className="btn primary">Update</button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
