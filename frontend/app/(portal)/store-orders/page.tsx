"use client";

import { useState } from "react";
import { Badge, Empty, ErrorBox, Loading, PageHead, Pager, Select, useToast } from "@/components/ui";
import { api, download } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { ORDER_STATUS, type StoreOrder, rupees } from "@/lib/store";

const NEXT: Record<string, { value: StoreOrder["status"]; label: string }[]> = {
  pending_payment: [{ value: "cancelled", label: "Cancel" }],
  placed: [
    { value: "confirmed", label: "Confirm" },
    { value: "out_for_delivery", label: "Out for delivery" },
    { value: "delivered", label: "Delivered" },
    { value: "cancelled", label: "Cancel" },
  ],
  confirmed: [
    { value: "out_for_delivery", label: "Out for delivery" },
    { value: "delivered", label: "Delivered" },
    { value: "cancelled", label: "Cancel" },
  ],
  out_for_delivery: [
    { value: "delivered", label: "Delivered" },
    { value: "cancelled", label: "Cancel" },
  ],
};

/** Plant store orders: what to pack, who to call, and the bill for each order. */
export default function StoreOrdersPage() {
  const toast = useToast();
  const act = useAction();
  const [status, setStatus] = useState("open");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 20;
  const { data, loading, error, reload } = useApi<{ items: StoreOrder[]; total: number }>("/store/orders", { status, q, limit, offset });

  async function change(o: StoreOrder, body: Record<string, unknown>, done: string) {
    const r = await act.run(() => api(`/store/orders/${o.id}`, { method: "PATCH", body }));
    if (r) {
      toast(done);
      reload();
    }
  }

  return (
    <>
      <PageHead title="Plant store orders" sub="Orders from the website. Cash on delivery is marked paid when you mark the order delivered." />
      <div className="row" style={{ marginBottom: 12 }}>
        <Select
          value={status}
          onChange={(v) => {
            setStatus(v);
            setOffset(0);
          }}
          options={[
            { value: "open", label: "Open orders" },
            { value: "", label: "All orders" },
            ...Object.entries(ORDER_STATUS).map(([value, label]) => ({ value, label })),
          ]}
        />
        <input
          placeholder="Order number, name or phone"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOffset(0);
          }}
        />
      </div>
      <ErrorBox error={act.error || error} />
      {loading && !data ? <Loading /> : null}
      {data && !data.items.length ? <Empty title="No orders here yet">New website orders show up on this page.</Empty> : null}
      {data?.items.map((o) => (
        <div key={o.id} className="card">
          <div className="card-head">
            <div>
              <h2>
                {o.number} · {rupees(o.total)}
              </h2>
              <p className="small muted">
                {fmtDateTime(o.created_at)} · {o.items.reduce((n, i) => n + i.quantity, 0)} plant(s) · bill {o.bill_number}
              </p>
            </div>
            <div className="row">
              <Badge status={o.status === "delivered" ? "paid" : o.status === "cancelled" ? "cancelled" : "pending"} text={ORDER_STATUS[o.status]} />
              <Badge
                status={o.payment_status === "paid" ? "paid" : "pending"}
                text={o.payment_status === "paid" ? (o.payment_method === "online" ? "Paid online" : "Cash collected") : o.payment_method === "cod" ? "Cash on delivery" : "Awaiting payment"}
              />
            </div>
          </div>
          <div className="store-admin">
            <div>
              <p className="small muted">Customer</p>
              <p>
                <b>{o.customer_name}</b>
                <br />
                <a href={`tel:${o.phone}`}>{o.phone}</a>
                {o.email ? (
                  <>
                    {" · "}
                    <a href={`mailto:${o.email}`}>{o.email}</a>
                  </>
                ) : null}
              </p>
              <p className="small muted">Deliver to</p>
              <p>
                {o.address}, {o.area}, Bangalore {o.pincode}
                {o.landmark ? ` (near ${o.landmark})` : ""}
              </p>
              {o.notes ? (
                <>
                  <p className="small muted">Customer notes</p>
                  <p>{o.notes}</p>
                </>
              ) : null}
              {o.cancelled_reason ? <p className="small muted">Cancelled: {o.cancelled_reason}</p> : null}
            </div>
            <div>
              <p className="small muted">Items</p>
              <ul className="store-mini">
                {o.items.map((i) => (
                  <li key={i.slug}>
                    <span>
                      {i.quantity} × {i.name}
                    </span>
                    <span>{rupees(i.line_total)}</span>
                  </li>
                ))}
                <li>
                  <span>Delivery</span>
                  <span>{o.delivery_fee ? rupees(o.delivery_fee) : "Free"}</span>
                </li>
              </ul>
            </div>
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            {(NEXT[o.status] ?? []).map((n) => (
              <button
                key={n.value}
                className={`btn small${n.value === "cancelled" ? " danger" : n.value === "delivered" ? " primary" : ""}`}
                disabled={act.pending}
                onClick={() => {
                  const reason = n.value === "cancelled" ? window.prompt(`Why is ${o.number} cancelled?`) : null;
                  if (n.value === "cancelled" && !reason) return;
                  change(o, { status: n.value, ...(reason ? { reason } : {}) }, `${o.number} is ${ORDER_STATUS[n.value].toLowerCase()}`);
                }}
              >
                {n.label}
              </button>
            ))}
            {o.payment_method === "cod" && o.payment_status !== "paid" && o.status !== "cancelled" ? (
              <button className="btn small" disabled={act.pending} onClick={() => change(o, { paid: true }, `${o.number} marked paid`)}>
                Mark paid
              </button>
            ) : null}
            <button className="btn small ghost" onClick={() => download(`/store/orders/${o.id}/bill.pdf`, undefined, `${o.bill_number}.pdf`)}>
              Bill (PDF)
            </button>
            <a className="btn small ghost" href={`https://wa.me/${o.phone.replace(/\D/g, "").replace(/^0+/, "").replace(/^(?!91)/, "91")}`} target="_blank" rel="noopener noreferrer">
              WhatsApp
            </a>
          </div>
        </div>
      ))}
      {data ? <Pager total={data.total} limit={limit} offset={offset} onChange={setOffset} /> : null}
    </>
  );
}
