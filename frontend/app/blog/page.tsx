import type { Metadata } from "next";
import Link from "next/link";
import { ServiceShell } from "@/components/ServicePage";
import { POSTS } from "@/lib/blog";

export const metadata: Metadata = {
  title: "Guides for Bangalore Plot Owners",
  description: "Plot cleaning costs, NRI plot care, encroachment and monsoon checklists: practical guides for owners of vacant plots in Bangalore.",
  alternates: { canonical: "/blog" },
};

export default function BlogIndex() {
  return (
    <ServiceShell>
      <main>
        <section className="svc-wrap svc-hero">
          <p className="svc-eyebrow">Guides</p>
          <h1>Guides for Bangalore plot owners</h1>
          <p className="svc-lead">Straight answers on costs, upkeep and keeping your plot safe, from the team that looks after plots every day.</p>
        </section>
        <section className="svc-wrap svc-grid wide">
          {POSTS.map((p) => (
            <Link key={p.slug} href={`/blog/${p.slug}`} className="card svc-item svc-link">
              <h3>{p.title}</h3>
              <p>{p.description}</p>
              <span className="svc-more">Read the guide →</span>
            </Link>
          ))}
        </section>
      </main>
    </ServiceShell>
  );
}
