import type { MetadataRoute } from "next";
import { absolute } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/api/", "/proof/"] }],
    sitemap: absolute("/sitemap.xml"),
  };
}
