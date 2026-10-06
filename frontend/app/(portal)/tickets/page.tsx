"use client";

import Link from "next/link";
import { useState } from "react";
import { NewTicketDialog, TicketTable } from "@/components/Tickets";
import { Empty, ErrorBox, Loading, PageHead, Pager, Select, Stat } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { fmtDateTime, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Page, TicketCategory, TicketDashboard, TicketSummary } from "@/lib/types";

type Tab = { key: string; label: string; query: Record<string, string> };

const OFFICE_TABS: Tab[] = [
  { key: "active", label: "All open", query: { bucket: "active" } },
  { key: "new", label: "New", query: { bucket: "new" } },
  { key: "unassigned", label: "Unassigned", query: { bucket: "unassigned" } },
  { key: "assigned", label: "Assigned", query: { bucket: "assigned" } },
  { key: "in_progress", label: "In progress", query: { status: "in_progress" } },
  { key: "sla_at_risk", label: "SLA at risk", query: { bucket: "sla_at_risk" } },
  { key: "sla_breached", label: "SLA breached", query: { bucket: "sla_breached" } },
  { key: "awaiting_verification", label: "Awaiting verification", query: { bucket: "awaiting_verification" } },
  { key: "resolved", label: "Resolved", query: { bucket: "resolved" } },
  { key: "reopened", label: "Reopened", query: { bucket: "reopened" } },
  { key: "closed", label: "Closed", query: { bucket: "closed" } },
  { key: "all", label: "All", query: {} },
];
const ASSIGNEE_TABS: Tab[] = [
  { key: "new_assignments", label: "New assignments", query: { bucket: "new_assignments" } },
  { key: "accepted", label: "Accepted", query: { bucket: "accepted" } },
  { key: "in_progress", label: "In progress", query: { status: "in_progress" } },
  { key: "awaiting_verification", label: "Awaiting verification", query: { bucket: "awaiting_verification" } },
  { key: "completed", label: "Completed", query: { bucket: "completed" } },
  { key: "rejected", label: "Rejected", query: {} },
];
const CUSTOMER_TABS: Tab[] = [
  { key: "all", label: "All", query: {} },
  { key: "open", label: "Open", query: { bucket: "open" } },
  { key: "in_progress", label: "In progress", query: { bucket: "in_progress" } },
  { key: "resolved", label: "Resolved", query: { bucket: "resolved" } },
  { key: "closed", label: "Closed", query: { bucket: "closed" } },
  { key: "reopened", label: "Reopened", query: { bucket: "reopened" } },
];

