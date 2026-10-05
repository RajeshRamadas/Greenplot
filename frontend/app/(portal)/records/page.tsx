"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Empty, ErrorBox, Loading, PageHead, Select } from "@/components/ui";
import { fmtDate, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { linkFor } from "@/lib/links";
import type { SearchHit } from "@/lib/types";

const EXAMPLES = ["Show all gate repairs for Plot 117 in the last 12 months", "open complaints", "overdue maintenance", "streetlight", "GP-MNT-2026-00001"];

/** Digital records search across every module (requirements §23). */
export default function RecordsPage() {
  const [input, setInput] = useState("");
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const enabled = !!(q || type || from);
  const { data, error, loading } = useApi<{ interpreted: Record<string, unknown>; total: number; items: SearchHit[] }>(enabled ? "/records/search" : null, {
    q,
    type,
    date_from: from ? new Date(from).toISOString() : undefined,
    date_to: to ? new Date(`${to}T23:59:59`).toISOString() : undefined,
    limit: 100,
  });

  return (
    <>
      <PageHead title="Digital records" sub="Search maintenance, complaints, inspections, incidents, assets, properties, vendors and staff — in plain language." />
      <form
        className="card"
        onSubmit={(e) => {
          e.preventDefault();
          setQ(input.trim());
        }}
      >
        <div className="row">
          <input type="search" placeholder="e.g. gate repairs for Plot 117 in the last 12 months" value={input} onChange={(e) => setInput(e.target.value)} style={{ flex: 1, minWidth: 220, fontSize: 16 }} />
          <button className="btn primary">Search</button>
        </div>
        <div className="filters" style={{ marginTop: 12, marginBottom: 0 }}>
          <Select value={type} onChange={setType} placeholder="All record types" options={["maintenance", "complaint", "inspection", "incident", "asset", "property", "vendor", "staff"]} />
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From date" />
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To date" />
        </div>
        <div className="row small" style={{ marginTop: 10 }}>
          <span className="muted">Try:</span>
          {EXAMPLES.map((x) => (
            <button key={x} type="button" className="btn small ghost" onClick={() => (setInput(x), setQ(x))}>
              {x}
            </button>
          ))}
        </div>
      </form>
      <ErrorBox error={error} />
      {loading ? <Loading /> : null}
      {data ? (
        <div className="card">
          <div className="card-head">
            <h2>{data.total} records</h2>
            {Object.keys(data.interpreted).length ? (
              <span className="small muted">
                Understood as:{" "}
                {Object.entries(data.interpreted)
                  .map(([k, v]) => `${label(k)}: ${Array.isArray(v) ? v.join("/") : k === "date_from" ? fmtDate(String(v)) : String(v)}`)
                  .join(" · ")}
              </span>
            ) : null}
          </div>
          {!data.items.length ? <Empty title="No matching records" /> : null}
          <div className="list">
            {data.items.map((h) => {
              const href = linkFor(h.type, h.id) ?? "#";
              return (
                <Link key={`${h.type}-${h.id}`} href={href} className="list-item">
                  <div>
                    <div className="title">
                      <Badge status="grey" text={label(h.type)} /> {h.title}
                    </div>
                    <div className="small muted">
                      {h.number ? <span className="mono">{h.number}</span> : null} {h.category ? `· ${label(h.category)}` : ""} {h.property_label ? `· ${h.property_label}` : ""}{" "}
                      {h.date ? `· ${fmtDate(h.date)}` : ""}
                    </div>
                  </div>
                  {h.status ? <Badge status={h.status} /> : null}
                </Link>
              );
            })}
          </div>
        </div>
      ) : null}
    </>
  );
}
