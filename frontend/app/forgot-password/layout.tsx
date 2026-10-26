import type { Metadata } from "next";

// The page is a client page, so its title is set here; the X-Robots-Tag header keeps it out of search results.
export const metadata: Metadata = { title: "Reset your password", description: "Reset your GreenPlot password." };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
