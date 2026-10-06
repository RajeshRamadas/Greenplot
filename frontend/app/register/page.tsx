"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ErrorBox, Field, Select } from "@/components/ui";
import { publicPost } from "@/lib/api";

type Layout = { slug: string; name: string; city: string };
type CodeResp = { sent: boolean; channels: string[]; dev_code?: string };

const SERVICES = ["cleaning", "gardening", "plumbing", "electrical", "gate_fence", "civil", "painting", "repairs", "security", "other"];

/** Residents and vendors ask to join a layout; the layout office approves and sends the invite. */
export default function RegisterPage() {
  const [q, setQ] = useState("");
  const [layouts, setLayouts] = useState<Layout[]>([]);
  const [layout, setLayout] = useState<Layout | null>(null);
  const [f, setF] = useState<Record<string, string>>({ kind: "resident", relation: "owner" });
  const [services, setServices] = useState<string[]>([]);
  const [sent, setSent] = useState<CodeResp | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (q.trim().length < 2 || layout) return setLayouts([]);
    const t = setTimeout(async () => {
      try {
        const r = await fetch(`/api/v1/public/layouts?q=${encodeURIComponent(q.trim())}`);
        setLayouts(r.ok ? await r.json() : []);
      } catch {
        setLayouts([]);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [q, layout]);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const vendor = f.kind === "vendor";
  return (
    <div className="auth-page">
      <div className="card auth-card" style={{ width: "min(520px, 100%)" }}>
        <div className="brand" style={{ padding: "0 0 18px" }}>
          <b style={{ fontSize: 30 }}>
            <span>Green</span>Plot
          </b>
          <small>Request access to your layout</small>
        </div>
        {done ? (
          <div className="stack">
            <div className="alert ok">
              Thanks! Your request has been sent to <b>{done}</b>. Once the office approves it, you&apos;ll get a link by email and on your phone to set your password.
            </div>
            <Link className="btn" href="/">
              Back to website
            </Link>
          </div>
        ) : (
          <form
            className="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!layout) return setError("Choose your layout");
              if (!sent) return run(async () => setSent(await publicPost<CodeResp>("/public/signup/code", { phone: f.phone })));
              run(async () => {
                const r = await publicPost<{ layout: string }>("/public/signup", {
                  layout: layout.slug,
                  kind: f.kind,
                  full_name: f.name,
                  email: f.email,
                  phone: f.phone,
                  code: (f.code || "").trim(),
                  plot_number: vendor ? null : f.plot,
                  relation: vendor ? null : f.relation,
                  company_name: vendor ? f.company : null,
                  service_categories: vendor ? services : [],
                  message: f.message || null,
                });
                setDone(r.layout);
              });
            }}
          >
            <Field label="Your layout / association">
              {layout ? (
                <div className="row between">
                  <b>
                    {layout.name} <span className="small muted">· {layout.city}</span>
                  </b>
                  <button type="button" className="btn small ghost" disabled={!!sent} onClick={() => (setLayout(null), setQ(""))}>
                    Change
                  </button>
                </div>
              ) : (
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Start typing the layout name" autoFocus />
              )}
            </Field>
            {!layout && layouts.length ? (
              <div className="list" role="listbox" aria-label="Matching layouts">
                {layouts.map((l) => (
                  <button key={l.slug} type="button" role="option" aria-selected={false} className="list-item btn ghost" style={{ justifyContent: "space-between" }} onClick={() => setLayout(l)}>
                    <span className="title">{l.name}</span>
                    <span className="small muted">{l.city}</span>
                  </button>
                ))}
              </div>
            ) : null}
            <Field label="I am a">
              <Select value={f.kind} disabled={!!sent} onChange={(v) => setF({ ...f, kind: v })} options={[{ value: "resident", label: "Resident / plot owner" }, { value: "vendor", label: "Vendor / service provider" }]} />
            </Field>
            <Field label="Full name">
              <input required minLength={2} disabled={!!sent} value={f.name || ""} onChange={(e) => setF({ ...f, name: e.target.value })} />
            </Field>
            <Field label="Email">
              <input required type="email" disabled={!!sent} value={f.email || ""} onChange={(e) => setF({ ...f, email: e.target.value })} />
            </Field>
            <Field label="Mobile number" hint="We'll send a code to confirm it">
              <input required type="tel" disabled={!!sent} value={f.phone || ""} onChange={(e) => setF({ ...f, phone: e.target.value })} placeholder="98450 12345" />
            </Field>
            {vendor ? (
              <>
                <Field label="Company name">
                  <input required disabled={!!sent} value={f.company || ""} onChange={(e) => setF({ ...f, company: e.target.value })} />
                </Field>
                <Field label="Services you provide">
                  <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                    {SERVICES.map((s) => (
                      <label key={s} className="small row" style={{ gap: 4 }}>
                        <input type="checkbox" disabled={!!sent} checked={services.includes(s)} onChange={(e) => setServices(e.target.checked ? [...services, s] : services.filter((x) => x !== s))} />
                        {s.replace("_", " / ")}
                      </label>
                    ))}
                  </div>
                </Field>
              </>
            ) : (
              <div className="form two" style={{ gap: 12 }}>
                <Field label="Plot number">
                  <input required disabled={!!sent} value={f.plot || ""} onChange={(e) => setF({ ...f, plot: e.target.value })} placeholder="e.g. 117" />
                </Field>
                <Field label="I am the">
                  <Select value={f.relation} disabled={!!sent} onChange={(v) => setF({ ...f, relation: v })} options={[{ value: "owner", label: "Owner" }, { value: "tenant", label: "Tenant" }, { value: "family", label: "Family member" }]} />
                </Field>
              </div>
            )}
            <Field label="Message to the office (optional)">
              <textarea disabled={!!sent} value={f.message || ""} onChange={(e) => setF({ ...f, message: e.target.value })} />
            </Field>
            {sent ? (
              <>
                <div className="alert info small">
                  Enter the code we sent to {f.phone}.{sent.dev_code ? ` Demo code: ${sent.dev_code}` : ""}
                </div>
                <Field label="6-digit code">
                  <input inputMode="numeric" autoComplete="one-time-code" required maxLength={6} value={f.code || ""} onChange={(e) => setF({ ...f, code: e.target.value })} />
                </Field>
              </>
            ) : null}
            <ErrorBox error={error} />
            <button className="btn primary big" disabled={busy}>
              {busy ? "Please wait…" : sent ? "Send request" : "Verify mobile number"}
            </button>
            {sent ? (
              <button type="button" className="btn ghost" onClick={() => setSent(null)}>
                Edit details
              </button>
            ) : null}
          </form>
        )}
        <p className="small muted" style={{ marginTop: 16 }}>
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
