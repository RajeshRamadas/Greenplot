import type { Metadata } from "next";
import { JsonLd } from "@/components/JsonLd";
import { PlantCard, StoreShell } from "@/components/StoreShell";
import { CATEGORIES, getPlants, getStoreConfig, rupees } from "@/lib/store";
import { absolute, breadcrumbSchema, businessSchema, pageOpenGraph } from "@/lib/site";

// The catalogue comes from the API, so the page is rendered on request (its data is cached for a minute).
export const dynamic = "force-dynamic";

const title = "Buy Plants Online in Bangalore, Delivered to Your Door";
const description = "Indoor plants, flowering shrubs, herbs and succulents delivered across Bangalore. Pay online or cash on delivery, with a bill for every order.";

export const metadata: Metadata = {
  title,
  description,
  alternates: { canonical: "/store" },
  openGraph: pageOpenGraph({ title, description, url: "/store" }),
};

export default async function StorePage() {
  const [plants, cfg] = await Promise.all([getPlants(), getStoreConfig()]);
  const groups = Object.entries(CATEGORIES)
    .map(([slug, name]) => ({ slug, name, plants: (plants ?? []).filter((p) => p.category === slug) }))
    .filter((g) => g.plants.length);
  return (
    <StoreShell>
      <JsonLd
        items={[
          businessSchema(),
          breadcrumbSchema([
            { name: "Home", path: "/" },
            { name: "Plant store", path: "/store" },
          ]),
          {
            "@type": "ItemList",
            name: "Plants for sale in Bangalore",
            itemListElement: (plants ?? []).map((p, i) => ({ "@type": "ListItem", position: i + 1, url: absolute(`/store/${p.slug}`), name: p.name })),
          },
        ]}
      />
      <main>
        <section className="svc-wrap svc-hero">
          <p className="svc-eyebrow">Plant store · Bangalore</p>
          <h1>Healthy plants, delivered to your door in Bangalore</h1>
          <p className="svc-lead">Nursery-grown plants for homes, balconies, offices and plots, picked and packed by our gardeners.</p>
          <ul className="svc-chips" aria-label="Why buy here">
            {cfg ? <li>Free delivery over {rupees(cfg.free_delivery_over)}</li> : null}
            {cfg?.cod ? <li>Cash on delivery</li> : null}
            <li>UPI, cards and net banking</li>
            <li>Bill with every order</li>
          </ul>
        </section>
        {groups.length > 1 ? (
          <nav className="svc-wrap svc-area-list" aria-label="Categories">
            {groups.map((g) => (
              <a key={g.slug} href={`#${g.slug}`}>
                {g.name}
              </a>
            ))}
          </nav>
        ) : null}
        {plants === null ? (
          <section className="svc-wrap">
            <div className="alert error">The store could not be loaded just now. Please refresh in a minute, or WhatsApp us to order.</div>
          </section>
        ) : !groups.length ? (
          <section className="svc-wrap">
            <p className="muted">New plants are on their way. Please check back soon.</p>
          </section>
        ) : (
          groups.map((g) => (
            <section key={g.slug} id={g.slug} className="svc-wrap store-section">
              <h2>{g.name}</h2>
              <div className="store-grid">
                {g.plants.map((p) => (
                  <PlantCard key={p.slug} p={p} />
                ))}
              </div>
            </section>
          ))
        )}
        <section className="svc-wrap">
          <h2>How ordering works</h2>
          <ol className="svc-steps store-steps">
            <li>
              <b>Pick your plants</b>
              <span>Add them to your cart and check out with your address.</span>
            </li>
            <li>
              <b>Pay your way</b>
              <span>Pay online by UPI, card or net banking, or in cash when the plants arrive.</span>
            </li>
            <li>
              <b>Get your bill</b>
              <span>Your order page shows the bill straight away; print it or save it as a PDF.</span>
            </li>
            <li>
              <b>Delivered with care</b>
              <span>We call before delivery and bring the plants in their nursery pots, watered and ready.</span>
            </li>
          </ol>
        </section>
      </main>
    </StoreShell>
  );
}
