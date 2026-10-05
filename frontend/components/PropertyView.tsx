"use client";

import Link from "next/link";
import { useState } from "react";
import { CaptureButton } from "@/components/Capture";
import { MediaGallery } from "@/components/MediaGallery";
import { Badge, Dialog, Empty, ErrorBox, Field, Loading, PageHead, Select, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { linkFor } from "@/lib/links";
import type { Asset, Page, Property, Resident, TimelineEntry } from "@/lib/types";

/** Property profile + searchable history timeline (requirements §6). */
export function PropertyView({ id }: { id: string }) {
  const { can, me } = useAuth();
  const toast = useToast();
  const { data: p, error, loading, setData } = useApi<Property>(`/properties/${id}`);
  const history = useApi<TimelineEntry[]>(`/properties/${id}/history`, { limit: 200 });
  const residents = useApi<Page<Resident>>(can("residents.read") ? "/residents" : null, { property_id: id });
  const assets = useApi<Asset[]>(can("assets.read") ? `/properties/${id}/assets` : null);
  const act = useAction();
  const [kind, setKind] = useState("");
  const [edit, setEdit] = useState(false);
  const [addRes, setAddRes] = useState(false);
  const [f, setF] = useState<Record<string, string>>({});
  const [mediaKey, setMediaKey] = useState(0);

  if (loading && !p) return <Loading />;
  if (!p) return <ErrorBox error={error || "Not found"} />;
  const items = (history.data ?? []).filter((h) => !kind || h.kind === kind);
  const kinds = Array.from(new Set((history.data ?? []).map((h) => h.kind)));

  return (
    <div>
      <PageHead title={`Plot ${p.plot_number}`} sub={<><span className="mono">{p.code}</span> · {p.layout_name} {p.block ? `· Block ${p.block}` : ""}</>}>
        <Badge status={p.condition} text={`Condition: ${label(p.condition)}`} />
        {can("properties.manage") ? (
          <button className="btn" onClick={() => (setF({ owner_name: p.owner_name || "", owner_phone: p.owner_phone || "", status: p.status, condition: p.condition, notes: p.notes || "" }), setEdit(true))}>
            Edit
          </button>
        ) : null}
      </PageHead>
      <div className="grid side">
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <h2>Property history</h2>
              <Select value={kind} onChange={setKind} placeholder="Everything" options={kinds} style={{ width: "auto" }} />
            </div>
            {!items.length ? <Empty title="No history yet" /> : null}
            <ul className="timeline">
              {items.map((h) => {
                const href = linkFor(h.kind === "gardening" ? "maintenance" : h.kind === "property_watch" ? "inspection" : h.kind, h.id);
                return (
                  <li key={`${h.kind}-${h.id}`}>
                    <div className="row between">
                      <span>
                        <Badge status="grey" text={label(h.kind)} />{" "}
                        {href && h.kind !== "record" ? <Link href={href}>{h.title}</Link> : h.title}
                      </span>
                      {h.status ? <Badge status={h.status} /> : null}
                    </div>
                    <small>
                      {h.number ? <span className="mono">{h.number}</span> : null} {fmtDate(h.at)}
                    </small>
                  </li>
                );
              })}
            </ul>
          </div>
          <div className="card">
            <h2>Documents & media</h2>
            <MediaGallery entityType="property" entityId={p.id} refreshKey={mediaKey} />
            {can("properties.manage") || me?.role === "resident" ? (
              <div style={{ marginTop: 10, maxWidth: 260 }}>
                <CaptureButton entityType="property" entityId={p.id} evidenceType="document" text="Upload document" onDone={() => setMediaKey((k) => k + 1)} />
              </div>
            ) : null}
          </div>
        </div>
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <h2>Profile</h2>
            <dl className="kv" style={{ gridTemplateColumns: "100px 1fr" }}>
              <dt>Owner</dt>
              <dd>{p.owner_name || "—"}</dd>
              <dt>Phone</dt>
              <dd>{p.owner_phone || "—"}</dd>
              <dt>Status</dt>
              <dd>{label(p.status)}</dd>
              <dt>Area</dt>
              <dd>{p.area_sqft ? `${p.area_sqft} sq ft` : "—"}</dd>
              <dt>Units</dt>
              <dd>{p.units}</dd>
              <dt>Address</dt>
              <dd>{p.address || "—"}</dd>
              {p.notes ? (
                <>
                  <dt>Notes</dt>
                  <dd>{p.notes}</dd>
                </>
              ) : null}
            </dl>
          </div>
          {residents.data ? (
            <div className="card">
              <div className="card-head">
                <h2>Residents</h2>
                {can("residents.manage") ? (
                  <button className="btn small" onClick={() => (setF({ relation: "owner" }), setAddRes(true))}>
                    Add
                  </button>
                ) : null}
              </div>
              {!residents.data.items.length ? <p className="small muted">No residents recorded.</p> : null}
              {residents.data.items.map((r) => (
                <div key={r.id} className="list-item">
                  <div>
                    <div className="title">{r.name}</div>
                    <div className="small muted">
                      {label(r.relation)} {r.phone ? `· ${r.phone}` : ""} {r.user_id ? "· has login" : ""}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {assets.data?.length ? (
            <div className="card">
              <h2>Assets</h2>
              {assets.data.map((a) => (
                <Link key={a.id} href={`/assets/${a.id}`} className="list-item">
                  <span>{a.name}</span>
                  <Badge status={a.condition} />
                </Link>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <Dialog title="Edit property" open={edit} onClose={() => setEdit(false)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const r = await act.run(() => api<Property>(`/properties/${p.id}`, { method: "PATCH", body: f }));
            if (r) {
              setData(r);
              setEdit(false);
            }
          }}
        >
          <Field label="Owner name">
            <input value={f.owner_name} onChange={(e) => setF({ ...f, owner_name: e.target.value })} />
          </Field>
          <Field label="Owner phone">
            <input value={f.owner_phone} onChange={(e) => setF({ ...f, owner_phone: e.target.value })} />
          </Field>
          <Field label="Status">
            <Select value={f.status} onChange={(v) => setF({ ...f, status: v })} options={["vacant_plot", "occupied", "under_construction", "rented"]} />
          </Field>
          <Field label="Condition">
            <Select value={f.condition} onChange={(v) => setF({ ...f, condition: v })} options={["good", "attention", "issue"]} />
          </Field>
          <Field label="Notes" full>
            <textarea value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary">Save</button>
          </div>
        </form>
      </Dialog>
      <Dialog title="Add resident" open={addRes} onClose={() => setAddRes(false)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const r = await act.run(() =>
              api<{ invite_url: string | null }>("/residents", {
                body: { property_id: p.id, name: f.name, phone: f.phone || null, email: f.email || null, relation: f.relation, invite: f.invite === "yes", in_directory: f.dir === "yes" },
              }),
            );
            if (r) {
              setAddRes(false);
              residents.reload();
              if (r.invite_url) {
                await navigator.clipboard?.writeText(r.invite_url).catch(() => {});
                toast("Resident added. Invite link copied to clipboard.");
              }
            }
          }}
        >
          <Field label="Name" full>
            <input required value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field label="Phone">
            <input value={f.phone || ""} onChange={(e) => setF({ ...f, phone: e.target.value })} />
          </Field>
          <Field label="Email">
            <input type="email" value={f.email || ""} onChange={(e) => setF({ ...f, email: e.target.value })} />
          </Field>
          <Field label="Relation">
            <Select value={f.relation || "owner"} onChange={(v) => setF({ ...f, relation: v })} options={["owner", "tenant", "family"]} />
          </Field>
          <Field label="Invite to GreenPlot app">
            <Select value={f.invite || "no"} onChange={(v) => setF({ ...f, invite: v })} options={[{ value: "no", label: "No" }, { value: "yes", label: "Yes — create login" }]} />
          </Field>
          <Field label="Show in resident directory" full>
            <Select value={f.dir || "no"} onChange={(v) => setF({ ...f, dir: v })} options={[{ value: "no", label: "No" }, { value: "yes", label: "Yes (opt-in)" }]} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary">Add resident</button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
