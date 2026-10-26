"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { loadCheckout, type RazorpayResponse } from "@/components/Pay";
import { ErrorBox, Field, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import { BUSINESS } from "@/lib/legal";
import { newId } from "@/lib/offline";
import {
  type CartLine,
  ORDER_STATUS,
  type Plant,
  type StoreConfig,
  type StoreOrder,
  addToCart,
  onCartChange,
  orderPath,
  readCart,
  rupees,
  saveOrder,
  writeCart,
} from "@/lib/store";

// The cart is read from localStorage; a snapshot string keeps useSyncExternalStore stable between renders.
const cartSnapshot = () => (typeof window === "undefined" ? "[]" : JSON.stringify(readCart()));

export function useCart(): CartLine[] {
  const raw = useSyncExternalStore(onCartChange, cartSnapshot, () => "[]");
  return JSON.parse(raw) as CartLine[];
}

export function CartButton() {
  const count = useCart().reduce((n, l) => n + l.quantity, 0);
  return (
    <Link href="/store/cart" className="btn small primary" aria-label={`Cart, ${count} item${count === 1 ? "" : "s"}`}>
      Cart{count ? <span className="store-count">{count}</span> : null}
    </Link>
  );
}

function Stepper({ value, onChange, max }: { value: number; onChange: (v: number) => void; max: number }) {
  return (
    <div className="store-qty" role="group" aria-label="Quantity">
      <button type="button" className="btn small" onClick={() => onChange(Math.max(1, value - 1))} disabled={value <= 1} aria-label="One less">
        −
      </button>
      <span aria-live="polite">{value}</span>
      <button type="button" className="btn small" onClick={() => onChange(Math.min(max, value + 1))} disabled={value >= max} aria-label="One more">
        +
      </button>
    </div>
  );
}

/** Quantity and "Add to cart" on a plant's page. */
export function AddToCart({ plant }: { plant: Pick<Plant, "slug" | "name" | "price" | "image" | "stock"> }) {
  const toast = useToast();
  const router = useRouter();
  const max = Math.min(20, plant.stock ?? 20);
  const [qty, setQty] = useState(1);
  if (max <= 0) return <p className="alert info">Out of stock. WhatsApp us and we will tell you when it is back.</p>;
  return (
    <div className="store-buy">
      <Stepper value={qty} onChange={setQty} max={max} />
      <button
        className="btn primary big"
        onClick={() => {
          addToCart(plant, qty, max);
          toast(`${qty} × ${plant.name} added to your cart`);
        }}
      >
        Add to cart
      </button>
      <button
        className="btn big"
        onClick={() => {
          addToCart(plant, qty, max);
          router.push("/store/checkout");
        }}
      >
        Buy now
      </button>
    </div>
  );
}

/** Small "Add" button on the store listing. */
export function QuickAdd({ plant }: { plant: Pick<Plant, "slug" | "name" | "price" | "image" | "stock"> }) {
  const toast = useToast();
  if (plant.stock === 0) return <span className="small muted">Out of stock</span>;
  return (
    <button
      className="btn small primary"
      onClick={() => {
        addToCart(plant, 1, Math.min(20, plant.stock ?? 20));
        toast(`${plant.name} added to your cart`);
      }}
    >
      Add
    </button>
  );
}

function totals(lines: CartLine[], cfg: Pick<StoreConfig, "delivery_fee" | "free_delivery_over"> | null) {
  const subtotal = lines.reduce((n, l) => n + l.price * l.quantity, 0);
  const fee = !cfg || !lines.length ? 0 : subtotal >= cfg.free_delivery_over ? 0 : cfg.delivery_fee;
  return { subtotal, fee, total: subtotal + fee };
}

function Summary({ lines, cfg }: { lines: CartLine[]; cfg: StoreConfig | null }) {
  const t = totals(lines, cfg);
  return (
    <dl className="store-sum">
      <dt>Subtotal</dt>
      <dd>{rupees(t.subtotal)}</dd>
      <dt>Delivery</dt>
      <dd>{t.fee ? rupees(t.fee) : "Free"}</dd>
      <dt className="store-total">Total</dt>
      <dd className="store-total">{rupees(t.total)}</dd>
    </dl>
  );
}

/** The cart page. */
export function CartView({ cfg }: { cfg: StoreConfig | null }) {
  const lines = useCart();
  const set = (slug: string, quantity: number) => writeCart(readCart().map((l) => (l.slug === slug ? { ...l, quantity } : l)));
  if (!lines.length)
    return (
      <div className="card store-empty">
        <h2>Your cart is empty</h2>
        <p className="muted">Pick a few plants for your home, balcony or plot.</p>
        <Link href="/store" className="btn primary">
          Browse plants
        </Link>
      </div>
    );
  const t = totals(lines, cfg);
  return (
    <div className="store-cart">
      <ul className="store-lines">
        {lines.map((l) => (
          <li key={l.slug} className="card">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={l.image} alt="" />
            <div className="store-line-main">
              <Link href={`/store/${l.slug}`}>
                <b>{l.name}</b>
              </Link>
              <span className="small muted">{rupees(l.price)} each</span>
              <div className="row">
                <Stepper value={l.quantity} onChange={(q) => set(l.slug, q)} max={cfg?.max_quantity ?? 20} />
                <button className="btn small ghost" onClick={() => set(l.slug, 0)}>
                  Remove
                </button>
              </div>
            </div>
            <b className="store-line-total">{rupees(l.price * l.quantity)}</b>
          </li>
        ))}
      </ul>
      <aside className="card store-side">
        <h2>Order summary</h2>
        <Summary lines={lines} cfg={cfg} />
        {cfg && t.fee ? <p className="small muted">Add {rupees(cfg.free_delivery_over - t.subtotal)} more for free delivery.</p> : null}
        <Link href="/store/checkout" className="btn primary big">
          Checkout
        </Link>
        <Link href="/store" className="btn ghost">
          Continue shopping
        </Link>
      </aside>
    </div>
  );
}

const EMPTY = { name: "", phone: "", email: "", address: "", area: "", pincode: "", landmark: "", notes: "" };

/** Delivery details and payment choice; places the order and opens payment when paying online. */
export function Checkout({ cfg }: { cfg: StoreConfig | null }) {
  const lines = useCart();
  const router = useRouter();
  const act = useAction();
  const [f, setF] = useState(EMPTY);
  // One key per checkout visit, so a double tap never places two orders.
  const [key] = useState(() => newId("ord"));
  const t = totals(lines, cfg);
  const codOk = !!cfg?.cod && t.total <= (cfg?.cod_limit ?? 0);
  const [method, setMethod] = useState<"cod" | "online" | null>(null);
  const chosen = method ?? (cfg?.online ? "online" : codOk ? "cod" : null);
  const pinOk = !f.pincode || !cfg || cfg.pincode_prefixes.some((p) => f.pincode.startsWith(p));
  const field = (k: keyof typeof EMPTY) => ({ value: f[k], onChange: (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value }) });

  if (!lines.length)
    return (
      <div className="card store-empty">
        <h2>Your cart is empty</h2>
        <Link href="/store" className="btn primary">
          Browse plants
        </Link>
      </div>
    );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!chosen) return;
    const r = await act.run(() =>
      api<{ order: StoreOrder; token: string | null }>("/public/store/orders", {
        body: { ...f, email: f.email || null, landmark: f.landmark || null, notes: f.notes || null, payment_method: chosen, items: lines.map((l) => ({ slug: l.slug, quantity: l.quantity })) },
        headers: { "Idempotency-Key": key },
      }),
    );
    if (!r) return;
    if (r.token) saveOrder({ number: r.order.number, token: r.token, total: r.order.total, at: r.order.created_at });
    writeCart([]);
    if (r.token) router.push(`${orderPath(r.order.number, r.token)}${chosen === "online" ? "&pay=1" : ""}`);
  }

  return (
    <form className="store-cart" onSubmit={submit}>
      <div className="card form two store-form">
        <h2 className="full">Delivery details</h2>
        <Field label="Full name">
          <input required minLength={2} autoComplete="name" {...field("name")} />
        </Field>
        <Field label="Mobile number" hint="We call before delivery">
          <input required type="tel" inputMode="tel" pattern="[\d+\s\(\)\-]{10,20}" autoComplete="tel" {...field("phone")} />
        </Field>
        <Field label="Email (optional)" hint="For your bill" full>
          <input type="email" autoComplete="email" {...field("email")} />
        </Field>
        <Field label="House / flat, street" full>
          <textarea required minLength={8} rows={2} autoComplete="street-address" {...field("address")} />
        </Field>
        <Field label="Area">
          <input required minLength={2} placeholder="e.g. Jalahalli" {...field("area")} />
        </Field>
        <Field label="PIN code" hint={pinOk ? "Bangalore only for now" : "We deliver only within Bangalore for now"}>
          <input required inputMode="numeric" pattern="[1-9][0-9]{5}" maxLength={6} autoComplete="postal-code" {...field("pincode")} aria-invalid={!pinOk} />
        </Field>
        <Field label="Landmark (optional)" full>
          <input {...field("landmark")} />
        </Field>
        <Field label="Notes for delivery (optional)" full>
          <textarea rows={2} placeholder="Best time to deliver, gate code…" {...field("notes")} />
        </Field>
        <fieldset className="full store-pay">
          <legend>Payment</legend>
          {cfg?.online ? (
            <label className={`store-opt${chosen === "online" ? " on" : ""}`}>
              <input type="radio" name="pay" checked={chosen === "online"} onChange={() => setMethod("online")} />
              <span>
                <b>Pay online</b>
                <small>UPI, cards or net banking through Razorpay{cfg.online === "demo" ? " (test mode: no real money is taken)" : ""}</small>
              </span>
            </label>
          ) : null}
          {cfg?.cod ? (
            <label className={`store-opt${chosen === "cod" ? " on" : ""}${codOk ? "" : " off"}`}>
              <input type="radio" name="pay" checked={chosen === "cod"} disabled={!codOk} onChange={() => setMethod("cod")} />
              <span>
                <b>Cash on delivery</b>
                <small>{codOk ? "Pay in cash or UPI when the plants arrive" : `Available for orders up to ${rupees(cfg.cod_limit)}`}</small>
              </span>
            </label>
          ) : null}
          {!cfg ? <p className="alert error">The store is not reachable right now. Please try again, or WhatsApp us to order.</p> : null}
        </fieldset>
      </div>
      <aside className="card store-side">
        <h2>Your order</h2>
        <ul className="store-mini">
          {lines.map((l) => (
            <li key={l.slug}>
              <span>
                {l.quantity} × {l.name}
              </span>
              <span>{rupees(l.price * l.quantity)}</span>
            </li>
          ))}
        </ul>
        <Summary lines={lines} cfg={cfg} />
        <ErrorBox error={act.error} />
        <button className="btn primary big" disabled={act.pending || !chosen || !pinOk || !cfg}>
          {act.pending ? "Placing order…" : chosen === "online" ? `Place order and pay ${rupees(t.total)}` : "Place order"}
        </button>
        <p className="small muted">
          By placing the order you agree to our <Link href="/terms">terms</Link> and <Link href="/refund-policy">refund policy</Link>. Prices include all taxes.
        </p>
        <Link href="/store/cart" className="btn ghost">
          Back to cart
        </Link>
      </aside>
    </form>
  );
}

