import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import { PostGrid } from "@/components/Blog";
import { JsonLd } from "@/components/JsonLd";
import { Markdown, outline } from "@/components/Markdown";
import { ServiceShell } from "@/components/ServicePage";
import { ShareButtons } from "@/components/Share";
import { CATEGORIES, fillTokens, getPost, longDate, tagSlug } from "@/lib/blog";
import { serviceBySlug } from "@/lib/services";
import { absolute, breadcrumbSchema, pageOpenGraph, pageTitle, SHARE_IMAGE } from "@/lib/site";

// Posts come from the API, so the page is rendered on request (its data is cached for a minute).
export const dynamic = "force-dynamic";

const load = cache(getPost);

type Props = { params: Promise<{ slug: string }> };

const absoluteImage = (src: string) => (src.startsWith("/") ? absolute(src) : src);

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const data = await load((await params).slug);
  if (!data) return {};
  const p = data.post;
  const path = `/blog/${p.slug}`;
  const title = p.seo_title || p.title;
  const description = fillTokens(p.seo_description || p.excerpt);
  return {
    title: pageTitle(title),
    description,
    keywords: p.tags,
    alternates: { canonical: path },
    openGraph: {
      ...pageOpenGraph({ type: "article", title, description, url: path, publishedTime: p.published_at ?? undefined }),
      modifiedTime: p.updated_at,
      tags: p.tags,
      ...(p.cover_image ? { images: [{ url: absoluteImage(p.cover_image), alt: p.cover_alt ?? p.title }] } : {}),
    },
  };
}

export default async function PostPage({ params }: Props) {
  const data = await load((await params).slug);
  if (!data) notFound();
  const { post: p, related } = data;
  const path = `/blog/${p.slug}`;
  const category = CATEGORIES[p.category] ?? p.category;
  const toc = outline(p.body);
  const services = p.services.flatMap((slug) => {
    const s = serviceBySlug(slug);
    return s ? [s] : [];
  });
  return (
    <ServiceShell>
      <JsonLd
        items={[
          {
            "@type": "BlogPosting",
            headline: p.title,
            description: fillTokens(p.seo_description || p.excerpt),
            datePublished: p.published_at,
            dateModified: p.updated_at,
            image: absoluteImage(p.cover_image || SHARE_IMAGE.url),
            url: absolute(path),
            mainEntityOfPage: absolute(path),
            articleSection: category,
            keywords: p.tags.join(", "),
            wordCount: p.reading_minutes * 200,
            author: { "@type": "Organization", name: p.author_name, url: absolute("/") },
            publisher: { "@id": absolute("/#business") },
          },
          breadcrumbSchema([
            { name: "Home", path: "/" },
            { name: "Guides", path: "/blog" },
            { name: category, path: `/blog/category/${p.category}` },
            { name: p.title, path },
          ]),
        ]}
      />
      <main>
        <article className="post">
          <nav className="svc-crumbs" aria-label="Breadcrumb">
            <a href="/">Home</a> › <Link href="/blog">Guides</Link> › <Link href={`/blog/category/${p.category}`}>{category}</Link>
          </nav>
          <h1>{p.title}</h1>
          <p className="post-meta">
            {p.published_at ? `Published ${longDate(p.published_at)}` : null} by {p.author_name} · {p.reading_minutes} min read
          </p>
          {p.cover_image ? (
            <figure className="post-cover">
              {/* eslint-disable-next-line @next/next/no-img-element -- covers can come from the API or another https site */}
              <img src={p.cover_image} alt={p.cover_alt ?? ""} decoding="async" fetchPriority="high" />
            </figure>
          ) : null}
          {toc.length >= 3 ? (
            <nav className="post-toc card" aria-label="In this guide">
              <b>In this guide</b>
              <ol>
                {toc.map((h) => (
                  <li key={h.id}>
                    <a href={`#${h.id}`}>{h.text}</a>
                  </li>
                ))}
              </ol>
            </nav>
          ) : null}
          <div className="post-body">
            <Markdown source={p.body} />
          </div>
          {p.tags.length ? (
            <ul className="post-tags" aria-label="Tags">
              {p.tags.map((t) => (
                <li key={t}>
                  <Link href={`/blog/tag/${tagSlug(t)}`}>#{t}</Link>
                </li>
              ))}
            </ul>
          ) : null}
          <ShareButtons url={absolute(path)} title={p.title} />
          {services.length ? (
            <section className="post-services">
              <h2>Services in this guide</h2>
              <div className="svc-grid">
                {services.map((s) => (
                  <Link key={s.slug} href={`/services/${s.slug}`} className="card svc-item svc-link">
                    <h3>{s.name} in Bangalore</h3>
                    <p>{s.promise}</p>
                    <span className="svc-more">Prices and plans →</span>
                  </Link>
                ))}
              </div>
            </section>
          ) : null}
        </article>
        {related.length ? (
          <section className="svc-wrap">
            <h2>More guides</h2>
            <PostGrid posts={related} />
          </section>
        ) : null}
      </main>
    </ServiceShell>
  );
}
