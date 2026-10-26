/**
 * The marketing blog (/blog). Posts live in the API and are written from the office's Blog page.
 * Bodies are Markdown (see components/Markdown.tsx) with {{…}} price tokens, filled in here from
 * SERVICES so a price change updates every post that mentions it.
 */
import { serviceBySlug, TERRAIN_NOTE } from "@/lib/services";
import { rupees } from "@/lib/site";

export interface PostCard {
  slug: string;
  title: string;
  excerpt: string;
  cover_image: string | null;
  cover_alt: string | null;
  category: string;
  tags: string[];
  published_at: string | null;
  updated_at: string;
  featured: boolean;
  author_name: string;
  reading_minutes: number;
}

export interface Post extends PostCard {
  body: string;
  services: string[];
  seo_title: string | null;
  seo_description: string | null;
}

export interface AdminPost extends Post {
  id: string;
  created_at: string;
  status: "draft" | "published";
  state: "draft" | "scheduled" | "published";
}

export interface Topics {
  categories: { slug: string; name: string; count: number }[];
  tags: { slug: string; name: string; count: number }[];
  updated_at: string | null;
}

/** Keep in step with app.services.blog.CATEGORIES in the API. */
export const CATEGORIES: Record<string, string> = {
  costs: "Costs & pricing",
  "plot-care": "Plot care",
  nri: "For NRI owners",
  protection: "Protecting your plot",
  seasonal: "Seasonal guides",
  gardening: "Gardens & plants",
  "our-work": "Our work",
  news: "GreenPlot news",
};

export const PAGE_SIZE = 12;

export const slugify = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

export const tagSlug = slugify;

export const longDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric", timeZone: "Asia/Kolkata" });

// ------------------------------------------------------------------ price tokens

/** What each token means, for the editor's help. */
export const TOKENS: { token: string; means: string }[] = [
  { token: "{{rate:plot-cleaning}}", means: "price per sq ft, e.g. ₹2" },
  { token: "{{minimum:plot-cleaning}}", means: "minimum charge per visit" },
  { token: "{{estimate:plot-cleaning:1200}}", means: "price of one visit for 1,200 sq ft" },
  { token: "{{plan:plot-cleaning:1}}", means: "name of the 1st annual plan (Basic)" },
  { token: "{{plan-rate:plot-cleaning:1}}", means: "that plan's price per sq ft a year" },
  { token: "{{plan-summary:plot-cleaning:1}}", means: "what that plan includes, e.g. 4 cleanings a year" },
  { token: "{{terrain-note}}", means: "the standard note on overgrown or rocky plots" },
];

function token(name: string, slug = "", arg = ""): string {
  if (name === "terrain-note") return TERRAIN_NOTE;
  const s = serviceBySlug(slug);
  const plan = s?.amc?.[Number(arg) - 1];
  switch (name) {
    case "rate":
      return s?.price ? rupees(s.price.perSqft) : "on request";
    case "minimum":
      return s?.price ? rupees(s.price.minimum) : "on request";
    case "estimate":
      return s?.price && Number(arg) > 0 ? rupees(Math.max(Number(arg) * s.price.perSqft, s.price.minimum)) : "on request";
    case "plan":
      return plan?.name ?? "annual";
    case "plan-rate":
      return plan ? rupees(plan.perSqftYear) : "on request";
    case "plan-summary":
      return plan ? plan.summary.toLowerCase() : "regular visits";
  }
  return "";
}

/** Replace {{name:service:arg}} tokens with today's prices. Unknown tokens are dropped. */
export const fillTokens = (text: string) => text.replace(/\{\{\s*([a-z-]+)(?::([a-z0-9-]+))?(?::([0-9]+))?\s*\}\}/g, (_, n, s, a) => token(n, s, a));

// ------------------------------------------------------------------ reading the API on the server

const API = (process.env.GREENPLOT_API_URL || "http://localhost:8000").replace(/\/$/, "");

/**
 * Read public blog data from the API on the server. Returns null when the API cannot be reached
 * or the item does not exist; with `strict`, only a missing item gives null and an unreachable API
 * throws, so a short outage shows an error page instead of telling search engines the post is gone.
 */
async function blogGet<T>(path: string, query?: Record<string, string | number | undefined>, strict = false): Promise<T | null> {
  const qs = new URLSearchParams(Object.entries(query ?? {}).flatMap(([k, v]) => (v === undefined || v === "" ? [] : [[k, String(v)]]))).toString();
  let r: Response;
  try {
    // Scheduled posts appear within a minute of their time.
    r = await fetch(`${API}/api/v1/public/blog${path}${qs ? `?${qs}` : ""}`, { next: { revalidate: 60 } });
  } catch (e) {
    if (strict) throw e;
    return null;
  }
  if (r.ok) return (await r.json()) as T;
  if (strict && r.status !== 404) throw new Error(`Blog API answered ${r.status}`);
  return null;
}

export const getPosts = (q: { category?: string; tag?: string; limit?: number; offset?: number } = {}) =>
  blogGet<{ items: PostCard[]; total: number; limit: number; offset: number }>("/posts", { limit: PAGE_SIZE, ...q });
export const getPost = (slug: string) => blogGet<{ post: Post; related: PostCard[] }>(`/posts/${encodeURIComponent(slug)}`, undefined, true);
export const getTopics = () => blogGet<Topics>("/topics");
/** Every live post, newest first, for the sitemap and RSS feed. */
export const getAllPosts = async () => (await getPosts({ limit: 500 }))?.items ?? null;
