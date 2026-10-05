"use client";

import { useState } from "react";
import { ErrorBox, Loading, PageHead, Pager, Select } from "@/components/ui";
import { fmtDateTime, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { linkFor } from "@/lib/links";
import type { AuditEntry, Page } from "@/lib/types";

function short(v: Record<string, unknown> | null) {
  if (!v) return "";
  return Object.entries(v)
    .slice(0, 4)
    .map(([k, x]) => `${k}: ${typeof x === "object" ? JSON.stringify(x) : String(x)}`)
    .join(" · ");
}

export default function AuditPage() {
  const [entity, setEntity] = useState("");
  const [action, setAction] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error, loading } = useApi<Page<AuditEntry>>("/audit", { entity_type: entity, action, limit: 100, offset });
  return (
    <>
      <PageHead title="Audit log" sub="Every important action: who, what, when, before and after. Entries are append-only." />
      <div className="filters">
        <Select
          value={entity}
          onChange={setEntity}
          placeholder="All records"
          options={["maintenance_task", "complaint", "inspection", "incident", "property", "user", "payment", "invoice", "media", "tenant", "evidence_policy", "sos", "visitor"]}
        />
        <input placeholder="Action starts with… e.g. maintenance.approve" value={action} onChange={(e) => setAction(e.target.value)} />
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Action</th>
                <th>Record</th>
                <th>Change</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => {
                const href = linkFor(a.entity_type, a.entity_id);
                return (
                  <tr key={a.id}>
                    <td className="small">{fmtDateTime(a.timestamp)}</td>
                    <td>
                      {a.actor_name || "System"}
                      <div className="small muted">{label(a.actor_role)}</div>
                    </td>
                    <td className="mono">{a.action}</td>
                    <td>{href ? <a href={href}>{label(a.entity_type)}</a> : label(a.entity_type)}</td>
                    <td className="small" style={{ maxWidth: 360 }}>
                      {a.old_value ? <div className="muted">− {short(a.old_value)}</div> : null}
                      {a.new_value ? <div>+ {short(a.new_value)}</div> : null}
                    </td>
                    <td className="small muted">{a.ip || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
      {data ? <Pager total={data.total} limit={data.limit} offset={offset} onChange={setOffset} /> : null}
    </>
  );
}
