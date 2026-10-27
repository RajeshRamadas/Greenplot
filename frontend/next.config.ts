import type { NextConfig } from "next";

const api = process.env.GREENPLOT_API_URL || "http://localhost:8000";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return {
      // The public marketing site (repository index.html) is served at "/".
      beforeFiles: [{ source: "/", destination: "/index.html" }],
      afterFiles: [{ source: "/api/v1/:path*", destination: `${api}/api/v1/:path*` }],
      fallback: [],
    };
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(self), geolocation=(self), microphone=()" },
          // No other site may show our pages inside a frame (stops click-tricking on the sign-in and office pages).
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'; base-uri 'self'; object-src 'none'" },
          // Browsers only accept this over HTTPS, so it does nothing on a local http:// setup.
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        ],
      },
      // Sign-in, invite and job proof pages are client pages that cannot set metadata, so keep them out of search here.
      ...["/login", "/register", "/forgot-password", "/accept-invite", "/proof/:path*"].map((source) => ({
        source,
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      })),
      // Website pictures keep their names when replaced, so browsers reuse them for a day and refresh them in the background after that.
      ...["/showcase/:path*", "/site/:path*", "/store/:path*", "/og/:path*", "/icons/:path*"].map((source) => ({
        source,
        headers: [{ key: "Cache-Control", value: "public, max-age=86400, stale-while-revalidate=604800" }],
      })),
      { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache" }, { key: "Service-Worker-Allowed", value: "/" }] },
    ];
  },
};

export default config;
