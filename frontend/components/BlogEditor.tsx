"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Markdown } from "@/components/Markdown";
import { ErrorBox, Field, Select, useToast } from "@/components/ui";
import { api } from "@/lib/api";
import { type AdminPost, CATEGORIES, fillTokens, longDate, slugify, TOKENS } from "@/lib/blog";
import { useAction } from "@/lib/hooks";
import { SERVICES } from "@/lib/services";

const STATE_LABEL: Record<AdminPost["state"], string> = { draft: "Draft", scheduled: "Scheduled", published: "Live" };
const STATE_TONE: Record<AdminPost["state"], string> = { draft: "grey", scheduled: "blue", published: "green" };

export function StateBadge({ state }: { state: AdminPost["state"] }) {
  return <span className={`badge ${STATE_TONE[state]}`}>{STATE_LABEL[state]}</span>;
}

interface Form {
  title: string;
  slug: string;
  excerpt: string;
  body: string;
  cover_image: string;
  cover_alt: string;
  category: string;
  tags: string;
  services: string[];
  seo_title: string;
  seo_description: string;
  featured: boolean;
  author_name: string;
  /** datetime-local value in the browser's time zone; empty means "now" when publishing. */
  publish_at: string;
}

/** ISO time → the value a datetime-local input shows, in the browser's time zone. */
const toLocalInput = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
};

const toForm = (p?: AdminPost): Form => ({
  title: p?.title ?? "",
  slug: p?.slug ?? "",
  excerpt: p?.excerpt ?? "",
  body: p?.body ?? "",
  cover_image: p?.cover_image ?? "",
  cover_alt: p?.cover_alt ?? "",
  category: p?.category ?? "plot-care",
  tags: p?.tags.join(", ") ?? "",
  services: p?.services ?? [],
  seo_title: p?.seo_title ?? "",
  seo_description: p?.seo_description ?? "",
  featured: p?.featured ?? false,
  author_name: p?.author_name ?? "GreenPlot team",
  publish_at: p?.state === "draft" && !p.published_at ? "" : toLocalInput(p?.published_at ?? null),
});

const STARTER = `Start with the answer the reader came for, in two or three sentences.

## First section heading

Explain one idea per section. Short paragraphs read best on a phone.

- A list works well for steps or prices
- Keep each point to one line

[[cta]]
`;

function Counter({ value, ideal }: { value: string; ideal: [number, number] }) {
  const n = value.length;
  const tone = n === 0 ? "muted" : n < ideal[0] || n > ideal[1] ? "warn-text" : "ok-text";
  return (
    <small className={tone}>
      {n} characters (best {ideal[0]} to {ideal[1]})
    </small>
  );
}

