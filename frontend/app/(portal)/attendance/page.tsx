"use client";

import { Empty, ErrorBox, PageHead, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getPosition } from "@/lib/capture";
import { fmtDate, fmtTime } from "@/lib/format";
import { useAction, useApi, useOnline } from "@/lib/hooks";
import { enqueue } from "@/lib/offline";

interface Row {
  id: string;
  work_date: string;
  check_in_at: string | null;
  check_out_at: string | null;
  method: string;
}

export default function AttendancePage() {
  const { me } = useAuth();
  const online = useOnline();
  const toast = useToast();
  const act = useAction();
  const { data, reload } = useApi<Row[]>("/staff/attendance");
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
  const row = data?.find((r) => r.work_date === today);

  async function mark(dir: "check_in" | "check_out") {
    if (!me) return;
    const pos = await getPosition(5000);
    if (!online) {
      await enqueue(me.id, "attendance", dir, pos ? { latitude: pos.latitude, longitude: pos.longitude } : {}, dir === "check_in" ? "Check in" : "Check out");
      return toast("Saved offline");
    }
    if (await act.run(() => api(`/staff/attendance/${dir.replace("_", "-")}`, { body: pos ?? {} }))) {
      toast(dir === "check_in" ? "Checked in" : "Checked out");
      reload();
    }
  }

  return (
    <>
      <PageHead title="Attendance" sub="Check in when your shift starts and out when it ends." />
      <ErrorBox error={act.error} />
      <div className="card" style={{ maxWidth: 520 }}>
        <h2>Today</h2>
        <p className="muted" style={{ marginBottom: 14 }}>
          {row?.check_in_at ? `Checked in at ${fmtTime(row.check_in_at)}` : "Not checked in yet"}
          {row?.check_out_at ? ` · out at ${fmtTime(row.check_out_at)}` : ""}
        </p>
        {!row?.check_in_at ? (
          <button className="btn primary big" onClick={() => mark("check_in")}>
            Check in
          </button>
        ) : !row.check_out_at ? (
          <button className="btn big" onClick={() => mark("check_out")}>
            Check out
          </button>
        ) : (
          <div className="alert ok">Shift complete.</div>
        )}
      </div>
      <div className="card" style={{ maxWidth: 520 }}>
        <h2>History</h2>
        {!data?.length ? <Empty title="No attendance yet" /> : null}
        {data?.map((r) => (
          <div key={r.id} className="list-item">
            <span>{fmtDate(r.work_date)}</span>
            <span className="small muted">
              {fmtTime(r.check_in_at)} – {r.check_out_at ? fmtTime(r.check_out_at) : "…"}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}
