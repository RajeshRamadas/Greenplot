"use client";

import Link from "next/link";
import { TaskCard } from "@/components/Tasks";
import { Badge, Empty, ErrorBox, Loading, PageHead } from "@/components/ui";
import { fmtDateTime } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Inspection, TaskSummary } from "@/lib/types";

export default function MyTasksPage() {
  const { data, error, loading, reload } = useApi<{ maintenance: TaskSummary[]; inspections: Inspection[] }>("/tasks/mine");
  const groups = [
    { title: "Rework required", items: data?.maintenance.filter((t) => t.status === "rework_required") ?? [] },
    { title: "In progress", items: data?.maintenance.filter((t) => t.status === "started") ?? [] },
    { title: "To do", items: data?.maintenance.filter((t) => ["assigned", "accepted"].includes(t.status)) ?? [] },
    { title: "Waiting for review", items: data?.maintenance.filter((t) => t.status === "completed") ?? [] },
  ];
  return (
    <>
      <PageHead title="My tasks" sub="Open a task to start work, capture evidence and submit.">
        <button className="btn" onClick={reload}>
          Refresh
        </button>
        <Link className="btn primary" href="/scan">
          Scan asset
        </Link>
      </PageHead>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data && !data.maintenance.length && !data.inspections.length ? (
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
