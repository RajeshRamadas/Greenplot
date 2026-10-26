import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { JsonLd } from "@/components/JsonLd";
import { FaqList, ServiceShell } from "@/components/ServicePage";
import { getPosts } from "@/lib/blog";
import { type City, cityBySlug, liveCities } from "@/lib/cities";
import type { Faq } from "@/lib/faqs";
import { SERVICES, TERRAIN_NOTE } from "@/lib/services";
import { absolute, breadcrumbSchema, businessSchema, faqSchema, pageOpenGraph, rupees } from "@/lib/site";

export const dynamicParams = false;

export function generateStaticParams() {
  return liveCities().map((c) => ({ city: c.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ city: string }> }): Promise<Metadata> {
  const c = cityBySlug((await params).city);
  if (!c) return {};
  const title = `Plot Maintenance Services in ${c.name}`;
  const description = `Plot cleaning, fencing, garden upkeep and inspections across ${c.name}: ${c.areas.slice(0, 5).map((a) => a.name).join(", ")} and more. Photo proof of every visit.`;
  return { title, description, alternates: { canonical: `/${c.slug}` }, openGraph: pageOpenGraph({ title, description, url: `/${c.slug}` }) };
}

function cityFaqs(c: City): Faq[] {
  return [
    {
      q: `What does plot maintenance in ${c.name} include?`,
      a: `Plot cleaning, garden and landscape upkeep, inspections, fencing and gate repairs, general repairs and layout staff. Every job is proven with photos and a checklist. ${TERRAIN_NOTE}`,
    },
    { q: `Which areas of ${c.name} do you cover?`, a: `${c.areas.map((a) => a.name).join(", ")}. If your plot is elsewhere in ${c.name}, message us on WhatsApp.` },
    { q: "Can I book if I live abroad?", a: "Yes. Most of our owners live in another city or country. You book and pay online, and every visit is reported with photos on WhatsApp or email." },
  ];
}

export default async function CityPage({ params }: { params: Promise<{ city: string }> }) {
  const c = cityBySlug((await params).city);
  if (!c) notFound();
  const faqs = cityFaqs(c);
  const posts = (await getPosts({ limit: 6 }))?.items ?? [];
  return (
    <ServiceShell>
      <JsonLd
        items={[
          { ...businessSchema(), areaServed: [{ "@type": "City", name: c.name }, ...c.areas.map((a) => ({ "@type": "Place", name: `${a.name}, ${c.name}` }))] },
          faqSchema(faqs),
          breadcrumbSchema([
            { name: "Home", path: "/" },
            { name: c.name, path: `/${c.slug}` },
          ]),
          {
            "@type": "ItemList",
            name: `Areas we cover in ${c.name}`,
            itemListElement: c.areas.map((a, i) => ({ "@type": "ListItem", position: i + 1, url: absolute(`/${c.slug}/${a.slug}`), name: a.name })),
          },
        ]}
      />
      <main>
        <section className="svc-wrap svc-hero">
          <p className="svc-eyebrow">{c.name}, {c.state}</p>
          <h1>Plot maintenance services in {c.name}</h1>
          <p className="svc-lead">Your plot cleaned, fenced and checked on schedule, with photos of every visit.</p>
          <p>{c.intro}</p>
        </section>

        <section className="svc-wrap">
          <h2>Areas we cover in {c.name}</h2>
          <ul className="svc-area-list">
            {c.areas.map((a) => (
              <li key={a.slug}>
                <Link href={`/${c.slug}/${a.slug}`}>{a.name}</Link>
              </li>
            ))}
          </ul>
        </section>

        <section className="svc-wrap">
          <h2>Services and starting prices</h2>
          <div className="svc-grid wide">
            {SERVICES.map((s) => (
              <Link key={s.slug} href={`/services/${s.slug}`} className="card svc-item svc-link">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={s.thumb} alt={`${s.name} in ${c.name}`} loading="lazy" />
                <h3>
                  {s.name} in {c.name}
                </h3>
                <p>{s.promise}</p>
                {s.price ? (
                  <p className="svc-from">
                    From {rupees(s.price.perSqft)} per sq ft, {s.price.per}
                  </p>
                ) : null}
                <span className="svc-more">See details →</span>
              </Link>
            ))}
          </div>
        </section>

        {posts.length ? (
          <section className="svc-wrap">
            <h2>Guides for {c.name} plot owners</h2>
            <ul className="svc-ticks">
              {posts.map((p) => (
                <li key={p.slug}>
                  <Link href={`/blog/${p.slug}`}>{p.title}</Link>
                </li>
              ))}
            </ul>
            <p>
              <Link href="/blog">All guides →</Link>
            </p>
          </section>
        ) : null}

        <FaqList faqs={faqs} />
      </main>
    </ServiceShell>
  );
}
