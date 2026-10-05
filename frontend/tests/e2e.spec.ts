import { expect, test, type Page } from "@playwright/test";

/** End-to-end smoke tests against the seeded demo layout (python -m app.seed). */

const PASSWORD = "GreenPlot@2026";
const JPEG = Buffer.from(
  "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=",
  "base64",
);

async function login(page: Page, email: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

function watchErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("response", (r) => {
    if (r.url().includes("/api/v1/") && r.status() >= 500) errors.push(`${r.status()} ${r.url()}`);
  });
  return errors;
}

test("public website loads with the WhatsApp contact", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1")).toContainText("Manage your property");
  await expect(page.locator('a[href^="https://wa.me/918105568225"]').first()).toBeVisible();
  await expect(page.getByRole("heading", { name: "Every maintenance task. Documented and verified." })).toBeVisible();
  await page.locator("#demoForm input[name=name]").fill("E2E Secretary");
  await page.locator("#demoForm input[name=phone]").fill("+91 98450 22222");
  await page.locator("#demoForm input[name=layout_name]").fill("E2E Layout");
  await page.locator("#demoForm button[type=submit]").click();
  await expect(page.locator(".demoStatus")).toContainText("Thank you");
});

const ROLES: [string, string[]][] = [
  ["admin@greenvalley.example", ["/dashboard", "/tickets", "/maintenance", "/approvals", "/gardening", "/inspections", "/complaints", "/properties", "/assets", "/staff", "/vendors", "/visitors", "/vehicles", "/patrol", "/incidents", "/billing", "/notices", "/records", "/reports", "/audit", "/settings"]],
  ["supervisor@greenvalley.example", ["/dashboard", "/tickets", "/approvals", "/maintenance", "/my-tasks", "/scan"]],
  ["staff@greenvalley.example", ["/my-tasks", "/tickets", "/scan", "/attendance", "/offline"]],
  ["vendor@greenvalley.example", ["/tickets", "/my-tasks", "/maintenance"]],
  ["guard@greenvalley.example", ["/dashboard", "/visitors", "/vehicles", "/patrol", "/incidents"]],
  ["resident@greenvalley.example", ["/dashboard", "/tickets", "/my-property", "/inspections", "/maintenance", "/visitors", "/billing", "/notices", "/sos"]],
  ["platform@greenplot.in", ["/tenants"]],
];

for (const [email, paths] of ROLES) {
  test(`every page renders for ${email.split("@")[0]}`, async ({ page }) => {
    const errors = watchErrors(page);
    await login(page, email);
    for (const p of paths) {
      await page.goto(p);
      await expect(page.locator("h1").first()).toBeVisible();
      await expect(page.locator(".alert.error")).toHaveCount(0);
    }
    expect(errors).toEqual([]);
  });
}

test("worker captures proof of work and supervisor approves", async ({ browser }) => {
  // Supervisor creates and assigns a cleaning job.
  const sup = await browser.newPage();
  const errors = watchErrors(sup);
  await login(sup, "supervisor@greenvalley.example");
  await sup.goto("/maintenance");
  await sup.getByRole("button", { name: "New task" }).click();
  const title = `E2E clean ${Date.now()}`;
  const dialog = sup.getByRole("dialog");
  await dialog.getByLabel("Title").fill(title);
  await dialog.getByLabel("Assign staff").selectOption({ label: "Ramesh Kumar" });
  await dialog.getByLabel("Custom checklist (one item per line)").fill("Weeds removed\nDebris bagged");
  await dialog.getByRole("button", { name: "Create task" }).click();
  await sup.waitForURL(/\/maintenance\/[0-9a-f-]+$/);
  const taskUrl = sup.url();

  // Staff does the work on a phone-sized screen.
  const field = await browser.newContext({ permissions: ["geolocation"], geolocation: { latitude: 12.9141, longitude: 77.6387, accuracy: 8 } });
  const staff = await field.newPage();
  errors.push(...watchErrors(staff));
  await login(staff, "staff@greenvalley.example");
  await staff.goto(taskUrl);
  await staff.getByRole("button", { name: "Accept task" }).click();
  await staff.getByRole("button", { name: "Start work" }).click();
  await expect(staff.getByRole("button", { name: "Submit for review" })).toBeVisible();

  // Submitting without proof is blocked with a clear message.
  await staff.getByRole("button", { name: "Submit for review" }).click();
  await expect(staff.locator(".alert.error")).toContainText("Required proof of work is missing");

  for (const item of ["Weeds removed", "Debris bagged"]) {
    await staff.getByRole("group", { name: `Result for ${item}` }).getByRole("button", { name: "✓ Done" }).click();
  }
  const [chooser] = await Promise.all([staff.waitForEvent("filechooser"), staff.getByRole("button", { name: "After photo" }).click()]);
  await chooser.setFiles({ name: "after.jpg", mimeType: "image/jpeg", buffer: JPEG });
  await expect(staff.locator(".evidence-tile")).toHaveCount(1);
  await staff.getByRole("button", { name: "Edit" }).click();
  await staff.getByLabel("Work performed").fill("Cleared all weeds and bagged debris.");
  await staff.getByRole("button", { name: "Save notes" }).click();
  await staff.getByRole("button", { name: "Submit for review" }).click();
  await expect(staff.getByText("Submitted — waiting for supervisor review.")).toBeVisible();

  // Supervisor verifies and approves.
  await sup.goto(taskUrl);
  await sup.getByRole("button", { name: "Approve" }).first().click();
  await sup.getByRole("dialog").getByLabel("Comment (optional)").fill("Checked on site");
  await sup.getByRole("dialog").getByRole("button", { name: "Approve" }).click();
  await expect(sup.locator(".badge").filter({ hasText: "Closed" }).first()).toBeVisible();
  await expect(sup.getByText("Proof report (PDF)")).toBeVisible();
  await expect(sup.locator(".timeline").last()).toContainText("Approve");

  // It is searchable as a digital record.
  await sup.goto("/records");
  await sup.getByPlaceholder(/gate repairs/).fill(title);
  await sup.getByRole("button", { name: "Search" }).click();
  await expect(sup.getByText(title)).toBeVisible();
  expect(errors).toEqual([]);
});

