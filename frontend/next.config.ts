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
        ],
      },
      { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache" }, { key: "Service-Worker-Allowed", value: "/" }] },
    ];
  },
};

export default config;
