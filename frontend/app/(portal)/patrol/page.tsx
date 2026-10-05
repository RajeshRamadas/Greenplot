"use client";

import { useCallback, useState } from "react";
import { QrScanner } from "@/components/QrScanner";
import { Badge, Dialog, Empty, ErrorBox, Field, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getPosition } from "@/lib/capture";
import { fmtDateTime, fmtTime } from "@/lib/format";
import { useAction, useApi, useOnline } from "@/lib/hooks";
import { enqueue, newId } from "@/lib/offline";
import type { PatrolRoute, PatrolRun } from "@/lib/types";

/** Offline patrol keeps its state locally and references the queued start operation. */
interface LocalRun {
  opId: string;
  route: PatrolRoute;
  scanned: string[];
}

export default function PatrolPage() {
  const { me, can } = useAuth();
  const online = useOnline();
  const toast = useToast();
  const act = useAction();
  const routes = useApi<PatrolRoute[]>("/patrol/routes");
  const runs = useApi<PatrolRun[]>("/patrol/runs", { limit: 20 });
  const [active, setActive] = useState<PatrolRun | null>(null);
  const [local, setLocal] = useState<LocalRun | null>(null);
  const [exception, setException] = useState("");
  const [newRoute, setNewRoute] = useState(false);
  const [f, setF] = useState({ name: "", checkpoints: "" });

  const current = active ?? runs.data?.find((r) => r.status === "in_progress" && me?.role === "guard") ?? null;
  const route = local?.route ?? routes.data?.find((r) => r.id === current?.route_id);

  async function start(r: PatrolRoute) {
    if (!me) return;
    if (!online) {
      const opId = newId("patrol");
      await enqueue(me.id, "patrol", "start", { route_id: r.id }, `Patrol start: ${r.name}`, opId);
      setLocal({ opId, route: r, scanned: [] });
      return;
    }
    const run = await act.run(() => api<PatrolRun>(`/patrol/routes/${r.id}/start`, { method: "POST" }));
    if (run) setActive(run);
  }

  const onCode = useCallback(
    async (code: string, method: "qr" | "nfc" | "manual") => {
      if (!me) return;
      const pos = await getPosition(3000);
      const payload = { code, method, exception: exception || null, latitude: pos?.latitude, longitude: pos?.longitude };
      if (local || !online) {
        const cp = route?.checkpoints.find((c) => c.qr_code === code || c.nfc_id === code);
        await enqueue(me.id, "patrol", "scan", { ...payload, ...(local ? { run_op_id: local.opId } : { run_id: current?.id }) }, `Checkpoint: ${cp?.name ?? code}`);
        if (local) setLocal({ ...local, scanned: [...local.scanned, cp?.id ?? code] });
        setException("");
        return toast(`${cp?.name ?? "Checkpoint"} recorded offline`);
      }
      if (!current) return;
      const run = await act.run(() => api<PatrolRun>(`/patrol/runs/${current.id}/scan`, { body: payload }));
      if (run) {
        setActive(run);
        setException("");
        toast("Checkpoint recorded");
      }
    },
    [me, exception, local, online, route, current, act, toast],
  );

  async function finish() {
    if (!me) return;
    if (local) {
      await enqueue(me.id, "patrol", "finish", { run_op_id: local.opId }, `Patrol finish: ${local.route.name}`);
      setLocal(null);
      return toast("Patrol saved offline");
    }
    if (!current) return;
    const run = await act.run(() => api<PatrolRun>(`/patrol/runs/${current.id}/finish`, { body: {} }));
    if (run) {
      setActive(null);
      runs.reload();
      toast(run.status === "completed" ? "Patrol complete" : "Patrol finished with missed checkpoints");
    }
  }

  const scannedIds = local ? local.scanned : (current?.scans.map((s) => s.checkpoint_id) ?? []);

  return (
    <>
      <PageHead title="Patrol" sub="Scan each checkpoint's QR or NFC tag along the route. Works offline.">
        {can("patrol.manage") ? (
          <button className="btn" onClick={() => setNewRoute(true)}>
            New route
          </button>
        ) : null}
      </PageHead>
      <ErrorBox error={act.error || routes.error} />
      {(current || local) && route ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-head">
            <h2>On patrol · {route.name}</h2>
            <Badge status="in_progress" text={`${new Set(scannedIds).size}/${route.checkpoints.length} checkpoints`} />
          </div>
          <div className="list" style={{ marginBottom: 14 }}>
            {route.checkpoints.map((c) => (
              <div key={c.id} className="list-item">
                <span>{c.name}</span>
                {scannedIds.includes(c.id) ? <Badge status="completed" text="Scanned" /> : <Badge status="grey" text="Pending" />}
              </div>
            ))}
          </div>
          {me?.role === "guard" ? (
            <>
              <Field label="Exception at this checkpoint (optional)">
                <input placeholder="e.g. light not working, gate open" value={exception} onChange={(e) => setException(e.target.value)} />
              </Field>
              <div style={{ marginTop: 10 }}>
                <QrScanner onCode={onCode} />
              </div>
              <button className="btn primary big" style={{ marginTop: 14 }} onClick={finish}>
                Finish patrol
              </button>
            </>
          ) : null}
        </div>
      ) : null}
      {!current && !local && can("patrol.perform") ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2>Start a patrol</h2>
          {!routes.data?.length ? <Empty title="No routes configured" /> : null}
          <div className="stack">
            {routes.data?.map((r) => (
              <button key={r.id} className="btn big" onClick={() => start(r)}>
                {r.name} · {r.checkpoints.length} checkpoints
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <div className="card">
        <h2>Recent patrols</h2>
        {runs.data && !runs.data.length ? <Empty title="No patrols yet" /> : null}
        {runs.data?.map((r) => (
          <div key={r.id} className="list-item">
            <div>
              <div className="title">{r.route_name}</div>
              <div className="small muted">
                {r.guard_name} · {fmtDateTime(r.started_at)} {r.completed_at ? `– ${fmtTime(r.completed_at)}` : ""} · {r.scans.length}/{r.checkpoints_total} scanned
                {r.scans.some((s) => s.exception) ? ` · ${r.scans.filter((s) => s.exception).length} exception(s)` : ""}
              </div>
            </div>
            <Badge status={r.status} />
          </div>
        ))}
      </div>
      {can("patrol.manage") && routes.data?.length ? (
        <div className="card">
          <h2>Checkpoint labels</h2>
          {routes.data.map((r) => (
            <div key={r.id} style={{ marginBottom: 10 }}>
              <b>{r.name}</b>
              <div className="small muted">
                {r.checkpoints.map((c) => (
                  <span key={c.id} style={{ marginRight: 12 }}>
                    {c.name}: <span className="mono">{c.qr_code}</span>
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
      <Dialog title="New patrol route" open={newRoute} onClose={() => setNewRoute(false)}>
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            const checkpoints = f.checkpoints.split("\n").map((s) => s.trim()).filter(Boolean).map((name, position) => ({ name, position }));
            if (await act.run(() => api("/patrol/routes", { body: { name: f.name, checkpoints } }))) {
              setNewRoute(false);
              routes.reload();
            }
          }}
        >
          <Field label="Route name">
            <input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field label="Checkpoints (one per line, in order)" hint="QR codes are generated for each checkpoint">
            <textarea required value={f.checkpoints} onChange={(e) => setF({ ...f, checkpoints: e.target.value })} />
          </Field>
          <div className="actions">
            <button className="btn primary">Create route</button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
