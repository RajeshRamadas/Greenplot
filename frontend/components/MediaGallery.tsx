"use client";

import { fmtDateTime, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { MediaItem } from "@/lib/types";

export function MediaGallery({ entityType, entityId, items, refreshKey }: { entityType?: string; entityId?: string; items?: MediaItem[] | null; refreshKey?: number }) {
  const fetched = useApi<MediaItem[]>(!items && entityType && entityId ? "/media" : null, { entity_type: entityType, entity_id: entityId, k: refreshKey });
  const list = items ?? fetched.data ?? [];
  if (!list.length) return <p className="small muted">No photos or files yet.</p>;
  return (
    <div className="evidence-grid">
      {list.map((m) => (
        <a key={m.id} className="evidence-tile" href={m.url || undefined} target="_blank" rel="noreferrer" style={{ color: "inherit", textDecoration: "none" }}>
          <div className="thumb">{m.thumbnail_url ? <img src={m.thumbnail_url} alt="" /> : <span>{m.content_type.includes("pdf") ? "PDF" : m.content_type.startsWith("video") ? "▶ Video" : "File"}</span>}</div>
          <div className="cap">
            <b>{label(m.evidence_type || m.original_filename || "file")}</b>
            <span className="muted">{fmtDateTime(m.captured_at || m.uploaded_at)}</span>
            {m.sha256 ? <span className="mono muted">#{m.sha256.slice(0, 12)}</span> : null}
          </div>
        </a>
      ))}
    </div>
  );
}
