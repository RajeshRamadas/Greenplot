// Copies the public marketing page (repository root index.html) into public/ so Next serves it at "/".
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "..", "index.html");
const dest = join(here, "..", "public", "index.html");
if (existsSync(src)) {
  // index.html names https://greenplot.in in its canonical, share tags and structured data; point them at the real domain.
  const site = (process.env.NEXT_PUBLIC_SITE_URL || "").replace(/\/$/, "");
  const html = readFileSync(src, "utf8");
  writeFileSync(dest, site ? html.replaceAll("https://greenplot.in", site) : html);
  console.log("synced marketing site -> public/index.html");
} else if (!existsSync(dest)) {
  console.warn("index.html not found; the marketing page will be missing");
}
