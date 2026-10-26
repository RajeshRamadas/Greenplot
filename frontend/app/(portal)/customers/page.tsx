"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Empty, ErrorBox, Loading, PageHead, Pager } from "@/components/ui";
import { ago } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { CustomerSummary, Page } from "@/lib/types";

const LIMIT = 50;

/** Every customer, with their plots, open tickets and when we last spoke. Layout admins only. */
export default function CustomersPage() {
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, error, loading } = useApi<Page<CustomerSummary>>("/customers", { q, limit: LIMIT, offset });

  return (
    <>
      <PageHead title="Customers" sub={`${data?.total ?? "…"} customers · plots, conversations, jobs, payments and photos in one place`} />
      <div className="filters">
        <input type="search" placeholder="Name, phone, email or plot number" value={q} onChange={(e) => (setQ(e.target.value), setOffset(0))} />
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data && !data.items.length ? <Empty title="No customers found">Customers appear here once they have a GreenPlot login.</Empty> : null}
      {data?.items.length ? (
        <div className="card">
          {data.items.map((c) => (
            <Link key={c.id} href={`/customers/${c.id}`} className="list-item">
              <div>
                <div className="title">{c.full_name}</div>
                <div className="small muted">
                  {c.plots.join(", ") || "No plot linked"} {c.phone ? `· ${c.phone}` : ""} {!c.is_active ? "· inactive" : ""}
                </div>
              </div>
              <div className="when small muted" style={{ textAlign: "right" }}>
                {c.open_tickets ? <Badge status="amber" text={`${c.open_tickets} open`} /> : null}
                <div>{c.last_contact_at ? `Last spoke ${ago(c.last_contact_at)}` : "No conversations yet"}</div>
              </div>
            </Link>
          ))}
        </div>
      ) : null}
      {data && data.total > LIMIT ? <Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} /> : null}
    </>
  );
}
