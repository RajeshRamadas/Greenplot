"use client";

import { useState } from "react";
import { NewTaskDialog, TaskTable } from "@/components/Tasks";
import { Badge, Empty, PageHead } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { fmtDate, label } from "@/lib/format";
import { useApi } from "@/lib/hooks";

interface Schedule {
  id: string;
  title: string;
  category: string;
  interval_days: number;
  next_run_on: string;
  is_active: boolean;
  location_note: string | null;
}

const CATS = ["gardening", "landscaping", "cleaning", "compound_maintenance"];

export default function GardeningPage() {
  const { can } = useAuth();
  const [tab, setTab] = useState<"gardening" | "cleaning">("gardening");
  const [creating, setCreating] = useState(false);
  const schedules = useApi<Schedule[]>("/maintenance/schedules");
  const cats = tab === "gardening" ? CATS.slice(0, 2) : CATS.slice(2);
  return (
    <>
      <PageHead title="Gardening & cleaning" sub="Recurring landscaping, gardening, plot and compound cleaning with before/after proof.">
        {can("maintenance.create") ? (
          <button className="btn primary" onClick={() => setCreating(true)}>
            New job
          </button>
        ) : null}
      </PageHead>
      <div className="tabs">
        <button className={tab === "gardening" ? "on" : ""} onClick={() => setTab("gardening")}>
          Landscaping & gardening
        </button>
        <button className={tab === "cleaning" ? "on" : ""} onClick={() => setTab("cleaning")}>
          Cleaning & compound
        </button>
      </div>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head">
          <h2>Recurring schedules</h2>
          <a href="/settings#schedules" className="small">
            Manage schedules
          </a>
        </div>
        {schedules.data?.filter((s) => cats.includes(s.category)).length ? (
          <div className="list">
            {schedules.data
              .filter((s) => cats.includes(s.category))
              .map((s) => (
                <div key={s.id} className="list-item">
                  <div>
                    <div className="title">{s.title}</div>
                    <div className="small muted">
                      {label(s.category)} · every {s.interval_days} days {s.location_note ? `· ${s.location_note}` : ""}
                    </div>
                  </div>
                  <div className="row">
                    <span className="small muted">Next {fmtDate(s.next_run_on)}</span>
                    <Badge status={s.is_active ? "good" : "cancelled"} text={s.is_active ? "Active" : "Paused"} />
                  </div>
                </div>
              ))}
          </div>
        ) : (
          <Empty title="No recurring schedules" />
        )}
      </div>
      <TaskTable query={{ category: cats }} empty="No jobs yet" />
      {creating ? <NewTaskDialog open onClose={() => setCreating(false)} preset={{ category: cats[0] }} /> : null}
    </>
  );
}
