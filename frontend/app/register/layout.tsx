import type { Metadata } from "next";

// The page is a client page, so its title is set here; the X-Robots-Tag header keeps it out of search results.
export const metadata: Metadata = { title: "Request access", description: "Ask your layout office for a GreenPlot account." };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
