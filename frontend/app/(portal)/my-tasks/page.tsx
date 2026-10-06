"use client";

import Link from "next/link";
import { TaskCard } from "@/components/Tasks";
import { SlaBadge } from "@/components/Tickets";
import { Badge, Empty, ErrorBox, Loading, PageHead } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Inspection, Page, TaskSummary, TicketSummary } from "@/lib/types";

export default function MyTasksPage() {
  const { can } = useAuth();
  const { data, error, loading, reload } = useApi<{ maintenance: TaskSummary[]; inspections: Inspection[] }>("/tasks/mine");
  const tickets = useApi<Page<TicketSummary>>(can("tickets.work") && !can("tickets.manage") ? "/tickets" : null, { bucket: "active", sort: "due_at", limit: 50 });
  const groups = [
    { title: "Rework required", items: data?.maintenance.filter((t) => t.status === "rework_required") ?? [] },
    { title: "In progress", items: data?.maintenance.filter((t) => t.status === "started") ?? [] },
    { title: "To do", items: data?.maintenance.filter((t) => ["assigned", "accepted"].includes(t.status)) ?? [] },
    { title: "Waiting for review", items: data?.maintenance.filter((t) => t.status === "completed") ?? [] },
  ];
  return (
    <>
      <PageHead title="My tasks" sub="Customer tickets and jobs assigned to you. Open one to start work, capture evidence and submit.">
        <button className="btn" onClick={() => (reload(), tickets.reload())}>
          Refresh
        </button>
        <Link className="btn primary" href="/scan">
          Scan asset
        </Link>
      </PageHead>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {tickets.data?.items.length ? (
        <section style={{ marginBottom: 22 }}>
          <h2 style={{ marginBottom: 10 }}>
            Customer tickets <span className="muted">({tickets.data.items.length})</span>
          </h2>
          <div className="stack">
            {tickets.data.items.map((t) => (
              <Link key={t.id} href={`/tickets/${t.id}`} className="task-card">
                <div className="row between">
                  <b>{t.title}</b>
                  <Badge status={t.status} />
                </div>
                <div className="meta">
                  <span className="mono">{t.number}</span>
                  <span>{t.category_name}</span>
                  <span>{t.property_label || "Common area"}</span>
                  <Badge status={t.priority} />
                  <SlaBadge state={t.sla_state} due={t.due_at} />
                </div>
              </Link>
            ))}
          </div>
        </section>
      ) : null}
      {data && !data.maintenance.length && !data.inspections.length && !tickets.data?.items.length ? (
        <div className="card">
          <Empty title="No tasks assigned to you">New assignments appear here and as notifications.</Empty>
        </div>
      ) : null}
      {groups
        .filter((g) => g.items.length)
        .map((g) => (
          <section key={g.title} style={{ marginBottom: 22 }}>
            <h2 style={{ marginBottom: 10 }}>
              {g.title} <span className="muted">({g.items.length})</span>
            </h2>
            <div className="stack">
              {g.items.map((t) => (
                <TaskCard key={t.id} t={t} />
              ))}
            </div>
          </section>
        ))}
      {data?.inspections.length ? (
        <section>
          <h2 style={{ marginBottom: 10 }}>Inspections</h2>
          <div className="stack">
            {data.inspections.map((i) => (
              <Link key={i.id} href={`/inspections/${i.id}`} className="task-card">
                <div className="row between">
                  <b>{i.is_property_watch ? "Property Watch visit" : "Inspection"}</b>
                  <Badge status={i.status} />
                </div>
                <div className="meta">
                  <span className="mono">{i.number}</span>
                  {i.scheduled_for ? <span>{fmtDateTime(i.scheduled_for)}</span> : null}
                </div>
              </Link>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}
