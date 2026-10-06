"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { homeFor } from "@/components/AppShell";
import { ErrorBox, Field } from "@/components/ui";
import { publicPost } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Mode = "password" | "code";
type CodeResp = { sent: boolean; channels: string[]; dev_code?: string };

const channelText = (c: string[]) =>
  c.length ? `We sent a code by ${c.map((x) => ({ whatsapp: "WhatsApp", sms: "SMS", email: "email" })[x] ?? x).join(" & ")}.` : "If this number is registered, a code is on its way.";

function LoginForm() {
  const { me, login, loginWithCode, finishMfa, loading } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode] = useState<Mode>("password");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState<CodeResp | null>(null);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!loading && me) {
      const next = params.get("next");
      router.replace(me.mfa_setup_required ? "/profile?setup=2fa" : next && next.startsWith("/") && !next.startsWith("//") ? next : homeFor(me.role, me.features));
    }
  }, [me, loading, router, params]);

  async function step(fn: () => Promise<{ mfa_token?: string } | void>) {
    setBusy(true);
    setError(null);
    try {
      const r = await fn();
      if (r && r.mfa_token) setMfaToken(r.mfa_token);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const brand = (
    <div className="brand" style={{ padding: "0 0 18px" }}>
      <b style={{ fontSize: 30 }}>
        <span>Green</span>Plot
      </b>
      <small>Property Management Made Simple</small>
    </div>
  );

  if (mfaToken) {
    return (
      <div className="auth-page">
        <div className="card auth-card">
          {brand}
          <h2>2-step verification</h2>
          <p className="small muted">Enter the 6-digit code from your authenticator app, or one of your recovery codes.</p>
          <form className="form" onSubmit={(e) => (e.preventDefault(), step(() => finishMfa(mfaToken, mfaCode.trim())))}>
            <Field label="Verification code">
              <input inputMode="text" autoComplete="one-time-code" autoFocus required value={mfaCode} onChange={(e) => setMfaCode(e.target.value)} />
            </Field>
            <ErrorBox error={error} />
            <button className="btn primary big" disabled={busy}>
              {busy ? "Checking…" : "Verify"}
            </button>
            <button type="button" className="btn ghost" onClick={() => (setMfaToken(null), setMfaCode(""), setError(null))}>
              Back
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="card auth-card">
        {brand}
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={mode === "password"} className={mode === "password" ? "on" : ""} onClick={() => (setMode("password"), setError(null))}>
            Email & password
          </button>
          <button role="tab" aria-selected={mode === "code"} className={mode === "code" ? "on" : ""} onClick={() => (setMode("code"), setError(null))}>
            Mobile number
          </button>
        </div>
        {mode === "password" ? (
          <form className="form" onSubmit={(e) => (e.preventDefault(), step(() => login(email.trim(), password)))}>
            <Field label="Email">
              <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Password">
              <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <ErrorBox error={error} />
            <button className="btn primary big" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
            <Link href="/forgot-password" className="small">
              Forgot password?
            </Link>
          </form>
        ) : (
          <form
            className="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!codeSent) step(async () => setCodeSent(await publicPost<CodeResp>("/auth/otp/request", { phone })));
              else step(() => loginWithCode(phone, code.trim()));
            }}
          >
            <Field label="Mobile number" hint="The number registered with your layout office">
              <input type="tel" autoComplete="tel" required value={phone} disabled={!!codeSent} onChange={(e) => setPhone(e.target.value)} placeholder="98450 12345" />
            </Field>
            {codeSent ? (
              <>
                <div className="alert info small">
                  {channelText(codeSent.channels)}
                  {codeSent.dev_code ? ` Demo code: ${codeSent.dev_code}` : ""}
                </div>
                <Field label="6-digit code">
                  <input inputMode="numeric" autoComplete="one-time-code" autoFocus required maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} />
                </Field>
              </>
            ) : null}
            <ErrorBox error={error} />
            <button className="btn primary big" disabled={busy}>
              {busy ? "Please wait…" : codeSent ? "Sign in" : "Send code"}
            </button>
            {codeSent ? (
              <button type="button" className="btn ghost" onClick={() => (setCodeSent(null), setCode(""))}>
                Use a different number
              </button>
            ) : null}
          </form>
        )}
        <p className="small muted" style={{ marginTop: 16 }}>
          New resident or vendor? <Link href="/register">Request access</Link> or use the invite sent by your layout office. <a href="/">Back to website</a>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
