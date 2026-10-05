"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Dialog, Empty, ErrorBox, Field, Loading, PageHead, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import type { Inspection, Page } from "@/lib/types";

export default function InspectionsPage() {
  const { me, can, meta } = useAuth();
  const router = useRouter();
  const lookups = useLookups();
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<Record<string, string>>({});
  const [points, setPoints] = useState<string[] | null>(null);
  const act = useAction();
  const { data, error, loading } = useApi<Page<Inspection>>("/inspections", { status, limit: 100 });
  const resident = me?.role === "resident";

  return (
    <>
      <PageHead title="Property Watch & inspections" sub="Scheduled visits with condition checks, photos and follow-up maintenance — for owners who cannot be there.">
        {can("inspections.request") ? (
          <button className="btn primary" onClick={() => setOpen(true)}>
            {resident ? "Request a visit" : "Schedule inspection"}
          </button>
        ) : null}
      </PageHead>
      <div className="filters">
        <Select value={status} onChange={setStatus} placeholder="Any status" options={["scheduled", "in_progress", "completed", "cancelled"]} />
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data && !data.items.length ? (
        <div className="card">
          <Empty title="No inspections yet" />
        </div>
      ) : null}
      {data?.items.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Record</th>
                <th>Property</th>
                <th>Type</th>
                <th>Inspector</th>
                <th>Date</th>
                <th>Condition</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((i) => (
                <tr key={i.id} className="clickable" onClick={() => router.push(`/inspections/${i.id}`)}>
                  <td className="mono">{i.number}</td>
                  <td>{i.property_label}</td>
                  <td>{i.is_property_watch ? "Property Watch" : "Inspection"}</td>
                  <td>{i.inspector_name || <span className="muted">Unassigned</span>}</td>
                  <td>{fmtDate(i.completed_at || i.scheduled_for || i.created_at)}</td>
                  <td>{i.overall_condition ? <Badge status={i.overall_condition} /> : "—"}</td>
                  <td>
                    <Badge status={i.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <Dialog title={resident ? "Request a Property Watch visit" : "Schedule inspection"} open={open} onClose={() => setOpen(false)}>
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            const i = await act.run(() =>
              api<Inspection>("/inspections", {
                body: {
                  property_id: f.property_id || lookups.properties[0]?.id,
                  inspector_id: f.inspector || null,
                  is_property_watch: resident || f.watch === "yes",
                  scheduled_for: f.when ? new Date(f.when).toISOString() : null,
                  points,
                },
              }),
            );
            if (i) router.push(`/inspections/${i.id}`);
          }}
        >
          <Field label="Property">
            <Select required value={f.property_id || ""} onChange={(v) => setF({ ...f, property_id: v })} placeholder="Select…" options={lookups.properties.map((p) => ({ value: p.id, label: `Plot ${p.plot_number} (${p.code})` }))} />
          </Field>
          <Field label="Preferred date">
            <input type="datetime-local" value={f.when || ""} onChange={(e) => setF({ ...f, when: e.target.value })} />
          </Field>
          {!resident ? (
            <>
              <Field label="Inspector">
                <Select value={f.inspector || ""} onChange={(v) => setF({ ...f, inspector: v })} placeholder="Assign later" options={lookups.staff.map((u) => ({ value: u.id, label: u.full_name }))} />
              </Field>
              <Field label="Type">
                <Select value={f.watch || "no"} onChange={(v) => setF({ ...f, watch: v })} options={[{ value: "no", label: "Routine inspection" }, { value: "yes", label: "Property Watch (owner report)" }]} />
              </Field>
            </>
          ) : null}
          <Field label="Inspection points">
            <div className="row" style={{ gap: 12 }}>
              {(meta?.inspection_points ?? []).map((p) => (
                <label key={p} className="row small" style={{ gap: 4 }}>
                  <input
                    type="checkbox"
                    checked={!points || points.includes(p)}
                    onChange={(e) => {
                      const base = points ?? meta?.inspection_points ?? [];
                      setPoints(e.target.checked ? [...base, p] : base.filter((x) => x !== p));
                    }}
                  />
                  {label(p)}
                </label>
              ))}
            </div>
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            <button className="btn primary" disabled={act.pending}>
              {resident ? "Request visit" : "Schedule"}
            </button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
