"use client";

import { useState } from "react";
import { Badge, Dialog, Empty, ErrorBox, Field, PageHead, Select, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, label } from "@/lib/format";
import { useAction, useApi, useOnline } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import { enqueue } from "@/lib/offline";
import type { Page, Vehicle, VehicleLog } from "@/lib/types";

export default function VehiclesPage() {
  const { me, can } = useAuth();
  const lookups = useLookups();
  const online = useOnline();
  const toast = useToast();
  const act = useAction();
  const [q, setQ] = useState("");
  const [plate, setPlate] = useState("");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState<Record<string, string>>({ vehicle_type: "car" });
  const vehicles = useApi<Page<Vehicle>>("/vehicles", { q, limit: 200 });
  const logs = useApi<Page<VehicleLog>>(can("vehicles.log") || me?.role === "supervisor" ? "/vehicles/log" : null, { limit: 30 });

  async function log(direction: "in" | "out") {
    if (!plate.trim() || !me) return;
    const body = { vehicle_number: plate, direction };
    if (!online) {
      await enqueue(me.id, "vehicle_log", "create", body, `Vehicle ${direction}: ${plate}`);
      setPlate("");
      return toast("Saved offline");
    }
    if (await act.run(() => api("/vehicles/log", { body }))) {
      toast(`${plate.toUpperCase()} logged ${direction}`);
      setPlate("");
      logs.reload();
    }
  }

  return (
    <>
      <PageHead title="Vehicles" sub="Registered resident vehicles and the gate entry/exit log.">
        {can("vehicles.manage") ? (
          <button className="btn" onClick={() => setOpen(true)}>
            Register vehicle
          </button>
        ) : null}
      </PageHead>
      <ErrorBox error={act.error} />
      {can("vehicles.log") ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2>Gate log</h2>
          <div className="grid three">
            <input placeholder="KA 01 AB 1234" value={plate} onChange={(e) => setPlate(e.target.value)} style={{ fontSize: 18, textTransform: "uppercase" }} />
            <button className="btn primary big" onClick={() => log("in")}>
              Vehicle IN
            </button>
            <button className="btn big" onClick={() => log("out")}>
              Vehicle OUT
            </button>
          </div>
        </div>
      ) : null}
      <div className="grid two">
        <div className="card">
          <h2>Registered vehicles</h2>
          <input type="search" placeholder="Search number" value={q} onChange={(e) => setQ(e.target.value)} style={{ marginBottom: 10 }} />
          {vehicles.data && !vehicles.data.items.length ? <Empty title="No vehicles" /> : null}
          {vehicles.data?.items.map((v) => (
            <div key={v.id} className="list-item">
              <div>
                <div className="title mono">{v.number}</div>
                <div className="small muted">
                  {label(v.vehicle_type)} {v.owner_name ? `· ${v.owner_name}` : ""} {v.make_model ? `· ${v.make_model}` : ""}
                </div>
              </div>
              {can("vehicles.manage") ? (
                <button className="btn small ghost" onClick={() => api(`/vehicles/${v.id}`, { method: "DELETE" }).then(vehicles.reload)}>
                  Remove
                </button>
              ) : null}
            </div>
          ))}
        </div>
        {logs.data ? (
          <div className="card">
            <h2>Recent movements</h2>
            {!logs.data.items.length ? <Empty title="No movements logged" /> : null}
            {logs.data.items.map((l) => (
              <div key={l.id} className="list-item">
                <div>
                  <div className="title mono">{l.vehicle_number}</div>
                  <div className="small muted">{fmtDateTime(l.at)}</div>
                </div>
                <div className="row">
                  {l.is_visitor ? <Badge status="amber" text="Visitor" /> : null}
                  <Badge status={l.direction === "in" ? "inside" : "exited"} text={l.direction.toUpperCase()} />
                </div>
              </div>
            ))}
          </div>
        ) : null}
      </div>
      <Dialog title="Register vehicle" open={open} onClose={() => setOpen(false)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const body = { number: f.number, vehicle_type: f.vehicle_type, owner_name: f.owner || null, make_model: f.model || null, property_id: f.property_id || lookups.properties[0]?.id || null };
            if (await act.run(() => api("/vehicles", { body }))) {
              setOpen(false);
              vehicles.reload();
            }
          }}
        >
          <Field label="Vehicle number">
            <input required value={f.number || ""} onChange={(e) => setF({ ...f, number: e.target.value })} />
          </Field>
          <Field label="Type">
            <Select value={f.vehicle_type} onChange={(v) => setF({ ...f, vehicle_type: v })} options={["car", "bike", "truck", "van", "other"]} />
          </Field>
          <Field label="Owner">
            <input value={f.owner || ""} onChange={(e) => setF({ ...f, owner: e.target.value })} />
          </Field>
          <Field label="Make / model">
            <input value={f.model || ""} onChange={(e) => setF({ ...f, model: e.target.value })} />
          </Field>
          {lookups.properties.length > 1 ? (
            <Field label="Property" full>
              <Select value={f.property_id || ""} onChange={(v) => setF({ ...f, property_id: v })} placeholder="—" options={lookups.properties.map((p) => ({ value: p.id, label: `Plot ${p.plot_number}` }))} />
            </Field>
          ) : null}
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary">Register</button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
