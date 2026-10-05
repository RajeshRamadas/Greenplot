"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ErrorBox, Field } from "@/components/ui";
import { acceptInvite } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function AcceptForm() {
  const params = useSearchParams();
  const router = useRouter();
  const { reload } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const token = params.get("token") || "";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) return setError("Passwords do not match");
    try {
      await acceptInvite(token, password);
      await reload();
      router.replace("/login");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="auth-page">
      <div className="card auth-card">
        <h1 style={{ marginBottom: 6 }}>Welcome to GreenPlot</h1>
        <p className="muted" style={{ marginBottom: 18 }}>Set a password to activate your account.</p>
        {!token ? <div className="alert error">This invite link is incomplete.</div> : null}
        <form className="form" onSubmit={submit}>
          <Field label="New password" hint="At least 8 characters, mixing letters and numbers or symbols">
            <input type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Field label="Confirm password">
            <input type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          <ErrorBox error={error} />
          <button className="btn primary big" disabled={!token}>
            Activate account
          </button>
        </form>
      </div>
    </div>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense>
      <AcceptForm />
    </Suspense>
  );
}
