import type { Metadata } from "next";
import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";
import { ServiceShell } from "@/components/ServicePage";
import { SERVICES } from "@/lib/services";
import { absolute, breadcrumbSchema, businessSchema, pageOpenGraph } from "@/lib/site";

const title = "Plot Maintenance Services and Prices in Bangalore";
const description = "Plot cleaning, gardening, inspections, fencing, repairs and layout staff in Bangalore, with per-sq-ft prices, AMC plans and photo proof of every job.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/services" },
  openGraph: pageOpenGraph({ title, description, url: "/services" }),
};

export default function ServicesIndex() {
  return (
    <ServiceShell>
      <JsonLd
        items={[
          businessSchema(),
          breadcrumbSchema([
            { name: "Home", path: "/" },
            { name: "Services", path: "/services" },
          ]),
          {
            "@type": "ItemList",
            name: "Plot maintenance services in Bangalore",
            itemListElement: SERVICES.map((s, i) => ({ "@type": "ListItem", position: i + 1, url: absolute(`/services/${s.slug}`), name: s.name })),
          },
        ]}
      />
      <main>
        <section className="svc-wrap svc-hero">
          <p className="svc-eyebrow">Services</p>
          <h1>Plot maintenance services in Bangalore, with proof</h1>
          <p className="svc-lead">Every job is photographed, checked and signed off, so you never have to wonder whether the work was done.</p>
        </section>
        <section className="svc-wrap svc-grid wide">
          {SERVICES.map((s) => (
            <Link key={s.slug} href={`/services/${s.slug}`} className="card svc-item svc-link">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={s.thumb} alt={`${s.name} in Bangalore`} loading="lazy" />
              <h3>{s.name}</h3>
              <p>{s.promise}</p>
              {s.price ? <p className="svc-from">From ₹{s.price.perSqft} per sq ft, {s.price.per}{s.amc ? " · AMC plans" : ""}</p> : null}
              <span className="svc-more">See how it works →</span>
            </Link>
          ))}
        </section>
      </main>
    </ServiceShell>
  );
}
