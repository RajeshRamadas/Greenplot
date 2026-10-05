import { defineConfig } from "@playwright/test";

// Expects the API (seeded with `python -m app.seed`) and `next start` to be running.
export default defineConfig({
  testDir: "tests",
  timeout: 60_000,
  workers: 1,
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:3000",
    viewport: { width: 412, height: 915 },
    launchOptions: process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
    trace: "retain-on-failure",
  },
});
