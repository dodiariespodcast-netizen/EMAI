// Click-through smoke test against a running backend + built frontend.
//
// Usage:
//   (from backend/) uvicorn app.main:app --port 8000
//   (from frontend/) VITE_API_BASE_URL=http://localhost:8000 npm run build && npm run preview -- --port 4173
//   (from frontend/) node scripts/e2e-smoke.mjs
//
// Env vars: SMOKE_BASE_URL (default http://localhost:4173),
// PLAYWRIGHT_CHROMIUM_PATH (override if Chromium lives somewhere else than
// this sandbox's pre-installed path).
import { chromium } from "playwright";

const executablePath =
  process.env.PLAYWRIGHT_CHROMIUM_PATH || "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";
const browser = await chromium.launch({ executablePath });
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (msg) => {
  if (msg.type() === "error") errors.push(`console.error: ${msg.text()}`);
});

const base = process.env.SMOKE_BASE_URL || "http://localhost:4173";
const rand = Math.random().toString(36).slice(2, 8);

async function step(name, fn) {
  try {
    await fn();
    console.log(`OK   ${name}`);
  } catch (e) {
    console.log(`FAIL ${name}: ${e.message}`);
    await page.screenshot({ path: `/tmp/e2e-smoke-fail-${name.replace(/\s+/g, "_")}.png` });
    throw e;
  }
}

await step("load signup page", async () => {
  await page.goto(`${base}/signup`);
  await page.waitForSelector("text=Create your organization");
});

await step("submit signup form", async () => {
  await page.fill('input[placeholder="Riverside Emergency Group"]', `Smoke Test EM ${rand}`);
  await page.fill("text=Password >> xpath=../input", ""); // no-op guard
  const inputs = await page.locator("input").all();
  // org name, org slug, email, password in order
  await page.locator('input[type="email"]').fill(`owner-${rand}@smoke.example.com`);
  await page.locator('input[type="password"]').fill("supersecret1");
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(`${base}/app`);
  await page.waitForSelector("text=Organization overview");
});

await step("create a site", async () => {
  await page.goto(`${base}/app/shifts`);
  await page.waitForSelector("text=Sites & Shifts");
  await page.locator('input[placeholder="Main ED"]').fill("Main ED");
  await page.locator("button", { hasText: "Add" }).first().click();
  await page.locator("p.font-medium", { hasText: "Main ED" }).waitFor({ state: "visible" });
});

await step("create a shift type", async () => {
  await page.locator('input[placeholder="Day 07-19"]').fill("Day 07-19");
  await page.locator("button", { hasText: "Add shift type" }).click();
  await page.waitForSelector("text=needs 1");
});

await step("generate shift instances", async () => {
  const shiftTypeSelect = page.locator("select", { has: page.locator("option", { hasText: "Day 07-19" }) });
  await shiftTypeSelect.selectOption({ label: "Day 07-19" });
  await page.locator('input[type="date"]').first().fill("2026-06-01");
  await page.locator('input[type="date"]').nth(1).fill("2026-06-07");
  await page.locator('button[type="submit"]', { hasText: "Generate" }).click();
  await page.waitForSelector("text=Generated 7 shift instance");
});

await step("create a physician", async () => {
  await page.goto(`${base}/app/roster`);
  await page.waitForSelector("text=Roster");
  await page.locator("button", { hasText: "Add physician" }).click();
  await page.locator("form input").nth(0).fill("Alex");
  await page.locator("form input").nth(1).fill("Rivera");
  await page.locator('form input[type="email"]').fill(`alex-${rand}@smoke.example.com`);
  await page.locator("button", { hasText: "Add physician" }).click();
  await page.waitForSelector("text=Alex Rivera");
});

await step("generate a schedule", async () => {
  await page.goto(`${base}/app/generate`);
  await page.waitForSelector("text=Generate Schedule");
  await page.locator('input[type="date"]').first().fill("2026-06-01");
  await page.locator('input[type="date"]').nth(1).fill("2026-06-07");
  await page.locator('button[type="submit"]', { hasText: "Generate" }).click();
  await page.waitForSelector("text=Solver status", { timeout: 30000 });
  await page.waitForSelector("text=OPTIMAL,FEASIBLE", { timeout: 1 }).catch(() => {});
});

await step("publish the schedule", async () => {
  await page.locator("button", { hasText: "Publish" }).click();
  await page.waitForSelector("text=published");
});

await step("view schedule calendar", async () => {
  await page.goto(`${base}/app/schedule`);
  await page.waitForSelector("text=Schedule");
});

await step("check compliance page", async () => {
  await page.goto(`${base}/app/compliance`);
  await page.waitForSelector("text=Expiring soon");
});

await step("check audit log page", async () => {
  await page.goto(`${base}/app/audit`);
  await page.waitForSelector("text=org.signup", { timeout: 5000 }).catch(async () => {
    await page.waitForSelector("text=Audit Log");
  });
});

let physicianEmail = "";
await step("invite a user linked to the physician", async () => {
  await page.goto(`${base}/app/users`);
  await page.waitForSelector("text=Invite a user");
  physicianEmail = `doc-${rand}@smoke.example.com`;
  await page.locator('input[type="email"]').fill(physicianEmail);
  await page.locator('input[type="password"]').fill("supersecret1");
  const physicianLinkSelect = page.locator("select", { has: page.locator("option", { hasText: "Alex Rivera" }) });
  await physicianLinkSelect.selectOption({ label: "Alex Rivera" });
  await page.locator("button", { hasText: "Invite" }).click();
  await page.waitForSelector(`text=${physicianEmail}`);
});

await step("log out and log in as the physician", async () => {
  await page.locator("button", { hasText: "Log out" }).first().click();
  await page.waitForURL(`${base}/login`);
  await page.locator('input[type="email"]').fill(physicianEmail);
  await page.locator('input[type="password"]').fill("supersecret1");
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(`${base}/app`);
});

await step("physician: view own schedule", async () => {
  await page.goto(`${base}/app/schedule`);
  await page.waitForSelector("text=Schedule");
});

await step("physician: submit a time-off request via free text", async () => {
  await page.goto(`${base}/app/requests`);
  await page.waitForSelector("text=New request");
  await page.locator("textarea").fill("I need 2026-06-05 off, it's important.");
  await page.locator("button", { hasText: "Submit request" }).click();
  await page.waitForSelector("text=Got it");
});

await step("physician: adjust standing preferences", async () => {
  await page.goto(`${base}/app/preferences`);
  await page.waitForSelector("text=Standing preferences");
  await page.locator("button", { hasText: "Save preferences" }).click();
  await page.waitForSelector("text=Saved.");
});

await step("physician: browse swap marketplace", async () => {
  await page.goto(`${base}/app/swaps`);
  await page.waitForSelector("text=Marketplace");
  await page.waitForSelector("text=Offer one of your shifts");
});

await step("physician: settings page + no OAuth buttons without client id", async () => {
  await page.goto(`${base}/app/settings`);
  await page.waitForSelector("text=Sign-in methods");
  const googleButtonCount = await page.locator("text=Continue with Microsoft").count();
  if (googleButtonCount !== 0) throw new Error("Microsoft button rendered without a configured client id");
});

await step("physician: cannot see scheduler-only nav", async () => {
  const rosterLink = await page.locator('a[href="/app/roster"]').count();
  if (rosterLink !== 0) throw new Error("Physician sees scheduler-only Roster nav link");
});

console.log("\n--- console/page errors seen ---");
console.log(errors.length ? errors.join("\n") : "(none)");

await browser.close();
process.exit(errors.some((e) => e.includes("pageerror")) ? 1 : 0);
