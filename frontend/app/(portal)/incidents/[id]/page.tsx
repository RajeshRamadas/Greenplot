"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { CaptureButton } from "@/components/Capture";
import { MediaGallery } from "@/components/MediaGallery";
import { Badge, ErrorBox, Field, Loading, PageHead, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Incident } from "@/lib/types";

const NEXT: Record<string, string[]> = {
  open: ["acknowledged", "investigating", "resolved"],
  acknowledged: ["investigating", "resolved"],
  investigating: ["resolved"],
  resolved: ["closed", "investigating"],
  closed: [],
};

export default function IncidentPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const { data: i, error, loading, setData } = useApi<Incident>(`/incidents/${id}`);
  const act = useAction();
  const [status, setStatus] = useState("");
  const [note, setNote] = useState("");
  const [mediaKey, setMediaKey] = useState(0);

  if (loading && !i) return <Loading />;
  if (!i) return <ErrorBox error={error || "Not found"} />;
  const options = NEXT[i.status] ?? [];
  return (
    <>
      <PageHead title={i.title} sub={<><span className="mono">{i.number}</span> · {label(i.category)} · reported by {i.reported_by_name} · {fmtDateTime(i.occurred_at)}</>}>
        <Badge status={i.severity} />
        <Badge status={i.status} />
      </PageHead>
      <ErrorBox error={act.error} />
      <div className="grid side">
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <h2>Details</h2>
            <p style={{ whiteSpace: "pre-wrap" }}>{i.description || <span className="muted">No description</span>}</p>
            <div className="divider" />
            <dl className="kv">
              <dt>Location</dt>
              <dd>
                {i.location || "—"}
                {i.latitude != null ? (
                  <>
                    {" · "}
                    <a href={`https://maps.google.com/?q=${i.latitude},${i.longitude}`} target="_blank" rel="noreferrer">
                      Map
                    </a>
                  </>
                ) : null}
              </dd>
              <dt>Resolution</dt>
              <dd>{i.resolution || "—"}</dd>
              {i.sos_id ? (
                <>
                  <dt>Source</dt>
                  <dd>
                    <Badge status="critical" text="SOS" />
                  </dd>
                </>
              ) : null}
            </dl>
          </div>
          <div className="card">
            <h2>Evidence</h2>
            <MediaGallery entityType="incident" entityId={i.id} refreshKey={mediaKey} />
            <div style={{ marginTop: 10, maxWidth: 260 }}>
              <CaptureButton entityType="incident" entityId={i.id} evidenceType="photo" text="Add photo / video" onDone={() => setMediaKey((k) => k + 1)} />
            </div>
            <p className="small muted" style={{ marginTop: 8 }}>Incident evidence is kept under extended retention.</p>
          </div>
        </div>
        <div className="stack" style={{ gap: 16 }}>
          {can("incidents.manage") && options.length ? (
            <div className="card">
              <h2>Update</h2>
              <form
                className="form"
                onSubmit={async (e) => {
                  e.preventDefault();
                  const r = await act.run(() => api<Incident>(`/incidents/${i.id}/status`, { body: { status: status || options[0], note: note || null } }));
                  if (r) {
                    setData(r);
                    setNote("");
                    setStatus("");
                  }
                }}
              >
                <Field label="Move to">
                  <Select value={status || options[0]} onChange={setStatus} options={options} />
                </Field>
                <Field label="Note" hint="Required when resolving or closing">
                  <textarea value={note} onChange={(e) => setNote(e.target.value)} />
                </Field>
                <button className="btn primary" disabled={act.pending}>
                  Update status
                </button>
              </form>
            </div>
          ) : null}
          <div className="card">
            <h2>Timeline</h2>
            <ul className="timeline">
              <li>
                <b>Reported</b>
                <small>{fmtDateTime(i.occurred_at)}</small>
              </li>
              {i.updates?.map((u) => (
                <li key={u.id}>
                  <b>{u.status_change ? label(u.status_change.split("->")[1]) : "Note"}</b> — {u.body}
                  <small>
                    {u.author_name} · {fmtDateTime(u.created_at)}
                  </small>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </>
  );
}
