// Copies the public marketing page (repository root index.html) into public/ so Next serves it at "/".
import { copyFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "..", "index.html");
const dest = join(here, "..", "public", "index.html");
if (existsSync(src)) {
  copyFileSync(src, dest);
  console.log("synced marketing site -> public/index.html");
} else if (!existsSync(dest)) {
  console.warn("index.html not found; the marketing page will be missing");
}
