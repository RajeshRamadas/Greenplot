import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { JsonLd } from "@/components/JsonLd";
import { AddToCart } from "@/components/Store";
import { PlantCard, StoreShell } from "@/components/StoreShell";
import { CATEGORIES, getPlant, getPlants, getStoreConfig, rupees } from "@/lib/store";
import { absolute, breadcrumbSchema, businessSchema, pageOpenGraph, pageTitle } from "@/lib/site";

export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const p = await getPlant((await params).slug);
  if (!p) return { title: "Plant not found", robots: { index: false } };
  const named = /plant$/i.test(p.name) ? p.name : `${p.name} Plant`;
  const title = `${named}, ${rupees(p.price)} · Delivered in Bangalore`;
  const description = `${p.summary} Buy ${p.name.toLowerCase()} online for ${rupees(p.price)} with delivery across Bangalore, cash on delivery or online payment.`;
  return {
    title: pageTitle(title),
    description,
    alternates: { canonical: `/store/${p.slug}` },
    // WhatsApp and Facebook do not show SVG previews, so the placeholder drawings fall back to the site's share image.
    openGraph: { ...pageOpenGraph({ title, description, url: `/store/${p.slug}` }), ...(p.image.endsWith(".svg") ? {} : { images: [{ url: p.image, alt: p.name }] }) },
  };
}

const CARE: { key: "light" | "water" | "size" | "pot" | "care_level"; label: string }[] = [
  { key: "light", label: "Light" },
  { key: "water", label: "Water" },
  { key: "size", label: "Size" },
  { key: "pot", label: "Comes in" },
  { key: "care_level", label: "Care" },
];

export default async function PlantPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const [p, all, cfg] = await Promise.all([getPlant(slug), getPlants(), getStoreConfig()]);
  if (!p) notFound();
  const category = CATEGORIES[p.category] ?? "Plants";
  const related = (all ?? []).filter((x) => x.slug !== p.slug && x.category === p.category).slice(0, 4);
  const more = related.length < 4 ? (all ?? []).filter((x) => x.slug !== p.slug && x.category !== p.category).slice(0, 4 - related.length) : [];
  const inStock = p.stock === null || p.stock > 0;
  return (
    <StoreShell>
      <JsonLd
        items={[
          businessSchema(),
          {
            "@type": "Product",
            name: p.name,
            description: p.description,
            image: absolute(p.image),
            sku: p.slug,
            category,
            brand: { "@type": "Brand", name: "GreenPlot" },
            offers: {
              "@type": "Offer",
              url: absolute(`/store/${p.slug}`),
              price: p.price,
              priceCurrency: "INR",
              availability: inStock ? "https://schema.org/InStock" : "https://schema.org/OutOfStock",
              itemCondition: "https://schema.org/NewCondition",
              seller: { "@id": absolute("/#business") },
              areaServed: { "@type": "City", name: "Bangalore" },
            },
          },
          breadcrumbSchema([
            { name: "Home", path: "/" },
            { name: "Plant store", path: "/store" },
            { name: p.name, path: `/store/${p.slug}` },
          ]),
        ]}
      />
      <main>
        <nav className="svc-wrap svc-crumbs" aria-label="Breadcrumb">
          <Link href="/store">Plant store</Link>
          <span aria-hidden="true">›</span>
          <Link href={`/store#${p.category}`}>{category}</Link>
          <span aria-hidden="true">›</span>
          <span aria-current="page">{p.name}</span>
        </nav>
        <section className="svc-wrap store-detail">
          <figure className="store-photo">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={p.image} alt={`${p.name}${p.botanical_name ? ` (${p.botanical_name})` : ""}`} />
          </figure>
          <div className="store-info">
            <p className="svc-eyebrow">{category}</p>
            <h1>{p.name}</h1>
            {p.botanical_name ? <p className="store-botanical">{p.botanical_name}</p> : null}
            <p className="store-price big">
              {rupees(p.price)}
              {p.mrp && p.mrp > p.price ? (
                <>
                  <s>{rupees(p.mrp)}</s>
                  <span className="badge green">Save {rupees(p.mrp - p.price)}</span>
                </>
              ) : null}
            </p>
            <p className="small muted">Inclusive of all taxes. {cfg ? `Free delivery in Bangalore on orders over ${rupees(cfg.free_delivery_over)}.` : ""}</p>
            <p className="svc-lead">{p.summary}</p>
            {p.stock !== null && p.stock > 0 && p.stock <= 5 ? <p className="alert info">Only {p.stock} left</p> : null}
            <AddToCart plant={p} />
            <ul className="svc-ticks store-promise">
              <li>Delivered across Bangalore</li>
              <li>{cfg?.cod ? "Cash on delivery or pay online" : "Pay online by UPI, card or net banking"}</li>
              <li>Bill with every order</li>
            </ul>
          </div>
        </section>
        <section className="svc-wrap store-about">
          <div>
            <h2>About this plant</h2>
            <p>{p.description}</p>
          </div>
          <div className="card">
            <h2>Care at a glance</h2>
            <dl className="store-care">
              {CARE.filter((c) => p.care[c.key]).map((c) => (
                <div key={c.key}>
                  <dt>{c.label}</dt>
                  <dd>{p.care[c.key]}</dd>
                </div>
              ))}
              {typeof p.care.pet_safe === "boolean" ? (
                <div>
                  <dt>Pets</dt>
                  <dd>{p.care.pet_safe ? "Safe for cats and dogs" : "Keep away from pets that chew leaves"}</dd>
                </div>
              ) : null}
            </dl>
          </div>
        </section>
        {related.length + more.length ? (
          <section className="svc-wrap">
            <h2>You may also like</h2>
            <div className="store-grid">
              {[...related, ...more].map((x) => (
                <PlantCard key={x.slug} p={x} />
              ))}
            </div>
          </section>
        ) : null}
        <section className="svc-wrap svc-cta">
          <div>
            <h2>Have a plot that needs looking after?</h2>
            <p>We also clean, fence, garden and inspect plots across Bangalore, with photo proof of every visit.</p>
          </div>
          <div className="row">
            <Link href="/services" className="btn primary big">
              See plot services
            </Link>
          </div>
        </section>
      </main>
    </StoreShell>
  );
}
