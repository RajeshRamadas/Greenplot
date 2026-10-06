"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorBox, Field } from "@/components/ui";
import { publicPost } from "@/lib/api";

type CodeResp = { sent: boolean; channels: string[]; dev_code?: string };

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [sent, setSent] = useState<CodeResp | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <div className="brand" style={{ padding: "0 0 18px" }}>
          <b style={{ fontSize: 30 }}>
            <span>Green</span>Plot
          </b>
          <small>Reset your password</small>
        </div>
        {done ? (
          <div className="stack">
            <div className="alert ok">Your password has been changed. Other devices have been signed out.</div>
            <button className="btn primary big" onClick={() => router.push("/login")}>
              Sign in
            </button>
          </div>
        ) : (
          <form
            className="form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!sent) run(async () => setSent(await publicPost<CodeResp>("/auth/password/forgot", { identifier })));
              else run(async () => (await publicPost("/auth/password/reset", { identifier, code: code.trim(), new_password: password }), setDone(true)));
            }}
          >
            <Field label="Email or mobile number" hint="The one on your GreenPlot account">
              <input required value={identifier} disabled={!!sent} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" />
            </Field>
            {sent ? (
              <>
                <div className="alert info small">
                  If an account matches, we sent it a 6-digit code{sent.channels.length ? ` by ${sent.channels.join(" & ")}` : ""}. It expires in 10 minutes.
                  {sent.dev_code ? ` Demo code: ${sent.dev_code}` : ""}
                </div>
                <Field label="Code">
                  <input inputMode="numeric" autoComplete="one-time-code" required maxLength={6} value={code} onChange={(e) => setCode(e.target.value)} />
                </Field>
                <Field label="New password" hint="At least 8 characters, mixing letters and numbers or symbols">
                  <input type="password" autoComplete="new-password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
                </Field>
              </>
            ) : null}
            <ErrorBox error={error} />
            <button className="btn primary big" disabled={busy}>
              {busy ? "Please wait…" : sent ? "Set new password" : "Send code"}
            </button>
            {sent ? (
              <button type="button" className="btn ghost" onClick={() => (setSent(null), setCode(""))}>
                Start again
              </button>
            ) : null}
          </form>
        )}
        <p className="small muted" style={{ marginTop: 16 }}>
          <Link href="/login">Back to sign in</Link>
        </p>
      </div>
    </div>
  );
}
