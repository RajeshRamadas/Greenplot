"use client";

import { useState } from "react";
import { Badge, Dialog, Empty, ErrorBox, Field, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { invalidateLookups } from "@/lib/lookups";
import type { Page, Vendor } from "@/lib/types";
import { announceInvite } from "@/lib/invites";

interface Perf {
  vendor_id: string;
  vendor: string;
  jobs: number;
  open: number;
  completed: number;
  first_time_approved: number;
  rework_jobs: number;
  on_time_rate: number | null;
  avg_hours: number | null;
  materials_cost: number;
}

export default function VendorsPage() {
  const { can } = useAuth();
  const toast = useToast();
  const act = useAction();
  const vendors = useApi<Page<Vendor>>("/vendors", { limit: 200 });
  const perf = useApi<Perf[]>(can("reports.read") ? "/reports/vendors" : null);
  const [open, setOpen] = useState<Vendor | "new" | null>(null);
  const [login, setLogin] = useState<Vendor | null>(null);
  const [f, setF] = useState<Record<string, string>>({});
  const perfBy = new Map((perf.data ?? []).map((p) => [p.vendor_id, p]));

  return (
    <>
      <PageHead title="Vendors" sub="Contractors, service categories, assigned jobs and performance.">
        {can("vendors.manage") ? (
          <button className="btn primary" onClick={() => (setF({}), setOpen("new"))}>
            Add vendor
          </button>
        ) : null}
      </PageHead>
      <ErrorBox error={vendors.error || act.error} />
      {vendors.data && !vendors.data.items.length ? <Empty title="No vendors yet" /> : null}
      <div className="grid two">
        {vendors.data?.items.map((v) => {
          const p = perfBy.get(v.id);
          return (
            <div key={v.id} className="card" style={{ marginTop: 0 }}>
              <div className="card-head">
                <div>
                  <h2 style={{ marginBottom: 2 }}>{v.name}</h2>
                  <span className="small muted">
                    {v.contact_person} {v.phone ? `· ${v.phone}` : ""} {v.email ? `· ${v.email}` : ""}
                  </span>
                </div>
                <Badge status={v.is_active ? "good" : "cancelled"} text={v.is_active ? "Active" : "Inactive"} />
              </div>
              <div className="row small" style={{ marginBottom: 10 }}>
                {v.service_categories.map((c) => (
                  <Badge key={c} status="grey" text={label(c)} />
                ))}
              </div>
              {p ? (
                <dl className="kv" style={{ gridTemplateColumns: "150px 1fr" }}>
                  <dt>Jobs (open / done)</dt>
                  <dd>
                    {p.jobs} ({p.open} / {p.completed})
                  </dd>
                  <dt>Approved first time</dt>
                  <dd>{p.completed ? `${p.first_time_approved}/${p.completed}` : "—"}</dd>
                  <dt>On time</dt>
                  <dd>{p.on_time_rate != null ? `${Math.round(p.on_time_rate * 100)}%` : "—"}</dd>
                  <dt>Avg. job time</dt>
                  <dd>{p.avg_hours != null ? `${p.avg_hours} h` : "—"}</dd>
                </dl>
              ) : null}
              {can("vendors.manage") ? (
                <div className="row" style={{ marginTop: 12 }}>
                  <button className="btn small" onClick={() => (setF({ name: v.name, contact_person: v.contact_person || "", phone: v.phone || "", email: v.email || "", categories: v.service_categories.join(", ") }), setOpen(v))}>
                    Edit
                  </button>
                  <button className="btn small" onClick={() => (setF({}), setLogin(v))}>
                    Create vendor login
                  </button>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
      <Dialog title={open === "new" ? "Add vendor" : "Edit vendor"} open={!!open} onClose={() => setOpen(null)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const body = {
              name: f.name, contact_person: f.contact_person || null, phone: f.phone || null, email: f.email || null,
              service_categories: (f.categories || "").split(",").map((s) => s.trim()).filter(Boolean),
            };
            const ok = await act.run(() => (open === "new" ? api("/vendors", { body }) : api(`/vendors/${(open as Vendor).id}`, { method: "PATCH", body })));
            if (ok) {
              setOpen(null);
              invalidateLookups();
              vendors.reload();
            }
          }}
        >
          <Field label="Vendor name" full>
            <input required value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field label="Contact person">
            <input value={f.contact_person || ""} onChange={(e) => setF({ ...f, contact_person: e.target.value })} />
          </Field>
          <Field label="Phone">
            <input value={f.phone || ""} onChange={(e) => setF({ ...f, phone: e.target.value })} />
          </Field>
          <Field label="Email" full>
            <input type="email" value={f.email || ""} onChange={(e) => setF({ ...f, email: e.target.value })} />
          </Field>
          <Field label="Service categories" hint="Comma separated, e.g. gate_fence, electrical" full>
            <input value={f.categories || ""} onChange={(e) => setF({ ...f, categories: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary">Save</button>
          </div>
        </form>
      </Dialog>
      <Dialog title={`Vendor login · ${login?.name}`} open={!!login} onClose={() => setLogin(null)}>
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            const r = await act.run(() => api<{ invite_url: string | null; sent_via?: string[] }>("/users", { body: { email: f.email, full_name: f.name, phone: f.phone || null, role: "vendor", vendor_id: login!.id } }));
            if (r) {
              setLogin(null);
              await announceInvite(r, toast, "Invite");
            }
          }}
        >
          <Field label="Name">
            <input required value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field label="Email">
            <input required type="email" value={f.email || ""} onChange={(e) => setF({ ...f, email: e.target.value })} />
          </Field>
          <Field label="Phone">
            <input value={f.phone || ""} onChange={(e) => setF({ ...f, phone: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            <button className="btn primary">Create & invite</button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
