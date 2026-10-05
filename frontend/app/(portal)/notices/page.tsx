"use client";

import { useState } from "react";
import { Badge, Dialog, Empty, ErrorBox, Field, PageHead, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Notice, Page } from "@/lib/types";

const CHANNELS = ["in_app", "push", "sms", "whatsapp", "email"];

export default function NoticesPage() {
  const { can } = useAuth();
  const manage = can("notices.manage");
  const act = useAction();
  const [kind, setKind] = useState("");
  const { data, error, reload } = useApi<Page<Notice>>("/notices", { kind, limit: 100 });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<Record<string, string>>({ kind: "announcement", audience: "all" });
  const [channels, setChannels] = useState<string[]>(["in_app", "push"]);

  return (
    <>
      <PageHead title={manage ? "Announcements" : "Notices"} sub="Announcements, notices, alerts, events and outages.">
        {manage ? (
          <button className="btn primary" onClick={() => setOpen(true)}>
            Publish
          </button>
        ) : null}
      </PageHead>
      <div className="filters">
        <Select value={kind} onChange={setKind} placeholder="All types" options={["announcement", "notice", "alert", "event", "outage"]} />
      </div>
      <ErrorBox error={error || act.error} />
      {data && !data.items.length ? <Empty title="No notices" /> : null}
      <div className="stack">
        {data?.items.map((n) => (
          <div key={n.id} className="card" style={{ marginTop: 0 }}>
            <div className="card-head">
              <h2>
                {n.pinned ? "📌 " : ""}
                {n.title}
              </h2>
              <div className="row">
                <Badge status={n.kind === "alert" || n.kind === "outage" ? "attention" : "grey"} text={label(n.kind)} />
                {manage ? (
                  <button className="btn small ghost" onClick={() => act.run(() => api(`/notices/${n.id}`, { method: "DELETE" })).then(reload)}>
                    Withdraw
                  </button>
                ) : null}
              </div>
            </div>
            <p style={{ whiteSpace: "pre-wrap" }}>{n.body}</p>
            <p className="small muted" style={{ marginTop: 8 }}>
              {fmtDateTime(n.published_at)} · to {n.audience} {manage ? `· via ${n.channels.map(label).join(", ")}` : ""}
            </p>
          </div>
        ))}
      </div>
      <Dialog title="Publish" open={open} onClose={() => setOpen(false)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const body = {
              kind: f.kind, title: f.title, body: f.body, audience: f.audience, channels, pinned: f.pinned === "yes",
              ends_at: f.ends ? new Date(f.ends).toISOString() : null,
            };
            if (await act.run(() => api("/notices", { body }))) {
              setOpen(false);
              reload();
            }
          }}
        >
          <Field label="Type">
            <Select value={f.kind} onChange={(v) => setF({ ...f, kind: v })} options={["announcement", "notice", "alert", "event", "outage"]} />
          </Field>
          <Field label="Audience">
            <Select value={f.audience} onChange={(v) => setF({ ...f, audience: v })} options={["all", "residents", "staff", "guards"]} />
          </Field>
          <Field label="Title" full>
            <input required minLength={3} value={f.title || ""} onChange={(e) => setF({ ...f, title: e.target.value })} />
          </Field>
          <Field label="Message" full>
            <textarea required value={f.body || ""} onChange={(e) => setF({ ...f, body: e.target.value })} />
          </Field>
          <Field label="Channels" full>
            <div className="row">
              {CHANNELS.map((c) => (
                <label key={c} className="row small" style={{ gap: 4 }}>
                  <input type="checkbox" checked={channels.includes(c)} disabled={c === "in_app"} onChange={(e) => setChannels(e.target.checked ? [...channels, c] : channels.filter((x) => x !== c))} />
                  {label(c)}
                </label>
              ))}
            </div>
          </Field>
          <Field label="Expires">
            <input type="datetime-local" value={f.ends || ""} onChange={(e) => setF({ ...f, ends: e.target.value })} />
          </Field>
          <Field label="Pin to top">
            <Select value={f.pinned || "no"} onChange={(v) => setF({ ...f, pinned: v })} options={[{ value: "no", label: "No" }, { value: "yes", label: "Yes" }]} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary" disabled={act.pending}>
              Publish
            </button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
