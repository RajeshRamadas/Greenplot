"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { CaptureButton } from "@/components/Capture";
import { Badge, Dialog, ErrorBox, Field, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago, label, until } from "@/lib/format";
import { useAction, useApi, useOnline } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import { enqueue } from "@/lib/offline";
import type { TicketCategory, TicketDetail, TicketSummary } from "@/lib/types";

/** CUSTOMER RAISES TICKET → … → CUSTOMER NOTIFIED (ticketing requirements §1). */
const FLOW = ["open", "under_review", "assigned", "accepted", "in_progress", "verification", "resolved", "closed"] as const;
const SIDE: Record<string, { at: string; tone: string }> = {
  waiting_for_customer: { at: "in_progress", tone: "var(--amber)" },
  on_hold: { at: "under_review", tone: "var(--amber)" },
  reopened: { at: "under_review", tone: "var(--red)" },
  rejected: { at: "under_review", tone: "var(--red)" },
  cancelled: { at: "open", tone: "var(--red)" },
  work_completed: { at: "verification", tone: "" },
};

export function TicketLifecycle({ status }: { status: string }) {
  const side = SIDE[status];
  const idx = FLOW.indexOf((side?.at ?? status) as (typeof FLOW)[number]);
  return (
    <div className="lifecycle" aria-label={`Status: ${label(status)}`}>
      {FLOW.map((s, i) => (
        <span key={s} style={{ display: "contents" }}>
          {i ? <i>→</i> : null}
          <span className={i < idx || (status === "closed" && i === idx) ? "done" : i === idx && !side?.tone ? "now" : ""}>
            {s === "verification" ? "Verified" : label(s)}
          </span>
        </span>
      ))}
      {side?.tone ? (
        <span className="now" style={{ background: side.tone }}>
          {label(status)}
        </span>
      ) : null}
    </div>
  );
}

export function SlaBadge({ state, due }: { state?: string | null; due?: string | null }) {
  if (!state) return null;
  const text = state === "met" ? "SLA met" : state === "breached" ? "SLA breached" : `Due ${until(due)}`;
  return <Badge status={state} text={text} />;
}

export function TicketRow({ t, showCustomer }: { t: TicketSummary; showCustomer?: boolean }) {
  const router = useRouter();
  return (
    <tr className="clickable" onClick={() => router.push(`/tickets/${t.id}`)}>
      <td className="mono" style={{ whiteSpace: "nowrap" }}>
        <Link href={`/tickets/${t.id}`} onClick={(e) => e.stopPropagation()}>
          {t.number}
        </Link>
      </td>
      <td>
        <b>{t.title}</b>
        <div className="small muted">
          {t.category_name}
          {t.subcategory ? ` · ${t.subcategory}` : ""} · {t.property_label || "Common area"}
          {showCustomer && t.customer_name ? ` · ${t.customer_name}` : ""}
        </div>
      </td>
      <td>
        <Badge status={t.priority} />
      </td>
      <td>{t.assignee_name || <span className="muted">Unassigned</span>}</td>
      <td>
        <SlaBadge state={t.sla_state} due={t.due_at} />
      </td>
      <td>
        <span className="small">{ago(t.updated_at)}</span>
      </td>
      <td>
        <Badge status={t.status} />
      </td>
    </tr>
  );
}

