"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { CaptureButton } from "@/components/Capture";
import { Badge, Dialog, Empty, ErrorBox, Field, Loading, PageHead, Pager, Select, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, fmtTime } from "@/lib/format";
import { useAction, useApi, useOnline } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import { enqueue } from "@/lib/offline";
import type { Page, Visitor } from "@/lib/types";

function VisitorsInner() {
  const { me, can } = useAuth();
  const params = useSearchParams();
  const lookups = useLookups();
  const online = useOnline();
  const toast = useToast();
  const act = useAction();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState(false);
  const [photoFor, setPhotoFor] = useState<Visitor | null>(null);
  const [f, setF] = useState<Record<string, string>>({});
  const { data, error, loading, reload } = useApi<Page<Visitor>>("/visitors", { status, q, limit: 50, offset });
  const guard = can("visitors.manage");
  const resident = me?.role === "resident";

  useEffect(() => {
    if (params.get("new")) setOpen(true);
  }, [params]);

  async function action(v: Visitor, path: string, body?: unknown) {
    if (!online && path === "exit" && me) {
      await enqueue(me.id, "visitor", "exit", { visitor_id: v.id }, `Exit: ${v.name}`);
      return toast("Exit saved offline");
    }
    if (await act.run(() => api(`/visitors/${v.id}/${path}`, { method: "POST", body }))) reload();
  }

  return (
    <>
      <PageHead title="Visitors" sub={resident ? "Pre-approve expected guests and respond to gate requests." : "Gate register: name, phone, purpose, host, entry and exit."}>
        <button className="btn primary" onClick={() => (setF({}), setOpen(true))}>
          {resident ? "Pre-approve a visitor" : "Register visitor"}
        </button>
      </PageHead>
      <div className="filters">
        <input type="search" placeholder="Name, phone, vehicle" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select value={status} onChange={setStatus} placeholder="Any status" options={["pending_approval", "approved", "inside", "exited", "denied"]} />
      </div>
      <ErrorBox error={error || act.error} />
      {loading && !data ? <Loading /> : null}
      {data && !data.items.length ? (
        <div className="card">
          <Empty title="No visitors" />
        </div>
      ) : null}
      <div className="stack">
        {data?.items.map((v) => (
          <div key={v.id} className="card" style={{ padding: 14 }}>
            <div className="row between">
              <div>
                <b>{v.name}</b> {v.pre_approved ? <Badge status="green" text="Pre-approved" /> : null}
                <div className="small muted">
                  {v.purpose} · {v.property_label || "Common area"} {v.phone ? `· ${v.phone}` : ""} {v.vehicle_number ? `· ${v.vehicle_number}` : ""}
                </div>
                <div className="small muted">
                  {v.entry_at ? `In ${fmtTime(v.entry_at)}` : `Registered ${fmtDateTime(v.created_at)}`} {v.exit_at ? `· Out ${fmtTime(v.exit_at)}` : ""}
                </div>
              </div>
              <div className="row">
                <Badge status={v.status} />
                {v.status === "pending_approval" && (resident || me?.role === "layout_admin") ? (
                  <>
                    <button className="btn small primary" onClick={() => action(v, "decision", { approve: true })}>
                      Approve
                    </button>
                    <button className="btn small" onClick={() => action(v, "decision", { approve: false })}>
                      Deny
                    </button>
                  </>
                ) : null}
                {guard && v.status === "approved" ? (
                  <button className="btn small primary" onClick={() => action(v, "entry")}>
                    Mark entry
                  </button>
                ) : null}
                {guard && v.status === "inside" ? (
                  <button className="btn small" onClick={() => action(v, "exit")}>
                    Mark exit
                  </button>
                ) : null}
                {guard && ["inside", "pending_approval", "approved"].includes(v.status) ? (
                  <button className="btn small ghost" onClick={() => setPhotoFor(v)}>
                    Photo
                  </button>
                ) : null}
              </div>
            </div>
          </div>
        ))}
      </div>
      {data ? <Pager total={data.total} limit={data.limit} offset={offset} onChange={setOffset} /> : null}

      <Dialog title={resident ? "Pre-approve a visitor" : "Register visitor"} open={open} onClose={() => setOpen(false)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const body = {
              name: f.name, phone: f.phone || null, purpose: f.purpose, property_id: f.property_id || (resident ? lookups.properties[0]?.id : null) || null,
              host_name: f.host || null, vehicle_number: f.vehicle || null, expected_at: f.expected ? new Date(f.expected).toISOString() : null,
            };
            if (!online && me) {
              await enqueue(me.id, "visitor", "create", body, `Visitor: ${f.name}`);
              setOpen(false);
              return toast("Saved offline — will sync when connected");
            }
            if (await act.run(() => api("/visitors", { body }))) {
              setOpen(false);
              reload();
            }
          }}
        >
          <Field label="Visitor name">
            <input required minLength={2} value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field label="Phone">
            <input type="tel" value={f.phone || ""} onChange={(e) => setF({ ...f, phone: e.target.value })} />
          </Field>
          <Field label="Purpose">
            <input required placeholder="Delivery, guest, service…" value={f.purpose || ""} onChange={(e) => setF({ ...f, purpose: e.target.value })} />
          </Field>
          <Field label="Vehicle number">
            <input value={f.vehicle || ""} onChange={(e) => setF({ ...f, vehicle: e.target.value })} />
          </Field>
          {lookups.properties.length > (resident ? 1 : 0) ? (
            <Field label="Host property" full>
              <Select value={f.property_id || ""} onChange={(v) => setF({ ...f, property_id: v })} placeholder={resident ? "My property" : "Common area (no approval needed)"} options={lookups.properties.map((p) => ({ value: p.id, label: `Plot ${p.plot_number}${p.owner_name ? ` · ${p.owner_name}` : ""}` }))} />
            </Field>
          ) : null}
          {resident ? (
            <Field label="Expected at" full>
              <input type="datetime-local" value={f.expected || ""} onChange={(e) => setF({ ...f, expected: e.target.value })} />
            </Field>
          ) : (
            <p className="small muted full">Visitors to a property wait for the resident&apos;s approval unless they were pre-approved.</p>
          )}
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary" disabled={act.pending}>
              {resident ? "Pre-approve" : "Register"}
            </button>
          </div>
        </form>
      </Dialog>
      <Dialog title={`Photo · ${photoFor?.name}`} open={!!photoFor} onClose={() => setPhotoFor(null)}>
        {photoFor ? <CaptureButton entityType="visitor" entityId={photoFor.id} evidenceType="photo" text="Take visitor photo" primary onDone={() => setPhotoFor(null)} /> : null}
      </Dialog>
    </>
  );
}

export default function VisitorsPage() {
  return (
    <Suspense>
      <VisitorsInner />
    </Suspense>
  );
}
