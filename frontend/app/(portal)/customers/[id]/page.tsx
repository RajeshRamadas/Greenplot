"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { CaptureButton } from "@/components/Capture";
import { ConversationList, LogConversation } from "@/components/Conversations";
import { Badge, Empty, ErrorBox, Loading, PageHead, Select, Stat } from "@/components/ui";
import { download } from "@/lib/api";
import { fmtDate, fmtDateTime, inr, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { linkFor } from "@/lib/links";
import type { Customer, CustomerEvent, Interaction, MediaItem } from "@/lib/types";

type CustomerMedia = MediaItem & { source: string };

const GROUPS: Record<string, string[]> = {
  conversations: ["note", "phone_call", "whatsapp_call", "whatsapp_chat", "sms", "email", "site_visit", "meeting", "whatsapp", "ticket_message", "complaint_message"],
  updates: ["update_sent", "plot_report"],
  work: ["ticket", "job", "inspection", "complaint", "feedback"],
  money: ["invoice", "payment"],
};

/** The customer record: profile, plots, everything that happened, conversations and photos. Layout admins only. */
export default function CustomerPage() {
  const { id } = useParams<{ id: string }>();
  const { data: c, error, loading, reload } = useApi<Customer>(`/customers/${id}`);
  const history = useApi<CustomerEvent[]>(`/customers/${id}/history`, { limit: 500 });
  const convo = useApi<Interaction[]>(`/customers/${id}/interactions`);
  const [mediaKey, setMediaKey] = useState(0);
  const media = useApi<CustomerMedia[]>(`/customers/${id}/media`, { k: mediaKey });
  const [group, setGroup] = useState("");
  const [logOpen, setLogOpen] = useState(false);
  const act = useAction();

  if (loading && !c) return <Loading />;
  if (!c) return <ErrorBox error={error || "Not found"} />;
  const items = (history.data ?? []).filter((e) => !group || GROUPS[group]?.includes(e.kind));
  const refresh = () => (convo.reload(), history.reload(), reload());

  return (
    <>
      <p className="small" style={{ marginBottom: 8 }}>
        <Link href="/customers">← All customers</Link>
      </p>
      <PageHead title={c.full_name} sub={c.plots.map((p) => `Plot ${p.plot_number}`).join(" · ") || "No plot linked"}>
        <button className="btn primary" onClick={() => setLogOpen(true)}>
          Log conversation
        </button>
        <button className="btn" disabled={act.pending} onClick={() => act.run(() => download(`/customers/${id}/export`))}>
          Download everything
        </button>
      </PageHead>
      <ErrorBox error={act.error} />
      <div className="stats">
        <Stat label="Tickets" value={c.stats.open_tickets ? `${c.stats.tickets} (${c.stats.open_tickets} open)` : c.stats.tickets} kind={c.stats.open_tickets ? "warn" : undefined} />
        <Stat label="Jobs done" value={c.stats.jobs_done} />
        <Stat label="Photos & files" value={c.stats.photos} />
        <Stat label="Conversations" value={c.stats.conversations} />
        <Stat label="Paid" value={inr(c.stats.paid)} />
        <Stat label="Outstanding" value={inr(c.stats.outstanding)} kind={c.stats.outstanding > 0 ? "alert" : undefined} />
      </div>
      <div className="grid side">
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <h2>History</h2>
              <Select
                value={group}
                onChange={setGroup}
                placeholder="Everything"
                options={[
                  { value: "conversations", label: "Conversations" },
                  { value: "updates", label: "Updates we sent" },
                  { value: "work", label: "Tickets & jobs" },
                  { value: "money", label: "Invoices & payments" },
                ]}
                style={{ width: "auto" }}
              />
            </div>
            {history.loading && !history.data ? <Loading /> : null}
            {history.data && !items.length ? <Empty title="Nothing here yet" /> : null}
            <ul className="timeline">
              {items.map((e, n) => {
                const href = e.entity_type === "customer_interaction" ? null : linkFor(e.entity_type, e.entity_id);
                return (
                  <li key={`${e.kind}-${e.entity_id}-${e.at}-${n}`}>
                    <div className="row between">
                      <span>
                        <Badge status={e.direction === "in" ? "blue" : "grey"} text={label(e.kind)} /> {href ? <Link href={href}>{e.title}</Link> : e.title}
                      </span>
                      <span>
                        {e.internal ? <Badge status="amber" text="Office only" /> : null} {e.status ? <Badge status={e.status} /> : null}
                      </span>
                    </div>
                    {e.body ? <div className="small" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", margin: "4px 0" }}>{e.body}</div> : null}
                    <small>
                      {e.number ? <span className="mono">{e.number}</span> : null} {fmtDateTime(e.at)} {e.by ? `· ${e.by}` : ""}
                      {e.direction ? ` · ${e.direction === "in" ? "from customer" : "to customer"}` : ""}
                    </small>
                  </li>
                );
              })}
            </ul>
          </div>
          <div className="card">
            <h2>Photos & files</h2>
            <p className="small muted">From their tickets, jobs, inspections and plots, plus files kept on this record. Files you upload here are kept until you delete them.</p>
            {media.data && !media.data.length ? <p className="small muted">No photos or files yet.</p> : null}
            <div className="evidence-grid">
              {media.data?.map((m) => (
                <a key={m.id} className="evidence-tile" href={m.url || undefined} target="_blank" rel="noreferrer" style={{ color: "inherit", textDecoration: "none" }}>
                  <div className="thumb">{m.thumbnail_url ? <img src={m.thumbnail_url} alt="" /> : <span>{m.content_type.includes("pdf") ? "PDF" : m.content_type.startsWith("video") ? "▶ Video" : "File"}</span>}</div>
                  <div className="cap">
                    <b>{m.source}</b>
                    <span className="muted">{label(m.evidence_type || m.original_filename || "file")}</span>
                    <span className="muted">{fmtDateTime(m.captured_at || m.uploaded_at)}</span>
                  </div>
                </a>
              ))}
            </div>
            <div style={{ marginTop: 10, maxWidth: 260 }}>
              <CaptureButton entityType="customer" entityId={c.id} evidenceType="document" text="Upload photo or document" onDone={() => (setMediaKey((k) => k + 1), reload())} />
            </div>
          </div>
        </div>
        <div className="stack" style={{ gap: 16 }}>
          <div className="card">
            <h2>Profile</h2>
            <dl className="kv" style={{ gridTemplateColumns: "110px 1fr" }}>
              <dt>Phone</dt>
              <dd>{c.phone ? <a href={`tel:${c.phone}`}>{c.phone}</a> : "—"} {c.phone_verified ? <Badge status="green" text="Verified" /> : null}</dd>
              <dt>WhatsApp</dt>
              <dd>
                {c.whatsapp_phone || (c.phone ? "Same number" : "—")} {c.whatsapp_opt_in ? <Badge status="green" text="Opted in" /> : <Badge status="grey" text="Not opted in" />}
              </dd>
              <dt>Email</dt>
              <dd>{c.email}</dd>
              <dt>Customer since</dt>
              <dd>{fmtDate(c.joined_at)}</dd>
              <dt>Last sign-in</dt>
              <dd>{c.last_login_at ? fmtDateTime(c.last_login_at) : "Never"}</dd>
              <dt>Rating</dt>
              <dd>{c.stats.avg_rating ? `${c.stats.avg_rating} / 5` : "—"}</dd>
              <dt>Plans</dt>
              <dd>{c.stats.active_subscriptions ? `${c.stats.active_subscriptions} active` : "None"}</dd>
            </dl>
          </div>
          <div className="card">
            <h2>Plots</h2>
            {!c.plots.length ? <p className="small muted">No plot linked yet.</p> : null}
            {c.plots.map((p) => (
              <Link key={p.id} href={`/properties/${p.id}`} className="list-item">
                <div>
                  <div className="title">Plot {p.plot_number}</div>
                  <div className="small muted">
                    <span className="mono">{p.code}</span> {p.layout_name ? `· ${p.layout_name}` : ""} {p.area_sqft ? `· ${p.area_sqft} sq ft` : ""}
                  </div>
                </div>
                <Badge status="grey" text={label(p.relation)} />
              </Link>
            ))}
          </div>
          <div className="card">
            <div className="card-head">
              <h2>Conversations</h2>
              <button className="btn small" onClick={() => setLogOpen(true)}>
                Add
              </button>
            </div>
            <ConversationList items={convo.data ?? []} onDeleted={refresh} />
          </div>
        </div>
      </div>
      <LogConversation open={logOpen} onClose={() => setLogOpen(false)} path={`/customers/${id}/interactions`} plots={c.plots} onSaved={refresh} />
    </>
  );
}
