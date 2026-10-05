"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Dialog, Empty, ErrorBox, Field, PageHead, Select, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago, fmtDateTime, label } from "@/lib/format";
import { useAction, useApi, useOnline } from "@/lib/hooks";
import { enqueue } from "@/lib/offline";
import type { Incident, Page, Sos } from "@/lib/types";
import { getPosition } from "@/lib/capture";

export default function IncidentsPage() {
  const { me, can } = useAuth();
  const router = useRouter();
  const online = useOnline();
  const toast = useToast();
  const act = useAction();
  const [openOnly, setOpenOnly] = useState(true);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<Record<string, string>>({ category: "security", severity: "medium" });
  const { data, error, reload } = useApi<Page<Incident>>("/incidents", { open_only: openOnly, limit: 100 });
  const sos = useApi<Sos[]>(can("sos.respond") ? "/sos" : null);

  async function sosAction(s: Sos, action: string) {
    if (await act.run(() => api(`/sos/${s.id}/action`, { body: { action } }))) {
      sos.reload();
      reload();
    }
  }

  return (
    <>
      <PageHead title="Incidents & SOS" sub="OPEN → ACKNOWLEDGED → INVESTIGATING → RESOLVED → CLOSED">
        {can("incidents.create") ? (
          <button className="btn primary" onClick={() => setOpen(true)}>
            Report incident
          </button>
        ) : null}
      </PageHead>
      <ErrorBox error={error || act.error} />
      {sos.data?.length ? (
        <div className="card" style={{ borderColor: "var(--red)", marginBottom: 16 }}>
          <h2 style={{ color: "var(--red)" }}>Active SOS</h2>
          {sos.data.map((s) => (
            <div key={s.id} className="list-item">
              <div>
                <div className="title">
                  {s.raised_by_name} · {ago(s.created_at)} {s.escalation_level ? <Badge status="critical" text={`Escalated ×${s.escalation_level}`} /> : null}
                </div>
                <div className="small muted">
                  {s.message || "Emergency assistance requested"}
                  {s.latitude != null ? (
                    <>
                      {" · "}
                      <a href={`https://maps.google.com/?q=${s.latitude},${s.longitude}`} target="_blank" rel="noreferrer">
                        Open location
                      </a>
                    </>
                  ) : null}
                </div>
              </div>
              <div className="row">
                <Badge status={s.status} />
                {s.status === "active" ? (
                  <button className="btn small primary" onClick={() => sosAction(s, "acknowledge")}>
                    Respond
                  </button>
                ) : null}
                <button className="btn small" onClick={() => sosAction(s, "resolve")}>
                  Resolve
                </button>
                <button className="btn small ghost" onClick={() => sosAction(s, "false_alarm")}>
                  False alarm
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : null}
      <div className="filters">
        <label className="row small" style={{ minWidth: 0 }}>
          <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} /> Open incidents only
        </label>
      </div>
      {data && !data.items.length ? (
        <div className="card">
          <Empty title="No incidents" />
        </div>
      ) : null}
      {data?.items.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Incident</th>
                <th>Title</th>
                <th>Severity</th>
                <th>Reported</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((i) => (
                <tr key={i.id} className="clickable" onClick={() => router.push(`/incidents/${i.id}`)}>
                  <td className="mono">{i.number}</td>
                  <td>
                    <b>{i.title}</b>
                    <div className="small muted">
                      {label(i.category)} {i.location ? `· ${i.location}` : ""}
                    </div>
                  </td>
                  <td>
                    <Badge status={i.severity} />
                  </td>
                  <td>
                    {fmtDateTime(i.occurred_at)}
                    <div className="small muted">{i.reported_by_name}</div>
                  </td>
                  <td>
                    <Badge status={i.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <Dialog title="Report incident" open={open} onClose={() => setOpen(false)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const pos = await getPosition(4000);
            const body = { title: f.title, description: f.description || null, category: f.category, severity: f.severity, location: f.location || null, ...(pos ?? {}) };
            if (!online && me) {
              await enqueue(me.id, "incident", "create", body, `Incident: ${f.title}`);
              setOpen(false);
              return toast("Saved offline");
            }
            const inc = await act.run(() => api<Incident>("/incidents", { body }));
            if (inc) router.push(`/incidents/${inc.id}`);
          }}
        >
          <Field label="What happened?" full>
            <input required minLength={3} value={f.title || ""} onChange={(e) => setF({ ...f, title: e.target.value })} />
          </Field>
          <Field label="Category">
            <Select value={f.category} onChange={(v) => setF({ ...f, category: v })} options={["security", "fire", "medical", "theft", "trespass", "infrastructure", "other"]} />
          </Field>
          <Field label="Severity">
            <Select value={f.severity} onChange={(v) => setF({ ...f, severity: v })} options={["low", "medium", "high", "critical"]} />
          </Field>
          <Field label="Location" full>
            <input value={f.location || ""} onChange={(e) => setF({ ...f, location: e.target.value })} />
          </Field>
          <Field label="Details" full>
            <textarea value={f.description || ""} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary" disabled={act.pending}>
              Report
            </button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
