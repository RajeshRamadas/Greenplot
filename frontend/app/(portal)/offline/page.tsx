"use client";

import { useEffect, useState } from "react";
import { Badge, Empty, PageHead } from "@/components/ui";
import { fmtDateTime, label } from "@/lib/format";
import { useOnline } from "@/lib/hooks";
import { clearSynced, discard, flush, listQueue, onQueueChange, type QueuedBlob, type QueuedOp } from "@/lib/offline";

export default function OfflinePage() {
  const online = useOnline();
  const [ops, setOps] = useState<QueuedOp[]>([]);
  const [blobs, setBlobs] = useState<QueuedBlob[]>([]);

  useEffect(() => {
    const load = () => listQueue().then((q) => (setOps(q.ops), setBlobs(q.blobs)));
    load();
    return onQueueChange(load);
  }, []);

  return (
    <>
      <PageHead title="Offline queue" sub="Work captured without a connection. It syncs automatically when you are back online.">
        <button className="btn primary" disabled={!online} onClick={() => flush()}>
          Sync now
        </button>
        <button className="btn" onClick={() => clearSynced()}>
          Clear synced
        </button>
      </PageHead>
      <div className={`alert ${online ? "ok" : "warn"}`} style={{ marginBottom: 16 }}>
        {online ? "Online — queued work is being sent to the server." : "Offline — new entries are stored on this device."}
      </div>
      <div className="card">
        <h2>Actions ({ops.length})</h2>
        {!ops.length ? <Empty title="Nothing queued" /> : null}
        <div className="list">
          {ops.map((o) => (
            <div className="list-item" key={o.client_op_id}>
              <div>
                <div className="title">{o.label}</div>
                <div className="small muted">
                  {label(o.entity)} · {label(o.operation)} · {fmtDateTime(o.client_timestamp)} {o.attempts ? `· ${o.attempts} attempt(s)` : ""}
                </div>
                {o.error ? <div className="small" style={{ color: "var(--red)" }}>{o.error}</div> : null}
              </div>
              <div className="row">
                <Badge status={o.state} />
                {["failed", "conflict"].includes(o.state) ? (
                  <button className="btn small" onClick={() => discard("op", o.client_op_id)}>
                    Discard
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div className="card">
        <h2>Photos & files ({blobs.length})</h2>
        {!blobs.length ? <Empty title="No files waiting" /> : null}
        <div className="list">
          {blobs.map((b) => (
            <div className="list-item" key={b.client_ref}>
              <div>
                <div className="title">{b.label}</div>
                <div className="small muted">
                  {b.filename} · {(b.blob.size / 1024).toFixed(0)} KB · captured {fmtDateTime(b.captured_at)}
                </div>
                <div className="mono muted">SHA-256 {b.sha256.slice(0, 20)}…</div>
                {b.error ? <div className="small" style={{ color: "var(--red)" }}>{b.error}</div> : null}
              </div>
              <div className="row">
                <Badge status={b.state} />
                {b.state === "failed" ? (
                  <button className="btn small" onClick={() => discard("blob", b.client_ref)}>
                    Discard
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
