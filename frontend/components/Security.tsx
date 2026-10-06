"use client";

import { useState } from "react";
import { Badge, ErrorBox, Field, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ago, fmtDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

/** 2-step verification with an authenticator app (TOTP) and single-use recovery codes. */
export function TwoStepCard({ highlight }: { highlight?: boolean }) {
  const { me, reload } = useAuth();
  const toast = useToast();
  const { run, error, pending } = useAction();
  const [setup, setSetup] = useState<{ secret: string; qr_svg: string } | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [codes, setCodes] = useState<string[] | null>(null);
  if (!me) return null;
  const on = me.totp_enabled;

  return (
    <div className="card" style={{ marginBottom: 16, outline: highlight ? "2px solid var(--amber)" : undefined }} id="two-step">
      <div className="card-head">
        <h2>2-step verification</h2>
        <Badge status={on ? "completed" : "pending"} text={on ? "On" : "Off"} />
      </div>
      {me.mfa_setup_required ? <div className="alert warn" style={{ marginBottom: 12 }}>Your role requires 2-step verification. Set it up to continue using GreenPlot.</div> : null}
      <p className="muted" style={{ marginTop: 0 }}>
        After your password (or phone code), GreenPlot also asks for a 6-digit code from an authenticator app such as Google Authenticator or Microsoft Authenticator.
      </p>
      {codes ? (
        <div className="stack">
          <div className="alert ok">Save these recovery codes somewhere safe. Each works once if you lose your phone. They won&apos;t be shown again.</div>
          <pre className="mono" style={{ background: "var(--grey-bg)", padding: 12, borderRadius: 10, columns: 2 }}>{codes.join("\n")}</pre>
          <div className="row">
            <button className="btn" onClick={() => navigator.clipboard?.writeText(codes.join("\n")).then(() => toast("Copied"))}>
              Copy codes
            </button>
            <button className="btn primary" onClick={() => setCodes(null)}>
              I&apos;ve saved them
            </button>
          </div>
        </div>
      ) : !on && !setup ? (
        <button className="btn primary" disabled={pending} onClick={async () => setSetup((await run(() => api<{ secret: string; qr_svg: string }>("/auth/2fa/setup", { method: "POST" }))) ?? null)}>
          Set up 2-step verification
        </button>
      ) : !on && setup ? (
        <form
          className="stack"
          onSubmit={async (e) => {
            e.preventDefault();
            const r = await run(() => api<{ recovery_codes: string[] }>("/auth/2fa/enable", { body: { code: code.trim() } }));
            if (r) {
              setCodes(r.recovery_codes);
              setSetup(null);
              setCode("");
              await reload();
            }
          }}
        >
          <div className="row" style={{ alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
            <img src={setup.qr_svg} alt="QR code to scan with your authenticator app" width={180} height={180} style={{ background: "#fff", borderRadius: 10 }} />
            <div className="stack" style={{ flex: 1, minWidth: 220 }}>
              <p className="small" style={{ margin: 0 }}>
                1. Scan the QR code with your authenticator app. Can&apos;t scan? Enter this key: <span className="mono">{setup.secret.replace(/(.{4})/g, "$1 ")}</span>
              </p>
              <Field label="2. Enter the 6-digit code it shows">
                <input inputMode="numeric" autoComplete="one-time-code" required maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} />
              </Field>
            </div>
          </div>
          <ErrorBox error={error} />
          <div className="row">
            <button className="btn primary" disabled={pending}>
              Turn on
            </button>
            <button type="button" className="btn ghost" onClick={() => setSetup(null)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <form className="stack" onSubmit={(e) => e.preventDefault()}>
          <p className="small muted" style={{ margin: 0 }}>
            {me.recovery_codes_left} recovery code{me.recovery_codes_left === 1 ? "" : "s"} left.
          </p>
          <div className="form two">
            <Field label="Code from your app">
              <input inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} />
            </Field>
            <Field label="Password (to turn off)">
              <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
          </div>
          <ErrorBox error={error} />
          <div className="row">
            <button
              className="btn"
              disabled={pending || !code}
              onClick={async () => {
                const r = await run(() => api<{ recovery_codes: string[] }>("/auth/2fa/recovery-codes", { body: { code: code.trim() } }));
                if (r) {
                  setCodes(r.recovery_codes);
                  setCode("");
                  await reload();
                }
              }}
            >
              New recovery codes
            </button>
            <button
              className="btn danger"
              disabled={pending || !code || !password}
              onClick={async () => {
                if (await run(() => api("/auth/2fa/disable", { body: { code: code.trim(), password } }))) {
                  setCode("");
                  setPassword("");
                  await reload();
                  toast("2-step verification turned off");
                }
              }}
            >
              Turn off
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

interface SessionRow {
  id: string;
  device: string | null;
  ip: string | null;
  created_at: string;
  last_used_at: string | null;
  current: boolean;
}

function deviceName(ua: string | null) {
  if (!ua) return "Unknown device";
  const os = /Android/i.test(ua) ? "Android" : /iPhone|iPad/i.test(ua) ? "iPhone / iPad" : /Windows/i.test(ua) ? "Windows" : /Mac OS/i.test(ua) ? "Mac" : /Linux/i.test(ua) ? "Linux" : "";
  const br = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "";
  return [br, os].filter(Boolean).join(" on ") || ua.slice(0, 60);
}

/** Devices signed in to the account, with sign-out per device. */
export function SessionsCard() {
  const toast = useToast();
  const { run, error, pending } = useAction();
  const { data, reload } = useApi<SessionRow[]>("/auth/sessions");
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h2>Signed-in devices</h2>
      <ErrorBox error={error} />
      <div className="list">
        {data?.map((s) => (
          <div key={s.id} className="list-item">
            <div>
              <div className="title">
                {deviceName(s.device)} {s.current ? <Badge status="completed" text="This device" /> : null}
              </div>
              <div className="small muted">
                {s.ip ? `${s.ip} · ` : ""}signed in {fmtDateTime(s.created_at)} · active {ago(s.last_used_at)}
              </div>
            </div>
            {!s.current ? (
              <button
                className="btn small"
                disabled={pending}
                onClick={async () => {
                  if (await run(() => api(`/auth/sessions/${s.id}`, { method: "DELETE" }))) {
                    reload();
                    toast("Signed out of that device");
                  }
                }}
              >
                Sign out
              </button>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Change the account's mobile number; the new number is confirmed with a code. */
export function PhoneVerify({ onDone }: { onDone?: () => void }) {
  const { me, reload } = useAuth();
  const toast = useToast();
  const { run, error, pending } = useAction();
  const [phone, setPhone] = useState("");
  const [sent, setSent] = useState<{ dev_code?: string } | null>(null);
  const [code, setCode] = useState("");
  if (!me) return null;
  return (
    <form
      className="stack"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!sent) {
          const r = await run(() => api<{ dev_code?: string }>("/auth/phone/request", { body: { phone } }));
          if (r) setSent(r);
          return;
        }
        if (await run(() => api("/auth/phone/confirm", { body: { phone, code: code.trim() } }))) {
          setSent(null);
          setCode("");
          setPhone("");
          await reload();
          toast("Mobile number verified");
          onDone?.();
        }
      }}
    >
      <div className="form two">
        <Field label={me.phone ? "New mobile number" : "Mobile number"}>
          <input type="tel" required value={phone} disabled={!!sent} onChange={(e) => setPhone(e.target.value)} placeholder="98450 12345" />
        </Field>
        {sent ? (
          <Field label="Code sent to that number" hint={sent.dev_code ? `Demo code: ${sent.dev_code}` : undefined}>
            <input inputMode="numeric" autoComplete="one-time-code" required maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} />
          </Field>
        ) : null}
      </div>
      <ErrorBox error={error} />
      <div className="row">
        <button className="btn" disabled={pending}>
          {sent ? "Confirm number" : "Send code"}
        </button>
        {sent ? (
          <button type="button" className="btn ghost" onClick={() => setSent(null)}>
            Cancel
          </button>
        ) : null}
      </div>
    </form>
  );
}
