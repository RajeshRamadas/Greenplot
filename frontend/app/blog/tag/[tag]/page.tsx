import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { BlogList, pageNumber } from "@/components/Blog";
import { ServiceShell } from "@/components/ServicePage";
import { getPosts, getTopics, PAGE_SIZE } from "@/lib/blog";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ tag: string }>; searchParams: Promise<{ page?: string }> };

async function tagName(slug: string) {
  return (await getTopics())?.tags.find((t) => t.slug === slug)?.name;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { tag } = await params;
  const name = await tagName(tag);
  if (!name) return {};
  // Tag pages overlap with categories, so they help visitors but are kept out of search results.
  return { title: `Guides about ${name}`, robots: { index: false, follow: true } };
}

export default async function TagPage({ params, searchParams }: Props) {
  const { tag } = await params;
  const page = pageNumber((await searchParams).page);
  const [name, posts, topics] = await Promise.all([tagName(tag), getPosts({ tag, offset: (page - 1) * PAGE_SIZE }), getTopics()]);
  if (topics && !name) notFound();
  return (
    <ServiceShell>
      <main>
        <section className="svc-wrap svc-hero">
          <nav className="svc-crumbs" aria-label="Breadcrumb">
            <a href="/">Home</a> › <Link href="/blog">Guides</Link>
          </nav>
          <p className="svc-eyebrow">Tag</p>
          <h1>{name ?? tag}</h1>
        </section>
        <BlogList posts={posts} topics={topics} base={`/blog/tag/${tag}`} page={page} />
      </main>
    </ServiceShell>
  );
}
