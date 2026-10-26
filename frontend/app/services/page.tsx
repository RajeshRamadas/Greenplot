import type { Metadata } from "next";
import Link from "next/link";
import { ServiceShell } from "@/components/ServicePage";
import { SERVICES } from "@/lib/services";

export const metadata: Metadata = {
  title: "Plot Maintenance Services and Prices in Bangalore",
  description: "Plot cleaning, gardening, inspections, fencing, repairs and layout staff in Bangalore, with per-sq-ft prices, AMC plans and photo proof of every job.",
  alternates: { canonical: "/services" },
};

export default function ServicesIndex() {
  return (
    <ServiceShell>
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
              <img src={s.thumb} alt="" loading="lazy" />
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
