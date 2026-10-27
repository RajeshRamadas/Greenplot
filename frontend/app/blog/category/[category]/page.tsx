import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { BlogList, pageNumber } from "@/components/Blog";
import { JsonLd } from "@/components/JsonLd";
import { ServiceShell } from "@/components/ServicePage";
import { CATEGORIES, getPosts, getTopics, PAGE_SIZE } from "@/lib/blog";
import { breadcrumbSchema, pageOpenGraph, pageTitle } from "@/lib/site";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ category: string }>; searchParams: Promise<{ page?: string }> };

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const { category } = await params;
  const name = CATEGORIES[category];
  if (!name) return {};
  const page = pageNumber((await searchParams).page);
  const base = `/blog/category/${category}`;
  const title = `${name}: Guides for Bangalore Plot Owners`;
  const description = `GreenPlot's guides on ${name.toLowerCase()} for owners of plots and layouts in Bangalore.`;
  return {
    title: pageTitle(page > 1 ? `${title} (page ${page})` : title),
    description,
    alternates: { canonical: page > 1 ? `${base}?page=${page}` : base },
    openGraph: pageOpenGraph({ title, description, url: base }),
  };
}

export default async function CategoryPage({ params, searchParams }: Props) {
  const { category } = await params;
  const name = CATEGORIES[category];
  if (!name) notFound();
  const page = pageNumber((await searchParams).page);
  const base = `/blog/category/${category}`;
  const [posts, topics] = await Promise.all([getPosts({ category, offset: (page - 1) * PAGE_SIZE }), getTopics()]);
  return (
    <ServiceShell>
      <JsonLd
        items={[
          breadcrumbSchema([
            { name: "Home", path: "/" },
            { name: "Guides", path: "/blog" },
            { name, path: base },
          ]),
        ]}
      />
      <main>
        <section className="svc-wrap svc-hero">
          <nav className="svc-crumbs" aria-label="Breadcrumb">
            <a href="/">Home</a> › <Link href="/blog">Guides</Link>
          </nav>
          <h1>{name}</h1>
        </section>
        <BlogList posts={posts} topics={topics} current={category} base={base} page={page} />
      </main>
    </ServiceShell>
  );
}
