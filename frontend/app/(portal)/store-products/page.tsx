"use client";

import { useState } from "react";
import { Badge, Dialog, Empty, ErrorBox, Field, Loading, PageHead, Select, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import { CATEGORIES, type Plant, rupees } from "@/lib/store";

const CARE_FIELDS: { key: string; label: string; hint?: string }[] = [
  { key: "light", label: "Light", hint: "e.g. Bright indirect light" },
  { key: "water", label: "Water", hint: "e.g. Twice a week" },
  { key: "size", label: "Size", hint: "e.g. About 40 cm tall" },
  { key: "pot", label: "Comes in", hint: "e.g. 6 inch nursery pot" },
  { key: "care_level", label: "Care level", hint: "e.g. Very easy" },
];

type Form = Record<string, string>;

const toForm = (p?: Plant): Form => ({
  slug: p?.slug ?? "",
  name: p?.name ?? "",
  botanical_name: p?.botanical_name ?? "",
  category: p?.category ?? "indoor",
  summary: p?.summary ?? "",
  description: p?.description ?? "",
  price: p ? String(p.price) : "",
  mrp: p?.mrp ? String(p.mrp) : "",
  stock: p?.stock == null ? "" : String(p.stock),
  image: p?.image ?? "",
  pet_safe: p?.care.pet_safe == null ? "" : p.care.pet_safe ? "yes" : "no",
  ...Object.fromEntries(CARE_FIELDS.map((c) => [c.key, String((p?.care as Record<string, unknown>)?.[c.key] ?? "")])),
});

/** The plant catalogue behind the website's store: prices, photos, stock and care notes. */
export default function StoreProductsPage() {
  const toast = useToast();
  const act = useAction();
  const { data, loading, error, reload } = useApi<Plant[]>("/store/products");
  const [editing, setEditing] = useState<Plant | "new" | null>(null);
  const [f, setF] = useState<Form>(toForm());

  function open(p?: Plant) {
    setEditing(p ?? "new");
    setF(toForm(p));
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const care: Record<string, string | boolean> = {};
    for (const c of CARE_FIELDS) if (f[c.key]) care[c.key] = f[c.key];
    if (f.pet_safe) care.pet_safe = f.pet_safe === "yes";
    const body = {
      name: f.name,
      botanical_name: f.botanical_name || null,
      category: f.category,
      summary: f.summary,
      description: f.description,
      care,
      price: Number(f.price),
      mrp: f.mrp ? Number(f.mrp) : null,
      stock: f.stock === "" ? null : Number(f.stock),
      image: f.image,
    };
    const r =
      editing === "new"
        ? await act.run(() => api("/store/products", { body: { ...body, slug: f.slug } }))
        : await act.run(() => api(`/store/products/${(editing as Plant).id}`, { method: "PATCH", body }));
    if (r) {
      toast(editing === "new" ? `${f.name} added to the store` : `${f.name} saved`);
      setEditing(null);
      reload();
    }
  }

  return (
    <>
      <PageHead title="Store products" sub="The plants shown on greenplot.in/store. Prices include tax; leave stock empty if you do not track it.">
        <button className="btn primary" onClick={() => open()}>
          Add a plant
        </button>
      </PageHead>
      <ErrorBox error={act.error || error} />
      {loading && !data ? <Loading /> : null}
      {data && !data.length ? <Empty title="No plants yet">Add your first plant and it appears on the website at once.</Empty> : null}
      {data?.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Plant</th>
                <th>Category</th>
                <th>Price</th>
                <th>Stock</th>
                <th>On the website</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id}>
                  <td>
                    <b>{p.name}</b>
                    <div className="small muted">/store/{p.slug}</div>
                  </td>
                  <td>{CATEGORIES[p.category] ?? p.category}</td>
                  <td>
                    {rupees(p.price)}
                    {p.mrp && p.mrp > p.price ? <div className="small muted">MRP {rupees(p.mrp)}</div> : null}
                  </td>
                  <td>{p.stock == null ? "Not tracked" : p.stock}</td>
                  <td>
                    <Badge status={p.active ? "paid" : "cancelled"} text={p.active ? "Shown" : "Hidden"} />
                  </td>
                  <td>
                    <div className="row">
                      <button className="btn small ghost" onClick={() => open(p)}>
                        Edit
                      </button>
                      <button
                        className="btn small ghost"
                        disabled={act.pending}
                        onClick={async () => {
                          const r = await act.run(() => api(`/store/products/${p.id}`, { method: "PATCH", body: { active: !p.active } }));
                          if (r) {
                            toast(p.active ? `${p.name} hidden from the website` : `${p.name} is back on the website`);
                            reload();
                          }
                        }}
                      >
                        {p.active ? "Hide" : "Show"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <Dialog title={editing === "new" ? "Add a plant" : `Edit ${f.name}`} open={!!editing} onClose={() => setEditing(null)}>
        <form className="form two" onSubmit={save}>
          <Field label="Name">
            <input
              required
              value={f.name}
              onChange={(e) =>
                setF({
                  ...f,
                  name: e.target.value,
                  ...(editing === "new"
                    ? { slug: e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") }
                    : {}),
                })
              }
            />
          </Field>
          <Field label="Botanical name">
            <input value={f.botanical_name} onChange={(e) => setF({ ...f, botanical_name: e.target.value })} />
          </Field>
          {editing === "new" ? (
            <Field label="Web address" hint="greenplot.in/store/…">
              <input required pattern="[a-z0-9]+(-[a-z0-9]+)*" value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value })} />
            </Field>
          ) : null}
          <Field label="Category">
            <Select value={f.category} onChange={(v) => setF({ ...f, category: v })} options={Object.entries(CATEGORIES).map(([value, label]) => ({ value, label }))} />
          </Field>
          <Field label="Price (₹)">
            <input required inputMode="decimal" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value.replace(/[^0-9.]/g, "") })} />
          </Field>
          <Field label="MRP (₹)" hint="Shown struck through; leave empty for none">
            <input inputMode="decimal" value={f.mrp} onChange={(e) => setF({ ...f, mrp: e.target.value.replace(/[^0-9.]/g, "") })} />
          </Field>
          <Field label="Stock" hint="Leave empty if you do not track it">
            <input inputMode="numeric" value={f.stock} onChange={(e) => setF({ ...f, stock: e.target.value.replace(/\D/g, "") })} />
          </Field>
          <Field label="Photo" hint="Path on the website, e.g. /store/tulsi.jpg" full>
            <input required value={f.image} onChange={(e) => setF({ ...f, image: e.target.value })} />
          </Field>
          <Field label="One-line summary" hint="Shown on the store listing" full>
            <input required maxLength={300} value={f.summary} onChange={(e) => setF({ ...f, summary: e.target.value })} />
          </Field>
          <Field label="Description" hint="Shown on the plant's own page" full>
            <textarea required rows={4} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </Field>
          {CARE_FIELDS.map((c) => (
            <Field key={c.key} label={c.label} hint={c.hint}>
              <input value={f[c.key]} onChange={(e) => setF({ ...f, [c.key]: e.target.value })} />
            </Field>
          ))}
          <Field label="Safe for pets">
            <Select
              value={f.pet_safe}
              onChange={(v) => setF({ ...f, pet_safe: v })}
              options={[
                { value: "", label: "Not stated" },
                { value: "yes", label: "Safe for pets" },
                { value: "no", label: "Keep away from pets" },
              ]}
            />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary" disabled={act.pending}>
              {editing === "new" ? "Add to the store" : "Save"}
            </button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
