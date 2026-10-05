// Screenshot a page at desktop and phone widths: node scripts/shot.mjs <file-or-url> <out-prefix>
import { chromium } from "@playwright/test";
const [, , target, out] = process.argv;
const url = target.startsWith("http") ? target : `file://${target}`;
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH });
for (const [name, width] of [["desktop", 1366], ["phone", 390]]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.goto(url, { waitUntil: "load" });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  await page.screenshot({ path: `${out}-${name}.png`, fullPage: true });
  console.log(name, "horizontal overflow px:", overflow);
  await page.close();
}
await browser.close();
