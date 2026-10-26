import type { Metadata, Viewport } from "next";
import "./globals.css";
import { WhatsAppButton } from "@/components/Support";
import { SHARE_IMAGE, SITE_URL } from "@/lib/site";
import Providers from "./providers";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: "GreenPlot", template: "%s · GreenPlot" },
  description: "Plot cleaning, fencing, garden upkeep and inspections for plots and layouts in Bangalore, with photo proof of every visit.",
  openGraph: { type: "website", siteName: "GreenPlot", locale: "en_IN", images: [SHARE_IMAGE] },
  twitter: { card: "summary_large_image" },
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icons/icon.svg", apple: "/icons/icon-192.png" },
  appleWebApp: { capable: true, title: "GreenPlot", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: "#159a63",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-IN">
      <body>
        <Providers>
          {children}
          <WhatsAppButton />
        </Providers>
      </body>
    </html>
  );
}
