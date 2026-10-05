"use client";

import { useState } from "react";
import { NewTaskDialog, TaskTable } from "@/components/Tasks";
import { PageHead, Select } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useLookups } from "@/lib/lookups";

export default function MaintenancePage() {
  const { can, meta, me } = useAuth();
  const lookups = useLookups();
  const [creating, setCreating] = useState(false);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [property, setProperty] = useState("");
  const [staff, setStaff] = useState("");
  const [overdue, setOverdue] = useState(false);

  return (
    <>
      <PageHead
        title={me?.role === "resident" ? "Maintenance history" : "Maintenance"}
        sub="Every maintenance task, documented and verified."
      >
        {can("maintenance.create") ? (
          <button className="btn primary" onClick={() => setCreating(true)}>
            New task
          </button>
        ) : null}
      </PageHead>
      <div className="filters">
        <input type="search" placeholder="Search number, title, notes" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select value={status} onChange={setStatus} placeholder="Any status" options={meta?.task_statuses ?? []} />
        <Select value={category} onChange={setCategory} placeholder="Any category" options={meta?.task_categories ?? []} />
        {lookups.properties.length > 1 ? (
          <Select value={property} onChange={setProperty} placeholder="Any property" options={lookups.properties.map((p) => ({ value: p.id, label: `Plot ${p.plot_number}` }))} />
        ) : null}
        {lookups.staff.length ? <Select value={staff} onChange={setStaff} placeholder="Any staff" options={lookups.staff.map((u) => ({ value: u.id, label: u.full_name }))} /> : null}
        <label className="row small" style={{ minWidth: 0 }}>
          <input type="checkbox" checked={overdue} onChange={(e) => setOverdue(e.target.checked)} /> Overdue only
        </label>
      </div>
      <TaskTable
        query={{ q: q || undefined, status: status ? [status] : undefined, category: category ? [category] : undefined, property_id: property || undefined, staff_id: staff || undefined, overdue: overdue || undefined }}
      />
      {creating ? <NewTaskDialog open onClose={() => setCreating(false)} /> : null}
    </>
  );
}
