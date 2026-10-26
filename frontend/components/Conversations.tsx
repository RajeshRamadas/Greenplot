"use client";

import { useState } from "react";
import { Badge, Dialog, ErrorBox, Field, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime, label } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Interaction } from "@/lib/types";

export const INTERACTION_KINDS = [
  { value: "phone_call", label: "Phone call" },
  { value: "whatsapp_call", label: "WhatsApp call" },
  { value: "whatsapp_chat", label: "WhatsApp chat" },
  { value: "site_visit", label: "Site visit" },
  { value: "meeting", label: "Meeting" },
  { value: "sms", label: "SMS" },
  { value: "email", label: "Email" },
  { value: "note", label: "Note" },
];
const TWO_WAY = new Set(["phone_call", "whatsapp_call", "whatsapp_chat", "sms", "email"]);

/** Local date-time for a datetime-local input, in the browser's time zone. */
function nowLocal() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

/** "Log a conversation" dialog: posts to /customers/{id}/interactions or /properties/{id}/interactions. */
export function LogConversation({
  open,
  onClose,
  path,
  plots,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  path: string;
  plots?: { id: string; plot_number: string }[];
  onSaved: (i: Interaction) => void;
}) {
  const act = useAction();
  const [f, setF] = useState<Record<string, string>>({ kind: "phone_call", direction: "in", at: nowLocal() });
  return (
    <Dialog title="Log a conversation" open={open} onClose={onClose}>
      <form
        className="form two"
        onSubmit={async (e) => {
          e.preventDefault();
          const body = {
            kind: f.kind,
            direction: TWO_WAY.has(f.kind) ? f.direction || null : null,
            occurred_at: f.at ? new Date(f.at).toISOString() : null,
            summary: f.summary,
            outcome: f.outcome || null,
            property_id: f.property_id || null,
          };
          const r = await act.run(() => api<Interaction>(path, { body }));
          if (r) {
            onSaved(r);
            setF({ kind: "phone_call", direction: "in", at: nowLocal() });
            onClose();
          }
        }}
      >
        <Field label="What happened">
          <Select value={f.kind} onChange={(v) => setF({ ...f, kind: v })} options={INTERACTION_KINDS} />
        </Field>
        {TWO_WAY.has(f.kind) ? (
          <Field label="Who started it">
            <Select value={f.direction || "in"} onChange={(v) => setF({ ...f, direction: v })} options={[{ value: "in", label: "The customer" }, { value: "out", label: "We did" }]} />
          </Field>
        ) : (
          <div />
        )}
        <Field label="When">
          <input type="datetime-local" required value={f.at} onChange={(e) => setF({ ...f, at: e.target.value })} />
        </Field>
        {plots && plots.length > 1 ? (
          <Field label="About plot">
            <Select value={f.property_id || ""} onChange={(v) => setF({ ...f, property_id: v })} placeholder="Any / general" options={plots.map((p) => ({ value: p.id, label: `Plot ${p.plot_number}` }))} />
          </Field>
        ) : (
          <div />
        )}
        <Field label="What was said" full>
          <textarea required rows={5} placeholder="Customer asked about… We agreed to…" value={f.summary || ""} onChange={(e) => setF({ ...f, summary: e.target.value })} />
        </Field>
        <Field label="Outcome or next step" full>
          <input placeholder="e.g. Send a quote by Friday" value={f.outcome || ""} onChange={(e) => setF({ ...f, outcome: e.target.value })} />
        </Field>
        <div className="full">
          <ErrorBox error={act.error} />
        </div>
        <div className="actions full">
          <button className="btn primary" disabled={act.pending}>
            Save
          </button>
        </div>
      </form>
    </Dialog>
  );
}

/** A list of logged conversations, with delete for the office. */
export function ConversationList({ items, onDeleted }: { items: Interaction[]; onDeleted?: (id: string) => void }) {
  const act = useAction();
  if (!items.length) return <p className="small muted">No conversations logged yet.</p>;
  return (
    <>
    <ErrorBox error={act.error} />
    <ul className="timeline">
      {items.map((i) => (
        <li key={i.id}>
          <div className="row between">
            <span>
              <Badge status="blue" text={INTERACTION_KINDS.find((k) => k.value === i.kind)?.label || label(i.kind)} />{" "}
              {i.direction ? <span className="small muted">{i.direction === "in" ? "from customer" : "from us"}</span> : null}
            </span>
            {onDeleted ? (
              <button
                className="btn small"
                disabled={act.pending}
                onClick={async () => {
                  if (await act.run(() => api(`/customer-interactions/${i.id}`, { method: "DELETE" }).then(() => true))) onDeleted(i.id);
                }}
              >
                Delete
              </button>
            ) : null}
          </div>
          <div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", margin: "4px 0" }}>{i.summary}</div>
          {i.outcome ? <div className="small"><b>Outcome:</b> {i.outcome}</div> : null}
          <small>
            {fmtDateTime(i.occurred_at)} {i.author_name ? `· ${i.author_name}` : ""}
          </small>
        </li>
      ))}
    </ul>
    </>
  );
}
