"use client";

import { useState } from "react";
import { Badge, ErrorBox, PageHead } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getPosition } from "@/lib/capture";
import { ago } from "@/lib/format";
import { useAction, useApi, useOnline } from "@/lib/hooks";
import { enqueue } from "@/lib/offline";
import type { Sos } from "@/lib/types";

export default function SosPage() {
  const { me } = useAuth();
  const online = useOnline();
  const act = useAction();
  const [message, setMessage] = useState("");
  const [arming, setArming] = useState(false);
  const mine = useApi<Sos[]>("/sos");

  async function raise() {
    if (!me) return;
    const pos = await getPosition(5000);
    const body = { message: message || null, ...(pos ?? {}) };
    if (!online) {
      await enqueue(me.id, "sos", "create", body, "SOS");
      setArming(false);
      // Offline: the phone call is the dependable path.
      window.location.href = "tel:112";
      return;
    }
    if (await act.run(() => api("/sos", { body }))) {
      setArming(false);
      setMessage("");
      mine.reload();
    }
  }

  return (
    <>
      <PageHead title="SOS" sub="Alerts the security team and layout administrators immediately, with your location." />
      <ErrorBox error={act.error} />
      <div className="card" style={{ maxWidth: 520 }}>
        {!arming ? (
          <button className="sos-btn" onClick={() => setArming(true)}>
            SOS
          </button>
        ) : (
          <div className="stack">
            <textarea placeholder="Optional: what's happening?" value={message} onChange={(e) => setMessage(e.target.value)} autoFocus />
            <button className="sos-btn" onClick={raise} disabled={act.pending}>
              {act.pending ? "Sending…" : "SEND SOS NOW"}
            </button>
            <button className="btn" onClick={() => setArming(false)}>
              Cancel
            </button>
          </div>
        )}
        <p className="small muted" style={{ marginTop: 12 }}>
          In a life-threatening emergency also call <a href="tel:112">112</a>.
        </p>
      </div>
      {mine.data?.length ? (
        <div className="card" style={{ maxWidth: 520 }}>
          <h2>Your active alerts</h2>
          {mine.data.map((s) => (
            <div key={s.id} className="list-item">
              <span>
                Raised {ago(s.created_at)} {s.status === "acknowledged" ? "— help is on the way" : ""}
              </span>
              <div className="row">
                <Badge status={s.status} />
                <button className="btn small ghost" onClick={() => api(`/sos/${s.id}/action`, { body: { action: "false_alarm" } }).then(mine.reload)}>
                  Cancel (false alarm)
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}
