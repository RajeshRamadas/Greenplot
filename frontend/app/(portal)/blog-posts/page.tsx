"use client";

import Link from "next/link";
import { useState } from "react";
import { StateBadge } from "@/components/BlogEditor";
import { Empty, ErrorBox, Loading, PageHead } from "@/components/ui";
import { type AdminPost, CATEGORIES, longDate } from "@/lib/blog";
import { useApi } from "@/lib/hooks";

/** Every blog post, newest change first, with drafts and scheduled posts. */
export default function BlogPostsPage() {
  const [state, setState] = useState("");
  const [q, setQ] = useState("");
  const { data, loading, error } = useApi<AdminPost[]>("/blog/posts", { state, q });
  return (
    <>
      <PageHead title="Blog" sub="Guides and stories on greenplot.in/blog. Write a draft, preview it, then publish now or pick a date.">
        <a className="btn ghost" href="/blog" target="_blank" rel="noopener">
          View the blog
        </a>
        <Link className="btn primary" href="/blog-posts/new">
          Write a post
        </Link>
      </PageHead>
      <div className="tabs" role="tablist">
        {[
          ["", "All"],
          ["published", "Live"],
          ["scheduled", "Scheduled"],
          ["draft", "Drafts"],
        ].map(([v, l]) => (
          <button key={v} role="tab" aria-selected={state === v} className={state === v ? "on" : ""} onClick={() => setState(v)}>
            {l}
          </button>
        ))}
      </div>
      <div className="row" style={{ marginBottom: 14 }}>
        <input type="search" placeholder="Search titles" value={q} onChange={(e) => setQ(e.target.value)} style={{ maxWidth: 320 }} />
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <Loading /> : null}
      {data && !data.length ? (
        <Empty title={q || state ? "No posts match" : "No posts yet"}>{q || state ? "Try another search." : "Write your first guide and it can be live in minutes."}</Empty>
      ) : null}
      {data?.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Post</th>
                <th>Topic</th>
                <th>Status</th>
                <th>Date</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id}>
                  <td>
                    <Link href={`/blog-posts/${p.id}`}>
                      <b>{p.title}</b>
                    </Link>
                    {p.featured ? <span className="badge amber" style={{ marginLeft: 6 }}>Featured</span> : null}
                    <div className="small muted">/blog/{p.slug}</div>
                  </td>
                  <td>{CATEGORIES[p.category] ?? p.category}</td>
                  <td>
                    <StateBadge state={p.state} />
                  </td>
                  <td className="small">{p.published_at && p.state !== "draft" ? longDate(p.published_at) : `Edited ${longDate(p.updated_at)}`}</td>
                  <td>
                    <div className="row">
                      <Link className="btn small ghost" href={`/blog-posts/${p.id}`}>
                        Edit
                      </Link>
                      {p.state === "published" ? (
                        <a className="btn small ghost" href={`/blog/${p.slug}`} target="_blank" rel="noopener">
                          View
                        </a>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}
