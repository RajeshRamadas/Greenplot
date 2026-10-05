"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { NewTicketDialog } from "@/components/Tickets";
import { Badge, Empty, ErrorBox, Loading, PageHead, Stat } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { ago, fmtDateTime, inr } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Notice, Page, Sos, TicketDashboard, TicketSummary, Visitor } from "@/lib/types";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Dash = Record<string, any>;

function pct(v: number | null | undefined) {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

function TicketKpis() {
  const { data } = useApi<TicketDashboard>("/tickets/dashboard");
  if (!data?.buckets) return null;
  const b = data.buckets;
  return (
    <>
      <h2 style={{ margin: "4px 0 10px" }}>Service tickets</h2>
      <div className="stats">
        <Stat label="New tickets" value={b.new} href="/tickets" kind={b.new ? "warn" : undefined} />
        <Stat label="Unassigned" value={b.unassigned} href="/tickets" />
        <Stat label="Awaiting verification" value={b.awaiting_verification} href="/tickets" kind={b.awaiting_verification ? "warn" : undefined} />
        <Stat label="SLA at risk" value={b.sla_at_risk} href="/tickets" kind={b.sla_at_risk ? "warn" : undefined} />
        <Stat label="SLA breached" value={b.sla_breached} href="/tickets" kind={b.sla_breached ? "alert" : undefined} />
        <Stat label="Reopened" value={b.reopened} href="/tickets" />
      </div>
    </>
  );
}

function ManagerDashboard({ d }: { d: Dash }) {
  return (
    <>
      <TicketKpis />
      <h2 style={{ margin: "4px 0 10px" }}>Operations</h2>
      <div className="stats">
        <Stat label="Pending approvals" value={d.pending_approvals} href="/approvals" kind={d.pending_approvals ? "warn" : undefined} />
        <Stat label="Active maintenance" value={d.active_maintenance} href="/maintenance" />
        <Stat label="Overdue tasks" value={d.overdue_tasks} href="/maintenance" kind={d.overdue_tasks ? "alert" : undefined} />
        <Stat label="Completed this month" value={d.completed_this_month} href="/reports" />
        <Stat label="Open complaints" value={d.open_complaints} href="/complaints" />
        <Stat label="Open incidents" value={d.open_incidents} href="/incidents" kind={d.open_incidents ? "warn" : undefined} />
        <Stat label="Active SOS" value={d.active_sos} href="/incidents" kind={d.active_sos ? "alert" : undefined} />
        <Stat label="Inspections this month" value={d.inspections_this_month} href="/inspections" />
        <Stat label="Vendor jobs open" value={d.vendor_active_jobs} href="/vendors" />
        <Stat label="Staff jobs open" value={d.staff_active_jobs} href="/staff" />
        <Stat label="Maintenance cost (month)" value={inr(d.maintenance_cost_this_month)} href="/reports" />
        <Stat label="Visitors today" value={d.visitors_today} href="/visitors" />
      </div>
      <div className="grid two">
        <div className="card">
          <div className="card-head">
            <h2>Recent activity</h2>
            <Link href="/maintenance" className="small">
              All maintenance
            </Link>
          </div>
          {!d.recent_activity.length ? <Empty title="No activity yet" /> : null}
          <div className="list">
            {d.recent_activity.map((a: Dash) => (
              <Link key={a.id} href={`/maintenance/${a.id}`} className="list-item">
                <div>
                  <div className="title">{a.title}</div>
                  <div className="small muted">
                    <span className="mono">{a.number}</span>
                    {a.plot ? ` · Plot ${a.plot}` : ""} · {ago(a.updated_at)}
                  </div>
                </div>
                <Badge status={a.status} />
              </Link>
            ))}
          </div>
        </div>
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <h2>Billing status</h2>
            <dl className="kv">
              <dt>Billed</dt>
              <dd>{inr(d.billing.billed)}</dd>
              <dt>Collected</dt>
              <dd>{inr(d.billing.collected)}</dd>
              <dt>Outstanding</dt>
              <dd>
                <b>{inr(d.billing.outstanding)}</b>
              </dd>
            </dl>
          </div>
          <div className="card">
            <h2>Proof-of-work quality (90 days)</h2>
            <dl className="kv">
              <dt>Approved first time</dt>
              <dd>{pct(d.metrics.approved_without_rework)}</dd>
              <dt>Avg. completion time</dt>
              <dd>{d.metrics.avg_completion_hours != null ? `${d.metrics.avg_completion_hours} h` : "—"}</dd>
              <dt>Avg. approval time</dt>
              <dd>{d.metrics.avg_approval_hours != null ? `${d.metrics.avg_approval_hours} h` : "—"}</dd>
              <dt>Approved tasks</dt>
              <dd>{d.metrics.sample}</dd>
            </dl>
          </div>
        </div>
      </div>
    </>
  );
}

function GuardDashboard({ d }: { d: Dash }) {
  const sos = useApi<Sos[]>("/sos");
  const pending = useApi<Page<Visitor>>("/visitors", { status: "pending_approval", limit: 10 });
  return (
    <>
      {sos.data?.length ? (
        <div className="alert error" style={{ marginBottom: 16 }}>
          <b>Active SOS:</b>{" "}
          {sos.data.map((s) => (
            <Link key={s.id} href="/incidents" style={{ color: "inherit", textDecoration: "underline", marginRight: 10 }}>
              {s.raised_by_name} · {ago(s.created_at)}
            </Link>
          ))}
        </div>
      ) : null}
      <div className="stats">
        <Stat label="Visitors inside" value={d.visitors_inside} href="/visitors" />
        <Stat label="Awaiting approval" value={d.awaiting_approval} href="/visitors" kind={d.awaiting_approval ? "warn" : undefined} />
        <Stat label="Visitors today" value={d.visitors_today} href="/visitors" />
        <Stat label="Active SOS" value={d.active_sos} href="/incidents" kind={d.active_sos ? "alert" : undefined} />
        <Stat label="My active patrols" value={d.my_active_patrols} href="/patrol" />
      </div>
      <div className="grid three">
        <Link className="btn primary big" href="/visitors?new=1">
          Register visitor
        </Link>
        <Link className="btn big" href="/vehicles">
          Log vehicle
        </Link>
        <Link className="btn big" href="/patrol">
          Start patrol
        </Link>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <h2>Waiting for resident approval</h2>
        {pending.data?.items.length ? (
          <div className="list">
            {pending.data.items.map((v) => (
              <div key={v.id} className="list-item">
                <div>
                  <div className="title">{v.name}</div>
                  <div className="small muted">
                    {v.purpose} · {v.property_label} · {ago(v.created_at)}
                  </div>
                </div>
                <Badge status={v.status} />
              </div>
            ))}
          </div>
        ) : (
          <Empty title="No one waiting" />
        )}
      </div>
    </>
  );
}

function ResidentDashboard({ d }: { d: Dash }) {
  const notices = useApi<Page<Notice>>("/notices", { limit: 3 });
  const tickets = useApi<Page<TicketSummary>>("/tickets", { limit: 4 });
  const [raise, setRaise] = useState(false);
  const openTickets = tickets.data?.items.filter((t) => !["closed", "cancelled", "rejected"].includes(t.status)).length ?? 0;
  return (
    <>
      <div className="stats">
        <Stat label="Dues outstanding" value={inr(d.dues_outstanding)} href="/billing" kind={d.dues_outstanding ? "warn" : undefined} />
        <Stat label="Open service tickets" value={openTickets} href="/tickets" />
        <Stat label="Active maintenance" value={d.active_maintenance} href="/maintenance" />
        <Stat label="Expected visitors" value={d.visitors_expected} href="/visitors" />
      </div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <h2>Service tickets</h2>
          <div className="row">
            <Link href="/tickets" className="small">
              All tickets
            </Link>
            <button className="btn primary small" onClick={() => setRaise(true)}>
              Raise a ticket
            </button>
          </div>
        </div>
        {tickets.data && !tickets.data.items.length ? (
          <Empty title="No tickets yet">Something not working? Raise a ticket and track it until it's fixed.</Empty>
        ) : null}
        {tickets.data?.items.map((t) => (
          <Link key={t.id} href={`/tickets/${t.id}`} className="list-item">
            <div>
              <div className="title">{t.title}</div>
              <div className="small muted">
                <span className="mono">{t.number}</span> · {t.assignee_name ? `with ${t.assignee_name}` : "awaiting assignment"} · {ago(t.updated_at)}
              </div>
            </div>
            <Badge status={t.status} />
          </Link>
        ))}
      </div>
      <NewTicketDialog open={raise} onClose={() => (setRaise(false), tickets.reload())} />
      <div className="grid two">
        <div className="card">
          <div className="card-head">
            <h2>My property</h2>
            <Link href="/inspections" className="small">
              Request Property Watch visit
            </Link>
          </div>
          {d.properties.map((p: Dash) => (
            <Link key={p.id} href={`/properties/${p.id}`} className="list-item">
              <div>
                <div className="title">Plot {p.plot_number}</div>
                <div className="small muted">
                  {p.code} · {p.status.replace(/_/g, " ")}
                </div>
              </div>
              <Badge status={p.condition} />
            </Link>
          ))}
          {!d.properties.length ? <Empty title="No property linked yet">Ask your layout association to link your plot.</Empty> : null}
        </div>
        <div className="card">
          <h2>Recent maintenance</h2>
          {!d.recent_maintenance.length ? <Empty title="No maintenance yet" /> : null}
          {d.recent_maintenance.map((t: Dash) => (
            <Link key={t.id} href={`/maintenance/${t.id}`} className="list-item">
              <div>
                <div className="title">{t.title}</div>
                <div className="small muted mono">{t.number}</div>
              </div>
              <Badge status={t.status} />
            </Link>
          ))}
        </div>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head">
          <h2>Notices</h2>
          <Link href="/notices" className="small">
            All notices
          </Link>
        </div>
        {notices.data?.items.map((n) => (
          <div key={n.id} className="list-item">
            <div>
              <div className="title">{n.title}</div>
              <div className="small muted">{n.body}</div>
            </div>
            <span className="small muted">{fmtDateTime(n.published_at)}</span>
          </div>
        ))}
        {notices.data && !notices.data.items.length ? <Empty title="No notices" /> : null}
      </div>
    </>
  );
}

export default function DashboardPage() {
  const { me } = useAuth();
  const router = useRouter();
  const field = me?.role === "staff" || me?.role === "vendor";
  const super_ = me?.role === "super_admin";
  const { data, error, loading } = useApi<Dash>(me && !field && !super_ ? "/dashboard" : null);

  useEffect(() => {
    if (field) router.replace("/my-tasks");
    if (super_) router.replace("/tenants");
  }, [field, super_, router]);

  if (!me || field || super_) return null;
  const title = me.role === "guard" ? "Gate" : me.role === "resident" ? `Welcome, ${me.full_name.split(" ")[0]}` : "Layout overview";
  return (
    <>
      <PageHead title={title} sub={me.tenant_name || undefined} />
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data ? (
        me.role === "guard" ? <GuardDashboard d={data} /> : me.role === "resident" ? <ResidentDashboard d={data} /> : <ManagerDashboard d={data} />
      ) : null}
    </>
  );
}
