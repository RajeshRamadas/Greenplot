import type { Metadata } from "next";
import Link from "next/link";
import { ServiceShell } from "@/components/ServicePage";
import { SERVICES } from "@/lib/services";

export const metadata: Metadata = { title: "Services", description: "Plot cleaning, gardening, inspections, gates, repairs and staff, with proof of every job." };

export default function ServicesIndex() {
  return (
    <ServiceShell>
      <main>
        <section className="svc-wrap svc-hero">
          <p className="svc-eyebrow">Services</p>
          <h1>Everything your property needs, with proof</h1>
          <p className="svc-lead">Every job is photographed, checked and signed off, so you never have to wonder whether the work was done.</p>
        </section>
        <section className="svc-wrap svc-grid wide">
          {SERVICES.map((s) => (
            <Link key={s.slug} href={`/services/${s.slug}`} className="card svc-item svc-link">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={s.thumb} alt="" loading="lazy" />
              <h3>{s.name}</h3>
              <p>{s.promise}</p>
              <span className="svc-more">See how it works →</span>
            </Link>
          ))}
        </section>
      </main>
    </ServiceShell>
  );
}
