import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { JsonLd } from "@/components/JsonLd";
import { ServiceShell } from "@/components/ServicePage";
import { POSTS, postBySlug } from "@/lib/blog";
import { serviceBySlug } from "@/lib/services";
import { absolute, breadcrumbSchema, SHARE_IMAGE } from "@/lib/site";

export const dynamicParams = false;

export function generateStaticParams() {
  return POSTS.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const p = postBySlug((await params).slug);
  if (!p) return {};
  const path = `/blog/${p.slug}`;
  return {
    title: p.title,
    description: p.description,
    alternates: { canonical: path },
    openGraph: { type: "article", title: p.title, description: p.description, url: path, publishedTime: p.published },
  };
}

const longDate = (iso: string) => new Date(`${iso}T00:00:00+05:30`).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });

export default async function PostPage({ params }: { params: Promise<{ slug: string }> }) {
  const p = postBySlug((await params).slug);
  if (!p) notFound();
  const path = `/blog/${p.slug}`;
  return (
    <ServiceShell>
      <JsonLd
        items={[
          {
            "@type": "Article",
            headline: p.title,
            description: p.description,
            datePublished: p.published,
            image: absolute(SHARE_IMAGE.url),
            url: absolute(path),
            author: { "@type": "Organization", name: "GreenPlot", url: absolute("/") },
            publisher: { "@id": absolute("/#business") },
          },
          breadcrumbSchema([
            { name: "Home", path: "/" },
            { name: "Guides", path: "/blog" },
            { name: p.title, path },
          ]),
        ]}
      />
      <main>
        <article className="post">
          <nav className="svc-crumbs" aria-label="Breadcrumb">
            <Link href="/">Home</Link> › <Link href="/blog">Guides</Link>
          </nav>
          <h1>{p.title}</h1>
          <p className="post-meta">Published {longDate(p.published)} by the GreenPlot team</p>
          {p.sections.map((s, i) => (
            <section key={s.heading ?? i}>
              {s.heading ? <h2>{s.heading}</h2> : null}
              {s.paragraphs.map((t) => (
                <p key={t}>{t}</p>
              ))}
              {s.bullets ? (
                <ul>
                  {s.bullets.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
              ) : null}
            </section>
          ))}
          <h2>Related services</h2>
          <ul>
            {p.services.map((slug) => {
              const s = serviceBySlug(slug);
              return s ? (
                <li key={slug}>
                  <Link href={`/services/${slug}`}>{s.name} in Bangalore</Link>
                </li>
              ) : null;
            })}
          </ul>
        </article>
      </main>
    </ServiceShell>
  );
}
