import Link from "next/link";
import { BUSINESS, LEGAL_PAGES } from "@/lib/legal";

/** Shared layout for the public legal pages, with links between them. */
export function LegalPage({ title, intro, children }: { title: string; intro?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="legal-page">
      <header className="legal-head">
        <Link href="/" className="legal-brand" aria-label="GreenPlot home">
          <span>Green</span>Plot
        </Link>
        <Link href="/login" className="btn small ghost">
          Login
        </Link>
      </header>
      <main className="legal-body card">
        <h1>{title}</h1>
        <p className="small muted">Last updated: {BUSINESS.updated}</p>
        {intro ? <div className="legal-intro">{intro}</div> : null}
        {children}
      </main>
      <LegalLinks />
    </div>
  );
}

export function LegalLinks() {
  return (
    <nav className="legal-links small" aria-label="Policies">
      {LEGAL_PAGES.map((p) => (
        <Link key={p.href} href={p.href}>
          {p.label}
        </Link>
      ))}
    </nav>
  );
}

/** A labelled block of business details, for contact and grievance sections. */
export function ContactBlock({ grievance = false }: { grievance?: boolean }) {
  return (
    <dl className="legal-contact">
      {grievance ? (
        <>
          <dt>Grievance Officer</dt>
          <dd>{BUSINESS.grievanceOfficer}</dd>
          <dt>Email</dt>
          <dd>
            <a href={`mailto:${BUSINESS.grievanceEmail}`}>{BUSINESS.grievanceEmail}</a>
          </dd>
        </>
      ) : (
        <>
          <dt>Business</dt>
          <dd>{BUSINESS.legalName} (trading as {BUSINESS.brand})</dd>
          <dt>Email</dt>
          <dd>
            <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a>
          </dd>
        </>
      )}
      <dt>Phone</dt>
      <dd>{BUSINESS.phone}</dd>
      <dt>Address</dt>
      <dd>{BUSINESS.address}</dd>
      <dt>Hours</dt>
      <dd>{BUSINESS.hours}</dd>
    </dl>
  );
}
