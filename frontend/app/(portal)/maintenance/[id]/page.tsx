"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { CaptureButton } from "@/components/Capture";
import { QrScanner } from "@/components/QrScanner";
import { Badge, Dialog, Empty, ErrorBox, Field, Loading, PageHead, Select, useToast } from "@/components/ui";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getPosition } from "@/lib/capture";
import { fmtDateTime, inr, label } from "@/lib/format";
import { useAction, useApi, useOnline } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import { enqueue } from "@/lib/offline";
import type { AuditEntry, ChecklistItem, Evidence, TaskDetail } from "@/lib/types";

const FLOW = ["created", "assigned", "accepted", "started", "completed", "approved", "closed"];

function Lifecycle({ status }: { status: string }) {
  const idx = FLOW.indexOf(status === "rework_required" ? "started" : status);
  return (
    <div className="lifecycle" aria-label={`Status: ${status}`}>
      {FLOW.map((s, i) => (
        <span key={s} style={{ display: "contents" }}>
          {i ? <i>→</i> : null}
          <span className={i < idx ? "done" : i === idx ? "now" : ""}>{label(s)}</span>
        </span>
      ))}
      {status === "rework_required" ? <span className="now" style={{ background: "var(--amber)" }}>Rework required</span> : null}
      {status === "cancelled" ? <span className="now" style={{ background: "var(--red)" }}>Cancelled</span> : null}
    </div>
  );
}

function EvidenceGrid({ items }: { items: Evidence[] }) {
  if (!items.length) return <p className="small muted">None yet.</p>;
  return (
    <div className="evidence-grid">
      {items.map((e) => (
        <a key={e.id} className="evidence-tile" href={e.url || undefined} target="_blank" rel="noreferrer" style={{ color: "inherit", textDecoration: "none" }}>
          <div className="thumb">
            {e.thumbnail_url ? <img src={e.thumbnail_url} alt={label(e.evidence_type)} /> : <span>{e.content_type?.includes("pdf") ? "PDF" : e.content_type?.startsWith("video") ? "▶ Video" : "File"}</span>}
          </div>
          <div className="cap">
            <b>
              {label(e.evidence_type)}
              {e.rework_round ? ` · round ${e.rework_round + 1}` : ""}
            </b>
            <span className="muted">{fmtDateTime(e.captured_at || e.uploaded_at)}</span>
            <span className="muted">{e.uploaded_by_name}</span>
            {e.latitude != null ? <span className="muted">📍 {e.latitude.toFixed(5)}, {e.longitude?.toFixed(5)}</span> : null}
            <span className="mono muted" title={e.sha256}>
              #{e.sha256.slice(0, 12)}
            </span>
          </div>
        </a>
      ))}
    </div>
  );
}

