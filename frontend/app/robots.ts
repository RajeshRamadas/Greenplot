import type { MetadataRoute } from "next";
import { absolute } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    // Proof pages stay crawlable so search engines can read their noindex header.
    // Blog pictures are served by the API but are public, so Google Images and link previews may fetch them.
    rules: [{ userAgent: "*", allow: ["/", "/api/v1/public/blog/images/"], disallow: ["/api/"] }],
    sitemap: absolute("/sitemap.xml"),
  };
}
