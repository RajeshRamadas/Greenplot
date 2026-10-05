"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorBox, Field, PageHead, useToast } from "@/components/ui";
import { api, setTokens } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { roleLabel } from "@/lib/format";
import { useAction } from "@/lib/hooks";

export default function ProfilePage() {
  const { me } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const { run, error, pending } = useAction();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");

  if (!me) return null;
  return (
    <>
      <PageHead title="Profile" sub={`${me.full_name} · ${roleLabel[me.role]}`} />
      <div className="grid two">
        <div className="card">
          <h2>Account</h2>
          <dl className="kv">
            <dt>Name</dt>
            <dd>{me.full_name}</dd>
            <dt>Email</dt>
            <dd>{me.email}</dd>
            <dt>Phone</dt>
            <dd>{me.phone || "—"}</dd>
            <dt>Role</dt>
            <dd>{roleLabel[me.role]}</dd>
            <dt>Layout</dt>
            <dd>{me.tenant_name || "Platform"}</dd>
          </dl>
        </div>
        <div className="card">
          <h2>Change password</h2>
          <form
            className="form"
            onSubmit={async (e) => {
              e.preventDefault();
              const ok = await run(() => api("/auth/change-password", { body: { current_password: current, new_password: next } }));
              if (ok) {
                setTokens(null, null);
                router.replace("/login");
              }
            }}
          >
            <Field label="Current password">
              <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
            </Field>
            <Field label="New password" hint="At least 8 characters, mixing letters and numbers or symbols">
              <input type="password" autoComplete="new-password" minLength={8} value={next} onChange={(e) => setNext(e.target.value)} required />
            </Field>
            <ErrorBox error={error} />
            <button className="btn primary" disabled={pending}>
              Update password
            </button>
          </form>
        </div>
      </div>
      <div className="card">
        <h2>Lost device?</h2>
        <p className="muted" style={{ marginBottom: 12 }}>Sign out everywhere. Every session, including on a lost phone, will need to log in again.</p>
        <button
          className="btn danger"
          onClick={async () => {
            if (!confirm("Sign out of all devices?")) return;
            await run(() => api("/auth/logout-all", { method: "POST" }));
            toast("All sessions revoked");
            setTokens(null, null);
            router.replace("/login");
          }}
        >
          Sign out of all devices
        </button>
      </div>
    </>
  );
}