/** The office's editor for one blog post: write in Markdown, preview, then save as a draft, publish or schedule. */
export function BlogEditor({ post }: { post?: AdminPost }) {
  const router = useRouter();
  const toast = useToast();
  const act = useAction();
  const initial = useMemo(() => toForm(post), [post]);
  const [f, setF] = useState<Form>(post ? initial : { ...initial, body: STARTER });
  const [saved, setSaved] = useState<Form>(f);
  const [current, setCurrent] = useState(post);
  const [tab, setTab] = useState<"write" | "preview">("write");
  const [slugTouched, setSlugTouched] = useState(!!post);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [uploading, setUploading] = useState<"cover" | "body" | null>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);
  const coverInput = useRef<HTMLInputElement>(null);
  const bodyInput = useRef<HTMLInputElement>(null);
  const dirty = JSON.stringify(f) !== JSON.stringify(saved);

  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((x) => ({ ...x, [k]: v }));
  const live = current?.state === "published" || current?.state === "scheduled";
  const future = !!f.publish_at && new Date(f.publish_at).getTime() > Date.now() + 60_000;

  // ------------------------------------------------------------ body editing helpers

  function edit(fn: (text: string, start: number, end: number) => { text: string; select: [number, number] }) {
    const el = bodyRef.current;
    if (!el) return;
    const { text, select } = fn(f.body, el.selectionStart, el.selectionEnd);
    set("body", text);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(...select);
    });
  }

  const wrap = (before: string, after: string, placeholder: string) =>
    edit((t, s, e) => {
      const inner = t.slice(s, e) || placeholder;
      return { text: t.slice(0, s) + before + inner + after + t.slice(e), select: [s + before.length, s + before.length + inner.length] };
    });

  /** Start each selected line with a prefix (or the line the cursor is on). */
  const prefix = (p: string | ((i: number) => string)) =>
    edit((t, s, e) => {
      const from = t.lastIndexOf("\n", s - 1) + 1;
      const lines = t.slice(from, e).split("\n");
      const done = lines.map((l, i) => (typeof p === "string" ? p : p(i)) + l.replace(/^(#{1,3}\s+|[-*]\s+|\d+\.\s+|>\s?)/, "")).join("\n");
      return { text: t.slice(0, from) + done + t.slice(e), select: [from, from + done.length] };
    });

  /** Put a block on its own lines at the cursor. */
  const insertBlock = (block: string) =>
    edit((t, s) => {
      const before = t.slice(0, s);
      const lead = !before || before.endsWith("\n\n") ? "" : before.endsWith("\n") ? "\n" : "\n\n";
      const text = `${before}${lead}${block}\n\n${t.slice(s).replace(/^\n+/, "")}`;
      const at = before.length + lead.length + block.length;
      return { text, select: [at, at] };
    });

  const insertText = (s: string) => edit((t, a, b) => ({ text: t.slice(0, a) + s + t.slice(b), select: [a + s.length, a + s.length] }));

  async function upload(file: File, target: "cover" | "body") {
    const body = new FormData();
    body.append("file", file);
    setUploading(target);
    const r = await act.run(() => api<{ url: string }>("/blog/images", { body }));
    setUploading(null);
    if (!r) return;
    if (target === "cover") setF((x) => ({ ...x, cover_image: r.url }));
    else insertBlock(`![Describe the picture](${r.url} "Caption under the picture")`);
  }

  // ------------------------------------------------------------ saving

  async function save(action: "draft" | "publish" | "unpublish") {
    const body = {
      title: f.title.trim(),
      slug: f.slug,
      excerpt: f.excerpt.trim(),
      body: f.body,
      cover_image: f.cover_image.trim() || null,
      cover_alt: f.cover_alt.trim() || null,
      category: f.category,
      tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean),
      services: f.services,
      seo_title: f.seo_title.trim() || null,
      seo_description: f.seo_description.trim() || null,
      featured: f.featured,
      author_name: f.author_name.trim() || "GreenPlot team",
      // A live post keeps its date when it is only edited; "Save draft" remembers a planned date.
      published_at: f.publish_at ? new Date(f.publish_at).toISOString() : null,
      ...(action === "publish" ? { status: "published" } : action === "unpublish" ? { status: "draft" } : current ? {} : { status: "draft" }),
    };
    const r = await act.run(() => (current ? api<AdminPost>(`/blog/posts/${current.id}`, { method: "PATCH", body }) : api<AdminPost>("/blog/posts", { body })));
    if (!r) return;
    const next = toForm(r);
    setF(next);
    setSaved(next);
    setCurrent(r);
    toast(
      r.state === "published"
        ? action === "publish" && current?.state !== "published"
          ? "Published. It is on the website now."
          : "Saved. The website shows the change within a minute."
        : r.state === "scheduled"
          ? `Scheduled for ${new Date(r.published_at as string).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}`
          : "Draft saved",
    );
    if (!current) router.replace(`/blog-posts/${r.id}`);
  }

  async function remove() {
    if (!current) return;
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    const r = await act.run(() => api(`/blog/posts/${current.id}`, { method: "DELETE" }));
    if (r !== undefined) {
      setSaved(f); // nothing left to lose
      toast(`"${current.title}" deleted`);
      router.push("/blog-posts");
    }
  }

  const seoTitle = `${f.seo_title || f.title || "Post title"} · GreenPlot`;
  const seoDescription = fillTokens(f.seo_description || f.excerpt) || "The excerpt is shown here unless you write a search description.";

  return (
    <form
      className="blog-editor"
      onSubmit={(e) => {
        e.preventDefault();
        save(live ? "publish" : "draft");
      }}
    >
      <div className="page-head">
        <div>
          <p className="small">
            <Link href="/blog-posts">← All posts</Link>
          </p>
          <h1>{current ? "Edit post" : "Write a post"}</h1>
          <p>
            {current ? <StateBadge state={current.state} /> : <span className="badge grey">New</span>}{" "}
            {current?.state === "scheduled" && current.published_at ? `Goes live ${longDate(current.published_at)}. ` : null}
            {dirty ? "Unsaved changes" : current ? "All changes saved" : null}
          </p>
        </div>
        <div className="row">
          {current?.state === "published" ? (
            <a className="btn ghost" href={`/blog/${current.slug}`} target="_blank" rel="noopener">
              View on website
            </a>
          ) : null}
          {live ? (
            <>
              <button type="button" className="btn ghost" disabled={act.pending} onClick={() => save("unpublish")}>
                Unpublish
              </button>
              <button type="button" className="btn primary" disabled={act.pending || !dirty} onClick={() => save("publish")}>
                {future && current?.state !== "published" ? "Save schedule" : "Save changes"}
              </button>
            </>
          ) : (
            <>
              <button type="button" className="btn ghost" disabled={act.pending} onClick={() => save("draft")}>
                Save draft
              </button>
              <button type="button" className="btn primary" disabled={act.pending} onClick={() => save("publish")}>
                {future ? "Schedule" : "Publish now"}
              </button>
            </>
          )}
        </div>
      </div>
      <ErrorBox error={act.error} />

      <div className="blog-editor-grid">
        <div className="blog-editor-main">
          <Field label="Title" hint="What the reader searches for, in their words: e.g. How much does plot cleaning cost in Bangalore?">
            <input
              required
              maxLength={160}
              value={f.title}
              onChange={(e) => setF((x) => ({ ...x, title: e.target.value, ...(slugTouched ? {} : { slug: slugify(e.target.value).slice(0, 100) }) }))}
            />
          </Field>
          <div className="tabs" role="tablist">
            <button type="button" role="tab" aria-selected={tab === "write"} className={tab === "write" ? "on" : ""} onClick={() => setTab("write")}>
              Write
            </button>
            <button type="button" role="tab" aria-selected={tab === "preview"} className={tab === "preview" ? "on" : ""} onClick={() => setTab("preview")}>
              Preview
            </button>
          </div>
          {tab === "write" ? (
            <>
              <div className="md-toolbar" role="toolbar" aria-label="Formatting">
                <button type="button" className="btn small ghost" onClick={() => prefix("## ")} title="Section heading">
                  H2
                </button>
                <button type="button" className="btn small ghost" onClick={() => prefix("### ")} title="Smaller heading">
                  H3
                </button>
                <button type="button" className="btn small ghost" onClick={() => wrap("**", "**", "bold text")} title="Bold">
                  <b>B</b>
                </button>
                <button type="button" className="btn small ghost" onClick={() => wrap("*", "*", "italic text")} title="Italic">
                  <i>I</i>
                </button>
                <button type="button" className="btn small ghost" onClick={() => wrap("[", "](/services/plot-cleaning)", "link text")} title="Link">
                  Link
                </button>
                <button type="button" className="btn small ghost" onClick={() => prefix("- ")} title="Bullet list">
                  • List
                </button>
                <button type="button" className="btn small ghost" onClick={() => prefix((i) => `${i + 1}. `)} title="Numbered list">
                  1. List
                </button>
                <button type="button" className="btn small ghost" onClick={() => prefix("> ")} title="Quote">
                  Quote
                </button>
                <button type="button" className="btn small ghost" disabled={!!uploading} onClick={() => bodyInput.current?.click()} title="Add a picture">
                  {uploading === "body" ? "Uploading…" : "Picture"}
                </button>
                <button type="button" className="btn small ghost" onClick={() => insertBlock("[[cta]]")} title="WhatsApp box">
                  WhatsApp box
                </button>
                <Select
                  aria-label="Insert a price"
                  value=""
                  placeholder="Insert a price…"
                  onChange={(v) => v && insertText(v)}
                  options={TOKENS.map((t) => ({ value: t.token, label: t.means }))}
                />
              </div>
              <textarea ref={bodyRef} className="md-input" required value={f.body} onChange={(e) => set("body", e.target.value)} rows={24} spellCheck />
              <p className="small muted">
                ## starts a section, - starts a list item, **bold**, *italic*, [text](/page) for a link. Prices like {"{{rate:plot-cleaning}}"} always show today&apos;s
                price from the service pages.
              </p>
            </>
          ) : (
            <article className="post card blog-preview">
              {f.cover_image ? (
                <figure className="post-cover">
                  {/* eslint-disable-next-line @next/next/no-img-element -- uploaded pictures are served by the API */}
                  <img src={f.cover_image} alt={f.cover_alt} />
                </figure>
              ) : null}
              <h1>{f.title || "Post title"}</h1>
              <div className="post-body">
                <Markdown source={f.body} />
              </div>
            </article>
          )}
          <input ref={bodyInput} type="file" accept="image/jpeg,image/png,image/webp,image/heic" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0], "body").finally(() => (e.target.value = ""))} />
        </div>

        <aside className="blog-editor-side">
          <section className="card">
            <h2>Publishing</h2>
            <div className="form">
              <Field label="Publish on" hint={live ? "Change it to move the date. Leave empty to use now." : "Leave empty to publish straight away, or pick a date and time to schedule."}>
                <input type="datetime-local" value={f.publish_at} onChange={(e) => set("publish_at", e.target.value)} />
              </Field>
              <Field label="Topic">
                <Select value={f.category} onChange={(v) => set("category", v)} options={Object.entries(CATEGORIES).map(([value, label]) => ({ value, label }))} />
              </Field>
              <Field label="Tags" hint="Separated by commas, e.g. NRI, Monsoon, Plot cleaning">
                <input value={f.tags} onChange={(e) => set("tags", e.target.value)} />
              </Field>
              <label className="check">
                <input type="checkbox" checked={f.featured} onChange={(e) => set("featured", e.target.checked)} /> Feature at the top of the blog
              </label>
              <Field label="Written by">
                <input maxLength={120} value={f.author_name} onChange={(e) => set("author_name", e.target.value)} />
              </Field>
            </div>
          </section>

          <section className="card">
            <h2>Cover picture</h2>
            {f.cover_image ? (
              // eslint-disable-next-line @next/next/no-img-element -- uploaded pictures are served by the API
              <img className="blog-cover-preview" src={f.cover_image} alt={f.cover_alt} />
            ) : (
              <p className="small muted">Shown on the blog, at the top of the post and when the link is shared on WhatsApp. A wide photo (1200 × 630 or larger) works best.</p>
            )}
            <div className="row">
              <button type="button" className="btn small" disabled={!!uploading} onClick={() => coverInput.current?.click()}>
                {uploading === "cover" ? "Uploading…" : f.cover_image ? "Change picture" : "Upload a picture"}
              </button>
              {f.cover_image ? (
                <button type="button" className="btn small ghost" onClick={() => setF((x) => ({ ...x, cover_image: "", cover_alt: "" }))}>
                  Remove
                </button>
              ) : null}
            </div>
            <input ref={coverInput} type="file" accept="image/jpeg,image/png,image/webp,image/heic" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0], "cover").finally(() => (e.target.value = ""))} />
            <div className="form" style={{ marginTop: 12 }}>
              <Field label="Describe the picture" hint="Read out to blind visitors and used by Google Images">
                <input maxLength={200} value={f.cover_alt} onChange={(e) => set("cover_alt", e.target.value)} />
              </Field>
            </div>
          </section>

          <section className="card">
            <h2>Search and sharing</h2>
            <div className="seo-preview" aria-label="How it may look on Google">
              <span className="small muted">greenplot.in › blog › {f.slug || "web-address"}</span>
              <b>{seoTitle}</b>
              <span className="small">{seoDescription}</span>
            </div>
            <div className="form">
              <Field label="Excerpt" hint="One or two sentences shown on the blog and under the link when shared">
                <textarea required rows={3} maxLength={320} value={f.excerpt} onChange={(e) => set("excerpt", e.target.value)} />
              </Field>
              <Counter value={f.excerpt} ideal={[70, 160]} />
              <Field label="Web address" hint={current?.state === "published" ? "Changing it breaks links people have already shared" : "greenplot.in/blog/…"}>
                <input
                  required
                  pattern="[a-z0-9]+(-[a-z0-9]+)*"
                  maxLength={100}
                  value={f.slug}
                  onChange={(e) => {
                    setSlugTouched(true);
                    set("slug", e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"));
                  }}
                />
              </Field>
              <Field label="Search title (optional)" hint="Replaces the title on Google; include Bangalore and the service">
                <input maxLength={70} value={f.seo_title} onChange={(e) => set("seo_title", e.target.value)} />
              </Field>
              <Counter value={f.seo_title || f.title} ideal={[30, 60]} />
              <Field label="Search description (optional)" hint="Replaces the excerpt on Google">
                <textarea rows={2} maxLength={170} value={f.seo_description} onChange={(e) => set("seo_description", e.target.value)} />
              </Field>
            </div>
          </section>

          <section className="card">
            <h2>Services to link</h2>
            <p className="small muted">Shown as cards under the post, so readers can see prices and book.</p>
            <div className="form">
              {SERVICES.map((s) => (
                <label key={s.slug} className="check">
                  <input
                    type="checkbox"
                    checked={f.services.includes(s.slug)}
                    onChange={(e) => set("services", e.target.checked ? [...f.services, s.slug] : f.services.filter((x) => x !== s.slug))}
                  />{" "}
                  {s.name}
                </label>
              ))}
            </div>
          </section>

          {current ? (
            <section className="card">
              <button type="button" className="btn small danger" disabled={act.pending} onClick={remove}>
                {confirmDelete ? "Tap again to delete for good" : "Delete this post"}
              </button>
            </section>
          ) : null}
        </aside>
      </div>
    </form>
  );
}
