"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge, Dialog, Empty, ErrorBox, Field, Loading, PageHead, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import type { Asset, Page } from "@/lib/types";

export default function AssetsPage() {
  const { can, meta } = useAuth();
  const router = useRouter();
  const lookups = useLookups();
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [due, setDue] = useState(false);
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<Record<string, string>>({ category: "gate" });
  const act = useAction();
  const { data, error, loading } = useApi<Page<Asset>>("/assets", { q, category, service_due: due || undefined, limit: 200 });

  return (
    <>
      <PageHead title="Assets" sub="Gates, pumps, motors, streetlights and other maintainable infrastructure with QR/NFC tags.">
        {can("assets.manage") ? (
          <button className="btn primary" onClick={() => setOpen(true)}>
            Add asset
          </button>
        ) : null}
      </PageHead>
      <div className="filters">
        <input type="search" placeholder="Name, code, location" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select value={category} onChange={setCategory} placeholder="Any category" options={meta?.asset_categories ?? []} />
        <label className="row small" style={{ minWidth: 0 }}>
          <input type="checkbox" checked={due} onChange={(e) => setDue(e.target.checked)} /> Service due
        </label>
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data && !data.items.length ? <Empty title="No assets" /> : null}
      {data?.items.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Code</th>
                <th>Asset</th>
                <th>Location</th>
                <th>Next service</th>
                <th>Warranty</th>
                <th>Condition</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => (
                <tr key={a.id} className="clickable" onClick={() => router.push(`/assets/${a.id}`)}>
                  <td className="mono">{a.code}</td>
                  <td>
                    <b>{a.name}</b>
                    <div className="small muted">{label(a.category)}</div>
                  </td>
                  <td>{a.location || "—"}</td>
                  <td>
                    {fmtDate(a.next_service_due)}{" "}
                    {a.next_service_due && a.next_service_due <= new Date().toISOString().slice(0, 10) ? <Badge status="urgent" text="Due" /> : null}
                  </td>
                  <td>{fmtDate(a.warranty_until)}</td>
                  <td>
                    <Badge status={a.condition} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <Dialog title="Add asset" open={open} onClose={() => setOpen(false)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const a = await act.run(() =>
              api<Asset>("/assets", {
                body: {
                  code: f.code, name: f.name, category: f.category, location: f.location || null, qr_code: f.qr_code || null, nfc_id: f.nfc_id || null,
                  property_id: f.property_id || null, vendor_id: f.vendor_id || null, installed_on: f.installed_on || null, warranty_until: f.warranty_until || null,
                  service_interval_days: f.interval ? Number(f.interval) : null, next_service_due: f.next || null,
                },
              }),
            );
            if (a) router.push(`/assets/${a.id}`);
          }}
        >
          <Field label="Asset code">
            <input required value={f.code || ""} onChange={(e) => setF({ ...f, code: e.target.value })} />
          </Field>
          <Field label="Category">
            <Select value={f.category} onChange={(v) => setF({ ...f, category: v })} options={meta?.asset_categories ?? []} />
          </Field>
          <Field label="Name" full>
            <input required value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field label="Location">
            <input value={f.location || ""} onChange={(e) => setF({ ...f, location: e.target.value })} />
          </Field>
          <Field label="Property">
            <Select value={f.property_id || ""} onChange={(v) => setF({ ...f, property_id: v })} placeholder="Common asset" options={lookups.properties.map((p) => ({ value: p.id, label: `Plot ${p.plot_number}` }))} />
          </Field>
          <Field label="QR code" hint="Leave empty to generate one">
            <input value={f.qr_code || ""} onChange={(e) => setF({ ...f, qr_code: e.target.value })} />
          </Field>
          <Field label="NFC tag ID (optional)">
            <input value={f.nfc_id || ""} onChange={(e) => setF({ ...f, nfc_id: e.target.value })} />
          </Field>
          <Field label="Vendor">
            <Select value={f.vendor_id || ""} onChange={(v) => setF({ ...f, vendor_id: v })} placeholder="—" options={lookups.vendors.map((v) => ({ value: v.id, label: v.name }))} />
          </Field>
          <Field label="Installed on">
            <input type="date" value={f.installed_on || ""} onChange={(e) => setF({ ...f, installed_on: e.target.value })} />
          </Field>
          <Field label="Warranty until">
            <input type="date" value={f.warranty_until || ""} onChange={(e) => setF({ ...f, warranty_until: e.target.value })} />
          </Field>
          <Field label="Service every (days)">
            <input type="number" min="1" value={f.interval || ""} onChange={(e) => setF({ ...f, interval: e.target.value })} />
          </Field>
          <Field label="Next service due">
            <input type="date" value={f.next || ""} onChange={(e) => setF({ ...f, next: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary" disabled={act.pending}>
              Add asset
            </button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