export default function TicketsPage() {
  const { me, can } = useAuth();
  const office = can("tickets.manage");
  const assignee = !office && can("tickets.work");
  const tabs = office ? OFFICE_TABS : assignee ? ASSIGNEE_TABS : CUSTOMER_TABS;
  const [tab, setTab] = useState(tabs[0].key);
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState("");
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"list" | "reports">("list");
  const current = tabs.find((t) => t.key === tab) ?? tabs[0];
  const dash = useApi<TicketDashboard>("/tickets/dashboard");
  const cats = useApi<TicketCategory[]>(office ? "/tickets/categories" : null);
  const list = useApi<Page<TicketSummary>>(tab === "rejected" || view === "reports" ? null : "/tickets", {
    ...current.query,
    q,
    category,
    priority,
    limit: 50,
    offset,
  });
  const counts = dash.data?.buckets ?? dash.data?.sections ?? dash.data?.tabs ?? {};
  const k = dash.data?.kpis;

  function pick(key: string) {
    setTab(key);
    setOffset(0);
  }

  const sub = office
    ? "Customer requests: review, assign to staff or vendors, verify proof of work and close."
    : assignee
      ? "Tickets assigned to you. Accept or reject, do the work with proof, and submit for verification."
      : "Raise a service request and follow it until it's fixed.";

  return (
    <>
      <PageHead title={assignee ? "My service tickets" : office ? "Service tickets" : "My service tickets"} sub={sub}>
        {office ? (
          <button className="btn" onClick={() => setView(view === "list" ? "reports" : "list")}>
            {view === "list" ? "Reports" : "Ticket list"}
          </button>
        ) : null}
        {can("tickets.create") ? (
          <button className="btn primary" onClick={() => setOpen(true)}>
            Raise ticket
          </button>
        ) : null}
      </PageHead>

      {office && k ? (
        <div className="stats">
          <Stat label="Open tickets" value={k.open} />
          <Stat label="In progress" value={k.in_progress} />
          <Stat label="SLA at risk" value={k.sla_at_risk} kind={k.sla_at_risk ? "warn" : undefined} />
          <Stat label="Resolved today" value={k.resolved_today} />
          <Stat label="Closed today" value={k.closed_today} />
          <Stat label="SLA breached" value={k.sla_breached} kind={k.sla_breached ? "alert" : undefined} />
        </div>
      ) : null}

      {view === "reports" ? (
        <TicketReports />
      ) : (
        <>
          <div className="tabs" role="tablist">
            {tabs.map((t) => (
              <button key={t.key} role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""} onClick={() => pick(t.key)}>
                {t.label}
                {counts[t.key] ? <span className="muted"> ({counts[t.key]})</span> : null}
              </button>
            ))}
          </div>
          {tab !== "rejected" ? (
            <div className="filters">
              <input type="search" placeholder="Search number or text" value={q} onChange={(e) => (setQ(e.target.value), setOffset(0))} />
              {office ? (
                <>
                  <Select value={category} onChange={(v) => (setCategory(v), setOffset(0))} placeholder="Any category" options={(cats.data ?? []).map((c) => ({ value: c.code, label: c.name }))} />
                  <Select value={priority} onChange={(v) => (setPriority(v), setOffset(0))} placeholder="Any priority" options={["critical", "high", "medium", "low"]} />
                </>
              ) : null}
            </div>
          ) : null}
          <ErrorBox error={list.error || dash.error} />
          {tab === "rejected" ? (
            <div className="card">
              <h2>Assignments you rejected</h2>
              {!dash.data?.rejected?.length ? <Empty title="Nothing rejected" /> : null}
              <div className="list">
                {dash.data?.rejected?.map((r) => (
                  <div key={r.ticket_id + r.rejected_at} className="list-item">
                    <div>
                      <div className="title">
                        <span className="mono">{r.number}</span> · {r.title}
                      </div>
                      <div className="small muted">{r.reason}</div>
                    </div>
                    <span className="small muted">{fmtDateTime(r.rejected_at)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <>
              {list.loading && !list.data ? <Loading /> : null}
              {list.data && !list.data.items.length ? (
                <div className="card">
                  <Empty title={tab === tabs[0].key ? "No tickets yet" : `No ${current.label.toLowerCase()} tickets`}>
                    {can("tickets.create") && !office ? (
                      <p>
                        Something not working?{" "}
                        <button className="btn small primary" onClick={() => setOpen(true)}>
                          Raise a ticket
                        </button>
                      </p>
                    ) : null}
                  </Empty>
                </div>
              ) : null}
              {list.data?.items.length ? <TicketTable items={list.data.items} showCustomer={office || assignee} /> : null}
              {list.data ? <Pager total={list.data.total} limit={list.data.limit} offset={offset} onChange={setOffset} /> : null}
            </>
          )}
        </>
      )}
      {me ? <NewTicketDialog open={open} onClose={() => (setOpen(false), list.reload(), dash.reload())} /> : null}
    </>
  );
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function TicketReports() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const { data, error, loading } = useApi<Record<string, any>>("/tickets/reports", {
    date_from: from ? new Date(from).toISOString() : undefined,
    date_to: to ? new Date(to + "T23:59:59").toISOString() : undefined,
  });
  const hrs = (v: number | null) => (v == null ? "—" : `${v} h`);
  return (
    <>
      <div className="filters">
        <label className="small">
          From <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="small">
          To <input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data ? (
        <div className="stack" style={{ gap: 16 }}>
          <div className="grid two">
            <div className="card">
              <h2>Ticket volume</h2>
              <dl className="kv">
                {Object.entries(data.volume).map(([k, v]) => (
                  <Kv key={k} k={label(k)} v={String(v)} />
                ))}
              </dl>
            </div>
            <div className="card">
              <h2>SLA</h2>
              <dl className="kv">
                <Kv k="Met" v={data.sla.met} />
                <Kv k="Breached" v={data.sla.breached} />
                <Kv k="Avg. first response" v={hrs(data.sla.avg_response_hours)} />
                <Kv k="Avg. resolution" v={hrs(data.sla.avg_resolution_hours)} />
              </dl>
            </div>
          </div>
          <div className="card">
            <h2>Vendor & staff performance</h2>
            {!data.vendors.length ? <Empty title="No assignments in this period" /> : null}
            {data.vendors.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Assignee</th>
                      <th>Assigned</th>
                      <th>Accepted</th>
                      <th>Rejected</th>
                      <th>Completed</th>
                      <th>Reopened</th>
                      <th>Rework rate</th>
                      <th>Avg. accept</th>
                      <th>Avg. completion</th>
                      <th>SLA breaches</th>
                      <th>Rating</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.vendors.map((v: any) => (
                      <tr key={v.assignee_id}>
                        <td>
                          <b>{v.name}</b>
                          <div className="small muted">{label(v.assignee_type)}</div>
                        </td>
                        <td>{v.assigned}</td>
                        <td>{v.accepted}</td>
                        <td>{v.rejected}</td>
                        <td>{v.completed}</td>
                        <td>{v.reopened}</td>
                        <td>{v.rework_rate == null ? "—" : `${Math.round(v.rework_rate * 100)}%`}</td>
                        <td>{hrs(v.avg_accept_hours)}</td>
                        <td>{hrs(v.avg_completion_hours)}</td>
                        <td>{v.sla_breaches}</td>
                        <td>{v.avg_rating ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
          <div className="grid two">
            <div className="card">
              <h2>By category</h2>
              {data.categories.map((c: any) => (
                <div key={c.category} className="list-item">
                  <div className="title">{c.category}</div>
                  <span className="small muted">
                    {c.count} · avg {hrs(c.avg_resolution_hours)}
                  </span>
                </div>
              ))}
              {!data.categories.length ? <Empty title="No tickets" /> : null}
            </div>
            <div className="card">
              <h2>By property</h2>
              {data.properties.map((p: any) => (
                <Link key={p.property_id} href={`/properties/${p.property_id}`} className="list-item">
                  <div className="title">{p.property}</div>
                  <span className="small muted">
                    {p.count} tickets{p.repeat_complaints ? ` · ${p.repeat_complaints} repeat` : ""}
                  </span>
                </Link>
              ))}
              {!data.properties.length ? <Empty title="No tickets" /> : null}
              <div className="divider" />
              <h3>Customer satisfaction</h3>
              <dl className="kv">
                <Kv k="Average rating" v={data.satisfaction.avg_rating == null ? "—" : `${data.satisfaction.avg_rating} / 5`} />
                <Kv k="Ratings" v={data.satisfaction.ratings} />
                <Kv k="Confirmed resolved" v={data.satisfaction.confirmed_resolved} />
                <Kv k="Reopened" v={data.satisfaction.reopened} />
              </dl>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}

function Kv({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <>
      <dt>{k}</dt>
      <dd>{v}</dd>
    </>
  );
}
