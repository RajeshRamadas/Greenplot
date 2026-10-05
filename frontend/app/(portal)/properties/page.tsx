"use client";

import Link from "next/link";
import { useState } from "react";
import { Dialog, Empty, ErrorBox, Field, Loading, PageHead, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { invalidateLookups } from "@/lib/lookups";
import type { Page, Property } from "@/lib/types";

export default function PropertiesPage() {
  const { can } = useAuth();
  const [q, setQ] = useState("");
  const [condition, setCondition] = useState("");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<Record<string, string>>({ status: "vacant_plot" });
  const act = useAction();
  const layouts = useApi<{ id: string; name: string }[]>("/layouts");
  const { data, error, loading, reload } = useApi<Page<Property>>("/properties", { q, condition, limit: 500 });

  return (
    <>
      <PageHead title="Properties" sub={`${data?.total ?? "…"} properties · condition, owners, residents and history`}>
        {can("properties.manage") ? (
          <button className="btn primary" onClick={() => setOpen(true)}>
            Add property
          </button>
        ) : null}
      </PageHead>
      <div className="filters">
        <input type="search" placeholder="Plot number, ID, owner" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select value={condition} onChange={setCondition} placeholder="Any condition" options={["good", "attention", "issue"]} />
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data && !data.items.length ? <Empty title="No properties" /> : null}
      <div className="plot-grid">
        {data?.items.map((p) => (
          <Link key={p.id} href={`/properties/${p.id}`} className={`plot ${p.condition}`}>
            <b>Plot {p.plot_number}</b>
            <span className="small muted">{p.owner_name || p.code}</span>
            <div className="small" style={{ marginTop: 4 }}>
              {label(p.condition)} · {label(p.status)}
            </div>
          </Link>
        ))}
      </div>
      <Dialog title="Add property" open={open} onClose={() => setOpen(false)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const body = {
              layout_id: f.layout_id || layouts.data?.[0]?.id, code: f.code, plot_number: f.plot_number, block: f.block || null,
              address: f.address || null, area_sqft: f.area_sqft ? Number(f.area_sqft) : null, units: Number(f.units || 1), status: f.status,
              owner_name: f.owner_name || null, owner_phone: f.owner_phone || null, owner_email: f.owner_email || null,
            };
            if (await act.run(() => api("/properties", { body }))) {
              setOpen(false);
              invalidateLookups();
              reload();
            }
          }}
        >
          {layouts.data && layouts.data.length > 1 ? (
            <Field label="Layout" full>
              <Select value={f.layout_id || ""} onChange={(v) => setF({ ...f, layout_id: v })} options={layouts.data.map((l) => ({ value: l.id, label: l.name }))} />
            </Field>
          ) : null}
          <Field label="Property ID">
            <input required placeholder="GV-117" value={f.code || ""} onChange={(e) => setF({ ...f, code: e.target.value })} />
          </Field>
          <Field label="Plot number">
            <input required value={f.plot_number || ""} onChange={(e) => setF({ ...f, plot_number: e.target.value })} />
          </Field>
          <Field label="Block">
            <input value={f.block || ""} onChange={(e) => setF({ ...f, block: e.target.value })} />
          </Field>
          <Field label="Status">
            <Select value={f.status} onChange={(v) => setF({ ...f, status: v })} options={["vacant_plot", "occupied", "under_construction", "rented"]} />
          </Field>
          <Field label="Area (sq ft)">
            <input type="number" min="0" value={f.area_sqft || ""} onChange={(e) => setF({ ...f, area_sqft: e.target.value })} />
          </Field>
          <Field label="Units">
            <input type="number" min="1" value={f.units || "1"} onChange={(e) => setF({ ...f, units: e.target.value })} />
          </Field>
          <Field label="Owner name">
            <input value={f.owner_name || ""} onChange={(e) => setF({ ...f, owner_name: e.target.value })} />
          </Field>
          <Field label="Owner phone">
            <input value={f.owner_phone || ""} onChange={(e) => setF({ ...f, owner_phone: e.target.value })} />
          </Field>
          <Field label="Owner email" full>
            <input type="email" value={f.owner_email || ""} onChange={(e) => setF({ ...f, owner_email: e.target.value })} />
          </Field>
          <Field label="Address" full>
            <input value={f.address || ""} onChange={(e) => setF({ ...f, address: e.target.value })} />
          </Field>
          <div className="full">
            <ErrorBox error={act.error} />
          </div>
          <div className="actions full">
            <button className="btn primary" disabled={act.pending}>
              Add
            </button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
