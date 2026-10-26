import type { MetadataRoute } from "next";
import { getAllPosts, getTopics } from "@/lib/blog";
import { liveCities } from "@/lib/cities";
import { LEGAL_PAGES } from "@/lib/legal";
import { SERVICES } from "@/lib/services";
import { absolute } from "@/lib/site";

// Blog posts come from the API, so the sitemap is built on request.
export const dynamic = "force-dynamic";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  // Leave the posts out if the API cannot be reached rather than failing the whole sitemap.
  const [posts, topics] = await Promise.all([getAllPosts(), getTopics()]);
  const page = (path: string, priority: number, lastModified?: string | null): MetadataRoute.Sitemap[number] => ({
    url: absolute(path),
    priority,
    ...(lastModified ? { lastModified } : {}),
  });
  return [
    page("/", 1),
    page("/services", 0.9),
    ...SERVICES.map((s) => page(`/services/${s.slug}`, 0.9)),
    ...liveCities().flatMap((c) => [page(`/${c.slug}`, 0.9), ...c.areas.map((a) => page(`/${c.slug}/${a.slug}`, 0.8))]),
    page("/blog", 0.6, topics?.updated_at),
    ...(topics?.categories ?? []).map((c) => page(`/blog/category/${c.slug}`, 0.5)),
    ...(posts ?? []).map((p) => page(`/blog/${p.slug}`, 0.6, p.updated_at)),
    ...LEGAL_PAGES.map((l) => page(l.href, 0.3)),
  ];
}
