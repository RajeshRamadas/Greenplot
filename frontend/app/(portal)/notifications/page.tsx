"use client";

import Link from "next/link";
import { Empty, ErrorBox, Loading, PageHead } from "@/components/ui";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { linkFor } from "@/lib/links";
import type { Notification, Page } from "@/lib/types";

export default function NotificationsPage() {
  const { data, error, loading, reload } = useApi<Page<Notification>>("/notifications", { limit: 100 });
  return (
    <>
      <PageHead title="Notifications">
        <button className="btn" onClick={() => api("/notifications/read", { method: "POST" }).then(reload)}>
          Mark all read
        </button>
      </PageHead>
      <ErrorBox error={error} />
      <div className="card">
        {loading && !data ? <Loading /> : null}
        {data && !data.items.length ? <Empty title="You're all caught up" /> : null}
        <div className="list">
          {data?.items.map((n) => {
            const href = linkFor(n.entity_type, n.entity_id);
            const body = (
              <>
                <div>
                  <div className="title" style={{ fontWeight: n.read_at ? 500 : 800 }}>
                    {n.title}
                  </div>
                  {n.body ? <div className="small muted">{n.body}</div> : null}
                </div>
                <span className="small muted">{ago(n.created_at)}</span>
              </>
            );
            return href ? (
              <Link key={n.id} href={href} className="list-item">
                {body}
              </Link>
            ) : (
              <div key={n.id} className="list-item">
                {body}
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
