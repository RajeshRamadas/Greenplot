"use client";

import { TaskTable } from "@/components/Tasks";
import { PageHead } from "@/components/ui";

export default function ApprovalsPage() {
  return (
    <>
      <PageHead title="Pending approvals" sub="Submitted work waiting for supervisor verification. Open a task to review evidence, checklist, notes and materials." />
      <TaskTable query={{ approval: "pending", sort: "completed_at" }} empty="Nothing waiting for review" />
      <h2 style={{ margin: "28px 0 12px" }}>Sent back for rework</h2>
      <TaskTable query={{ status: ["rework_required"] }} empty="No tasks in rework" />
    </>
  );
}
