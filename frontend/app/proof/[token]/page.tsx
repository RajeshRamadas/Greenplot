"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorBox, Loading } from "@/components/ui";
import { fmtDate, fmtDateTime, label } from "@/lib/format";

type Photo = { url: string; thumbnail_url: string | null; taken_at: string | null };
type Proof = {
  number: string;
  title: string;
  category: string;
  plot: string | null;
  layout: string | null;
  completed_at: string | null;
  closed_at: string | null;
  before: Photo[];
  after: Photo[];
};

function Photos({ title, photos }: { title: string; photos: Photo[] }) {
  if (!photos.length) return null;
  return (
    <div className="stack">
      <h2>{title}</h2>
      {photos.map((p) => (
        <figure key={p.url} style={{ margin: 0 }}>
          <a href={p.url} target="_blank" rel="noreferrer">
            {/* eslint-disable-next-line @next/next/no-img-element -- short-lived signed URLs, not optimisable */}
            <img src={p.url} alt={title} style={{ width: "100%", borderRadius: 12, display: "block" }} />
          </a>
          {p.taken_at ? <figcaption className="small muted">Taken {fmtDateTime(p.taken_at)}</figcaption> : null}
        </figure>
      ))}
    </div>
  );
}

/** Public before/after photos of a finished job, opened from the owner's WhatsApp or email link. */
export default function ProofPage() {
  const { token } = useParams<{ token: string }>();
  const [proof, setProof] = useState<Proof | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/v1/public/job-proof/${encodeURIComponent(token)}`)
      .then(async (r) => {
        const data = await r.json().catch(() => null);
        if (!r.ok) throw new Error(data?.detail || "This link could not be opened.");
        setProof(data as Proof);
      })
      .catch((e: Error) => setError(e.message));
  }, [token]);

  return (
    <div className="auth-page" style={{ alignItems: "start" }}>
      <div className="card" style={{ width: "min(720px, 100%)" }}>
        <div className="brand" style={{ padding: "0 0 14px" }}>
          <b>
            <span>Green</span>Plot
          </b>
          <small>Photo proof of work</small>
        </div>
        {error ? <ErrorBox error={error} /> : null}
        {!proof && !error ? <Loading /> : null}
        {proof ? (
          <div className="stack" style={{ gap: 18 }}>
            <div>
              <h1 style={{ fontSize: 22 }}>{proof.title}</h1>
              <p className="small muted">
                {proof.plot ? `Plot ${proof.plot}` : null}
                {proof.layout ? ` · ${proof.layout}` : null} · {label(proof.category)} · {proof.number}
                {proof.closed_at ? ` · finished ${fmtDate(proof.closed_at)}` : null}
              </p>
            </div>
            <div className={proof.before.length ? "grid two" : "stack"}>
              <Photos title="Before" photos={proof.before} />
              <Photos title="After" photos={proof.after} />
            </div>
            <p className="small muted">Photos are taken on site by our team and stored with their time and location. Reply on WhatsApp if anything looks wrong.</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
