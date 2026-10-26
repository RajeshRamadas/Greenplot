"use client";

import { useState } from "react";
import { Dialog, ErrorBox, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { inr } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import { newId } from "@/lib/offline";
import type { Payment } from "@/lib/types";

const CHECKOUT_JS = "https://checkout.razorpay.com/v1/checkout.js";

export interface RazorpayResponse {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

export type RazorpayCtor = new (options: Record<string, unknown>) => { open: () => void; on: (event: string, fn: (r: { error?: { description?: string } }) => void) => void };

/** Load Razorpay Checkout's script once. */
export function loadCheckout(): Promise<RazorpayCtor> {
  const w = window as unknown as { Razorpay?: RazorpayCtor };
  if (w.Razorpay) return Promise.resolve(w.Razorpay);
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = CHECKOUT_JS;
    s.onload = () => (w.Razorpay ? resolve(w.Razorpay) : reject(new Error("Payment window failed to load")));
    s.onerror = () => reject(new Error("Payment window failed to load; check your connection"));
    document.body.appendChild(s);
  });
}

/** Pay what is outstanding on an invoice through Razorpay Checkout (or the demo simulation when no gateway is set up). */
export function PayDialog({
  invoice,
  onClose,
  onPaid,
}: {
  invoice: { id: string; description: string; outstanding: number } | null;
  onClose: () => void;
  onPaid: (p: Payment) => void;
}) {
  const toast = useToast();
  const act = useAction();
  const [payment, setPayment] = useState<Payment | null>(null);
  // One idempotency key per dialog so double-clicks never create two orders.
  const [key, setKey] = useState("");
  const [shownFor, setShownFor] = useState<string | null>(null);
  if (invoice && invoice.id !== shownFor) {
    setShownFor(invoice.id);
    setPayment(null);
    setKey(newId("pay"));
  }

  function done(p: Payment) {
    toast(`Payment received · ${p.receipt_number}`);
    setPayment(null);
    onPaid(p);
    onClose();
  }

  async function openCheckout(p: Payment) {
    const co = p.checkout!;
    const Razorpay = await loadCheckout();
    const rzp = new Razorpay({
      key: co.key_id,
      order_id: co.order_id,
      amount: co.amount_paise,
      currency: co.currency,
      name: co.name,
      description: co.description,
      prefill: Object.fromEntries(Object.entries(co.prefill || {}).filter(([, v]) => v)),
      theme: { color: "#2f7d32" },
      handler: async (r: RazorpayResponse) => {
        const out = await act.run(() => api<Payment>(`/payments/${p.id}/verify`, { body: r }));
        if (out?.status === "succeeded") done(out);
        else if (out) toast("Payment is being confirmed; it will show as paid shortly");
      },
    });
    rzp.on("payment.failed", (r) => toast(r.error?.description || "Payment failed", "error"));
    rzp.open();
  }

  async function start() {
    const p = payment ?? (await act.run(() => api<Payment>("/payments", { body: { invoice_id: invoice!.id }, headers: { "Idempotency-Key": key } })));
    if (!p) return;
    setPayment(p);
    if (p.checkout?.key_id) await openCheckout(p).catch((e) => toast(e.message, "error"));
  }

  return (
    <Dialog title="Pay" open={!!invoice} onClose={onClose}>
      {invoice ? (
        <div className="stack">
          <p>
            {invoice.description} · <b>{inr(invoice.outstanding)}</b>
          </p>
          <p className="small muted">Payment is completed in Razorpay&apos;s secure window (UPI, cards, net banking). GreenPlot never sees or stores your card details.</p>
          <ErrorBox error={act.error} />
          {payment && !payment.checkout?.key_id ? (
            <>
              <div className="alert info">
                Demo mode: order <span className="mono">{payment.checkout?.order_id}</span> was created, but no Razorpay keys are configured.
              </div>
              <button
                className="btn primary"
                disabled={act.pending}
                onClick={async () => {
                  const r = await act.run(() => api<Payment>(`/payments/${payment.id}/simulate`, { method: "POST" }));
                  if (r) done(r);
                }}
              >
                Simulate successful payment (demo)
              </button>
            </>
          ) : (
            <button className="btn primary big" disabled={act.pending} onClick={start}>
              {payment ? "Open payment window again" : `Pay ${inr(invoice.outstanding)}`}
            </button>
          )}
        </div>
      ) : null}
    </Dialog>
  );
}
