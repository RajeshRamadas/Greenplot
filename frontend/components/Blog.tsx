import Link from "next/link";
import { CATEGORIES, longDate, PAGE_SIZE, type PostCard, type Topics } from "@/lib/blog";

/** A post in a list: cover, category, title, excerpt and date. */
export function PostTile({ p, big }: { p: PostCard; big?: boolean }) {
  return (
    <Link href={`/blog/${p.slug}`} className={`card blog-tile${big ? " big" : ""}`}>
      {p.cover_image ? (
        // eslint-disable-next-line @next/next/no-img-element -- covers can come from the API or another https site
        <img src={p.cover_image} alt={p.cover_alt ?? ""} loading={big ? "eager" : "lazy"} decoding="async" />
      ) : (
        <span className="blog-tile-blank" aria-hidden="true" />
      )}
      <span className="blog-tile-body">
        <span className="blog-cat">{CATEGORIES[p.category] ?? p.category}</span>
        {big ? <h2>{p.title}</h2> : <h3>{p.title}</h3>}
        <span className="blog-excerpt">{p.excerpt}</span>
        <span className="post-meta">
          {p.published_at ? longDate(p.published_at) : null} · {p.reading_minutes} min read
        </span>
      </span>
    </Link>
  );
}

export function PostGrid({ posts }: { posts: PostCard[] }) {
  return (
    <div className="blog-grid">
      {posts.map((p) => (
        <PostTile key={p.slug} p={p} />
      ))}
    </div>
  );
}

/** Category menu above the list; the current one is marked. */
export function TopicNav({ topics, current }: { topics: Topics | null; current?: string }) {
  if (!topics?.categories.length) return null;
  return (
    <nav className="svc-wrap svc-area-list blog-topics" aria-label="Topics">
      <Link href="/blog" aria-current={current ? undefined : "page"}>
        All guides
      </Link>
      {topics.categories.map((c) => (
        <Link key={c.slug} href={`/blog/category/${c.slug}`} aria-current={current === c.slug ? "page" : undefined}>
          {c.name}
        </Link>
      ))}
    </nav>
  );
}

/** Older and newer pages, as plain links so search engines can follow them. */
export function PageLinks({ base, page, total }: { base: string; page: number; total: number }) {
  const pages = Math.ceil(total / PAGE_SIZE);
  if (pages <= 1) return null;
  const href = (n: number) => (n === 1 ? base : `${base}?page=${n}`);
  return (
    <nav className="svc-wrap blog-pager" aria-label="Pages">
      {page > 1 ? (
        <Link href={href(page - 1)} className="btn ghost" rel="prev">
          ← Newer
        </Link>
      ) : (
        <span />
      )}
      <span className="muted">
        Page {page} of {pages}
      </span>
      {page < pages ? (
        <Link href={href(page + 1)} className="btn ghost" rel="next">
          Older →
        </Link>
      ) : (
        <span />
      )}
    </nav>
  );
}

export const pageNumber = (v: string | string[] | undefined) => Math.max(1, Math.floor(Number(Array.isArray(v) ? v[0] : v) || 1));

/** The body of /blog, /blog/category/… and /blog/tag/…: menu, featured post on the first page, grid and pager. */
export function BlogList({
  posts,
  topics,
  current,
  base,
  page,
  feature,
}: {
  posts: { items: PostCard[]; total: number } | null;
  topics: Topics | null;
  current?: string;
  base: string;
  page: number;
  feature?: boolean;
}) {
  const items = posts?.items ?? [];
  const lead = feature && page === 1 ? (items.find((p) => p.featured) ?? items[0]) : undefined;
  const rest = lead ? items.filter((p) => p !== lead) : items;
  return (
    <>
      <TopicNav topics={topics} current={current} />
      {posts === null ? (
        <section className="svc-wrap">
          <div className="alert error">The guides could not be loaded just now. Please refresh in a minute.</div>
        </section>
      ) : !items.length ? (
        <section className="svc-wrap">
          <p className="muted">New guides are on their way. Please check back soon.</p>
        </section>
      ) : (
        <section className="svc-wrap">
          {lead ? <PostTile p={lead} big /> : null}
          <PostGrid posts={rest} />
        </section>
      )}
      {posts ? <PageLinks base={base} page={page} total={posts.total} /> : null}
    </>
  );
}
