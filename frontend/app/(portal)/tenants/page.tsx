"use client";

import { useState } from "react";
import { Badge, Dialog, ErrorBox, Field, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

interface Row {
  tenant_id: string;
  name: string;
  status: string;
  plan: string;
  properties: number;
  users: number;
  tasks: number;
  storage_bytes: number;
}

/** Platform super admin: tenants, subscriptions and usage (requirements §4, §46). */
export default function TenantsPage() {
  const toast = useToast();
  const act = useAction();
  const { data, reload } = useApi<Row[]>("/tenants/stats");
  const leads = useApi<{ items: { id: string; name: string; phone: string; email: string | null; layout_name: string | null; plots: number | null; message: string | null; created_at: string }[] }>("/public/demo-requests", { limit: 50 });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<Record<string, string>>({ plan: "core", city: "Bangalore" });

  return (
    <>
      <PageHead title="Tenants" sub="Layouts and associations on the GreenPlot platform.">
        <button className="btn primary" onClick={() => setOpen(true)}>
          Onboard layout
        </button>
      </PageHead>
      <ErrorBox error={act.error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Layout</th>
              <th>Plan</th>
              <th>Properties</th>
              <th>Users</th>
              <th>Tasks</th>
              <th>Storage</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data?.map((t) => (
              <tr key={t.tenant_id}>
                <td>
                  <b>{t.name}</b>
                </td>
                <td>{t.plan}</td>
                <td>{t.properties}</td>
                <td>{t.users}</td>
                <td>{t.tasks}</td>
                <td>{(t.storage_bytes / 1024 / 1024).toFixed(1)} MB</td>
                <td>
                  <Badge status={t.status === "active" ? "good" : "cancelled"} text={t.status} />
                </td>
                <td>
                  <button
                    className="btn small ghost"
                    onClick={() => act.run(() => api(`/tenants/${t.tenant_id}`, { method: "PATCH", body: { status: t.status === "active" ? "suspended" : "active" } })).then(reload)}
                  >
                    {t.status === "active" ? "Suspend" : "Reactivate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <h2>Demo requests from the website</h2>
        {leads.data && !leads.data.items.length ? <p className="muted">No requests yet.</p> : null}
        {leads.data?.items.map((l) => (
          <div key={l.id} className="list-item">
            <div>
              <div className="title">
                {l.name} {l.layout_name ? `· ${l.layout_name}` : ""} {l.plots ? `· ${l.plots} plots` : ""}
              </div>
              <div className="small muted">
                <a href={`tel:${l.phone}`}>{l.phone}</a> {l.email ? `· ${l.email}` : ""} {l.message ? `· ${l.message}` : ""}
              </div>
            </div>
            <span className="small muted">{fmtDateTime(l.created_at)}</span>
          </div>
        ))}
      </div>
      <Dialog title="Onboard a layout" open={open} onClose={() => setOpen(false)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const r = await act.run(() =>
              api<{ invite_url: string | null }>("/tenants", {
                body: { name: f.name, slug: f.slug, city: f.city, plan: f.plan, admin_email: f.admin_email, admin_name: f.admin_name, contact_phone: f.phone || null },
              }),
            );
            if (r) {
              setOpen(false);
              reload();
              if (r.invite_url) {
                await navigator.clipboard?.writeText(r.invite_url).catch(() => {});
                toast("Layout created. Admin invite link copied.");
              }
            }
          }}
        >
          <Field label="Layout / association name" full>
            <input required value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value, slug: e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") })} />
          </Field>
          <Field label="Slug">
            <input required pattern="[a-z0-9-]{3,80}" value={f.slug || ""} onChange={(e) => setF({ ...f, slug: e.target.value })} />
          </Field>
          <Field label="City">
            <input value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} />
          </Field>
          <Field label="Plan">
            <input value={f.plan} onChange={(e) => setF({ ...f, plan: e.target.value })} />
          </Field>
          <Field label="Contact phone">
            <input value={f.phone || ""} onChange={(e) => setF({ ...f, phone: e.target.value })} />
          </Field>
          <Field label="Admin name">
            <input required value={f.admin_name || ""} onChange={(e) => setF({ ...f, admin_name: e.target.value })} />
          </Field>
          <Field label="Admin email">
            <input required type="email" value={f.admin_email || ""} onChange={(e) => setF({ ...f, admin_email: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary" disabled={act.pending}>
              Create layout
            </button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