export function TicketTable({ items, showCustomer }: { items: TicketSummary[]; showCustomer?: boolean }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Issue</th>
            <th>Priority</th>
            <th>Assigned to</th>
            <th>SLA</th>
            <th>Updated</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <TicketRow key={t.id} t={t} showCustomer={showCustomer} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Create Ticket → Property → Category → Subcategory → Issue → Description → Priority → Photos → Preferred time (§6). */
export function NewTicketDialog({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated?: (t: TicketDetail) => void }) {
  const { me, meta, can } = useAuth();
  const router = useRouter();
  const lookups = useLookups();
  const online = useOnline();
  const act = useAction();
  const cats = useApi<TicketCategory[]>(open ? "/tickets/categories" : null);
  const [f, setF] = useState<Record<string, string>>({});
  const [created, setCreated] = useState<TicketDetail | null>(null);
  const [mediaCount, setMediaCount] = useState(0);
  const cat = cats.data?.find((c) => c.code === f.category);
  const manager = can("tickets.manage");

  function close() {
    setF({});
    setCreated(null);
    setMediaCount(0);
    onClose();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const body: Record<string, unknown> = {
      category: f.category,
      subcategory: f.subcategory || null,
      title: f.title,
      description: f.description,
      priority: f.priority || null,
      property_id: f.property_id || null,
      preferred_time: f.preferred_time || null,
      contact_phone: f.contact_phone || null,
      location: f.location || null,
    };
    if (manager && f.property_id) {
      const owner = lookups.properties.find((p) => p.id === f.property_id)?.owner_user_id;
      if (owner) body.customer_id = owner;
      body.source = f.source || "admin";
    }
    if (!online && me) {
      await enqueue(me.id, "ticket", "create", body, `Ticket: ${f.title}`);
      close();
      return;
    }
    const t = await act.run(() => api<TicketDetail>("/tickets", { body }));
    if (t) {
      setCreated(t);
      onCreated?.(t);
    }
  }

  return (
    <Dialog title={created ? `Ticket ${created.number} created` : "Raise a service ticket"} open={open} onClose={close}>
      {created ? (
        <div className="stack">
          <div className="alert ok">
            Your request is logged as <b className="mono">{created.number}</b>. We will notify you as it is reviewed, assigned and closed.
          </div>
          <p className="small muted">Add photos or a short video of the problem — it helps the vendor come prepared.</p>
          <CaptureButton entityType="ticket" entityId={created.id} text={mediaCount ? `Add another (${mediaCount} added)` : "Add photo / video"} onDone={() => setMediaCount((n) => n + 1)} />
          <div className="actions">
            <button className="btn" onClick={close}>
              Done
            </button>
            <button className="btn primary" onClick={() => (close(), router.push(`/tickets/${created.id}`))}>
              Track ticket
            </button>
          </div>
        </div>
      ) : (
        <form className="form two" onSubmit={submit}>
          {lookups.properties.length ? (
            <Field label="Property" full>
              <Select
                value={f.property_id || ""}
                onChange={(v) => setF({ ...f, property_id: v })}
                placeholder={me?.role === "resident" ? (lookups.properties.length === 1 ? `Plot ${lookups.properties[0].plot_number}` : "Common area") : "Common area"}
                options={lookups.properties.map((p) => ({
                  value: p.id,
                  label: `Plot ${p.plot_number}${manager && p.owner_name ? ` · ${p.owner_name}` : ""}`,
                }))}
              />
            </Field>
          ) : null}
          <Field label="Category">
            <Select
              required
              value={f.category || ""}
              onChange={(v) => setF({ ...f, category: v, subcategory: "", priority: "" })}
              placeholder="Choose…"
              options={(cats.data ?? []).map((c) => ({ value: c.code, label: c.name }))}
            />
          </Field>
          <Field label="Type of issue">
            {cat?.subcategories.length ? (
              <Select value={f.subcategory || ""} onChange={(v) => setF({ ...f, subcategory: v })} placeholder="—" options={cat.subcategories} />
            ) : (
              <input value={f.subcategory || ""} onChange={(e) => setF({ ...f, subcategory: e.target.value })} maxLength={100} />
            )}
          </Field>
          <Field label="What's the problem?" full>
            <input required minLength={3} maxLength={300} value={f.title || ""} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="e.g. Water leaking near the meter box" />
          </Field>
          <Field label="Description" full>
            <textarea required minLength={3} value={f.description || ""} onChange={(e) => setF({ ...f, description: e.target.value })} placeholder="Where exactly, since when, anything we should know" />
          </Field>
          {cat && (cat.customer_sets_priority || manager) ? (
            <Field label="Priority" hint={`Default for ${cat.name}: ${label(cat.default_priority)}`}>
              <Select value={f.priority || ""} onChange={(v) => setF({ ...f, priority: v })} placeholder="Default" options={meta?.ticket_priorities ?? ["low", "medium", "high", "critical"]} />
            </Field>
          ) : null}
          <Field label="Preferred time for a visit">
            <input value={f.preferred_time || ""} onChange={(e) => setF({ ...f, preferred_time: e.target.value })} placeholder="e.g. Weekdays after 5 pm" maxLength={120} />
          </Field>
          <Field label="Contact number (optional)">
            <input type="tel" value={f.contact_phone || ""} onChange={(e) => setF({ ...f, contact_phone: e.target.value })} maxLength={30} />
          </Field>
          <Field label="Exact location (optional)">
            <input value={f.location || ""} onChange={(e) => setF({ ...f, location: e.target.value })} placeholder="e.g. Rear gate, near the pump room" maxLength={300} />
          </Field>
          {manager ? (
            <Field label="Received via">
              <Select value={f.source || "admin"} onChange={(v) => setF({ ...f, source: v })} options={["admin", "phone", "whatsapp", "email", "walk_in"]} />
            </Field>
          ) : null}
          <div className="full">
            <ErrorBox error={act.error} />
            {!online ? <div className="alert warn">You are offline. The ticket will be submitted when you reconnect.</div> : null}
          </div>
          <div className="actions full">
            <button type="button" className="btn" onClick={close}>
              Cancel
            </button>
            <button className="btn primary" disabled={act.pending || !f.category}>
              Submit ticket
            </button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
