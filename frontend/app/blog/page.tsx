import type { Metadata } from "next";
import { BlogList, pageNumber } from "@/components/Blog";
import { JsonLd } from "@/components/JsonLd";
import { ServiceShell } from "@/components/ServicePage";
import { getPosts, getTopics, PAGE_SIZE } from "@/lib/blog";
import { absolute, breadcrumbSchema, pageOpenGraph } from "@/lib/site";

// Posts come from the API, so the page is rendered on request (its data is cached for a minute).
export const dynamic = "force-dynamic";

const title = "Guides for Bangalore Plot Owners";
const description = "Plot cleaning costs, NRI plot care, encroachment and monsoon checklists: practical guides for owners of vacant plots in Bangalore.";

export async function generateMetadata({ searchParams }: { searchParams: Promise<{ page?: string }> }): Promise<Metadata> {
  const page = pageNumber((await searchParams).page);
  const path = page > 1 ? `/blog?page=${page}` : "/blog";
  return {
    title: page > 1 ? `${title} (page ${page})` : title,
    description,
    alternates: { canonical: path, types: { "application/rss+xml": [{ url: "/blog/feed.xml", title: "GreenPlot guides" }] } },
    openGraph: pageOpenGraph({ title, description, url: path }),
  };
}

export default async function BlogIndex({ searchParams }: { searchParams: Promise<{ page?: string }> }) {
  const page = pageNumber((await searchParams).page);
  const [posts, topics] = await Promise.all([getPosts({ offset: (page - 1) * PAGE_SIZE }), getTopics()]);
  return (
    <ServiceShell>
      <JsonLd
        items={[
          breadcrumbSchema([
            { name: "Home", path: "/" },
            { name: "Guides", path: "/blog" },
          ]),
          {
            "@type": "Blog",
            name: "GreenPlot guides for plot owners",
            url: absolute("/blog"),
            publisher: { "@id": absolute("/#business") },
            blogPost: (posts?.items ?? []).map((p) => ({ "@type": "BlogPosting", headline: p.title, url: absolute(`/blog/${p.slug}`), datePublished: p.published_at })),
          },
        ]}
      />
      <main>
        <section className="svc-wrap svc-hero">
          <p className="svc-eyebrow">Guides · Bangalore</p>
          <h1>Guides for Bangalore plot owners</h1>
          <p className="svc-lead">Straight answers on costs, upkeep and keeping your plot safe, from the team that looks after plots every day.</p>
        </section>
        <BlogList posts={posts} topics={topics} base="/blog" page={page} feature />
      </main>
    </ServiceShell>
  );
}
