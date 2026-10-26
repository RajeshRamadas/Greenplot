import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PriceCard } from "@/components/PriceCard";
import { STEPS, ServiceShell } from "@/components/ServicePage";
import { SERVICES, serviceBySlug } from "@/lib/services";

export const dynamicParams = false;

export function generateStaticParams() {
  return SERVICES.map((s) => ({ slug: s.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const s = serviceBySlug((await params).slug);
  return s ? { title: s.name, description: s.promise } : {};
}

export default async function ServiceDetail({ params }: { params: Promise<{ slug: string }> }) {
  const s = serviceBySlug((await params).slug);
  if (!s) notFound();
  return (
    <ServiceShell current={s.slug}>
      <main>
        <section className="svc-wrap svc-hero">
          <p className="svc-eyebrow">Service</p>
          <h1>{s.name}</h1>
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
            <img src={s.beforeAfter} alt={`Sample before and after photos for ${s.name.toLowerCase()}`} />
            <figcaption>Sample before and after photos. These are illustrations; your reports show real photos from the site.</figcaption>
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
              <img src={s.shot.src} alt={s.shot.alt} loading="lazy" />
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
      </main>
    </ServiceShell>
  );
}
