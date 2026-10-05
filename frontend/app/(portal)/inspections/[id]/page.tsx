"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { CaptureButton } from "@/components/Capture";
import { MediaGallery } from "@/components/MediaGallery";
import { Badge, Dialog, ErrorBox, Field, Loading, PageHead, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getPosition } from "@/lib/capture";
import { fmtDateTime, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import type { Inspection, TaskDetail } from "@/lib/types";

export default function InspectionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { me, can } = useAuth();
  const lookups = useLookups();
  const { data: i, error, loading, setData, reload } = useApi<Inspection>(`/inspections/${id}`);
  const act = useAction();
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [finish, setFinish] = useState(false);
  const [f, setF] = useState<Record<string, string>>({ overall: "good" });
  const [followUp, setFollowUp] = useState<string | null>(null);

  if (loading && !i) return <Loading />;
  if (!i || !me) return <ErrorBox error={error || "Not found"} />;
  const inspector = i.inspector_id === me.id || can("inspections.manage");
  const working = i.status === "in_progress" && inspector && can("inspections.perform");
  const counts = i.items.reduce<Record<string, number>>((a, x) => ((a[x.condition || "pending"] = (a[x.condition || "pending"] || 0) + 1), a), {});

  async function record(itemId: string, condition: string) {
    const r = await act.run(() => api<Inspection>(`/inspections/${i!.id}/items/${itemId}`, { method: "PATCH", body: { condition, notes: notes[itemId] || null } }));
    if (r) setData({ ...r, media: i!.media });
  }

  return (
    <>
      <PageHead
        title={`${i.is_property_watch ? "Property Watch" : "Inspection"} · ${i.property_label}`}
        sub={<><span className="mono">{i.number}</span> · {i.inspector_name || "Inspector not assigned"} · {fmtDateTime(i.completed_at || i.scheduled_for)}</>}
      >
        <Badge status={i.status} />
        {i.overall_condition ? <Badge status={i.overall_condition} text={`Overall: ${label(i.overall_condition)}`} /> : null}
      </PageHead>
      <ErrorBox error={act.error} />
      <div className="grid side">
        <div className="stack" style={{ gap: 16 }}>
          {i.status === "scheduled" && can("inspections.manage") && !i.inspector_id ? (
            <div className="card">
              <h2>Assign inspector</h2>
              <div className="row">
                <Select value={f.inspector || ""} onChange={(v) => setF({ ...f, inspector: v })} placeholder="Select…" options={lookups.staff.map((u) => ({ value: u.id, label: u.full_name }))} />
                <button
                  className="btn primary"
                  disabled={!f.inspector}
                  onClick={async () => {
                    const r = await act.run(() => api<Inspection>(`/inspections/${i.id}/assign`, { method: "POST", query: { inspector_id: f.inspector } }));
                    if (r) setData(r);
                  }}
                >
                  Assign
                </button>
              </div>
            </div>
          ) : null}
          {i.status === "scheduled" && inspector && can("inspections.perform") ? (
            <button
              className="btn primary big"
              onClick={async () => {
                const r = await act.run(() => api<Inspection>(`/inspections/${i.id}/start`, { method: "POST" }));
                if (r) setData(r);
              }}
            >
              Start inspection
            </button>
          ) : null}
          <div className="card">
            <div className="card-head">
              <h2>Condition checklist</h2>
              <span className="small muted">
                {Object.entries(counts)
                  .map(([k, v]) => `${v} ${label(k).toLowerCase()}`)
                  .join(" · ")}
              </span>
            </div>
            {i.items.map((it) => (
              <div key={it.id} className="checklist-item">
                <div>
                  <div style={{ fontWeight: 600 }}>{label(it.point)}</div>
                  {working ? (
                    <input
                      placeholder="Notes (required for attention / issue)"
                      value={notes[it.id] ?? it.notes ?? ""}
                      onChange={(e) => setNotes({ ...notes, [it.id]: e.target.value })}
                      style={{ marginTop: 6 }}
                    />
                  ) : it.notes ? (
                    <div className="small muted">{it.notes}</div>
                  ) : null}
                  {it.follow_up_task_id ? (
                    <Link className="small" href={`/maintenance/${it.follow_up_task_id}`}>
                      Follow-up job →
                    </Link>
                  ) : null}
                </div>
                <div className="stack" style={{ alignItems: "flex-end", gap: 6 }}>
                  {working ? (
                    <div className="seg">
                      {[
                        ["good", "completed"],
                        ["attention", "skipped"],
                        ["issue", "failed"],
                        ["na", "na"],
                      ].map(([c, cls]) => (
                        <button key={c} className={`${cls} ${it.condition === c ? "on" : ""}`} onClick={() => record(it.id, c)}>
                          {c === "na" ? "N/A" : label(c)}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <Badge status={it.condition || "pending"} text={it.condition ? label(it.condition) : "Not checked"} />
                  )}
                  {i.status === "completed" && can("inspections.manage") && ["attention", "issue"].includes(it.condition || "") && !it.follow_up_task_id ? (
                    <button className="btn small" onClick={() => setFollowUp(it.id)}>
                      Create follow-up job
                    </button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
          <div className="card">
            <h2>Photos & video</h2>
            <MediaGallery items={i.media} />
            {working ? (
              <div className="grid two" style={{ marginTop: 12 }}>
                <CaptureButton entityType="inspection" entityId={i.id} evidenceType="photo" text="Add photo" onDone={reload} primary />
                <CaptureButton entityType="inspection" entityId={i.id} evidenceType="video" text="Add video" onDone={reload} />
              </div>
            ) : null}
          </div>
          {working ? (
            <button className="btn primary big" onClick={() => setFinish(true)}>
              Complete inspection
            </button>
          ) : null}
        </div>
        <div className="card">
          <h2>Findings</h2>
          <p style={{ whiteSpace: "pre-wrap" }}>{i.findings || <span className="muted">No findings recorded yet.</span>}</p>
          <div className="divider" />
          <dl className="kv" style={{ gridTemplateColumns: "100px 1fr" }}>
            <dt>Scheduled</dt>
            <dd>{fmtDateTime(i.scheduled_for)}</dd>
            <dt>Started</dt>
            <dd>{fmtDateTime(i.started_at)}</dd>
            <dt>Completed</dt>
            <dd>{fmtDateTime(i.completed_at)}</dd>
            <dt>Property</dt>
            <dd>
              <Link href={`/properties/${i.property_id}`}>{i.property_label}</Link>
            </dd>
          </dl>
        </div>
      </div>

      <Dialog title="Complete inspection" open={finish} onClose={() => setFinish(false)}>
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            const pos = await getPosition();
            const r = await act.run(() => api<Inspection>(`/inspections/${i.id}/complete`, { body: { overall_condition: f.overall, findings: f.findings || null, ...(pos ?? {}) } }));
            if (r) {
              setFinish(false);
              reload();
            }
          }}
        >
          <Field label="Overall condition">
            <Select value={f.overall} onChange={(v) => setF({ ...f, overall: v })} options={["good", "attention", "issue"]} />
          </Field>
          <Field label="Findings / summary for the owner">
            <textarea value={f.findings || ""} onChange={(e) => setF({ ...f, findings: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            <button className="btn primary" disabled={act.pending}>
              Complete & send report
            </button>
          </div>
        </form>
      </Dialog>
      <Dialog title="Create follow-up maintenance" open={!!followUp} onClose={() => setFollowUp(null)}>
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            const t = await act.run(() =>
              api<TaskDetail>(`/inspections/${i.id}/follow-up`, { body: { item_id: followUp, assigned_staff_id: f.staff || null, vendor_id: f.vendor || null } }),
            );
            if (t) router.push(`/maintenance/${t.id}`);
          }}
        >
          <Field label="Assign staff">
            <Select value={f.staff || ""} onChange={(v) => setF({ ...f, staff: v })} placeholder="—" options={lookups.staff.map((u) => ({ value: u.id, label: u.full_name }))} />
          </Field>
          <Field label="or vendor">
            <Select value={f.vendor || ""} onChange={(v) => setF({ ...f, vendor: v })} placeholder="—" options={lookups.vendors.map((v) => ({ value: v.id, label: v.name }))} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            <button className="btn primary">Create job</button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