// ------------------------------------------------------------------ order and bill

/** The customer's order page: status, payment and the printable bill. */
export function OrderView({ number }: { number: string }) {
  const params = useSearchParams();
  const token = params.get("t") || "";
  const toast = useToast();
  const act = useAction();
  const [order, setOrder] = useState<StoreOrder | null>(null);
  const [missing, setMissing] = useState(false);
  const [demoOrder, setDemoOrder] = useState<string | null>(null);
  const q = { t: token };

  useEffect(() => {
    if (!token) {
      setMissing(true);
      return;
    }
    api<StoreOrder>(`/public/store/orders/${number}`, { query: q })
      .then(setOrder)
      .catch(() => setMissing(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [number, token]);

  async function pay() {
    const co = await act.run(() =>
      api<{ key_id: string | null; order_id: string; amount_paise: number; currency: string; name: string; description: string; prefill: Record<string, string | null> }>(
        `/public/store/orders/${number}/pay`,
        { method: "POST", query: q },
      ),
    );
    if (!co) return;
    if (!co.key_id) {
      setDemoOrder(co.order_id);
      return;
    }
    try {
      const Razorpay = await loadCheckout();
      const rzp = new Razorpay({
        key: co.key_id,
        order_id: co.order_id,
        amount: co.amount_paise,
        currency: co.currency,
        name: co.name,
        description: co.description,
        prefill: Object.fromEntries(Object.entries(co.prefill || {}).filter(([, v]) => v)),
        theme: { color: "#159a63" },
        handler: async (r: RazorpayResponse) => {
          const out = await act.run(() => api<StoreOrder>(`/public/store/orders/${number}/verify`, { body: r, query: q }));
          if (out) {
            setOrder(out);
            toast(out.payment_status === "paid" ? "Payment received. Thank you!" : "Payment is being confirmed; this page will show it shortly");
          }
        },
      });
      rzp.on("payment.failed", (r) => toast(r.error?.description || "Payment failed", "error"));
      rzp.open();
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  // Coming straight from checkout with online payment: open the payment window once.
  const autoPay = params.get("pay") === "1";
  const [autoDone, setAutoDone] = useState(false);
  useEffect(() => {
    if (autoPay && !autoDone && order && order.payment_method === "online" && order.payment_status !== "paid" && order.status !== "cancelled") {
      setAutoDone(true);
      pay();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order, autoPay, autoDone]);

  if (missing)
    return (
      <div className="card store-empty">
        <h2>Order not found</h2>
        <p className="muted">Open the order from the link we sent you, or WhatsApp us with your order number.</p>
      </div>
    );
  if (!order) return <div className="card store-empty">Loading your order…</div>;

  const unpaidOnline = order.payment_method === "online" && order.payment_status !== "paid" && order.status !== "cancelled";
  const steps: StoreOrder["status"][] = ["placed", "confirmed", "out_for_delivery", "delivered"];
  const at = steps.indexOf(order.status);

  return (
    <div className="stack">
      <div className="card store-done no-print">
        {order.status === "cancelled" ? (
          <h2>Order {order.number} was cancelled</h2>
        ) : unpaidOnline ? (
          <h2>Almost done: pay {rupees(order.total)} to confirm order {order.number}</h2>
        ) : (
          <h2>Thank you, {order.customer_name.split(" ")[0]}! Order {order.number} is {order.status === "delivered" ? "delivered" : "confirmed"}.</h2>
        )}
        {order.status !== "cancelled" && order.status !== "pending_payment" ? (
          <ol className="store-track" aria-label="Order progress">
            {steps.map((s, i) => (
              <li key={s} className={i <= at ? "done" : ""} aria-current={i === at ? "step" : undefined}>
                {ORDER_STATUS[s]}
              </li>
            ))}
          </ol>
        ) : null}
        {order.cancelled_reason ? <p className="muted">Reason: {order.cancelled_reason}</p> : null}
        <ErrorBox error={act.error} />
        {unpaidOnline ? (
          demoOrder ? (
            <div className="stack">
              <div className="alert info">
                Test mode: payment order <span className="mono">{demoOrder}</span> was created, but Razorpay keys are not set up yet, so no real money is taken.
              </div>
              <button
                className="btn primary"
                disabled={act.pending}
                onClick={async () => {
                  const r = await act.run(() => api<StoreOrder>(`/public/store/orders/${number}/simulate`, { method: "POST", query: q }));
                  if (r) {
                    setOrder(r);
                    toast("Test payment received");
                  }
                }}
              >
                Simulate a successful payment (test)
              </button>
            </div>
          ) : (
            <div className="row">
              <button className="btn primary big" disabled={act.pending} onClick={pay}>
                Pay {rupees(order.total)}
              </button>
            </div>
          )
        ) : null}
        <p className="small muted">
          Save this page: it is your order link. We have also sent it to {order.phone}
          {order.email ? ` and ${order.email}` : ""}. Questions? WhatsApp us on {BUSINESS.phone}.
        </p>
        <div className="row">
          <button className="btn" onClick={() => window.print()}>
            Print bill
          </button>
          <a className="btn" href={`/api/v1/public/store/orders/${number}/bill.pdf?t=${encodeURIComponent(token)}`} target="_blank" rel="noopener noreferrer">
            Download bill (PDF)
          </a>
          <Link className="btn ghost" href="/store">
            Shop more
          </Link>
        </div>
      </div>
      <Bill order={order} />
    </div>
  );
}

/** The bill, laid out for screen and print. */
export function Bill({ order }: { order: StoreOrder }) {
  const paid =
    order.payment_status === "paid"
      ? `Paid${order.payment_method === "online" ? " online" : ""}${order.paid_at ? ` on ${fmtDateTime(order.paid_at)}` : ""}`
      : order.payment_method === "cod"
        ? "To pay on delivery"
        : "Not paid yet";
  return (
    <article className="card store-bill" aria-label={`Bill ${order.bill_number}`}>
      <header className="store-bill-head">
        <div>
          <div className="legal-brand">
            <span>Green</span>Plot
          </div>
          <p className="small muted">
            {BUSINESS.legalName}
            <br />
            {BUSINESS.address}
            <br />
            {BUSINESS.phone} · {BUSINESS.email}
          </p>
        </div>
        <div className="store-bill-no">
          <h2>Bill</h2>
          <p>
            <b>{order.bill_number}</b>
          </p>
          <p className="small muted">
            Order {order.number}
            <br />
            {fmtDateTime(order.created_at)}
          </p>
        </div>
      </header>
      <div className="store-bill-to">
        <div>
          <p className="small muted">Billed and delivered to</p>
          <p>
            <b>{order.customer_name}</b>
            <br />
            {order.address}, {order.area}, Bangalore {order.pincode}
            {order.landmark ? (
              <>
                <br />
                Near {order.landmark}
              </>
            ) : null}
            <br />
            {order.phone}
            {order.email ? ` · ${order.email}` : ""}
          </p>
        </div>
        <div>
          <p className="small muted">Payment</p>
          <p>
            <b>{order.payment_method === "cod" ? "Cash on delivery" : "Online (Razorpay)"}</b>
            <br />
            {paid}
            {order.provider_payment_id ? (
              <>
                <br />
                <span className="mono small">{order.provider_payment_id}</span>
              </>
            ) : null}
          </p>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Item</th>
              <th className="num">Qty</th>
              <th className="num">Price</th>
              <th className="num">Amount</th>
            </tr>
          </thead>
          <tbody>
            {order.items.map((it) => (
              <tr key={it.slug}>
                <td>{it.name}</td>
                <td className="num">{it.quantity}</td>
                <td className="num">{rupees(it.unit_price)}</td>
                <td className="num">{rupees(it.line_total)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={3}>Subtotal</td>
              <td className="num">{rupees(order.subtotal)}</td>
            </tr>
            <tr>
              <td colSpan={3}>Delivery</td>
              <td className="num">{order.delivery_fee ? rupees(order.delivery_fee) : "Free"}</td>
            </tr>
            <tr className="store-total">
              <td colSpan={3}>Total</td>
              <td className="num">{rupees(order.total)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="small muted">Prices include all taxes. This is a computer-generated bill and needs no signature.</p>
    </article>
  );
}