test("customer ticket reaches the vendor, returns to the office and closes with a customer notification", async ({ browser }) => {
  // Resident raises a ticket from the portal.
  const res = await browser.newPage();
  const errors = watchErrors(res);
  await login(res, "resident@greenvalley.example");
  await res.goto("/tickets");
  await res.getByRole("button", { name: "Raise ticket" }).click();
  const d = res.getByRole("dialog");
  await d.getByLabel("Category").selectOption({ label: "Plumbing" });
  await d.getByLabel("Type of issue").selectOption("Leak");
  const title = `E2E leak ${Date.now()}`;
  await d.getByLabel("What's the problem?").fill(title);
  await d.getByLabel("Description").fill("Water pooling next to the gate");
  await d.getByRole("button", { name: "Submit ticket" }).click();
  await expect(d.getByText(/GP-TKT-\d{4}-\d{6}/).first()).toBeVisible();
  await d.getByRole("button", { name: "Track ticket" }).click();
  await res.waitForURL(/\/tickets\/[0-9a-f-]+$/);
  const url = res.url();

  // Office assigns it to the vendor.
  const admin = await browser.newPage();
  errors.push(...watchErrors(admin));
  await login(admin, "admin@greenvalley.example");
  await admin.goto(url);
  await admin.getByRole("button", { name: "Assign", exact: true }).click();
  await admin.getByRole("dialog").getByLabel("Vendor").selectOption({ label: "FixIt Gates & Fabrication" });
  await admin.getByRole("dialog").getByRole("button", { name: "Assign", exact: true }).click();
  await expect(admin.locator(".badge").filter({ hasText: "Assigned" }).first()).toBeVisible();

  // The vendor sees it, accepts, then hands it back with a reason.
  const vendor = await browser.newPage();
  errors.push(...watchErrors(vendor));
  await login(vendor, "vendor@greenvalley.example");
  await vendor.goto("/tickets");
  await vendor.getByText(title).click();
  await vendor.getByRole("button", { name: "Accept job" }).click();
  await expect(vendor.locator(".badge").filter({ hasText: "Accepted" }).first()).toBeVisible();
  await res.reload();
  await expect(res.locator(".timeline")).toContainText("Accepted by the assignee");
  await vendor.getByRole("button", { name: "Reject assignment" }).click();
  await vendor.getByRole("dialog").getByLabel("Reason").selectOption("wrong_category");
  await vendor.getByRole("dialog").getByLabel("Details").fill("Plumbing is not our trade");
  await vendor.getByRole("dialog").getByRole("button", { name: "Reject assignment" }).click();
  await vendor.waitForURL(/\/tickets$/);

  // The office resolves and closes it; the resident is notified.
  await admin.reload();
  await expect(admin.locator(".timeline")).toContainText("declined");
  await admin.getByRole("button", { name: "Resolve" }).click();
  await admin.getByRole("dialog").getByRole("textbox").fill("Valve tightened by the layout plumber.");
  await admin.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
  await admin.getByRole("button", { name: "Close ticket" }).click();
  await expect(admin.locator(".badge").filter({ hasText: "Closed" }).first()).toBeVisible();

  await res.goto("/notifications");
  await expect(res.getByText("GreenPlot Ticket Closed").first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("guard registers a visitor while offline and it syncs", async ({ page, context }) => {
  await login(page, "guard@greenvalley.example");
  await page.goto("/visitors");
  await context.setOffline(true);
  await page.getByRole("button", { name: "Register visitor" }).click();
  const name = `Offline Visitor ${Date.now() % 100000}`;
  await page.getByRole("dialog").getByLabel("Visitor name").fill(name);
  await page.getByRole("dialog").getByLabel("Purpose").fill("Delivery");
  await page.getByRole("dialog").getByRole("button", { name: "Register" }).click();
  await expect(page.getByText("Saved offline")).toBeVisible();
  await page.goto("/offline").catch(() => {});
  await context.setOffline(false);
  await page.goto("/offline");
  await page.getByRole("button", { name: "Sync now" }).click();
  await expect(page.locator(".list-item").filter({ hasText: name }).locator(".badge")).toHaveText(/Synced/, { timeout: 15_000 });
  await page.goto("/visitors");
  await expect(page.getByText(name)).toBeVisible();
});
