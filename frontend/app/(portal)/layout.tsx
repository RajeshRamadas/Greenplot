import type { Metadata } from "next";
import AppShell from "@/components/AppShell";

// Signed-in pages are private and should never appear in search results.
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
