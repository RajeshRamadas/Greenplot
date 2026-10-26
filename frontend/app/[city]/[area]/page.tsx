import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { JsonLd } from "@/components/JsonLd";
import { FaqList, ServiceShell } from "@/components/ServicePage";
import { areaBySlug, cityBySlug, liveCities } from "@/lib/cities";
import { areaFaqs } from "@/lib/faqs";
import { SERVICES, serviceBySlug } from "@/lib/services";
import { absolute, breadcrumbSchema, businessSchema, faqSchema, pageOpenGraph, rupees } from "@/lib/site";

export const dynamicParams = false;

export function generateStaticParams() {
  return liveCities().flatMap((c) => c.areas.map((a) => ({ city: c.slug, area: a.slug })));
}

async function load(params: Promise<{ city: string; area: string }>) {
  const p = await params;
  const city = cityBySlug(p.city);
  const area = city && areaBySlug(city, p.area);
  return city && area ? { city, area } : null;
}

export async function generateMetadata({ params }: { params: Promise<{ city: string; area: string }> }): Promise<Metadata> {
  const found = await load(params);
  if (!found) return {};
  const { city, area } = found;
  const cleaning = serviceBySlug("plot-cleaning");
  const title = `Plot Cleaning and Maintenance in ${area.name}, ${city.name}`;
  const description = `Plot cleaning${cleaning?.price ? ` from ${rupees(cleaning.price.perSqft)}/sq ft ${cleaning.price.per}` : ""}, fencing, garden upkeep and inspections in ${area.name}, ${city.name}: ${area.localities.join(", ")}. Photo proof of every visit.`;
  const path = `/${city.slug}/${area.slug}`;
  return { title, description, alternates: { canonical: path }, openGraph: pageOpenGraph({ title, description, url: path }) };
}

export default async function AreaPage({ params }: { params: Promise<{ city: string; area: string }> }) {
  const found = await load(params);
  if (!found) notFound();
  const { city, area } = found;
  const faqs = areaFaqs(area, city);
  const cleaning = serviceBySlug("plot-cleaning");
  const path = `/${city.slug}/${area.slug}`;
  return (
    <ServiceShell>
      <JsonLd
        items={[
          businessSchema(),
          {
            "@type": "Service",
            name: `Plot maintenance in ${area.name}, ${city.name}`,
            serviceType: "Plot maintenance",
            url: absolute(path),
            provider: { "@id": absolute("/#business") },
            areaServed: { "@type": "Place", name: `${area.name}, ${city.name}`, containedInPlace: { "@type": "City", name: city.name } },
          },
          faqSchema(faqs),
          breadcrumbSchema([
            { name: "Home", path: "/" },
            { name: city.name, path: `/${city.slug}` },
            { name: area.name, path },
          ]),
        ]}
      />
      <main>
        <section className="svc-wrap svc-hero">
          <nav className="svc-crumbs" aria-label="Breadcrumb">
            <Link href="/">Home</Link> › <Link href={`/${city.slug}`}>{city.name}</Link> › <span aria-current="page">{area.name}</span>
          </nav>
          <h1>Plot maintenance in {area.name}</h1>
          <p className="svc-lead">Plot cleaning, fencing and inspections in {area.name}, {city.name}, with photos of every visit.</p>
          <p>{area.intro}</p>
          <ul className="svc-chips" aria-label="Localities we cover">
            {area.localities.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </section>

        {cleaning?.beforeAfter ? (
          <figure className="svc-wrap svc-ba">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={cleaning.beforeAfter} alt={`Sample before and after photos of a cleaned plot, like those we send owners in ${area.name}`} />
            <figcaption>Sample before and after photos. These are illustrations; your reports show real photos from your plot.</figcaption>
          </figure>
        ) : null}

        <section className="svc-wrap">
          <h2>What {area.name} plot owners ask us for</h2>
          <ul className="svc-ticks">
            {area.needs.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>

        <section className="svc-wrap">
          <h2>Services in {area.name}</h2>
          <div className="svc-grid wide">
            {SERVICES.map((s) => (
              <Link key={s.slug} href={`/services/${s.slug}`} className="card svc-item svc-link">
                <h3>
                  {s.name} in {area.name}
                </h3>
                <p>{s.promise}</p>
                {s.price ? (
                  <p className="svc-from">
                    From {rupees(s.price.perSqft)} per sq ft, {s.price.per}
                  </p>
                ) : null}
                <span className="svc-more">Prices and details →</span>
              </Link>
            ))}
          </div>
        </section>

        <FaqList faqs={faqs} />

        <section className="svc-wrap">
          <h2>Other areas in {city.name}</h2>
          <ul className="svc-area-list">
            {city.areas
              .filter((a) => a.slug !== area.slug)
              .map((a) => (
                <li key={a.slug}>
                  <Link href={`/${city.slug}/${a.slug}`}>{a.name}</Link>
                </li>
              ))}
          </ul>
        </section>
      </main>
    </ServiceShell>
  );
}
