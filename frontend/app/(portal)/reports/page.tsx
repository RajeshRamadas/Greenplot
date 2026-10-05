"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Empty, ErrorBox, Loading, PageHead, Select, Stat, useToast } from "@/components/ui";
import { download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, inr, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";

interface Row {
  id: string;
  number: string;
  title: string;
  category: string;
  status: string;
  plot: string | null;
  staff: string | null;
  vendor: string | null;
  created_at: string;
  completed_at: string | null;
  approved_at: string | null;
  rework_count: number;
  evidence_items: number;
  materials_cost: number;
  work_hours: number | null;
  approval_hours: number | null;
  overdue: boolean;
}

const REPORTS = [
  ["history", "Maintenance history"],
  ["pending", "Pending work"],
  ["completed", "Completed work"],
  ["rework", "Rework"],
  ["cost", "Maintenance cost"],
  ["proof", "Proof-of-work records"],
];

export default function ReportsPage() {
  const { meta } = useAuth();
  const lookups = useLookups();
  const toast = useToast();
  const [report, setReport] = useState("history");
  const [f, setF] = useState<Record<string, string>>({});
  const query = {
    report,
    date_from: f.from ? new Date(f.from).toISOString() : undefined,
    date_to: f.to ? new Date(`${f.to}T23:59:59`).toISOString() : undefined,
    property_id: f.property || undefined,
    category: f.category ? [f.category] : undefined,
    staff_id: f.staff || undefined,
    vendor_id: f.vendor || undefined,
    status: f.status ? [f.status] : undefined,
    approval: f.approval || undefined,
  };
  const { data, error, loading } = useApi<{ summary: { count: number; materials_cost: number; rework_tasks: number; overdue: number; by_category: Record<string, number> }; rows: Row[] }>(
    "/reports/maintenance",
    query,
  );

  return (
    <>
      <PageHead title="Reports" sub="Filter, review and export maintenance records. Download a Proof of Work PDF from any approved task.">
        <button className="btn" onClick={() => download("/reports/maintenance", { ...query, format: "csv" }).catch((e) => toast(e.message, "error"))}>
          Export CSV
        </button>
        <Link className="btn" href="/vendors">
          Vendor performance
        </Link>
      </PageHead>
      <div className="tabs">
        {REPORTS.map(([k, l]) => (
          <button key={k} className={report === k ? "on" : ""} onClick={() => setReport(k)}>
            {l}
          </button>
        ))}
      </div>
      <div className="filters">
        <input type="date" value={f.from || ""} onChange={(e) => setF({ ...f, from: e.target.value })} aria-label="From" />
        <input type="date" value={f.to || ""} onChange={(e) => setF({ ...f, to: e.target.value })} aria-label="To" />
        <Select value={f.property || ""} onChange={(v) => setF({ ...f, property: v })} placeholder="Any property" options={lookups.properties.map((p) => ({ value: p.id, label: `Plot ${p.plot_number}` }))} />
        <Select value={f.category || ""} onChange={(v) => setF({ ...f, category: v })} placeholder="Any category" options={meta?.task_categories ?? []} />
        <Select value={f.staff || ""} onChange={(v) => setF({ ...f, staff: v })} placeholder="Any staff" options={lookups.staff.map((u) => ({ value: u.id, label: u.full_name }))} />
        <Select value={f.vendor || ""} onChange={(v) => setF({ ...f, vendor: v })} placeholder="Any vendor" options={lookups.vendors.map((v) => ({ value: v.id, label: v.name }))} />
        <Select value={f.status || ""} onChange={(v) => setF({ ...f, status: v })} placeholder="Any status" options={meta?.task_statuses ?? []} />
        <Select value={f.approval || ""} onChange={(v) => setF({ ...f, approval: v })} placeholder="Any approval" options={["pending", "approved", "rework"]} />
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data ? (
        <>
          <div className="stats">
            <Stat label="Tasks" value={data.summary.count} />
            <Stat label="Materials cost" value={inr(data.summary.materials_cost)} />
            <Stat label="With rework" value={data.summary.rework_tasks} />
            <Stat label="Overdue" value={data.summary.overdue} kind={data.summary.overdue ? "alert" : undefined} />
          </div>
          {!data.rows.length ? <Empty title="No records match" /> : null}
          {data.rows.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Record</th>
                    <th>Task</th>
                    <th>Plot</th>
                    <th>Staff / vendor</th>
                    <th>Completed</th>
                    <th>Evidence</th>
                    <th>Cost</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r) => (
                    <tr key={r.id}>
                      <td className="mono">
                        <Link href={`/maintenance/${r.id}`}>{r.number}</Link>
                      </td>
                      <td>
                        {r.title}
                        <div className="small muted">
                          {label(r.category)} {r.work_hours != null ? `· ${r.work_hours} h` : ""}
                        </div>
                      </td>
                      <td>{r.plot ?? "—"}</td>
                      <td>{[r.staff, r.vendor].filter(Boolean).join(" / ") || "—"}</td>
                      <td>{fmtDate(r.completed_at)}</td>
                      <td>{r.evidence_items}</td>
                      <td>{r.materials_cost ? inr(r.materials_cost) : "—"}</td>
                      <td>
                        <Badge status={r.status} />
                        {r.rework_count ? <div className="small muted">Rework ×{r.rework_count}</div> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      ) : null}
    </>
  );
}
