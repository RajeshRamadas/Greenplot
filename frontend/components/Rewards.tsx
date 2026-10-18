"use client";

import { useState } from "react";
import { Badge, Dialog, Empty, ErrorBox, Field, Select, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDate, inr, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import type { Referrals, Subscription, SubscriptionOption } from "@/lib/types";

const every = (months: number) => (months === 3 ? "quarter" : months === 1 ? "month" : `${months} months`);

/** Owner view: discounted monthly / quarterly plans for their plots, and their active subscriptions. */
export function MySubscriptions({ onChange }: { onChange?: () => void }) {
  const toast = useToast();
  const act = useAction();
  const opts = useApi<SubscriptionOption[]>("/subscriptions/options");
  const subs = useApi<Subscription[]>("/subscriptions");
  const active = (subs.data ?? []).filter((s) => s.status === "active");
  const taken = new Set(active.map((s) => `${s.plan_id}:${s.property_id}`));
  const offers = (opts.data ?? []).filter((o) => !taken.has(`${o.plan_id}:${o.property_id}`));
  if (!active.length && !offers.length) return null;
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h2>Subscription plans</h2>
      <ErrorBox error={opts.error || subs.error || act.error} />
      {active.map((s) => (
        <div key={s.id} className="list-item">
          <div>
            <div className="title">
              {s.plan_name} · {s.property_label}
            </div>
            <div className="small muted">
              {inr(s.price)} every {every(s.frequency_months)} ({s.discount_pct}% off) · next bill {fmtDate(s.next_billing_date)}
            </div>
          </div>
          <button
            className="btn small ghost"
            onClick={async () => {
              if (await act.run(() => api(`/subscriptions/${s.id}/cancel`, { method: "POST" }))) {
                toast("Subscription cancelled");
                subs.reload();
              }
            }}
          >
            Cancel
          </button>
        </div>
      ))}
      {offers.length ? <p className="small muted">Pay once a month or once a quarter and save. Bills are raised for you automatically.</p> : null}
      {offers.map((o) => (
        <div key={`${o.plan_id}:${o.property_id}:${o.frequency_months}`} className="list-item">
          <div>
            <div className="title">
              {o.plan_name} · {o.frequency} · {o.property_label}
            </div>
            <div className="small muted">
              <b>{inr(o.price)}</b> per {every(o.frequency_months)}
              {o.saving > 0 ? (
                <>
                  {" "}
                  · <s>{inr(o.full_price)}</s> · save {inr(o.saving)} ({o.discount_pct}% off)
                </>
              ) : null}
            </div>
          </div>
          <button
            className="btn small primary"
            disabled={act.pending}
            onClick={async () => {
              const s = await act.run(() =>
                api<Subscription>("/subscriptions", { body: { property_id: o.property_id, plan_id: o.plan_id, frequency_months: o.frequency_months } }),
              );
              if (s) {
                toast(`Subscribed · first bill of ${inr(s.price)} raised`);
                subs.reload();
                onChange?.();
              }
            }}
          >
            Subscribe
          </button>
        </div>
      ))}
    </div>
  );
}

/** Owner view: refer a neighbour and see the free-cleaning credit earned. */
export function ReferNeighbour() {
  const toast = useToast();
  const act = useAction();
  const refs = useApi<Referrals>("/referrals");
  const [f, setF] = useState<Record<string, string>>({});
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h2>Refer a neighbour</h2>
      <p className="small muted">
        When a neighbour you refer becomes a customer, your next cleaning is free{refs.data ? ` (${inr(refs.data.reward_amount)} off your dues)` : ""}.
        {refs.data?.credit_remaining ? <b> Credit waiting: {inr(refs.data.credit_remaining)}</b> : null}
      </p>
      <form
        className="row"
        style={{ marginBottom: 12 }}
        onSubmit={async (e) => {
          e.preventDefault();
          if (await act.run(() => api("/referrals", { body: { neighbour_name: f.name, neighbour_phone: f.phone, note: f.note || null } }))) {
            toast("Thanks! We'll get in touch with them.");
            setF({});
            refs.reload();
          }
        }}
      >
        <input required placeholder="Neighbour's name" value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} style={{ flex: 1, minWidth: 140 }} />
        <input required type="tel" placeholder="Mobile number" value={f.phone || ""} onChange={(e) => setF({ ...f, phone: e.target.value })} style={{ width: 160 }} />
        <input placeholder="Their plot (optional)" value={f.note || ""} onChange={(e) => setF({ ...f, note: e.target.value })} style={{ width: 160 }} />
        <button className="btn primary" disabled={act.pending}>
          Refer
        </button>
      </form>
      <ErrorBox error={refs.error || act.error} />
      {refs.data?.items.map((r) => (
        <div key={r.id} className="list-item">
          <span>
            {r.neighbour_name} <span className="small muted">· {fmtDate(r.created_at)}</span>
          </span>
          <Badge status={r.status === "converted" ? "paid" : r.status} text={r.status === "converted" ? "Joined · reward earned" : label(r.status)} />
        </div>
      ))}
    </div>
  );
}

