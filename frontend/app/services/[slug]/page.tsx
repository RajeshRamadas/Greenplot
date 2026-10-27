import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";
import { PriceCard } from "@/components/PriceCard";
import { FaqList, STEPS, ServiceShell } from "@/components/ServicePage";
import { CITIES, liveCities } from "@/lib/cities";
import { serviceFaqs } from "@/lib/faqs";
import { BEFORE_AFTER_SIZE, type Service, SERVICES, serviceBySlug, wideImage } from "@/lib/services";
import { absolute, breadcrumbSchema, businessSchema, faqSchema, pageOpenGraph, pageTitle, rupees } from "@/lib/site";

// Service pages are written for the first live city; area pages carry the other places.
const CITY = liveCities()[0] ?? CITIES[0];

const fromPrice = (s: Service) => (s.price ? `from ${rupees(s.price.perSqft)}/sq ft ${s.price.per}` : "");

export const dynamicParams = false;

export function generateStaticParams() {
  return SERVICES.map((s) => ({ slug: s.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const s = serviceBySlug((await params).slug);
  if (!s) return {};
  const title = `${s.name} in ${CITY.name}${s.price ? `, ${fromPrice(s)}` : ""}`;
  const description = `${s.promise} ${s.name} for plots and layouts across ${CITY.name}${s.price ? `, ${fromPrice(s)}` : ""}. Photo proof of every job.`;
  return { title: pageTitle(title), description, alternates: { canonical: `/services/${s.slug}` }, openGraph: pageOpenGraph({ title, description, url: `/services/${s.slug}` }) };
}

export default async function ServiceDetail({ params }: { params: Promise<{ slug: string }> }) {
  const s = serviceBySlug((await params).slug);
  if (!s) notFound();
  const faqs = serviceFaqs(s, CITY);
  const service = {
    "@type": "Service",
    name: `${s.name} in ${CITY.name}`,
    serviceType: s.name,
    description: s.intro,
    url: absolute(`/services/${s.slug}`),
    provider: { "@id": absolute("/#business") },
    areaServed: [{ "@type": "City", name: CITY.name }, ...CITY.areas.map((a) => ({ "@type": "Place", name: `${a.name}, ${CITY.name}` }))],
    ...(s.price
      ? {
          offers: {
            "@type": "Offer",
            priceCurrency: "INR",
            priceSpecification: { "@type": "UnitPriceSpecification", price: s.price.perSqft, priceCurrency: "INR", unitText: `sq ft, ${s.price.per}` },
          },
        }
      : {}),
  };
  return (
    <ServiceShell current={s.slug}>
      <JsonLd
        items={[
          businessSchema(),
          service,
          faqSchema(faqs),
          breadcrumbSchema([
            { name: "Home", path: "/" },
            { name: "Services", path: "/services" },
            { name: s.name, path: `/services/${s.slug}` },
          ]),
        ]}
      />
      <main>
        <section className="svc-wrap svc-hero">
          <p className="svc-eyebrow">Service in {CITY.name}</p>
          <h1>
            {s.name} in {CITY.name}
          </h1>
          <p className="svc-lead">{s.promise}</p>
          <p>{s.intro}</p>
          <ul className="svc-chips" aria-label="Good for">
            {s.goodFor.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </section>

        {s.beforeAfter ? (
          <figure className="svc-wrap svc-ba">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img {...wideImage(s.beforeAfter)} {...BEFORE_AFTER_SIZE} fetchPriority="high" alt={`Sample before and after photos of ${s.name.toLowerCase()} on a ${CITY.name} plot`} />
            <figcaption>Sample before and after photos. These are illustrations; your reports show real photos from the site.</figcaption>
          </figure>
        ) : s.cover ? (
          <figure className="svc-wrap svc-ba">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img {...wideImage(s.cover.src)} width={s.cover.width} height={s.cover.height} fetchPriority="high" alt={s.cover.alt} />
            <figcaption>Sample photo. This is an illustration; your reports show real photos from the site.</figcaption>
          </figure>
        ) : null}

        <section className="svc-wrap">
          <h2>What&apos;s included</h2>
          <div className="svc-grid">
            {s.included.map((i) => (
              <div key={i.title} className="card svc-item">
                <h3>{i.title}</h3>
                <p>{i.text}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="svc-wrap">
          <h2>Proof of every job</h2>
          <div className="svc-proof">
            <figure className="svc-shot">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={s.shot.src} width={s.shot.width} height={s.shot.height} alt={s.shot.alt} loading="lazy" decoding="async" />
              <figcaption>{s.shot.caption} Sample data, not a real customer.</figcaption>
            </figure>
            <div>
              <p>When a job is done, you get:</p>
              <ul className="svc-ticks">
                {s.proof.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {s.price ? (
          <section className="svc-wrap">
            <h2>Price and AMC plans</h2>
            <PriceCard price={s.price} amc={s.amc} />
          </section>
        ) : null}

        <section className="svc-wrap">
          <h2>
            {s.name} across {CITY.name}
          </h2>
          <p className="muted">We look after plots in these areas. Pick yours to see local details.</p>
          <ul className="svc-area-list">
            {CITY.areas.map((a) => (
              <li key={a.slug}>
                <Link href={`/${CITY.slug}/${a.slug}`}>{a.name}</Link>
              </li>
            ))}
          </ul>
        </section>

        <section className="svc-wrap">
          <h2>How every job runs</h2>
          <ol className="svc-steps">
            {STEPS.map((st) => (
              <li key={st.title}>
                <b>{st.title}</b>
                <span>{st.text}</span>
              </li>
            ))}
          </ol>
        </section>

        <FaqList faqs={faqs} />
      </main>
    </ServiceShell>
  );
}
