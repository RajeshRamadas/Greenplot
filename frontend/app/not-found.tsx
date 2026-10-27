import type { Metadata } from "next";
import Link from "next/link";
import { LegalLinks } from "@/components/Legal";

export const metadata: Metadata = { title: "Page not found", robots: { index: false } };

export default function NotFound() {
  return (
    <div className="legal-page">
      <header className="legal-head">
        <a href="/" className="legal-brand" aria-label="GreenPlot home">
          <span>Green</span>Plot
        </a>
        <Link href="/login" className="btn small ghost">
          Login
        </Link>
      </header>
      <main className="legal-body card">
        <h1>Page not found</h1>
        <p>This page has moved or never existed. These may help:</p>
        <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
          <a href="/" className="btn primary">
            Home
          </a>
          <Link href="/services" className="btn">
            Services and prices
          </Link>
          <Link href="/store" className="btn">
            Plant store
          </Link>
          <Link href="/blog" className="btn">
            Guides
          </Link>
        </div>
      </main>
      <LegalLinks />
    </div>
  );
}
