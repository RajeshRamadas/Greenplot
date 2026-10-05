"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { CaptureButton } from "@/components/Capture";
import { SlaBadge, TicketLifecycle } from "@/components/Tickets";
import { Badge, Dialog, Empty, ErrorBox, Field, Loading, PageHead, Select, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago, fmtDateTime, label, until } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import type { TicketAttachment, TicketCategory, TicketDetail } from "@/lib/types";

type DialogKind =
  | "assign"
  | "edit"
  | "verify"
  | "resolve"
  | "hold"
  | "wait"
  | "cancel"
  | "reject"
  | "reject_assignment"
  | "complete"
  | "feedback"
  | "reopen"
  | "deliveries";

const VIS_LABEL: Record<string, string> = {
  customer: "Customer can see",
  vendor: "Office & assignee only",
  internal: "Internal note (office only)",
  supervisor: "Supervisors only",
};

interface Delivery {
  id: string;
  user_name: string | null;
  event_type: string;
  channel: string;
  status: string;
  attempts: number;
  sent_at: string | null;
  failure_reason: string | null;
  created_at: string;
}

export default function TicketPage() {
  const { id } = useParams<{ id: string }>();
  const { me, meta } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const { data: t, error, loading, setData, reload } = useApi<TicketDetail>(`/tickets/${id}`);
  const act = useAction();
  const [dialog, setDialog] = useState<DialogKind | null>(null);

  if (loading && !t) return <Loading />;
  if (!t || !me) return <ErrorBox error={error || "Ticket not found"} />;
  const can = (a: string) => t.allowed_actions.includes(a);
  const office = can("internal_note");
  const isAssignee = can("accept") || can("start") || can("complete") || can("reject_assignment") || can("upload_evidence");

  async function post(path: string, body: unknown = {}, ok?: string) {
    const r = await act.run(() => api<TicketDetail>(`/tickets/${id}/${path}`, { body }));
    if (r) {
      if (path !== "reject") setData(r);
      setDialog(null);
      if (ok) toast(ok);
    }
    return r;
  }

  const workOrder = t.work_order;
  const ticketFiles = t.attachments.filter((a) => a.source === "ticket");
  const workFiles = t.attachments.filter((a) => a.source === "work");

  return (
    <>
      <PageHead
        title={t.title}
        sub={
          <>
            <span className="mono">{t.number}</span> · {t.category_name}
            {t.subcategory ? ` · ${t.subcategory}` : ""} · {t.property_label || "Common area"}
          </>
        }
      >
        <Badge status={t.priority} text={`${label(t.priority)} priority`} />
        <SlaBadge state={t.sla_state} due={t.due_at} />
        <Badge status={t.status} />
      </PageHead>
      <div className="card" style={{ marginBottom: 16 }}>
        <TicketLifecycle status={t.status} />
        <Actions t={t} can={can} pending={act.pending} post={post} open={setDialog} />
        <ErrorBox error={act.error} />
        <Guidance t={t} me={me.role} can={can} />
      </div>

      <div className="grid side">
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <h2>Issue</h2>
            <p style={{ whiteSpace: "pre-wrap", marginTop: 0 }}>{t.description}</p>
            <dl className="kv">
              <dt>Category</dt>
              <dd>
                {t.category_name}
                {t.subcategory ? ` · ${t.subcategory}` : ""}
              </dd>
              {t.location ? (
                <>
                  <dt>Location</dt>
                  <dd>{t.location}</dd>
                </>
              ) : null}
              <dt>Preferred time</dt>
              <dd>{t.preferred_time || "—"}</dd>
              <dt>Raised</dt>
              <dd>
                {fmtDateTime(t.created_at)} via {label(t.source)}
              </dd>
            </dl>
          </div>

          <div className="card">
            <div className="card-head">
              <h2>Photos & documents</h2>
            </div>
            <Gallery items={ticketFiles} empty="No attachments yet." />
            {can("attach") ? (
              <div style={{ marginTop: 10, maxWidth: 260 }}>
                <CaptureButton entityType="ticket" entityId={t.id} text="Add photo / video / document" onDone={reload} />
              </div>
            ) : null}
            {workFiles.length || workOrder ? (
              <>
                <div className="divider" />
                <h3 style={{ marginBottom: 8 }}>Proof of work</h3>
                <Gallery
                  items={workFiles}
                  empty={me.role === "resident" ? "Proof of work is shared once the supervisor verifies the job." : "No proof captured yet."}
                />
              </>
            ) : null}
          </div>

          <Conversation t={t} onPosted={reload} />

          <div className="card">
            <h2>Timeline</h2>
            <ul className="timeline">
              {t.timeline.map((i, n) => (
                <li key={n}>
                  <b>{i.title}</b>
                  {i.kind === "comment" && i.status && i.status !== "customer" ? <Badge status="pending" text={label(i.status)} /> : null}
                  {i.detail ? <div style={{ whiteSpace: "pre-wrap" }}>{i.detail}</div> : null}
                  <small>
                    {fmtDateTime(i.at)}
                    {i.actor_name ? ` · ${i.actor_name}` : ""}
                  </small>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <h2>Service level</h2>
            {t.sla ? (
              <dl className="kv" style={{ gridTemplateColumns: "130px 1fr" }}>
                <dt>Response due</dt>
                <dd>
                  {fmtDateTime(t.sla.response_due_at)}
                  {t.sla.first_response_at ? (
                    <div className="small muted">Responded {fmtDateTime(t.sla.first_response_at)}</div>
                  ) : (
                    <div className="small muted">{until(t.sla.response_due_at)}</div>
                  )}
                </dd>
                <dt>Resolution due</dt>
                <dd>
                  {fmtDateTime(t.sla.resolution_due_at)}
                  {!t.sla.resolved_at ? <div className="small muted">{until(t.sla.resolution_due_at)}</div> : null}
                </dd>
                <dt>Status</dt>
                <dd>
                  <SlaBadge state={t.sla.state} due={t.sla.resolution_due_at} />
                  {t.sla.escalation_level ? <div className="small muted">Escalated (level {t.sla.escalation_level})</div> : null}
                </dd>
              </dl>
            ) : (
              <p className="muted small">No SLA.</p>
            )}
          </div>

          <div className="card">
            <h2>Who is handling it</h2>
            <dl className="kv" style={{ gridTemplateColumns: "110px 1fr" }}>
              <dt>Assigned to</dt>
              <dd>
                {t.assignee_name ? (
                  <>
                    <b>{t.assignee_name}</b> <span className="small muted">({label(t.assigned_to_type)})</span>
                  </>
                ) : (
                  <span className="muted">Not assigned yet</span>
                )}
                {t.assignee_phone ? (
                  <div>
                    <a href={`tel:${t.assignee_phone}`}>{t.assignee_phone}</a>
                  </div>
                ) : null}
              </dd>
              <dt>Assigned</dt>
              <dd>{fmtDateTime(t.assigned_at)}</dd>
              <dt>Accepted</dt>
              <dd>{fmtDateTime(t.accepted_at)}</dd>
              <dt>Work started</dt>
              <dd>{fmtDateTime(t.started_at)}</dd>
              <dt>Verified</dt>
              <dd>{fmtDateTime(t.verified_at)}</dd>
              {me.role !== "resident" ? (
                <>
                  <dt>Customer</dt>
                  <dd>
                    {t.customer_name}
                    {t.customer_phone ? (
                      <div>
                        <a href={`tel:${t.customer_phone}`}>{t.customer_phone}</a>
                      </div>
                    ) : null}
                  </dd>
                </>
              ) : null}
            </dl>
          </div>

          {workOrder && me.role !== "resident" ? (
            <div className="card">
              <div className="card-head">
                <h2>Work order</h2>
                <Link href={`/maintenance/${workOrder.id}`} className="small mono">
                  {workOrder.number}
                </Link>
              </div>
              <dl className="kv" style={{ gridTemplateColumns: "110px 1fr" }}>
                <dt>Job status</dt>
                <dd>
                  <Badge status={workOrder.status} />
                  {workOrder.rework_count ? <span className="small muted"> · rework ×{workOrder.rework_count}</span> : null}
                </dd>
                <dt>Checklist</dt>
                <dd>
                  {workOrder.checklist_done}/{workOrder.checklist_total}
                </dd>
                <dt>Evidence</dt>
                <dd>{workOrder.evidence_count} files</dd>
                <dt>Materials</dt>
                <dd>{workOrder.materials_count}</dd>
              </dl>
              {workOrder.missing.length ? (
                <div className="alert warn" style={{ marginTop: 10 }}>
                  Still needed before submitting: {workOrder.missing.map((m) => label(m)).join(", ")}
                </div>
              ) : null}
              {isAssignee && can("upload_evidence") ? (
                <div className="stack" style={{ marginTop: 12, gap: 8 }}>
                  <CaptureButton entityType="maintenance_task" entityId={workOrder.id} evidenceType="before_photo" text="Before photo" onDone={reload} />
                  <CaptureButton entityType="maintenance_task" entityId={workOrder.id} evidenceType="after_photo" text="After photo" onDone={reload} />
                  <CaptureButton entityType="maintenance_task" entityId={workOrder.id} evidenceType="invoice" text="Invoice / receipt" onDone={reload} />
                </div>
              ) : null}
              <Link href={`/maintenance/${workOrder.id}`} className="btn block" style={{ marginTop: 12 }}>
                {isAssignee ? "Open job: checklist, materials & evidence" : "View proof of work"}
              </Link>
            </div>
          ) : null}

          {t.resolution || t.feedback_at ? (
            <div className="card">
              <h2>Resolution</h2>
              {t.resolution ? <p style={{ whiteSpace: "pre-wrap", marginTop: 0 }}>{t.resolution}</p> : null}
              <dl className="kv" style={{ gridTemplateColumns: "110px 1fr" }}>
                <dt>Resolved</dt>
                <dd>{fmtDateTime(t.resolved_at)}</dd>
                <dt>Closed</dt>
                <dd>{fmtDateTime(t.closed_at)}</dd>
                {t.feedback_at ? (
                  <>
                    <dt>Feedback</dt>
                    <dd>
                      {t.rating ? `${"★".repeat(t.rating)}${"☆".repeat(5 - t.rating)}` : null}
                      {t.feedback ? <div className="small">{t.feedback}</div> : null}
                    </dd>
                  </>
                ) : null}
              </dl>
              {me.role === "resident" && t.maintenance_task_id ? (
                <Link href={`/maintenance/${t.maintenance_task_id}`} className="btn block" style={{ marginTop: 12 }}>
                  View proof of work report
                </Link>
              ) : null}
            </div>
          ) : null}

          {office ? (
            <div className="card">
              <h2>Records</h2>
              {t.work_orders.length > 1 ? (
                <>
                  <h3>All work orders</h3>
                  {t.work_orders.map((w) => (
                    <Link key={w.id} href={`/maintenance/${w.id}`} className="list-item">
                      <div>
                        <div className="title mono">{w.number}</div>
                        <div className="small muted">{w.assignee_name}</div>
                      </div>
                      <Badge status={w.status} />
                    </Link>
                  ))}
                </>
              ) : null}
              <button className="btn block" style={{ marginTop: 8 }} onClick={() => setDialog("deliveries")}>
                Notification delivery log
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <AssignDialog t={t} open={dialog === "assign"} onClose={() => setDialog(null)} onDone={(r) => (setData(r), setDialog(null), toast("Assigned"))} />
      <EditDialog t={t} open={dialog === "edit"} office={office} onClose={() => setDialog(null)} onDone={(r) => (setData(r), setDialog(null), toast("Saved"))} />
      <ReasonDialog
        open={dialog === "resolve"}
        title="Resolve without field work"
        fieldLabel="Resolution (the customer will see this)"
        onClose={() => setDialog(null)}
        onSubmit={(v) => post("resolve", { resolution: v }, "Resolved")}
        error={act.error}
      />
      <ReasonDialog open={dialog === "hold"} title="Put on hold" fieldLabel="Reason" onClose={() => setDialog(null)} onSubmit={(v) => post("status", { action: "hold", reason: v })} error={act.error} />
      <ReasonDialog
        open={dialog === "wait"}
        title="Ask the customer"
        fieldLabel="Your question (the customer is notified)"
        onClose={() => setDialog(null)}
        onSubmit={(v) => post("status", { action: "wait", reason: v }, "Question sent")}
        error={act.error}
      />
      <ReasonDialog
        open={dialog === "cancel"}
        title="Cancel ticket"
        fieldLabel="Reason"
        optional
        onClose={() => setDialog(null)}
        onSubmit={(v) => post("status", { action: "cancel", reason: v || null }, "Ticket cancelled")}
        error={act.error}
      />
      <ReasonDialog
        open={dialog === "reject"}
        title="Decline this ticket"
        fieldLabel="Why it can't be accepted (the customer will see this)"
        onClose={() => setDialog(null)}
        onSubmit={(v) => post("status", { action: "reject", reason: v })}
        error={act.error}
      />
      <ReasonDialog
        open={dialog === "reopen"}
        title="Reopen ticket"
        fieldLabel="What is still wrong?"
        onClose={() => setDialog(null)}
        onSubmit={(v) => post("reopen", { resolution: v }, "Ticket reopened")}
        error={act.error}
      />
      <RejectAssignmentDialog
        open={dialog === "reject_assignment"}
        reasons={meta?.ticket_reject_reasons ?? ["wrong_category", "outside_service_area", "no_availability", "equipment_unavailable", "other"]}
        onClose={() => setDialog(null)}
        onSubmit={async (code, reason) => {
          // Once rejected, the ticket is no longer visible to this assignee.
          if (await post("reject", { reason_code: code, reason }, "Returned to the layout office")) router.push("/tickets");
        }}
        error={act.error}
      />
      <VerifyDialog t={t} open={dialog === "verify"} onClose={() => setDialog(null)} onSubmit={(decision, comment) => post("verify", { decision, comment: comment || null }, decision === "approve" ? "Approved — customer notified" : "Sent back for rework")} error={act.error} />
      <CompleteDialog t={t} open={dialog === "complete"} onClose={() => setDialog(null)} onSubmit={(b) => post("complete", b, "Submitted for verification")} error={act.error} />
      <FeedbackDialog t={t} open={dialog === "feedback"} onClose={() => setDialog(null)} onSubmit={(b) => post("feedback", b, b.outcome === "still_issue" ? "Ticket reopened" : "Thank you for the feedback")} error={act.error} />
      {dialog === "deliveries" ? <DeliveriesDialog id={t.id} onClose={() => setDialog(null)} /> : null}
    </>
  );
}

// ------------------------------------------------------------------ action bar

function Actions({
  t,
  can,
  pending,
  post,
  open,
}: {
  t: TicketDetail;
  can: (a: string) => boolean;
  pending: boolean;
  post: (path: string, body?: unknown, ok?: string) => Promise<unknown>;
  open: (d: DialogKind) => void;
}) {
  const btn = (show: boolean, text: string, onClick: () => void, kind: "primary" | "" | "danger" = "") =>
    show ? (
      <button className={`btn ${kind}`} disabled={pending} onClick={onClick}>
        {text}
      </button>
    ) : null;
  const buttons = [
    // assignee
    btn(can("accept"), "Accept job", () => post("accept", {}, "Accepted — the customer has been told"), "primary"),
    btn(can("start"), t.work_order?.status === "rework_required" ? "Start rework" : "Start work", () => post("start", {}, "Work started"), can("accept") ? "" : "primary"),
    btn(can("complete"), "Submit completion", () => open("complete"), "primary"),
    btn(can("reject_assignment"), "Reject assignment", () => open("reject_assignment"), "danger"),
    // office
    btn(can("review"), "Mark under review", () => post("review", {}, "Customer notified")),
    btn(can("assign"), "Assign", () => open("assign"), "primary"),
    btn(can("reassign"), "Reassign", () => open("assign")),
    btn(can("verify"), "Verify work", () => open("verify"), "primary"),
    btn(can("close"), "Close ticket", () => post("close", {}, "Closed — customer notified"), "primary"),
    btn(can("resolve"), "Resolve", () => open("resolve")),
    btn(can("resume"), "Resume", () => post("status", { action: "resume" })),
    btn(can("wait"), "Ask customer", () => open("wait")),
    btn(can("hold"), "Hold", () => open("hold")),
    // customer
    btn(can("confirm"), "Yes, it's fixed", () => open("feedback"), "primary"),
    btn(can("feedback") && !can("confirm"), "Rate the service", () => open("feedback")),
    btn(can("reopen"), can("confirm") ? "Still an issue" : "Reopen", () => open("reopen"), can("confirm") ? "danger" : ""),
    // shared
    btn(can("edit"), "Edit", () => open("edit")),
    btn(can("reject"), "Decline ticket", () => open("reject"), "danger"),
    btn(can("cancel"), "Cancel ticket", () => open("cancel"), "danger"),
  ].filter(Boolean);
  if (!buttons.length) return null;
  return (
    <div className="row" style={{ marginTop: 14, flexWrap: "wrap", gap: 8 }}>
      {buttons}
    </div>
  );
}

function Guidance({ t, me, can }: { t: TicketDetail; me: string; can: (a: string) => boolean }) {
  let text: string | null = null;
  if (me === "resident") {
    if (t.status === "resolved") text = "The work has been completed and verified. Please confirm it's fixed, or tell us it's still an issue.";
    else if (t.status === "waiting_for_customer") text = "We need a reply from you — see the conversation below.";
    else if (t.status === "closed" && t.reopen_until && can("reopen")) text = `Not fixed after all? You can reopen this ticket until ${fmtDateTime(t.reopen_until)}.`;
  } else if (can("accept")) text = "New assignment. Accept it, or reject it with a reason so the office can reassign it.";
  else if (can("complete")) text = "Capture after photos, complete the checklist and add work notes, then submit for verification.";
  else if (can("verify")) text = "Work submitted. Review the proof of work, then approve it or send it back for rework.";
  else if (can("assign") && t.timeline.some((i) => i.kind === "assignment" && i.title.endsWith("declined")))
    text = "The previous assignee declined this ticket — see the timeline for why, then reassign it.";
  return text ? (
    <div className="alert info" style={{ marginTop: 12 }}>
      {text}
    </div>
  ) : null;
}

// ------------------------------------------------------------------ attachments & conversation

function Gallery({ items, empty }: { items: TicketAttachment[]; empty: string }) {
  if (!items.length) return <p className="small muted">{empty}</p>;
  return (
    <div className="evidence-grid">
      {items.map((m) => (
        <a key={m.id} className="evidence-tile" href={m.url || undefined} target="_blank" rel="noreferrer" style={{ color: "inherit", textDecoration: "none" }}>
          <div className="thumb">
            {m.thumbnail_url ? <img src={m.thumbnail_url} alt="" /> : <span>{m.content_type?.includes("pdf") ? "PDF" : m.content_type?.startsWith("video") ? "▶ Video" : "File"}</span>}
          </div>
          <div className="cap">
            <b>{label(m.evidence_type)}</b>
            <span className="muted">
              {m.uploaded_by_name} · {fmtDateTime(m.uploaded_at)}
            </span>
            {m.sha256 ? <span className="mono muted">#{m.sha256.slice(0, 12)}</span> : null}
          </div>
        </a>
      ))}
    </div>
  );
}

function Conversation({ t, onPosted }: { t: TicketDetail; onPosted: () => void }) {
  const act = useAction();
  const [message, setMessage] = useState("");
  const [visibility, setVisibility] = useState(t.comment_visibilities[0] || "customer");
  const comments = t.comments;
  return (
    <div className="card">
      <h2>Conversation</h2>
      {!comments.length ? <Empty title="No messages yet" /> : null}
      <div className="list">
        {comments.map((c) => (
          <div key={c.id} className="list-item" style={{ alignItems: "flex-start" }}>
            <div style={{ minWidth: 0 }}>
              <div className="title">
                {c.author_name} <span className="small muted">{c.author_role ? label(c.author_role) : ""}</span>{" "}
                {c.visibility !== "customer" ? <Badge status="pending" text={VIS_LABEL[c.visibility] || label(c.visibility)} /> : null}
                {c.comment_type === "question" ? <Badge status="waiting_for_customer" text="Question" /> : null}
              </div>
              <div style={{ whiteSpace: "pre-wrap" }}>{c.message}</div>
            </div>
            <span className="small muted" title={fmtDateTime(c.created_at)}>
              {ago(c.created_at)}
            </span>
          </div>
        ))}
      </div>
      {t.allowed_actions.includes("comment") ? (
        <form
          className="stack"
          style={{ marginTop: 12 }}
          onSubmit={async (e) => {
            e.preventDefault();
            if (!message.trim()) return;
            if (await act.run(() => api(`/tickets/${t.id}/comments`, { body: { message, visibility } }))) {
              setMessage("");
              onPosted();
            }
          }}
        >
          <textarea placeholder={t.status === "waiting_for_customer" ? "Reply to the question" : "Write a message"} value={message} onChange={(e) => setMessage(e.target.value)} />
          <div className="row between">
            {t.comment_visibilities.length > 1 ? (
              <Select value={visibility} onChange={setVisibility} options={t.comment_visibilities.map((v) => ({ value: v, label: VIS_LABEL[v] || label(v) }))} aria-label="Who can see this" />
            ) : (
              <span className="small muted">{VIS_LABEL[t.comment_visibilities[0]]}</span>
            )}
            <button className="btn" disabled={act.pending}>
              Send
            </button>
          </div>
          <ErrorBox error={act.error} />
        </form>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ dialogs

function ReasonDialog({
  open,
  title,
  fieldLabel,
  optional,
  onClose,
  onSubmit,
  error,
}: {
  open: boolean;
  title: string;
  fieldLabel: string;
  optional?: boolean;
  onClose: () => void;
  onSubmit: (v: string) => void;
  error: string | null;
}) {
  const [v, setV] = useState("");
  return (
    <Dialog title={title} open={open} onClose={onClose}>
      <form className="form" onSubmit={(e) => (e.preventDefault(), onSubmit(v.trim()), setV(""))}>
        <Field label={fieldLabel}>
          <textarea required={!optional} minLength={optional ? 0 : 3} value={v} onChange={(e) => setV(e.target.value)} />
        </Field>
        <ErrorBox error={error} />
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>
            Back
          </button>
          <button className="btn primary">Confirm</button>
        </div>
      </form>
    </Dialog>
  );
}

function AssignDialog({ t, open, onClose, onDone }: { t: TicketDetail; open: boolean; onClose: () => void; onDone: (t: TicketDetail) => void }) {
  const lookups = useLookups();
  const act = useAction();
  const cats = useApi<TicketCategory[]>(open ? "/tickets/categories" : null);
  const [kind, setKind] = useState<"vendor" | "staff">("vendor");
  const [f, setF] = useState<Record<string, string>>({});
  const cat = cats.data?.find((c) => c.id === t.category_id);
  const vendors = [...lookups.vendors].sort(
    (a, b) => Number(b.service_categories?.includes(cat?.task_category ?? "")) - Number(a.service_categories?.includes(cat?.task_category ?? "")),
  );
  const reassign = !!t.assigned_to_id;
  return (
    <Dialog title={reassign ? `Reassign ${t.number}` : `Assign ${t.number}`} open={open} onClose={onClose}>
      <form
        className="form"
        onSubmit={async (e) => {
          e.preventDefault();
          const r = await act.run(() =>
            api<TicketDetail>(`/tickets/${t.id}/assign`, {
              body: {
                vendor_id: kind === "vendor" ? f.who : null,
                staff_id: kind === "staff" ? f.who : null,
                due_at: f.due ? new Date(f.due).toISOString() : null,
                notes: f.notes || null,
                reason: f.reason || null,
              },
            }),
          );
          if (r) {
            setF({});
            onDone(r);
          }
        }}
      >
        <p className="small muted">
          A work order is raised for the assignee with the {cat ? label(cat.task_category) : ""} proof-of-work checklist. The assignee and the customer are notified.
        </p>
        <div className="seg" role="radiogroup">
          {(["vendor", "staff"] as const).map((k) => (
            <button type="button" key={k} className={kind === k ? "on completed" : ""} onClick={() => (setKind(k), setF({ ...f, who: "" }))}>
              {k === "vendor" ? "External vendor" : "Internal staff"}
            </button>
          ))}
        </div>
        <Field label={kind === "vendor" ? "Vendor" : "Staff member"}>
          <Select
            required
            value={f.who || ""}
            onChange={(v) => setF({ ...f, who: v })}
            placeholder="Choose…"
            options={
              kind === "vendor"
                ? vendors.map((v) => ({ value: v.id, label: `${v.name}${v.service_categories?.includes(cat?.task_category ?? "") ? " ★ matches category" : ""}` }))
                : lookups.staff.map((u) => ({ value: u.id, label: `${u.full_name} (${label(u.role)})` }))
            }
          />
        </Field>
        <Field label="Due by" hint={t.due_at ? `Defaults to the SLA: ${fmtDateTime(t.due_at)}` : undefined}>
          <input type="datetime-local" value={f.due || ""} onChange={(e) => setF({ ...f, due: e.target.value })} />
        </Field>
        <Field label="Instructions for the assignee">
          <textarea value={f.notes || ""} onChange={(e) => setF({ ...f, notes: e.target.value })} />
        </Field>
        {reassign ? (
          <Field label="Reason for reassigning">
            <textarea required minLength={3} value={f.reason || ""} onChange={(e) => setF({ ...f, reason: e.target.value })} />
          </Field>
        ) : null}
        <ErrorBox error={act.error} />
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>
            Back
          </button>
          <button className="btn primary" disabled={act.pending}>
            {reassign ? "Reassign" : "Assign"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

function EditDialog({ t, open, office, onClose, onDone }: { t: TicketDetail; open: boolean; office: boolean; onClose: () => void; onDone: (t: TicketDetail) => void }) {
  const act = useAction();
  const cats = useApi<TicketCategory[]>(open && office ? "/tickets/categories" : null);
  const [f, setF] = useState<Record<string, string>>({});
  const v = (k: keyof TicketDetail) => f[k] ?? ((t[k] as string | null) || "");
  return (
    <Dialog title="Edit ticket" open={open} onClose={onClose}>
      <form
        className="form two"
        onSubmit={async (e) => {
          e.preventDefault();
          const r = await act.run(() => api<TicketDetail>(`/tickets/${t.id}`, { method: "PATCH", body: f }));
          if (r) {
            setF({});
            onDone(r);
          }
        }}
      >
        {office ? (
          <>
            <Field label="Category">
              <Select value={f.category ?? t.category_code ?? ""} onChange={(x) => setF({ ...f, category: x })} options={(cats.data ?? []).map((c) => ({ value: c.code, label: c.name }))} />
            </Field>
            <Field label="Priority" hint="Changing it recalculates the SLA">
              <Select value={v("priority")} onChange={(x) => setF({ ...f, priority: x })} options={["low", "medium", "high", "critical"]} />
            </Field>
          </>
        ) : null}
        <Field label="Title" full>
          <input value={v("title")} minLength={3} onChange={(e) => setF({ ...f, title: e.target.value })} />
        </Field>
        <Field label="Description" full>
          <textarea value={v("description")} onChange={(e) => setF({ ...f, description: e.target.value })} />
        </Field>
        <Field label="Location">
          <input value={v("location")} onChange={(e) => setF({ ...f, location: e.target.value })} />
        </Field>
        {!office ? (
          <Field label="Preferred time">
            <input value={v("preferred_time")} onChange={(e) => setF({ ...f, preferred_time: e.target.value })} />
          </Field>
        ) : null}
        <div className="full">
          <ErrorBox error={act.error} />
        </div>
        <div className="actions full">
          <button type="button" className="btn" onClick={onClose}>
            Back
          </button>
          <button className="btn primary" disabled={act.pending || !Object.keys(f).length}>
            Save
          </button>
        </div>
      </form>
    </Dialog>
  );
}

function RejectAssignmentDialog({ open, reasons, onClose, onSubmit, error }: { open: boolean; reasons: string[]; onClose: () => void; onSubmit: (code: string, reason: string) => void; error: string | null }) {
  const [code, setCode] = useState(reasons[0]);
  const [reason, setReason] = useState("");
  return (
    <Dialog title="Reject this assignment" open={open} onClose={onClose}>
      <form className="form" onSubmit={(e) => (e.preventDefault(), onSubmit(code, reason.trim()))}>
        <p className="small muted">The ticket goes back to the layout office for reassignment. The customer is not told your reason.</p>
        <Field label="Reason">
          <Select value={code} onChange={setCode} options={reasons} />
        </Field>
        <Field label="Details">
          <textarea required minLength={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
        <ErrorBox error={error} />
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>
            Back
          </button>
          <button className="btn danger">Reject assignment</button>
        </div>
      </form>
    </Dialog>
  );
}

function VerifyDialog({ t, open, onClose, onSubmit, error }: { t: TicketDetail; open: boolean; onClose: () => void; onSubmit: (d: "approve" | "rework", c: string) => void; error: string | null }) {
  const [comment, setComment] = useState("");
  const work = t.attachments.filter((a) => a.source === "work");
  return (
    <Dialog title={`Verify work on ${t.number}`} open={open} onClose={onClose}>
      <div className="stack">
        <p className="small muted">
          Check the proof of work. Approving resolves the ticket and asks the customer to confirm. Rework sends the job back to {t.assignee_name || "the assignee"}.
        </p>
        <Gallery items={work} empty="No proof of work files." />
        {t.work_order ? (
          <Link href={`/maintenance/${t.work_order.id}`} className="small">
            Full job record: checklist, materials, GPS & audit →
          </Link>
        ) : null}
        <Field label="Comment (required for rework)">
          <textarea value={comment} onChange={(e) => setComment(e.target.value)} />
        </Field>
        <ErrorBox error={error} />
        <div className="actions">
          <button className="btn danger" disabled={comment.trim().length < 3} onClick={() => onSubmit("rework", comment)}>
            Request rework
          </button>
          <button className="btn primary" onClick={() => onSubmit("approve", comment)}>
            Approve & resolve
          </button>
        </div>
      </div>
    </Dialog>
  );
}

function CompleteDialog({ t, open, onClose, onSubmit, error }: { t: TicketDetail; open: boolean; onClose: () => void; onSubmit: (b: Record<string, unknown>) => void; error: string | null }) {
  const [notes, setNotes] = useState("");
  const [outcome, setOutcome] = useState("");
  const w = t.work_order;
  return (
    <Dialog title="Submit completed work" open={open} onClose={onClose}>
      <form className="form" onSubmit={(e) => (e.preventDefault(), onSubmit({ work_notes: notes || null, outcome: outcome || null }))}>
        {w?.missing.filter((m) => m !== "work_notes").length ? (
          <div className="alert warn">
            Missing proof: {w.missing.filter((m) => m !== "work_notes").map((m) => label(m)).join(", ")}.{" "}
            <Link href={`/maintenance/${w.id}`}>Open the job</Link> to complete it.
          </div>
        ) : null}
        <Field label="Work notes — what did you do?">
          <textarea required minLength={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
        <Field label="Outcome for the customer (optional)">
          <textarea value={outcome} onChange={(e) => setOutcome(e.target.value)} placeholder="e.g. Latch replaced; gate closes and locks properly." />
        </Field>
        <ErrorBox error={error} />
        <div className="actions">
          <button type="button" className="btn" onClick={onClose}>
            Back
          </button>
          <button className="btn primary">Submit for verification</button>
        </div>
      </form>
    </Dialog>
  );
}

function FeedbackDialog({ t, open, onClose, onSubmit, error }: { t: TicketDetail; open: boolean; onClose: () => void; onSubmit: (b: { outcome?: string; rating?: number; comment?: string }) => void; error: string | null }) {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const resolved = t.status === "resolved";
  return (
    <Dialog title={resolved ? "Is it fixed?" : "Rate the service"} open={open} onClose={onClose}>
      <div className="stack">
        <div className="row" role="radiogroup" aria-label="Rating" style={{ fontSize: 30 }}>
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" className="btn ghost" aria-label={`${n} star${n > 1 ? "s" : ""}`} aria-pressed={rating >= n} onClick={() => setRating(n)} style={{ fontSize: 26, padding: "2px 6px", color: rating >= n ? "var(--amber)" : "var(--muted)" }}>
              {rating >= n ? "★" : "☆"}
            </button>
          ))}
        </div>
        <Field label="Comments (optional)">
          <textarea value={comment} onChange={(e) => setComment(e.target.value)} />
        </Field>
        <ErrorBox error={error} />
        <div className="actions">
          {resolved ? (
            <>
              <button className="btn danger" onClick={() => onSubmit({ outcome: "still_issue", rating: rating || undefined, comment: comment || "Still an issue" })}>
                Still an issue
              </button>
              <button className="btn primary" onClick={() => onSubmit({ outcome: "resolved", rating: rating || undefined, comment: comment || undefined })}>
                Resolved — close ticket
              </button>
            </>
          ) : (
            <button className="btn primary" disabled={!rating} onClick={() => onSubmit({ rating, comment: comment || undefined })}>
              Send feedback
            </button>
          )}
        </div>
      </div>
    </Dialog>
  );
}

function DeliveriesDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const { data, error, loading } = useApi<Delivery[]>(`/tickets/${id}/notifications`);
  return (
    <Dialog title="Notification delivery log" open onClose={onClose}>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data && !data.length ? <Empty title="No notifications sent" /> : null}
      {data?.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>To</th>
                <th>Event</th>
                <th>Channel</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.id}>
                  <td className="small">{fmtDateTime(d.created_at)}</td>
                  <td>{d.user_name}</td>
                  <td>{label(d.event_type)}</td>
                  <td>{label(d.channel)}</td>
                  <td>
                    <Badge status={["stored", "sent", "delivered", "read"].includes(d.status) ? "completed" : d.status === "failed" ? "failed" : "pending"} text={label(d.status)} />
                    {d.failure_reason ? <div className="small muted">{d.failure_reason}</div> : null}
                    {d.attempts > 1 ? <div className="small muted">{d.attempts} attempts</div> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <div className="actions">
        <button className="btn" onClick={onClose}>
          Close
        </button>
      </div>
    </Dialog>
  );
}
