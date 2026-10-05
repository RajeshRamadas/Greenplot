"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { QrScanner } from "@/components/QrScanner";
import { NewTaskDialog, TaskCard } from "@/components/Tasks";
import { Badge, ErrorBox, PageHead } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, label } from "@/lib/format";
import type { Asset, TaskSummary } from "@/lib/types";

/** SCAN QR/NFC → OPEN ASSET → VIEW HISTORY → CREATE MAINTENANCE (requirements §17). */
export default function ScanPage() {
  const { can } = useAuth();
  const [result, setResult] = useState<{ asset: Asset; open_tasks: TaskSummary[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const onCode = useCallback(async (code: string) => {
    setError(null);
    try {
      setResult(await api(`/maintenance/scan/${encodeURIComponent(code)}`));
    } catch (e) {
      setResult(null);
      setError((e as Error).message);
    }
  }, []);

  return (
    <>
      <PageHead title="Scan asset" sub="Scan the QR or NFC tag on a gate, pump, streetlight or other asset." />
      {!result ? (
        <div className="card">
          <QrScanner onCode={onCode} />
          <div style={{ marginTop: 12 }}>
            <ErrorBox error={error} />
          </div>
        </div>
      ) : (
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <div>
                <h2 style={{ marginBottom: 2 }}>{result.asset.name}</h2>
                <span className="mono muted">{result.asset.code}</span>
              </div>
              <Badge status={result.asset.condition} />
            </div>
            <dl className="kv">
              <dt>Category</dt>
              <dd>{label(result.asset.category)}</dd>
              <dt>Location</dt>
              <dd>{result.asset.location || "—"}</dd>
              <dt>Next service</dt>
              <dd>{fmtDate(result.asset.next_service_due)}</dd>
              <dt>Warranty</dt>
              <dd>{fmtDate(result.asset.warranty_until)}</dd>
            </dl>
            <div className="row" style={{ marginTop: 14 }}>
              {can("assets.read") ? (
                <Link className="btn" href={`/assets/${result.asset.id}`}>
                  View history
                </Link>
              ) : null}
              {can("maintenance.create") ? (
                <button className="btn primary" onClick={() => setCreating(true)}>
                  Create maintenance
                </button>
              ) : null}
              <button className="btn ghost" onClick={() => setResult(null)}>
                Scan another
              </button>
            </div>
          </div>
          <h2>Open tasks on this asset</h2>
          {result.open_tasks.length ? result.open_tasks.map((t) => <TaskCard key={t.id} t={t} />) : <p className="muted">No open tasks.</p>}
          {creating ? (
            <NewTaskDialog open onClose={() => setCreating(false)} preset={{ asset_id: result.asset.id, category: "asset_servicing", title: `Service ${result.asset.name}` }} />
          ) : null}
        </div>
      )}
    </>
  );
}
