"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CaptureButton } from "@/components/Capture";
import { MediaGallery } from "@/components/MediaGallery";
import { NewTaskDialog, TaskCard } from "@/components/Tasks";
import { Badge, Empty, ErrorBox, Loading, PageHead } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Asset, TaskSummary } from "@/lib/types";

export default function AssetPage() {
  const { id } = useParams<{ id: string }>();
  const { can } = useAuth();
  const { data, error, loading } = useApi<{ asset: Asset; maintenance: TaskSummary[] }>(`/assets/${id}/history`);
  const [qr, setQr] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [mediaKey, setMediaKey] = useState(0);

  useEffect(() => {
    let url: string | null = null;
    api<Response>(`/assets/${id}/qr.svg`, { raw: true })
      .then((r) => r.blob())
      .then((b) => setQr((url = URL.createObjectURL(b))))
      .catch(() => {});
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [id]);

  if (loading && !data) return <Loading />;
  if (!data) return <ErrorBox error={error || "Not found"} />;
  const a = data.asset;
  return (
    <>
      <PageHead title={a.name} sub={<><span className="mono">{a.code}</span> · {label(a.category)} · {a.location || "No location"}</>}>
        <Badge status={a.condition} />
        {can("maintenance.create") ? (
          <button className="btn primary" onClick={() => setCreating(true)}>
            Create maintenance
          </button>
        ) : null}
      </PageHead>
      <div className="grid side">
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <h2>Maintenance history</h2>
            {!data.maintenance.length ? <Empty title="No maintenance recorded" /> : null}
            <div className="stack">
              {data.maintenance.map((t) => (
                <TaskCard key={t.id} t={t} />
              ))}
            </div>
          </div>
          <div className="card">
            <h2>Documents & media</h2>
            <MediaGallery entityType="asset" entityId={a.id} refreshKey={mediaKey} />
            {can("assets.manage") ? (
              <div style={{ marginTop: 10, maxWidth: 260 }}>
                <CaptureButton entityType="asset" entityId={a.id} evidenceType="warranty" text="Upload warranty / manual" onDone={() => setMediaKey((k) => k + 1)} />
              </div>
            ) : null}
          </div>
        </div>
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <h2>QR label</h2>
            {qr ? <img src={qr} alt={`QR code ${a.qr_code}`} style={{ width: 220, margin: "0 auto" }} /> : null}
            <p className="mono muted" style={{ textAlign: "center", marginTop: 6 }}>
              {a.qr_code}
            </p>
            {qr ? (
              <a className="btn block" href={qr} download={`${a.code}-qr.svg`} style={{ marginTop: 10 }}>
                Download label
              </a>
            ) : null}
          </div>
          <div className="card">
            <h2>Details</h2>
            <dl className="kv" style={{ gridTemplateColumns: "110px 1fr" }}>
              <dt>NFC tag</dt>
              <dd>{a.nfc_id || "—"}</dd>
              <dt>Installed</dt>
              <dd>{fmtDate(a.installed_on)}</dd>
              <dt>Warranty</dt>
              <dd>{fmtDate(a.warranty_until)}</dd>
              <dt>Service every</dt>
              <dd>{a.service_interval_days ? `${a.service_interval_days} days` : "—"}</dd>
              <dt>Next service</dt>
              <dd>{fmtDate(a.next_service_due)}</dd>
              <dt>Notes</dt>
              <dd>{a.notes || "—"}</dd>
            </dl>
          </div>
        </div>
      </div>
      {creating ? <NewTaskDialog open onClose={() => setCreating(false)} preset={{ asset_id: a.id, category: "asset_servicing", title: `Service ${a.name}` }} /> : null}
    </>
  );
}
