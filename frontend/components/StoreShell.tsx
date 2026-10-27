import Link from "next/link";
import { LegalLinks } from "@/components/Legal";
import { CartButton, QuickAdd } from "@/components/Store";
import { BUSINESS } from "@/lib/legal";
import { CATEGORIES, type Plant, rupees } from "@/lib/store";

/** Header and footer of the plant store pages. */
export function StoreShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="svc-page">
      <header className="svc-head">
        {/* A plain link: "/" is the static marketing page, which Next would otherwise prefetch in full. */}
        <a href="/" className="legal-brand" aria-label="GreenPlot home">
          <span>Green</span>Plot
        </a>
        <nav className="row">
          <Link href="/store" className="btn small ghost">
            Plant store
          </Link>
          <Link href="/services" className="btn small ghost hide-sm">
            Plot services
          </Link>
          <CartButton />
        </nav>
      </header>
      {children}
      <nav className="svc-wrap svc-others" aria-label="Plant categories">
        {Object.entries(CATEGORIES).map(([slug, name]) => (
          <Link key={slug} href={`/store#${slug}`}>
            {name}
          </Link>
        ))}
      </nav>
      <address className="svc-wrap svc-nap">
        <b>
          {BUSINESS.brand} · {BUSINESS.legalName}
        </b>
        <span>{BUSINESS.address}</span>
        <span>
          <a href={`tel:${BUSINESS.phone.replace(/\s/g, "")}`}>{BUSINESS.phone}</a> · <a href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a> · {BUSINESS.hours}
        </span>
      </address>
      <LegalLinks />
    </div>
  );
}

/** A plant on the store listing. */
export function PlantCard({ p }: { p: Plant }) {
  return (
    <div className="card store-card svc-link">
      <Link href={`/store/${p.slug}`} className="store-card-link">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={p.image} alt={p.name} loading="lazy" />
        <h3>{p.name}</h3>
        <p>{p.summary}</p>
      </Link>
      <div className="store-card-foot">
        <span className="store-price">
          {rupees(p.price)}
          {p.mrp && p.mrp > p.price ? <s>{rupees(p.mrp)}</s> : null}
        </span>
        <QuickAdd plant={p} />
      </div>
    </div>
  );
}
