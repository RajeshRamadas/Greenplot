import type { MetadataRoute } from "next";
import { POSTS } from "@/lib/blog";
import { liveCities } from "@/lib/cities";
import { LEGAL_PAGES } from "@/lib/legal";
import { SERVICES } from "@/lib/services";
import { absolute } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const page = (path: string, priority: number, lastModified?: string): MetadataRoute.Sitemap[number] => ({
    url: absolute(path),
    priority,
    ...(lastModified ? { lastModified } : {}),
  });
  return [
    page("/", 1),
    page("/services", 0.9),
    ...SERVICES.map((s) => page(`/services/${s.slug}`, 0.9)),
    ...liveCities().flatMap((c) => [page(`/${c.slug}`, 0.9), ...c.areas.map((a) => page(`/${c.slug}/${a.slug}`, 0.8))]),
    page("/blog", 0.6),
    ...POSTS.map((p) => page(`/blog/${p.slug}`, 0.6, p.published)),
    ...LEGAL_PAGES.map((l) => page(l.href, 0.3)),
  ];
}
