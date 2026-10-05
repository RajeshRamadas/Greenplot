"use client";

import { useState } from "react";
import { Badge, Dialog, Empty, ErrorBox, Field, PageHead, Select, Stat, useToast } from "@/components/ui";
import { api, download } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtDate, fmtDateTime, inr, label } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { newId } from "@/lib/offline";
import type { Invoice, Page, Payment, Plan } from "@/lib/types";

function Invoices({ admin }: { admin: boolean }) {
  const toast = useToast();
  const act = useAction();
  const [status, setStatus] = useState("");
  const invoices = useApi<Page<Invoice>>("/billing/invoices", { status, limit: 200 });
  const payments = useApi<Page<Payment>>("/payments", { limit: 100 });
  const [pay, setPay] = useState<{ invoice: Invoice; payment?: Payment } | null>(null);
  const [record, setRecord] = useState<Invoice | null>(null);
  const [f, setF] = useState<Record<string, string>>({ method: "upi" });
  // One idempotency key per payment attempt so double-clicks never create two charges.
  const [key, setKey] = useState("");

  return (
    <>
      <div className="filters">
        <Select value={status} onChange={setStatus} placeholder="Any status" options={["unpaid", "partial", "paid", "waived"]} />
      </div>
      <ErrorBox error={invoices.error || act.error} />
      {invoices.data && !invoices.data.items.length ? <Empty title="No dues" /> : null}
      {invoices.data?.items.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Invoice</th>
                <th>Property</th>
                <th>Description</th>
                <th>Amount</th>
                <th>Paid</th>
                <th>Due</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {invoices.data.items.map((i) => (
                <tr key={i.id}>
                  <td className="mono">{i.number}</td>
                  <td>{i.property_label}</td>
                  <td>{i.description}</td>
                  <td>{inr(i.amount)}</td>
                  <td>{inr(i.amount_paid)}</td>
                  <td>
                    {fmtDate(i.due_date)} {i.overdue ? <Badge status="urgent" text="Overdue" /> : null}
                  </td>
                  <td>
                    <Badge status={i.status} />
                  </td>
                  <td>
                    {["unpaid", "partial"].includes(i.status) ? (
                      admin ? (
                        <div className="row">
                          <button className="btn small" onClick={() => (setRecord(i), setKey(newId("cash")), setF({ method: "upi", amount: String(i.amount - i.amount_paid) }))}>
                            Record payment
                          </button>
                          <button className="btn small ghost" onClick={() => act.run(() => api(`/billing/invoices/${i.id}/waive`, { method: "POST" })).then(invoices.reload)}>
                            Waive
                          </button>
                        </div>
                      ) : (
                        <button className="btn small primary" onClick={() => (setPay({ invoice: i }), setKey(newId("pay")))}>
                          Pay {inr(i.amount - i.amount_paid)}
                        </button>
                      )
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Payments & receipts</h2>
        {payments.data && !payments.data.items.length ? <Empty title="No payments yet" /> : null}
        {payments.data?.items.map((p) => (
          <div key={p.id} className="list-item">
            <div>
              <div className="title">
                {inr(p.amount)} · {label(p.method)}
              </div>
              <div className="small muted">
                {p.receipt_number ? <span className="mono">{p.receipt_number}</span> : p.provider_order_id} · {fmtDateTime(p.paid_at || p.created_at)}
              </div>
            </div>
            <div className="row">
              <Badge status={p.status === "succeeded" ? "paid" : p.status} text={label(p.status)} />
              {p.status === "succeeded" ? (
                <button className="btn small" onClick={() => download(`/payments/${p.id}/receipt.pdf`).catch((e) => toast(e.message, "error"))}>
                  Receipt
                </button>
              ) : null}
            </div>
          </div>
        ))}
      </div>

      <Dialog title="Pay dues" open={!!pay} onClose={() => setPay(null)}>
        {pay && !pay.payment ? (
          <div className="stack">
            <p>
              {pay.invoice.description} · <b>{inr(pay.invoice.amount - pay.invoice.amount_paid)}</b>
            </p>
            <p className="small muted">Payment is completed on the payment provider&apos;s secure page. GreenPlot never sees or stores your card details.</p>
            <ErrorBox error={act.error} />
            <button
              className="btn primary big"
              disabled={act.pending}
              onClick={async () => {
                const p = await act.run(() => api<Payment>("/payments", { body: { invoice_id: pay.invoice.id }, headers: { "Idempotency-Key": key } }));
                if (p) setPay({ ...pay, payment: p });
              }}
            >
              Continue to payment
            </button>
          </div>
        ) : pay?.payment ? (
          <div className="stack">
            <div className="alert info">
              Order <span className="mono">{pay.payment.checkout?.order_id}</span> created for {inr((pay.payment.checkout?.amount_paise ?? 0) / 100)}. In production the
              provider checkout opens here and confirms via a signed webhook.
            </div>
            <button
              className="btn primary"
              onClick={async () => {
                const r = await act.run(() => api<Payment>(`/payments/${pay.payment!.id}/simulate`, { method: "POST" }));
                if (r) {
                  toast(`Payment received · ${r.receipt_number}`);
                  setPay(null);
                  invoices.reload();
                  payments.reload();
                }
              }}
            >
              Simulate successful payment (demo)
            </button>
            <ErrorBox error={act.error} />
          </div>
        ) : null}
      </Dialog>

      <Dialog title={`Record payment · ${record?.number}`} open={!!record} onClose={() => setRecord(null)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            const r = await act.run(() =>
              api<Payment>("/payments/record", {
                body: { invoice_id: record!.id, amount: Number(f.amount), method: f.method, reference: f.reference || null, paid_at: f.paid_at ? new Date(f.paid_at).toISOString() : null },
                headers: { "Idempotency-Key": key },
              }),
            );
            if (r) {
              toast(`Recorded · ${r.receipt_number}`);
              setRecord(null);
              invoices.reload();
              payments.reload();
            }
          }}
        >
          <Field label="Amount (₹)">
            <input required type="number" step="0.01" min="1" value={f.amount || ""} onChange={(e) => setF({ ...f, amount: e.target.value })} />
          </Field>
          <Field label="Method">
            <Select value={f.method} onChange={(v) => setF({ ...f, method: v })} options={["upi", "cash", "cheque", "bank_transfer"]} />
          </Field>
          <Field label="Reference (UTR / cheque no.)">
            <input value={f.reference || ""} onChange={(e) => setF({ ...f, reference: e.target.value })} />
          </Field>
          <Field label="Paid on">
            <input type="datetime-local" value={f.paid_at || ""} onChange={(e) => setF({ ...f, paid_at: e.target.value })} />
          </Field>
          <ErrorBox error={act.error} />
          <div className="actions full">
            <button className="btn primary" disabled={act.pending}>
              Record & issue receipt
            </button>
          </div>
        </form>
      </Dialog>
    </>
  );
}

function Plans() {
  const act = useAction();
  const toast = useToast();
  const plans = useApi<Plan[]>("/billing/plans");
  const [open, setOpen] = useState(false);
  const [gen, setGen] = useState<Plan | null>(null);
  const [f, setF] = useState<Record<string, string>>({ basis: "per_plot", frequency_months: "1", due_days: "15" });
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 8) + "01");
  return (
    <div className="card">
      <div className="card-head">
        <h2>Billing plans</h2>
        <button className="btn small primary" onClick={() => setOpen(true)}>
          New plan
        </button>
      </div>
      {plans.data && !plans.data.length ? <Empty title="No plans" /> : null}
      {plans.data?.map((p) => (
        <div key={p.id} className="list-item">
          <div>
            <div className="title">{p.name}</div>
            <div className="small muted">
              {label(p.basis)} · {inr(p.rate)}
              {p.basis === "per_sqft" ? "/sq ft" : ""} · every {p.frequency_months} month(s) · due in {p.due_days} days
            </div>
          </div>
          <button className="btn small" onClick={() => setGen(p)}>
            Generate dues
          </button>
        </div>
      ))}
      <ErrorBox error={act.error} />
      <Dialog title="New billing plan" open={open} onClose={() => setOpen(false)}>
        <form
          className="form two"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await act.run(() => api("/billing/plans", { body: { name: f.name, basis: f.basis, rate: Number(f.rate), frequency_months: Number(f.frequency_months), due_days: Number(f.due_days) } }))) {
              setOpen(false);
              plans.reload();
            }
          }}
        >
          <Field label="Name" full>
            <input required value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} />
          </Field>
          <Field label="Basis">
            <Select value={f.basis} onChange={(v) => setF({ ...f, basis: v })} options={["per_plot", "per_unit", "per_sqft", "fixed", "custom"]} />
          </Field>
          <Field label="Rate (₹)">
            <input required type="number" step="0.01" min="0" value={f.rate || ""} onChange={(e) => setF({ ...f, rate: e.target.value })} />
          </Field>
          <Field label="Every (months)">
            <input type="number" min="1" max="12" value={f.frequency_months} onChange={(e) => setF({ ...f, frequency_months: e.target.value })} />
          </Field>
          <Field label="Due after (days)">
            <input type="number" min="0" value={f.due_days} onChange={(e) => setF({ ...f, due_days: e.target.value })} />
          </Field>
          <div className="actions full">
            <button className="btn primary">Create</button>
          </div>
        </form>
      </Dialog>
      <Dialog title={`Generate dues · ${gen?.name}`} open={!!gen} onClose={() => setGen(null)}>
        <form
          className="form"
          onSubmit={async (e) => {
            e.preventDefault();
            const r = await act.run(() => api<{ created: number; skipped: string[] }>("/billing/generate", { body: { plan_id: gen!.id, period_start: period } }));
            if (r) {
              toast(`${r.created} invoices raised, ${r.skipped.length} skipped`);
              setGen(null);
            }
          }}
        >
          <Field label="Billing period starts" hint="Generating twice for the same period never duplicates dues">
            <input type="date" value={period} onChange={(e) => setPeriod(e.target.value)} />
          </Field>
          <div className="actions">
            <button className="btn primary">Generate</button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

function Defaulters() {
  const d = useApi<{ property: string; owner: string | null; phone: string | null; invoices: number; outstanding: number; oldest_due: string }[]>("/billing/defaulters");
  const rec = useApi<{ stale_orders: unknown[]; invoice_mismatches: unknown[] }>("/payments/reconciliation");
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card">
        <h2>Defaulters</h2>
        {d.data && !d.data.length ? <Empty title="No overdue dues" /> : null}
        {d.data?.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Property</th>
                  <th>Owner</th>
                  <th>Invoices</th>
                  <th>Outstanding</th>
                  <th>Oldest due</th>
                </tr>
              </thead>
              <tbody>
                {d.data.map((r) => (
                  <tr key={r.property}>
                    <td>{r.property}</td>
                    <td>
                      {r.owner || "—"} {r.phone ? <a href={`tel:${r.phone}`}>{r.phone}</a> : null}
                    </td>
                    <td>{r.invoices}</td>
                    <td>
                      <b>{inr(r.outstanding)}</b>
                    </td>
                    <td>{fmtDate(r.oldest_due)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
      <div className="card">
        <h2>Reconciliation</h2>
        {rec.data ? (
          rec.data.stale_orders.length || rec.data.invoice_mismatches.length ? (
            <div className="alert warn">
              {rec.data.stale_orders.length} stale payment orders · {rec.data.invoice_mismatches.length} invoices whose totals disagree with payments
            </div>
          ) : (
            <div className="alert ok">All payments reconcile with invoices.</div>
          )
        ) : null}
      </div>
    </div>
  );
}

function Expenses() {
  const act = useAction();
  const list = useApi<Page<{ id: string; category: string; amount: number; spent_on: string; description: string | null }>>("/billing/expenses", { limit: 100 });
  const [f, setF] = useState<Record<string, string>>({ category: "electricity", spent_on: new Date().toISOString().slice(0, 10) });
  return (
    <div className="card">
      <h2>Basic expenses</h2>
      <form
        className="row"
        style={{ marginBottom: 12 }}
        onSubmit={async (e) => {
          e.preventDefault();
          if (await act.run(() => api("/billing/expenses", { body: { category: f.category, amount: Number(f.amount), spent_on: f.spent_on, description: f.description || null } }))) {
            setF({ ...f, amount: "", description: "" });
            list.reload();
          }
        }}
      >
        <Select value={f.category} onChange={(v) => setF({ ...f, category: v })} options={["electricity", "water", "security", "maintenance", "gardening", "salaries", "other"]} style={{ width: 160 }} />
        <input required type="number" placeholder="Amount" value={f.amount || ""} onChange={(e) => setF({ ...f, amount: e.target.value })} style={{ width: 130 }} />
        <input type="date" value={f.spent_on} onChange={(e) => setF({ ...f, spent_on: e.target.value })} style={{ width: 160 }} />
        <input placeholder="Description" value={f.description || ""} onChange={(e) => setF({ ...f, description: e.target.value })} style={{ flex: 1, minWidth: 160 }} />
        <button className="btn primary">Add</button>
      </form>
      <ErrorBox error={act.error} />
      {list.data?.items.map((x) => (
        <div key={x.id} className="list-item">
          <span>
            {label(x.category)} {x.description ? <span className="muted">· {x.description}</span> : null}
          </span>
          <span>
            {inr(x.amount)} <span className="small muted">· {fmtDate(x.spent_on)}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

export default function BillingPage() {
  const { can } = useAuth();
  const admin = can("billing.manage");
  const [tab, setTab] = useState("dues");
  const summary = useApi<{ billed: number; collected: number; outstanding: number; overdue_invoices: number; expenses: number }>(admin ? "/billing/summary" : null);
  return (
    <>
      <PageHead title={admin ? "Billing & dues" : "Dues & payments"} sub="Recurring dues, receipts and payments. Full accounting and GST are outside GreenPlot V1." />
      {summary.data ? (
        <div className="stats">
          <Stat label="Billed" value={inr(summary.data.billed)} />
          <Stat label="Collected" value={inr(summary.data.collected)} />
          <Stat label="Outstanding" value={inr(summary.data.outstanding)} kind={summary.data.outstanding ? "warn" : undefined} />
          <Stat label="Overdue invoices" value={summary.data.overdue_invoices} kind={summary.data.overdue_invoices ? "alert" : undefined} />
          <Stat label="Expenses" value={inr(summary.data.expenses)} />
        </div>
      ) : null}
      {admin ? (
        <div className="tabs">
          {["dues", "plans", "defaulters", "expenses"].map((t) => (
            <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
              {label(t)}
            </button>
          ))}
        </div>
      ) : null}
      {tab === "dues" ? <Invoices admin={admin} /> : null}
      {tab === "plans" ? <Plans /> : null}
      {tab === "defaulters" ? <Defaulters /> : null}
      {tab === "expenses" ? <Expenses /> : null}
    </>
  );
}
