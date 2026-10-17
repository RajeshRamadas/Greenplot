"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CaptureButton } from "@/components/Capture";
import { ErrorBox, Field, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useAction, useApi, useOnline } from "@/lib/hooks";
import { useLookups } from "@/lib/lookups";
import { enqueue } from "@/lib/offline";
import type { TicketCategory, TicketDetail } from "@/lib/types";

// ------------------------------------------------------------------ WhatsApp chat button

let contact: Promise<string | null> | null = null;

/** The support WhatsApp number from the API's config (GP_WHATSAPP_NUMBER), fetched once per page load. */
function loadNumber(): Promise<string | null> {
  contact ??= fetch("/api/v1/public/contact")
    .then((r) => (r.ok ? r.json() : null))
    .then((d: { whatsapp_number?: string } | null) => d?.whatsapp_number?.replace(/\D/g, "") || null)
    .catch(() => {
      contact = null; // try again on the next page
      return null;
    });
  return contact;
}

export function whatsappLink(number: string, text: string) {
  return `https://wa.me/${number}?text=${encodeURIComponent(text)}`;
}

const WA_PATH =
  "M16.02 3.2C9.03 3.2 3.35 8.84 3.34 15.78c0 2.22.59 4.39 1.71 6.31L3.2 28.8l6.89-1.8a12.8 12.8 0 0 0 5.92 1.45h.01c6.98 0 12.66-5.64 12.67-12.58A12.48 12.48 0 0 0 25 6.96a12.6 12.6 0 0 0-8.98-3.76Zm0 23.1h-.01a10.6 10.6 0 0 1-5.39-1.47l-.39-.23-4.09 1.07 1.09-3.96-.25-.4a10.4 10.4 0 0 1-1.62-5.53c0-5.88 4.79-10.66 10.67-10.66 2.85 0 5.53 1.11 7.55 3.13a10.56 10.56 0 0 1 3.12 7.54c0 5.88-4.79 10.66-10.67 10.66Zm5.86-7.98c-.32-.16-1.9-.94-2.19-1.05-.29-.11-.51-.16-.72.16-.21.32-.83 1.05-1.02 1.27-.19.21-.38.24-.7.08-.32-.16-1.35-.5-2.57-1.59-.95-.84-1.59-1.88-1.78-2.2-.19-.32-.02-.49.14-.65.14-.14.32-.38.48-.57.16-.19.21-.32.32-.54.11-.21.05-.4-.03-.56-.08-.16-.72-1.73-.99-2.37-.26-.62-.52-.54-.72-.55h-.61c-.21 0-.56.08-.85.4-.29.32-1.12 1.09-1.12 2.66s1.15 3.09 1.31 3.3c.16.21 2.26 3.44 5.47 4.82.76.33 1.36.52 1.83.67.77.24 1.47.21 2.02.13.62-.09 1.9-.78 2.17-1.53.27-.75.27-1.39.19-1.53-.08-.13-.29-.21-.61-.37Z";

/** WhatsApp link to support with a greeting that says who is writing; null until the number loads. */
function useSupportLink(): string | null {
  const { me } = useAuth();
  const [number, setNumber] = useState<string | null>(null);
  useEffect(() => {
    loadNumber().then(setNumber);
  }, []);
  if (!number) return null;
  const who = me ? ` This is ${me.full_name}${me.tenant_name ? `, ${me.tenant_name}` : ""}.` : "";
  return whatsappLink(number, `Hi GreenPlot, I need some help.${who}`);
}

export function WhatsAppLink({ children }: { children: React.ReactNode }) {
  const href = useSupportLink();
  return href ? (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ) : (
    <>{children}</>
  );
}

/** Floating "Chat with us on WhatsApp" button, shown on every page of the app. */
export function WhatsAppButton() {
  const href = useSupportLink();
  if (!href) return null;
  return (
    <a
      className="wa-float"
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Chat with GreenPlot on WhatsApp"
      title="Chat with us on WhatsApp"
    >
      <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false">
        <path d={WA_PATH} />
      </svg>
    </a>
  );
}

// ------------------------------------------------------------------ star rating

/** 1-5 star picker; one tap sets the rating. */
export function StarInput({ value, onChange, size = 30 }: { value: number; onChange: (n: number) => void; size?: number }) {
  return (
    <div className="row" role="radiogroup" aria-label="Rating out of 5" style={{ gap: 0 }}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          className="btn ghost"
          aria-label={`${n} star${n > 1 ? "s" : ""}`}
          aria-checked={value === n}
          onClick={() => onChange(n)}
          style={{ fontSize: size, padding: "2px 6px", lineHeight: 1, color: value >= n ? "var(--amber)" : "var(--muted)" }}
        >
          {value >= n ? "★" : "☆"}
        </button>
      ))}
    </div>
  );
}

