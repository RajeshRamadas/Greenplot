import { BUSINESS } from "@/lib/legal";

/** Public address of the website. Canonical links, the sitemap and structured data are built from it. */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || "https://greenplot.in").replace(/\/$/, "");

export const absolute = (path: string) => `${SITE_URL}${path.startsWith("/") ? path : `/${path}`}`;

/** Image shown when a page is shared on WhatsApp, Facebook or X. */
export const SHARE_IMAGE = { url: "/og/greenplot.jpg", width: 1200, height: 630, alt: "A Bangalore plot before and after cleaning by GreenPlot" };

/** Open Graph tags for a page. Next replaces the layout's openGraph object whole, so the share image is repeated here. */
export const pageOpenGraph = (og: { title: string; description: string; url: string; type?: "website" | "article"; publishedTime?: string }) => ({
  siteName: "GreenPlot",
  locale: "en_IN",
  images: [SHARE_IMAGE],
  ...og,
});

export const rupees = (n: number) => `₹${n.toLocaleString("en-IN")}`;

/** The business as schema.org sees it; pages refer to it by @id. */
export function businessSchema() {
  return {
    "@type": "LocalBusiness",
    "@id": absolute("/#business"),
    name: BUSINESS.brand,
    legalName: BUSINESS.legalName,
    url: absolute("/"),
    image: absolute(SHARE_IMAGE.url),
    telephone: BUSINESS.phone.replace(/\s+/g, "-"),
    email: BUSINESS.email,
    priceRange: "₹₹",
    address: {
      "@type": "PostalAddress",
      streetAddress: BUSINESS.street,
      addressLocality: BUSINESS.city,
      addressRegion: BUSINESS.state,
      postalCode: BUSINESS.postalCode,
      addressCountry: "IN",
    },
    openingHoursSpecification: [
      { "@type": "OpeningHoursSpecification", dayOfWeek: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"], opens: "09:00", closes: "18:00" },
    ],
  };
}

export function breadcrumbSchema(items: { name: string; path: string }[]) {
  return {
    "@type": "BreadcrumbList",
    itemListElement: items.map((it, i) => ({ "@type": "ListItem", position: i + 1, name: it.name, item: absolute(it.path) })),
  };
}

export function faqSchema(faqs: { q: string; a: string }[]) {
  return {
    "@type": "FAQPage",
    mainEntity: faqs.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
  };
}
