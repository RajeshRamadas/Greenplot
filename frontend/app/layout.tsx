import type { Metadata, Viewport } from "next";
import "./globals.css";
import Providers from "./providers";

export const metadata: Metadata = {
  title: { default: "GreenPlot", template: "%s · GreenPlot" },
  description: "Property Management Made Simple — maintenance, security, inspections and digital records for residential layouts.",
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
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
