import Link from "next/link";
import { Fragment, type ReactNode } from "react";
import { fillTokens, slugify } from "@/lib/blog";
import { BUSINESS } from "@/lib/legal";

/**
 * The small Markdown used by blog posts, turned into React elements (never raw HTML, so a post
 * cannot inject scripts). Blocks: ## and ### headings, paragraphs, - and 1. lists, > quotes,
 * a picture on its own line (![alt](src "caption")), --- rules, and [[cta]] for a WhatsApp box.
 * Inline: **bold**, *italic*, [links](/path) and {{price}} tokens (lib/blog.ts).
 */

type Block =
  | { kind: "h2" | "h3"; text: string; id: string }
  | { kind: "p" | "quote"; text: string }
  | { kind: "ul" | "ol"; items: string[] }
  | { kind: "img"; alt: string; src: string; caption?: string }
  | { kind: "hr" | "cta" };

const IMAGE = /^!\[([^\]]*)\]\(\s*(\S+?)(?:\s+"([^"]*)")?\s*\)$/;

export function parse(md: string): Block[] {
  const blocks: Block[] = [];
  const ids = new Map<string, number>();
  const uniqueId = (text: string) => {
    const base = slugify(text) || "section";
    const n = ids.get(base) ?? 0;
    ids.set(base, n + 1);
    return n ? `${base}-${n + 1}` : base;
  };
  let para: string[] = [];
  let list: { kind: "ul" | "ol"; items: string[] } | null = null;
  let quote: string[] = [];
  const flush = () => {
    if (para.length) blocks.push({ kind: "p", text: para.join(" ") });
    if (list) blocks.push(list);
    if (quote.length) blocks.push({ kind: "quote", text: quote.join(" ") });
    para = [];
    list = null;
    quote = [];
  };
  for (const raw of md.replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.trim();
    let m: RegExpMatchArray | null;
    if (!line) {
      flush();
    } else if ((m = line.match(/^(#{1,3})\s+(.+)$/))) {
      flush();
      const text = m[2].replace(/\s+#+$/, "");
      blocks.push({ kind: m[1].length === 3 ? "h3" : "h2", text, id: uniqueId(text) });
    } else if (/^(-{3,}|\*{3,})$/.test(line)) {
      flush();
      blocks.push({ kind: "hr" });
    } else if (/^\[\[\s*cta\s*\]\]$/i.test(line)) {
      flush();
      blocks.push({ kind: "cta" });
    } else if ((m = line.match(IMAGE))) {
      flush();
      blocks.push({ kind: "img", alt: m[1], src: m[2], caption: m[3] });
    } else if ((m = line.match(/^[-*+]\s+(.+)$/)) || (m = line.match(/^\d+[.)]\s+(.+)$/))) {
      const kind = /^\d/.test(line) ? "ol" : "ul";
      if (para.length || quote.length || (list && list.kind !== kind)) flush();
      list ??= { kind, items: [] };
      list.items.push(m[1]);
    } else if ((m = line.match(/^>\s?(.*)$/))) {
      if (para.length || list) flush();
      quote.push(m[1]);
    } else if (list && /^\s{2,}/.test(raw)) {
      list.items[list.items.length - 1] += ` ${line}`; // an indented line continues the list item
    } else {
      if (list || quote.length) flush();
      para.push(line);
    }
  }
  flush();
  return blocks;
}

/** Links may go to pages on this site, https sites, WhatsApp, email or phone; anything else is shown as text. */
export function safeHref(href: string): string | null {
  const h = href.trim();
  if (/^\/(?!\/)/.test(h) || h.startsWith("#")) return h;
  if (/^(https?:\/\/|mailto:|tel:)/i.test(h)) return h;
  return null;
}

export function safeSrc(src: string): string | null {
  const s = src.trim();
  return /^\/(?!\/)/.test(s) || /^https:\/\//i.test(s) ? s : null;
}

const INLINE = /\*\*(.+?)\*\*|(?<!\w)__(.+?)__(?!\w)|\*(.+?)\*|(?<!\w)_(.+?)_(?!\w)|\[([^\]]+)\]\(\s*([^)\s]+)\s*\)/;

export function Inline({ text }: { text: string }): ReactNode {
  const out: ReactNode[] = [];
  let rest = fillTokens(text);
  let key = 0;
  while (rest) {
    const m = rest.match(INLINE);
    if (!m || m.index === undefined) {
      out.push(rest);
      break;
    }
    if (m.index) out.push(rest.slice(0, m.index));
    const k = key++;
    if (m[1] ?? m[2]) {
      out.push(
        <strong key={k}>
          <Inline text={(m[1] ?? m[2]) as string} />
        </strong>,
      );
    } else if (m[3] ?? m[4]) {
      out.push(
        <em key={k}>
          <Inline text={(m[3] ?? m[4]) as string} />
        </em>,
      );
    } else {
      const href = safeHref(m[6]);
      const label = <Inline text={m[5]} />;
      if (!href) out.push(<Fragment key={k}>{label}</Fragment>);
      else if (href.startsWith("/"))
        out.push(
          <Link key={k} href={href}>
            {label}
          </Link>,
        );
      else
        out.push(
          <a key={k} href={href} {...(/^https?:/i.test(href) ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
            {label}
          </a>,
        );
    }
    rest = rest.slice(m.index + m[0].length);
  }
  return <>{out}</>;
}

const WHATSAPP = `https://wa.me/${BUSINESS.phone.replace(/\D/g, "")}`;

function Cta() {
  return (
    <aside className="post-cta">
      <div>
        <b>Want us to look after your plot?</b>
        <span>Send your plot location on WhatsApp and get a price the same day, with photos after every visit.</span>
      </div>
      <a href={`${WHATSAPP}?text=${encodeURIComponent("Hi GreenPlot, I read your guide and would like a price for my plot.")}`} className="btn primary" target="_blank" rel="noopener noreferrer">
        WhatsApp us
      </a>
    </aside>
  );
}

export function Markdown({ source }: { source: string }) {
  return (
    <>
      {parse(source).map((b, i) => {
        switch (b.kind) {
          case "h2":
            return (
              <h2 key={i} id={b.id}>
                <Inline text={b.text} />
              </h2>
            );
          case "h3":
            return (
              <h3 key={i} id={b.id}>
                <Inline text={b.text} />
              </h3>
            );
          case "p":
            return (
              <p key={i}>
                <Inline text={b.text} />
              </p>
            );
          case "quote":
            return (
              <blockquote key={i}>
                <Inline text={b.text} />
              </blockquote>
            );
          case "ul":
          case "ol": {
            const Tag = b.kind;
            return (
              <Tag key={i}>
                {b.items.map((t, j) => (
                  <li key={j}>
                    <Inline text={t} />
                  </li>
                ))}
              </Tag>
            );
          }
          case "img": {
            const src = safeSrc(b.src);
            return src ? (
              <figure key={i} className="post-figure">
                {/* eslint-disable-next-line @next/next/no-img-element -- pictures can come from the API or another https site */}
                <img src={src} alt={b.alt} loading="lazy" decoding="async" />
                {b.caption ? <figcaption>{b.caption}</figcaption> : null}
              </figure>
            ) : null;
          }
          case "hr":
            return <hr key={i} />;
          case "cta":
            return <Cta key={i} />;
        }
      })}
    </>
  );
}

/** The post's ## headings, for its table of contents. */
export const outline = (source: string) => parse(source).flatMap((b) => (b.kind === "h2" ? [{ id: b.id, text: fillTokens(b.text).replace(/[*_]/g, "") }] : []));