/** Office view: every subscription. */
export function SubscriptionsAdmin() {
  const act = useAction();
  const subs = useApi<Subscription[]>("/subscriptions");
  return (
    <div className="card">
      <h2>Subscriptions</h2>
      <p className="small muted">Mark a billing plan &quot;Offer as subscription&quot; so owners can take it monthly or quarterly at a discount. The worker raises each bill on schedule.</p>
      <ErrorBox error={subs.error || act.error} />
      {subs.data && !subs.data.length ? <Empty title="No subscriptions yet" /> : null}
      {subs.data?.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Property</th>
                <th>Plan</th>
                <th>Price</th>
                <th>Next bill</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {subs.data.map((s) => (
                <tr key={s.id}>
                  <td>{s.property_label}</td>
                  <td>{s.plan_name}</td>
                  <td>
                    {inr(s.price)} / {every(s.frequency_months)} <span className="small muted">({s.discount_pct}% off)</span>
                  </td>
                  <td>{s.status === "active" ? fmtDate(s.next_billing_date) : "—"}</td>
                  <td>
                    <Badge status={s.status === "active" ? "paid" : s.status} text={label(s.status)} />
                  </td>
                  <td>
                    {s.status === "active" ? (
                      <button className="btn small ghost" onClick={() => act.run(() => api(`/subscriptions/${s.id}/cancel`, { method: "POST" })).then(subs.reload)}>
                        Cancel
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

/** Office view: referrals to follow up, and confirming the neighbour joined (which rewards the referrer). */
export function ReferralsAdmin() {
  const toast = useToast();
  const act = useAction();
  const { properties } = useLookups();
  const refs = useApi<Referrals>("/referrals");
  const [convert, setConvert] = useState<string | null>(null);
  const [plot, setPlot] = useState("");
  return (
    <div className="card">
      <h2>Referrals</h2>
      <p className="small muted">
        When a referred neighbour becomes a customer, mark it joined. The referrer gets a free cleaning ({inr(refs.data?.reward_amount)}) taken off their dues automatically.
      </p>
      <ErrorBox error={refs.error || act.error} />
      {refs.data && !refs.data.items.length ? <Empty title="No referrals yet" /> : null}
      {refs.data?.items.map((r) => (
        <div key={r.id} className="list-item">
          <div>
            <div className="title">
              {r.neighbour_name} · <a href={`tel:${r.neighbour_phone}`}>{r.neighbour_phone}</a>
            </div>
            <div className="small muted">
              Referred by {r.referrer_name} ({r.property_label}) · {fmtDate(r.created_at)}
              {r.note ? ` · ${r.note}` : ""}
              {r.status === "converted" ? ` · reward ${inr(r.reward_amount)}, ${inr(r.reward_remaining)} unused` : ""}
            </div>
          </div>
          {r.status === "pending" ? (
            <div className="row">
              <button className="btn small primary" onClick={() => (setConvert(r.id), setPlot(""))}>
                Joined
              </button>
              <button className="btn small ghost" onClick={() => act.run(() => api(`/referrals/${r.id}/decline`, { method: "POST" })).then(refs.reload)}>
                Decline
              </button>
            </div>
          ) : (
            <Badge status={r.status === "converted" ? "paid" : r.status} text={label(r.status)} />
          )}
        </div>
      ))}
      <Dialog title="Neighbour joined" open={!!convert} onClose={() => setConvert(null)}>
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await act.run(() => api(`/referrals/${convert}/convert`, { body: { property_id: plot } }))) {
              toast("Referrer rewarded with a free cleaning");
              setConvert(null);
              refs.reload();
            }
          }}
        >
          <Field label="Neighbour's plot">
            <Select
              required
              value={plot}
              onChange={setPlot}
              placeholder="Choose plot"
              options={properties.map((p) => ({ value: p.id, label: `Plot ${p.plot_number}${p.owner_name ? ` · ${p.owner_name}` : ""}` }))}
            />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions">
            <button className="btn primary" disabled={act.pending}>
              Reward referrer
            </button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