export function Stars({ rating }: { rating: number }) {
  return (
    <span aria-label={`${rating} out of 5`} style={{ color: "var(--amber)", letterSpacing: 1 }}>
      {"★".repeat(rating)}
      <span style={{ color: "var(--muted)" }}>{"☆".repeat(5 - rating)}</span>
    </span>
  );
}

// ------------------------------------------------------------------ report a problem

/** Category used when the customer doesn't pick one; the office re-categorises during review. */
const FALLBACK_CATEGORY = "other";

function titleFrom(text: string) {
  const first = text.trim().split(/\n|(?<=[.!?])\s/)[0].trim();
  if (first.length < 3) return "Problem reported";
  return first.length > 80 ? `${first.slice(0, 77).trimEnd()}…` : first;
}

/**
 * Short "Report a problem" form: say what's wrong (and where), optionally pick a kind, add a photo.
 * It raises a service ticket, which the office reviews and assigns as a job.
 */
export function ReportProblemForm() {
  const { me } = useAuth();
  const router = useRouter();
  const online = useOnline();
  const lookups = useLookups();
  const act = useAction();
  const cats = useApi<TicketCategory[]>("/tickets/categories");
  const [text, setText] = useState("");
  const [kind, setKind] = useState("");
  const [propertyId, setPropertyId] = useState("");
  const [created, setCreated] = useState<TicketDetail | null>(null);
  const [queued, setQueued] = useState(false);
  const [photos, setPhotos] = useState(0);

  const active = (cats.data ?? []).filter((c) => c.is_active);
  const fallback = active.find((c) => c.code === FALLBACK_CATEGORY)?.code ?? active[active.length - 1]?.code;

  function reset() {
    setText("");
    setKind("");
    setCreated(null);
    setQueued(false);
    setPhotos(0);
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const description = text.trim();
    const body = {
      category: kind || fallback,
      title: titleFrom(description),
      description,
      property_id: propertyId || null,
    };
    if (!online && me) {
      await enqueue(me.id, "ticket", "create", body, `Problem: ${body.title}`);
      setQueued(true);
      return;
    }
    const t = await act.run(() => api<TicketDetail>("/tickets", { body }));
    if (t) setCreated(t);
  }

  if (queued) {
    return (
      <div className="stack">
        <div className="alert warn">You are offline. Your report is saved on this device and will be sent when you reconnect.</div>
        <div className="actions">
          <button className="btn" onClick={reset}>
            Report another problem
          </button>
        </div>
      </div>
    );
  }

  if (created) {
    return (
      <div className="stack">
        <div className="alert ok">
          Thanks, we&apos;ve got it. Your report is logged as <b className="mono">{created.number}</b>. The office will review it and send someone, and
          we&apos;ll keep you posted at every step.
        </div>
        <p className="small muted">A photo helps the team come prepared.</p>
        <CaptureButton entityType="ticket" entityId={created.id} text={photos ? `Add another photo (${photos} added)` : "Add a photo"} onDone={() => setPhotos((n) => n + 1)} />
        <div className="actions">
          <button className="btn" onClick={reset}>
            Report another problem
          </button>
          <button className="btn primary" onClick={() => router.push(`/tickets/${created.id}`)}>
            Track it
          </button>
        </div>
      </div>
    );
  }

  return (
    <form className="form" onSubmit={submit}>
      {lookups.properties.length > 1 ? (
        <Field label="Which plot?">
          <Select
            value={propertyId}
            onChange={setPropertyId}
            placeholder="Common area"
            options={lookups.properties.map((p) => ({ value: p.id, label: `Plot ${p.plot_number}` }))}
          />
        </Field>
      ) : null}
      <Field label="What's wrong?" hint="Say what you noticed and where, e.g. “Garbage dumped near the back fence of my plot.”">
        <textarea required minLength={5} maxLength={5000} rows={5} value={text} onChange={(e) => setText(e.target.value)} />
      </Field>
      <Field label="What kind of problem? (optional)">
        <Select value={kind} onChange={setKind} placeholder="Not sure" options={active.map((c) => ({ value: c.code, label: c.name }))} />
      </Field>
      <ErrorBox error={act.error || cats.error} />
      {!online ? <div className="alert warn">You are offline. The report will be sent when you reconnect.</div> : null}
      <div className="actions">
        <button className="btn primary" disabled={act.pending || !fallback || text.trim().length < 5}>
          Send report
        </button>
      </div>
    </form>
  );
}
