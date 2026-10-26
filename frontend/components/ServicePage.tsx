import Link from "next/link";
import { LegalLinks } from "@/components/Legal";
import { liveCities } from "@/lib/cities";
import type { Faq } from "@/lib/faqs";
import { BUSINESS } from "@/lib/legal";
import { SERVICES } from "@/lib/services";

const WHATSAPP = `https://wa.me/${BUSINESS.phone.replace(/\D/g, "")}`;

/** Header, footer and calls to action shared by the public service pages. */
export function ServiceShell({ current, children }: { current?: string; children: React.ReactNode }) {
  return (
    <div className="svc-page">
      <header className="svc-head">
        <Link href="/" className="legal-brand" aria-label="GreenPlot home">
          <span>Green</span>Plot
        </Link>
        <nav className="row">
          <Link href="/services" className="btn small ghost hide-sm">
            Services
          </Link>
          {liveCities().map((c) => (
            <Link key={c.slug} href={`/${c.slug}`} className="btn small ghost hide-sm">
              {c.name}
            </Link>
          ))}
          <Link href="/login" className="btn small ghost">
            Login
          </Link>
          <Link href="/#demo" className="btn small primary">
            Request a demo
          </Link>
        </nav>
      </header>
      {children}
      <section className="svc-wrap svc-cta">
        <div>
          <h2>See it working on your layout</h2>
          <p>We set up a demo with your plots and show you the app your staff and owners will use.</p>
        </div>
        <div className="row">
          <Link href="/#demo" className="btn primary big">
            Request a demo
          </Link>
          <a href={WHATSAPP} className="btn big" target="_blank" rel="noopener noreferrer">
            WhatsApp us
          </a>
        </div>
      </section>
      <nav className="svc-wrap svc-others" aria-label="All services">
        {SERVICES.map((s) =>
          s.slug === current ? (
            <span key={s.slug} aria-current="page">
              {s.name}
            </span>
          ) : (
            <Link key={s.slug} href={`/services/${s.slug}`}>
              {s.name}
            </Link>
          ),
        )}
      </nav>
      <address className="svc-wrap svc-nap">
        <b>
          {BUSINESS.brand} · {BUSINESS.legalName}
        </b>
        <span>{BUSINESS.address}</span>
        <span>
          <a href={`tel:${BUSINESS.phone.replace(/\s/g, "")}`}>{BUSINESS.phone}</a> · <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a> · {BUSINESS.hours}
        </span>
        <span>
          <Link href="/blog">Guides for plot owners</Link>
        </span>
      </address>
      <LegalLinks />
    </div>
  );
}

/** Questions and answers; the same list goes into the page's FAQ structured data. */
export function FaqList({ faqs }: { faqs: Faq[] }) {
  return (
    <section className="svc-wrap">
      <h2>Questions owners ask</h2>
      <div className="svc-faq">
        {faqs.map((f) => (
          <details key={f.q} className="card">
            <summary>{f.q}</summary>
            <p>{f.a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

export const STEPS = [
  { title: "Requested", text: "A schedule, the office or an owner creates the job." },
  { title: "Assigned", text: "It goes to a staff member or vendor with a due date." },
  { title: "Proven on site", text: "Photos and the checklist are captured, with location where you require it." },
  { title: "Approved", text: "A supervisor checks the proof, or sends it back for rework." },
  { title: "Closed", text: "The owner sees the result and pays online if there is a charge." },
];
