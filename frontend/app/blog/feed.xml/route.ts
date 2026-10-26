import { CATEGORIES, fillTokens, getAllPosts } from "@/lib/blog";
import { absolute } from "@/lib/site";

export const dynamic = "force-dynamic";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** RSS feed of the latest guides, for feed readers, Feedly and email newsletters. */
export async function GET() {
  const posts = await getAllPosts();
  if (posts === null) return new Response("The feed is not available just now.", { status: 503, headers: { "Retry-After": "120" } });
  const items = posts.slice(0, 30).map((p) => {
    const url = absolute(`/blog/${p.slug}`);
    return [
      "<item>",
      `<title>${esc(p.title)}</title>`,
      `<link>${url}</link>`,
      `<guid isPermaLink="true">${url}</guid>`,
      p.published_at ? `<pubDate>${new Date(p.published_at).toUTCString()}</pubDate>` : "",
      `<category>${esc(CATEGORIES[p.category] ?? p.category)}</category>`,
      `<description>${esc(fillTokens(p.excerpt))}</description>`,
      p.cover_image ? `<enclosure url="${esc(p.cover_image.startsWith("/") ? absolute(p.cover_image) : p.cover_image)}" type="${p.cover_image.endsWith(".png") ? "image/png" : "image/jpeg"}" length="0"/>` : "",
      "</item>",
    ].join("");
  });
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
<title>GreenPlot guides for Bangalore plot owners</title>
<link>${absolute("/blog")}</link>
<atom:link href="${absolute("/blog/feed.xml")}" rel="self" type="application/rss+xml"/>
<description>Plot cleaning costs, upkeep and protecting your plot in Bangalore.</description>
<language>en-IN</language>
${posts[0]?.published_at ? `<lastBuildDate>${new Date(posts[0].published_at).toUTCString()}</lastBuildDate>` : ""}
${items.join("\n")}
</channel>
</rss>`;
  return new Response(xml, { headers: { "Content-Type": "application/rss+xml; charset=utf-8", "Cache-Control": "public, max-age=600" } });
}
