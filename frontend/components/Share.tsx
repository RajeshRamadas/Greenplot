"use client";

import { useEffect, useState } from "react";

/** Share a post on WhatsApp, Facebook, X or LinkedIn, or copy its link. Phones get their own share sheet too. */
export function ShareButtons({ url, title }: { url: string; title: string }) {
  const [copied, setCopied] = useState(false);
  const [native, setNative] = useState(false);
  useEffect(() => setNative(typeof navigator !== "undefined" && typeof navigator.share === "function"), []);
  const u = encodeURIComponent(url);
  const t = encodeURIComponent(title);
  const links = [
    { name: "WhatsApp", href: `https://wa.me/?text=${encodeURIComponent(`${title} ${url}`)}` },
    { name: "Facebook", href: `https://www.facebook.com/sharer/sharer.php?u=${u}` },
    { name: "X", href: `https://twitter.com/intent/tweet?url=${u}&text=${t}` },
    { name: "LinkedIn", href: `https://www.linkedin.com/sharing/share-offsite/?url=${u}` },
  ];
  return (
    <div className="share" aria-label="Share this guide">
      <span className="muted small">Share</span>
      {links.map((l) => (
        <a key={l.name} className="btn small ghost" href={l.href} target="_blank" rel="noopener noreferrer">
          {l.name}
        </a>
      ))}
      <button
        type="button"
        className="btn small ghost"
        onClick={async () => {
          const ok = await navigator.clipboard?.writeText(url).then(
            () => true,
            () => false,
          );
          setCopied(!!ok);
          if (ok) setTimeout(() => setCopied(false), 2000);
        }}
      >
        {copied ? "Link copied" : "Copy link"}
      </button>
      {native ? (
        <button type="button" className="btn small ghost" onClick={() => navigator.share({ title, url }).catch(() => undefined)}>
          More…
        </button>
      ) : null}
    </div>
  );
}
