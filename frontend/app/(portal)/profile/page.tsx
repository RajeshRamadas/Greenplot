"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PhoneVerify, SessionsCard, TwoStepCard } from "@/components/Security";
import { Badge, ErrorBox, Field, PageHead, useToast } from "@/components/ui";
import { api, setTokens } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { roleLabel } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";

export default function ProfilePage() {
  const { me } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const { run, error, pending } = useAction();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [changingPhone, setChangingPhone] = useState(false);
  const [setup2fa, setSetup2fa] = useState(false);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("setup") === "2fa") {
      setSetup2fa(true);
      document.getElementById("two-step")?.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  if (!me) return null;
  return (
    <>
      <PageHead title="Profile" sub={`${me.full_name} · ${roleLabel[me.role]}`} />
      <TwoStepCard highlight={setup2fa || me.mfa_setup_required} />
      <div className="grid two">
        <div className="card">
          <h2>Account</h2>
          <dl className="kv">
            <dt>Name</dt>
            <dd>{me.full_name}</dd>
            <dt>Email</dt>
            <dd>{me.email}</dd>
            <dt>Mobile</dt>
            <dd>
              {me.phone || "—"} {me.phone ? <Badge status={me.phone_verified_at ? "completed" : "pending"} text={me.phone_verified_at ? "Verified" : "Not verified"} /> : null}
              <div>
                <button className="btn small ghost" onClick={() => setChangingPhone(!changingPhone)}>
                  {me.phone ? "Change number" : "Add number"}
                </button>
              </div>
            </dd>
            <dt>Role</dt>
            <dd>{roleLabel[me.role]}</dd>
            <dt>Layout</dt>
            <dd>{me.tenant_name || "Platform"}</dd>
          </dl>
          {changingPhone ? (
            <div style={{ marginTop: 12 }}>
              <PhoneVerify onDone={() => setChangingPhone(false)} />
            </div>
          ) : null}
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
      <WhatsAppCard onAddNumber={() => setChangingPhone(true)} />
      <SessionsCard />
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

/** Consent to WhatsApp updates (ticket progress, closure and notices). */
function WhatsAppCard({ onAddNumber }: { onAddNumber: () => void }) {
  const { me, reload } = useAuth();
  const toast = useToast();
  const { run, error, pending } = useAction();
  const info = useApi<{ business_number: string; live: boolean; opted_in: boolean }>("/whatsapp/info");
  if (!me || !me.tenant_id) return null;
  const on = me.whatsapp_opt_in;
  async function save(optIn: boolean) {
    if (await run(() => api("/whatsapp/consent", { method: "PUT", body: { whatsapp_opt_in: optIn } }))) {
      await reload();
      info.reload();
      toast(optIn ? "WhatsApp updates turned on" : "WhatsApp updates turned off");
    }
  }
  const number = info.data?.business_number;
  return (
    <div className="card" style={{ margin: "16px 0" }}>
      <div className="card-head">
        <h2>WhatsApp updates</h2>
        <span className={`badge ${on ? "green" : "grey"}`}>{on ? "On" : "Off"}</span>
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Get ticket updates — assigned, work started, completed and closed — and layout notices on WhatsApp. Reply to an update to add a message to
        your ticket. Reply STOP at any time to turn updates off.
      </p>
      {me.phone ? (
        <div className="row">
          <span>
            Updates go to <b>{me.phone}</b>
          </span>
          {on ? (
            <button className="btn danger" disabled={pending} onClick={() => save(false)}>
              Turn off
            </button>
          ) : (
            <button className="btn primary" disabled={pending} onClick={() => save(true)}>
              Get updates on WhatsApp
            </button>
          )}
        </div>
      ) : (
        <button className="btn" onClick={onAddNumber}>
          Add your mobile number first
        </button>
      )}
      <ErrorBox error={error} />
      {number ? (
        <p className="small muted" style={{ marginBottom: 0 }}>
          Save our number{" "}
          <a href={`https://wa.me/${number}?text=START`} target="_blank" rel="noreferrer">
            +{number}
          </a>{" "}
          so you recognise our messages.
          {info.data && !info.data.live ? " (WhatsApp sending is not switched on for this layout yet.)" : ""}
        </p>
      ) : null}
    </div>
  );
}