export default function TaskPage() {
  const { id } = useParams<{ id: string }>();
  const { me, meta } = useAuth();
  const toast = useToast();
  const online = useOnline();
  const lookups = useLookups();
  const { data: t, error, loading, reload, setData } = useApi<TaskDetail>(`/maintenance/${id}`);
  const audit = useApi<AuditEntry[]>(me?.role !== "resident" ? `/maintenance/${id}/audit` : null);
  const act = useAction();
  const [dialog, setDialog] = useState<null | "assign" | "reject" | "approve" | "exception" | "material" | "scan" | "reopen" | "cancel" | "decline" | "ack">(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [reasonFor, setReasonFor] = useState<ChecklistItem | null>(null);
  const [notes, setNotes] = useState<Record<string, string> | null>(null);

  if (loading && !t) return <Loading />;
  if (error || !t || !me) return <ErrorBox error={error || "Task not found"} />;

  const A = new Set(t.allowed_actions);
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  /** Call an action endpoint; when offline, queue the equivalent sync operation instead. */
  async function call(path: string, body: unknown = {}, offline?: { operation: string; payload: Record<string, unknown>; label: string }) {
    if (!online && offline && me) {
      await enqueue(me.id, "maintenance", offline.operation, { task_id: t!.id, ...offline.payload }, `${t!.number} · ${offline.label}`);
      toast("Saved offline — will sync when connected");
      return true;
    }
    const res = await act.run(() => api<TaskDetail>(`/maintenance/${t!.id}${path}`, { body }));
    if (res) {
      setData(res);
      audit.reload();
      setDialog(null);
      setForm({});
      return true;
    }
    return false;
  }

  async function withGps<T>(fn: (pos: { latitude?: number; longitude?: number; accuracy_m?: number }) => Promise<T>) {
    const pos = await getPosition();
    return fn(pos ?? {});
  }

  const before = t.evidence.filter((e) => e.evidence_type === "before_photo");
  const after = t.evidence.filter((e) => ["after_photo", "photo", "video"].includes(e.evidence_type));
  const docs = t.evidence.filter((e) => ["invoice", "receipt", "service_report", "warranty", "document", "supervisor"].includes(e.evidence_type));
  const canEdit = A.has("edit_checklist");
  const canCapture = A.has("upload_evidence");
  const assignedToMe = t.assigned_staff_id === me.id || (!!me.vendor_id && t.vendor_id === me.vendor_id);
  const isWorker = assignedToMe || canCapture || canEdit || A.has("start") || A.has("complete");

  return (
    <>
      <PageHead
        title={t.title}
        sub={
          <>
            <span className="mono">{t.number}</span> · {label(t.category)} · {label(t.priority)} priority
            {t.property_label ? <> · {t.property_label}</> : null}
            {t.asset_label ? <> · {t.asset_label}</> : null}
          </>
        }
      >
        <Badge status={t.status} />
        {t.overdue ? <Badge status="urgent" text="Overdue" /> : null}
        {A.has("download_report") ? (
          <button className="btn" onClick={() => download(`/maintenance/${t.id}/report.pdf`).catch((e) => toast(e.message, "error"))}>
            Proof report (PDF)
          </button>
        ) : null}
      </PageHead>
      <div className="card" style={{ marginBottom: 16 }}>
        <Lifecycle status={t.status} />
        {t.review_comment && ["rework_required", "approved", "closed"].includes(t.status) ? (
          <div className={`alert ${t.status === "rework_required" ? "warn" : "ok"}`} style={{ marginTop: 12 }}>
            <b>Supervisor:</b> {t.review_comment}
          </div>
        ) : null}
      </div>
      <ErrorBox error={act.error} />

      <div className="grid side">
        <div className="stack" style={{ gap: 16 }}>
          {/* ---------- worker actions (large, mobile-first) ---------- */}
          {isWorker ? (
            <div className="card">
              <h2>Your next step</h2>
              <div className="stack">
                {A.has("accept") ? (
                  <div className="grid two">
                    <button className="btn primary big" disabled={act.pending} onClick={() => call("/accept", {}, { operation: "accept", payload: {}, label: "Accept" })}>
                      Accept task
                    </button>
                    <button className="btn big" onClick={() => setDialog("decline")}>
                      Decline
                    </button>
                  </div>
                ) : null}
                {A.has("scan_asset") && !t.asset_scanned_at ? (
                  <button className="btn big" onClick={() => setDialog("scan")}>
                    Scan asset QR / NFC
                  </button>
                ) : null}
                {A.has("start") ? (
                  <button
                    className="btn primary big"
                    disabled={act.pending}
                    onClick={() => withGps((p) => call("/start", p, { operation: "start", payload: p, label: t.status === "rework_required" ? "Restart for rework" : "Start work" }))}
                  >
                    {t.status === "rework_required" ? "Start rework" : "Start work"}
                  </button>
                ) : null}
                {canCapture ? (
                  <div className="grid two">
                    <CaptureButton entityType="maintenance_task" entityId={t.id} evidenceType="before_photo" text="Before photo" onDone={reload} />
                    <CaptureButton entityType="maintenance_task" entityId={t.id} evidenceType="after_photo" text="After photo" onDone={reload} primary={t.status === "started"} />
                    <CaptureButton entityType="maintenance_task" entityId={t.id} evidenceType="video" text="Short video" onDone={reload} />
                    <CaptureButton entityType="maintenance_task" entityId={t.id} evidenceType="invoice" text="Invoice / receipt" onDone={reload} />
                  </div>
                ) : null}
                {A.has("complete") ? (
                  <button
                    className="btn primary big"
                    disabled={act.pending}
                    onClick={() => withGps((p) => call("/complete", p, { operation: "complete", payload: p, label: "Submit for review" }))}
                  >
                    Submit for review
                  </button>
                ) : null}
                {!A.has("accept") && !A.has("start") && !A.has("complete") && !canCapture ? (
                  <p className="muted">{t.status === "completed" ? "Submitted — waiting for supervisor review." : `Task is ${label(t.status).toLowerCase()}.`}</p>
                ) : null}
                {A.has("add_exception") ? (
                  <button className="btn ghost small" onClick={() => setDialog("exception")}>
                    Can&apos;t capture required evidence?
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}

          {/* ---------- supervisor review ---------- */}
          {A.has("approve") || A.has("reject") || A.has("assign") || A.has("reopen") || A.has("cancel") ? (
            <div className="card">
              <h2>Supervisor actions</h2>
              <div className="row">
                {A.has("approve") ? (
                  <button className="btn primary" onClick={() => setDialog("approve")}>
                    Approve
                  </button>
                ) : null}
                {A.has("reject") ? (
                  <button className="btn" onClick={() => setDialog("reject")}>
                    Request rework / reject
                  </button>
                ) : null}
                {A.has("assign") ? (
                  <button className="btn" onClick={() => setDialog("assign")}>
                    {t.assigned_staff_id || t.vendor_id ? "Reassign" : "Assign"}
                  </button>
                ) : null}
                {A.has("reopen") ? (
                  <button className="btn" onClick={() => setDialog("reopen")}>
                    Reopen
                  </button>
                ) : null}
                {A.has("cancel") ? (
                  <button className="btn ghost" onClick={() => setDialog("cancel")}>
                    Cancel task
                  </button>
                ) : null}
                {A.has("approve") ? <CaptureButton entityType="maintenance_task" entityId={t.id} evidenceType="supervisor" text="Add review photo" onDone={reload} /> : null}
              </div>
            </div>
          ) : null}

          {A.has("acknowledge") ? (
            <div className="card">
              <h2>Acknowledge completed work</h2>
              <p className="muted" style={{ marginBottom: 10 }}>Confirm you have seen the completed work on your property.</p>
              <button className="btn primary" onClick={() => setDialog("ack")}>
                Acknowledge
              </button>
            </div>
          ) : null}

          {/* ---------- checklist ---------- */}
          <div className="card">
            <div className="card-head">
              <h2>Checklist</h2>
              <span className="small muted">
                {t.checklist.filter((i) => i.status !== "pending").length}/{t.checklist.length} done
              </span>
            </div>
            {!t.checklist.length ? <Empty title="No checklist" /> : null}
            {t.checklist.map((item) => (
              <div className="checklist-item" key={item.id}>
                <div>
                  <div style={{ fontWeight: 600 }}>{item.label}</div>
                  {item.reason ? <div className="small muted">Reason: {item.reason}</div> : null}
                </div>
                {canEdit ? (
                  <div className="seg" role="group" aria-label={`Result for ${item.label}`}>
                    {(["completed", "failed", "skipped"] as const).map((s) => (
                      <button
                        key={s}
                        className={`${s} ${item.status === s ? "on" : ""}`}
                        onClick={() => {
                          if (s === "completed") {
                            void (async () => {
                              if (!online) {
                                await enqueue(me.id, "maintenance", "checklist", { task_id: t.id, item_id: item.id, status: s }, `${t.number} · ✓ ${item.label}`);
                                setData({ ...t, checklist: t.checklist.map((c) => (c.id === item.id ? { ...c, status: s } : c)) });
                                return;
                              }
                              const res = await act.run(() => api<TaskDetail>(`/maintenance/${t.id}/checklist/${item.id}`, { method: "PATCH", body: { status: s } }));
                              if (res) setData(res);
                            })();
                          } else {
                            setReasonFor({ ...item, status: s });
                            setForm({ reason: item.reason || "" });
                          }
                        }}
                      >
                        {s === "completed" ? "✓ Done" : label(s)}
                      </button>
                    ))}
                  </div>
                ) : (
                  <Badge status={item.status} />
                )}
              </div>
            ))}
          </div>

          {/* ---------- evidence ---------- */}
          <div className="card">
            <h2>Before evidence</h2>
            <EvidenceGrid items={before} />
            <div className="divider" />
            <h2>After evidence</h2>
            <EvidenceGrid items={after} />
            <div className="divider" />
            <h2>Documents</h2>
            <EvidenceGrid items={docs} />
            {me.role === "resident" && !t.evidence.length ? <p className="small muted">Evidence is visible once the work is approved.</p> : null}
          </div>

          {/* ---------- work notes ---------- */}
          <div className="card">
            <div className="card-head">
              <h2>Work notes</h2>
              {A.has("edit_notes") && !notes ? (
                <button className="btn small" onClick={() => setNotes({ work_notes: t.work_notes || "", issue_found: t.issue_found || "", outcome: t.outcome || "", observations: t.observations || "" })}>
                  Edit
                </button>
              ) : null}
            </div>
            {notes ? (
              <form
                className="form"
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (!online) {
                    await enqueue(me.id, "maintenance", "notes", { task_id: t.id, ...notes }, `${t.number} · Work notes`);
                    setData({ ...t, ...notes });
                    setNotes(null);
                    return toast("Saved offline");
                  }
                  const res = await act.run(() => api<TaskDetail>(`/maintenance/${t.id}`, { method: "PATCH", body: notes }));
                  if (res) {
                    setData(res);
                    setNotes(null);
                  }
                }}
              >
                <Field label="Work performed">
                  <textarea required value={notes.work_notes} onChange={(e) => setNotes({ ...notes, work_notes: e.target.value })} />
                </Field>
                <Field label="Issue found">
                  <textarea value={notes.issue_found} onChange={(e) => setNotes({ ...notes, issue_found: e.target.value })} />
                </Field>
                <Field label="Outcome">
                  <input value={notes.outcome} onChange={(e) => setNotes({ ...notes, outcome: e.target.value })} />
                </Field>
                <Field label="Observations">
                  <textarea value={notes.observations} onChange={(e) => setNotes({ ...notes, observations: e.target.value })} />
                </Field>
                <div className="row">
                  <button className="btn primary">Save notes</button>
                  <button type="button" className="btn" onClick={() => setNotes(null)}>
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <dl className="kv">
                <dt>Work performed</dt>
                <dd>{t.work_notes || "—"}</dd>
                <dt>Issue found</dt>
                <dd>{t.issue_found || "—"}</dd>
                <dt>Outcome</dt>
                <dd>{t.outcome || "—"}</dd>
                <dt>Observations</dt>
                <dd>{t.observations || "—"}</dd>
              </dl>
            )}
          </div>

          {/* ---------- materials ---------- */}
          <div className="card">
            <div className="card-head">
              <h2>Materials & spares</h2>
              {A.has("add_material") ? (
                <button className="btn small" onClick={() => setDialog("material")}>
                  Add material
                </button>
              ) : null}
            </div>
            {!t.materials.length ? <p className="small muted">None recorded.</p> : null}
            {t.materials.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Material</th>
                      <th>Qty</th>
                      <th>Unit cost</th>
                      <th>Supplier</th>
                    </tr>
                  </thead>
                  <tbody>
                    {t.materials.map((m) => (
                      <tr key={m.id}>
                        <td>{m.name}</td>
                        <td>
                          {Number(m.quantity)} {m.unit}
                        </td>
                        <td>{inr(m.unit_cost)}</td>
                        <td>{m.supplier || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {t.materials_cost ? <p className="small muted" style={{ marginTop: 8 }}>Materials cost: {inr(t.materials_cost)}</p> : null}
          </div>

          {/* ---------- comments ---------- */}
          <div className="card">
            <h2>Comments</h2>
            <ul className="timeline">
              {t.comments.map((c) => (
                <li key={c.id}>
                  <b>{c.author_name}</b> {c.kind === "review" ? <Badge status="pending" text="Review" /> : null}
                  <div>{c.body}</div>
                  <small>{fmtDateTime(c.created_at)}</small>
                </li>
              ))}
            </ul>
            <form
              className="row"
              onSubmit={async (e) => {
                e.preventDefault();
                if (!form.comment?.trim()) return;
                if (await act.run(() => api(`/maintenance/${t.id}/comments`, { body: { body: form.comment } }))) {
                  set("comment", "");
                  reload();
                }
              }}
            >
              <input placeholder="Add a comment" value={form.comment || ""} onChange={(e) => set("comment", e.target.value)} style={{ flex: 1 }} />
              <button className="btn">Post</button>
            </form>
          </div>
        </div>

        {/* ---------- sidebar ---------- */}
        <div className="stack" style={{ gap: 16 }}>
          {t.proof ? (
            <div className="card">
              <h2>Proof of work</h2>
              {t.proof.requirements
                .filter((r) => r.required)
                .map((r) => (
                  <div className="req" key={r.key}>
                    <span>{label(r.key)}</span>
                    <Badge status={r.state} />
                  </div>
                ))}
              <div className="req">
                <span>Work notes</span>
                <Badge status={t.work_notes ? "satisfied" : "missing"} />
              </div>
              {t.exceptions.length ? (
                <>
                  <div className="divider" />
                  <h3 style={{ marginBottom: 6 }}>Exceptions</h3>
                  {t.exceptions.map((x) => (
                    <div key={x.id} className="small" style={{ marginBottom: 8 }}>
                      <b>{label(x.requirement)}</b> — {label(x.reason_code)}: {x.reason} <Badge status={x.review_status} />
                    </div>
                  ))}
                </>
              ) : null}
            </div>
          ) : null}
          <div className="card">
            <h2>Details</h2>
            <dl className="kv" style={{ gridTemplateColumns: "110px 1fr" }}>
              <dt>Assigned</dt>
              <dd>{[t.assignee_name, t.vendor_name].filter(Boolean).join(" / ") || "—"}</dd>
              <dt>Supervisor</dt>
              <dd>{t.supervisor_name || "—"}</dd>
              <dt>Due</dt>
              <dd>{fmtDateTime(t.due_at)}</dd>
              <dt>Location</dt>
              <dd>{t.location_note || t.property_label || "—"}</dd>
              <dt>Started</dt>
              <dd>{fmtDateTime(t.started_at)}</dd>
              <dt>Completed</dt>
              <dd>
                {fmtDateTime(t.completed_at)}
                {t.completed_by_name ? ` · ${t.completed_by_name}` : ""}
              </dd>
              <dt>Approved</dt>
              <dd>
                {fmtDateTime(t.approved_at)}
                {t.reviewed_by_name ? ` · ${t.reviewed_by_name}` : ""}
              </dd>
              <dt>GPS</dt>
              <dd>
                {t.complete_latitude != null
                  ? `${t.complete_latitude.toFixed(5)}, ${t.complete_longitude?.toFixed(5)}`
                  : t.start_latitude != null
                    ? `${t.start_latitude.toFixed(5)}, ${t.start_longitude?.toFixed(5)}`
                    : "—"}
                {t.gps_accuracy_m ? ` (±${Math.round(t.gps_accuracy_m)} m)` : ""}
              </dd>
              <dt>Asset scan</dt>
              <dd>{t.asset_scanned_at ? `${(t.asset_scan_method || "").toUpperCase()} · ${fmtDateTime(t.asset_scanned_at)}` : "—"}</dd>
              <dt>Rework</dt>
              <dd>{t.rework_count}</dd>
              {t.complaint_id ? (
                <>
                  <dt>Complaint</dt>
                  <dd>
                    <Link href={`/complaints/${t.complaint_id}`}>View complaint</Link>
                  </dd>
                </>
              ) : null}
              {t.resident_ack_at ? (
                <>
                  <dt>Resident ack</dt>
                  <dd>{fmtDateTime(t.resident_ack_at)}</dd>
                </>
              ) : null}
            </dl>
            {t.description ? (
              <>
                <div className="divider" />
                <p>{t.description}</p>
              </>
            ) : null}
          </div>
          {audit.data ? (
            <div className="card">
              <h2>Audit trail</h2>
              <ul className="timeline">
                {audit.data.map((a) => (
                  <li key={a.id}>
                    <b>{label(a.action.replace("maintenance.", ""))}</b>
                    <small>
                      {a.actor_name || "System"} · {fmtDateTime(a.timestamp)}
                    </small>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>

      {/* ---------- dialogs ---------- */}
      <Dialog title={`Reason for ${label(reasonFor?.status)}`} open={!!reasonFor} onClose={() => setReasonFor(null)}>
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            if (!reasonFor) return;
            const body = { status: reasonFor.status, reason: form.reason };
            if (!online) {
              await enqueue(me.id, "maintenance", "checklist", { task_id: t.id, item_id: reasonFor.id, ...body }, `${t.number} · ${reasonFor.label}`);
              setData({ ...t, checklist: t.checklist.map((c) => (c.id === reasonFor.id ? { ...c, ...body } : c)) });
              return setReasonFor(null);
            }
            const res = await act.run(() => api<TaskDetail>(`/maintenance/${t.id}/checklist/${reasonFor.id}`, { method: "PATCH", body }));
            if (res) {
              setData(res);
              setReasonFor(null);
            }
          }}
        >
          <p className="muted">{reasonFor?.label}</p>
          <Field label="Reason (required)">
            <textarea required value={form.reason || ""} onChange={(e) => set("reason", e.target.value)} />
          </Field>
          <div className="actions">
            <button type="button" className="btn" onClick={() => setReasonFor(null)}>
              Cancel
            </button>
            <button className="btn primary">Save</button>
          </div>
        </form>
      </Dialog>

      <Dialog title="Assign task" open={dialog === "assign"} onClose={() => setDialog(null)}>
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault();
            call("/assign", {
              assigned_staff_id: form.staff || null,
              vendor_id: form.vendor || null,
              supervisor_id: form.supervisor || null,
              due_at: form.due ? new Date(form.due).toISOString() : null,
            });
          }}
        >
          <Field label="Staff member">
            <Select value={form.staff || ""} onChange={(v) => set("staff", v)} placeholder="—" options={lookups.staff.map((u) => ({ value: u.id, label: u.full_name }))} />
          </Field>
          <Field label="Vendor">
            <Select value={form.vendor || ""} onChange={(v) => set("vendor", v)} placeholder="—" options={lookups.vendors.map((v) => ({ value: v.id, label: v.name }))} />
          </Field>
          <Field label="Supervisor (reviewer)">
            <Select value={form.supervisor || ""} onChange={(v) => set("supervisor", v)} placeholder="Any supervisor" options={lookups.supervisors.map((u) => ({ value: u.id, label: u.full_name }))} />
          </Field>
          <Field label="Due">
            <input type="datetime-local" value={form.due || ""} onChange={(e) => set("due", e.target.value)} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            <button type="button" className="btn" onClick={() => setDialog(null)}>
              Cancel
            </button>
            <button className="btn primary" disabled={act.pending}>
              Assign
            </button>
          </div>
        </form>
      </Dialog>

      <Dialog title="Approve work" open={dialog === "approve"} onClose={() => setDialog(null)}>
        <form className="form" onSubmit={(e) => (e.preventDefault(), call("/approve", { comment: form.comment || null }))}>
          {t.proof?.missing.length ? <div className="alert warn">Missing: {t.proof.missing.map(label).join(", ")}</div> : null}
          {t.exceptions.some((x) => x.review_status === "pending") ? <div className="alert info">Approving also accepts the pending evidence exceptions.</div> : null}
          <Field label="Comment (optional)">
            <textarea value={form.comment || ""} onChange={(e) => set("comment", e.target.value)} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            <button type="button" className="btn" onClick={() => setDialog(null)}>
              Cancel
            </button>
            <button className="btn primary" disabled={act.pending}>
              Approve
            </button>
          </div>
        </form>
      </Dialog>

      <Dialog title="Request rework or reject" open={dialog === "reject"} onClose={() => setDialog(null)}>
        <form className="form" onSubmit={(e) => (e.preventDefault(), call("/reject", { comment: form.comment, decision: form.decision || "rework" }))}>
          <Field label="Decision">
            <Select value={form.decision || "rework"} onChange={(v) => set("decision", v)} options={[{ value: "rework", label: "Request rework" }, { value: "rejected", label: "Reject" }]} />
          </Field>
          <Field label="What needs to be fixed? (required)">
            <textarea required value={form.comment || ""} onChange={(e) => set("comment", e.target.value)} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            <button type="button" className="btn" onClick={() => setDialog(null)}>
              Cancel
            </button>
            <button className="btn primary" disabled={act.pending}>
              Send back
            </button>
          </div>
        </form>
      </Dialog>

      {(["reopen", "cancel", "decline"] as const).map((k) => (
        <Dialog key={k} title={`${label(k)} task`} open={dialog === k} onClose={() => setDialog(null)}>
          <form className="form" onSubmit={(e) => (e.preventDefault(), call(`/${k}`, { reason: form.reason }))}>
            <Field label="Reason (required)">
              <textarea required minLength={3} value={form.reason || ""} onChange={(e) => set("reason", e.target.value)} />
            </Field>
            <ErrorBox error={act.error} />
            <div className="actions">
              <button type="button" className="btn" onClick={() => setDialog(null)}>
                Back
              </button>
              <button className={`btn ${k === "cancel" ? "danger" : "primary"}`} disabled={act.pending}>
                {label(k)}
              </button>
            </div>
          </form>
        </Dialog>
      ))}

      <Dialog title="Acknowledge work" open={dialog === "ack"} onClose={() => setDialog(null)}>
        <form className="form" onSubmit={(e) => (e.preventDefault(), call("/acknowledge", { note: form.note || null }))}>
          <Field label="Note (optional)">
            <textarea value={form.note || ""} onChange={(e) => set("note", e.target.value)} />
          </Field>
          <div className="actions">
            <button className="btn primary">Acknowledge</button>
          </div>
        </form>
      </Dialog>

      <Dialog title="Evidence exception" open={dialog === "exception"} onClose={() => setDialog(null)}>
        <form
          className="form"
          onSubmit={(e) => {
            e.preventDefault();
            const payload = { requirement: form.requirement, reason_code: form.reason_code || "other", reason: form.reason };
            call("/exceptions", payload, { operation: "exception", payload, label: `Exception: ${label(form.requirement)}` });
          }}
        >
          <p className="muted small">The supervisor reviews every exception. Missing evidence is never treated as complete silently.</p>
          <Field label="Which evidence?">
            <Select
              required
              value={form.requirement || ""}
              onChange={(v) => set("requirement", v)}
              placeholder="Select…"
              options={(t.proof?.requirements.filter((r) => r.required && r.state === "missing").map((r) => r.key) ?? meta?.requirement_keys ?? []) as string[]}
            />
          </Field>
          <Field label="Reason">
            <Select value={form.reason_code || "other"} onChange={(v) => set("reason_code", v)} options={meta?.exception_reasons ?? ["other"]} />
          </Field>
          <Field label="Explain (required)">
            <textarea required minLength={5} value={form.reason || ""} onChange={(e) => set("reason", e.target.value)} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            <button className="btn primary" disabled={act.pending}>
              Record exception
            </button>
          </div>
        </form>
      </Dialog>

      <Dialog title="Add material" open={dialog === "material"} onClose={() => setDialog(null)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const payload = {
              name: form.name, quantity: Number(form.quantity), unit: form.unit || "pc",
              unit_cost: form.unit_cost ? Number(form.unit_cost) : null, supplier: form.supplier || null,
            };
            if (!online) {
              await enqueue(me.id, "maintenance", "material", { task_id: t.id, ...payload }, `${t.number} · ${payload.name}`);
              setDialog(null);
              return toast("Saved offline");
            }
            if (await act.run(() => api(`/maintenance/${t.id}/materials`, { body: payload }))) {
              setDialog(null);
              setForm({});
              reload();
            }
          }}
        >
          <Field label="Material" full>
            <input required value={form.name || ""} onChange={(e) => set("name", e.target.value)} />
          </Field>
          <Field label="Quantity">
            <input required type="number" step="any" min="0" value={form.quantity || ""} onChange={(e) => set("quantity", e.target.value)} />
          </Field>
          <Field label="Unit">
            <input required placeholder="kg, pc, m, l" value={form.unit || ""} onChange={(e) => set("unit", e.target.value)} />
          </Field>
          <Field label="Unit cost (₹, optional)">
            <input type="number" step="0.01" min="0" value={form.unit_cost || ""} onChange={(e) => set("unit_cost", e.target.value)} />
          </Field>
          <Field label="Supplier (optional)">
            <input value={form.supplier || ""} onChange={(e) => set("supplier", e.target.value)} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary">Add</button>
          </div>
        </form>
      </Dialog>

      <Dialog title="Scan asset" open={dialog === "scan"} onClose={() => setDialog(null)}>
        <p className="muted small" style={{ marginBottom: 10 }}>Confirm you are at: {t.asset_label}</p>
        <QrScanner
          onCode={(code, method) => {
            if (!online) {
              void enqueue(me.id, "maintenance", "scan", { task_id: t.id, code, method }, `${t.number} · Asset scan`);
              setDialog(null);
              return toast("Scan saved offline");
            }
            call("/scan", { code, method });
          }}
        />
        <ErrorBox error={act.error} />
      </Dialog>
    </>
  );
}
