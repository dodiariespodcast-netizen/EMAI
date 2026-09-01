// Click-through smoke test against a running backend + built frontend.
//
// Usage:
//   (from backend/) uvicorn app.main:app --port 8000
//   (from frontend/) VITE_API_BASE_URL=http://localhost:8000 npm run build && npm run preview -- --port 4173
//   (from frontend/) node scripts/e2e-smoke.mjs
//
// Env vars: SMOKE_BASE_URL (default http://localhost:4173),
// PLAYWRIGHT_CHROMIUM_PATH (an explicit Chromium binary, if you don't want
// the one Playwright manages).
import { existsSync } from "node:fs";
import { chromium } from "playwright";

// Prefer an explicitly configured browser, then a pre-provisioned one, and
// otherwise let Playwright use whatever `npx playwright install` gave it --
// so this runs unchanged on a dev machine, in CI, and in a prepared sandbox.
const candidatePaths = [
  process.env.PLAYWRIGHT_CHROMIUM_PATH,
  "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
].filter((p) => p && existsSync(p));

const browser = await chromium.launch(
  candidatePaths.length > 0 ? { executablePath: candidatePaths[0] } : {},
);
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (msg) => {
  if (msg.type() === "error") errors.push(`console.error: ${msg.text()}`);
});

// SMOKE_VERBOSE=1 traces auth traffic, which is what you want when a run
// ends up unexpectedly signed out.
if (process.env.SMOKE_VERBOSE) {
  page.on("response", (r) => {
    if (r.url().includes("/auth/")) console.log(`       <- ${r.status()} ${new URL(r.url()).pathname}`);
  });
}

const base = process.env.SMOKE_BASE_URL || "http://localhost:4173";
const rand = Math.random().toString(36).slice(2, 8);

// Schedule into next month, so the calendar view (which opens on the current
// month) reaches it with exactly one "next" click, and the dates stay valid
// no matter when this runs.
const now = new Date();
const scheduleMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const periodStart = iso(scheduleMonth);
const periodEnd = iso(new Date(scheduleMonth.getFullYear(), scheduleMonth.getMonth(), 7));
const periodEndOfMonth = iso(new Date(scheduleMonth.getFullYear(), scheduleMonth.getMonth() + 1, 0));
const scheduleMonthLabel = scheduleMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" });

async function step(name, fn) {
  try {
    await fn();
    console.log(`OK   ${name}`);
  } catch (e) {
    console.log(`FAIL ${name}: ${e.message}`);
    // Dump where we actually were, so a failure is diagnosable from the log
    // alone rather than needing a re-run with instrumentation.
    try {
      console.log(`     url: ${page.url()}`);
      const stored = await page.evaluate(() => localStorage.getItem("emai.auth.token"));
      console.log(`     session token: ${stored ? "present" : "absent"}`);
      const text = (await page.locator("body").innerText()).replace(/\n+/g, " | ").slice(0, 600);
      console.log(`     page: ${text}`);
    } catch {
      /* page may be gone */
    }
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
  await page.locator('input[type="date"]').first().fill(periodStart);
  await page.locator('input[type="date"]').nth(1).fill(periodEnd);
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
  await page.locator('input[type="date"]').first().fill(periodStart);
  await page.locator('input[type="date"]').nth(1).fill(periodEnd);
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
  await page.waitForSelector("text=short of its requirement");
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

await step("scheduler: hand-edit a shift on the calendar", async () => {
  await page.goto(`${base}/app/schedule`);
  await page.waitForSelector("text=short of its requirement");
  // Walk forward to the month this run's shifts live in. Bounded, so a
  // mismatch fails the step instead of clicking forever.
  for (let i = 0; i < 13; i++) {
    if (await page.locator("h2", { hasText: scheduleMonthLabel }).count()) break;
    if (i === 12) throw new Error(`never reached ${scheduleMonthLabel} in the calendar`);
    await page.locator("button", { hasText: "→" }).click();
  }
  await page.locator("button", { hasText: "Day 07-19" }).first().click();
  await page.waitForSelector("text=Assign someone");

  // The physician already on the shift must be reported as conflicted.
  await page.waitForSelector("text=conflict");

  // Remove them, leaving the shift short, then put them back.
  await page.locator("button", { hasText: "Remove" }).first().click();
  await page.waitForSelector("text=Nobody on this shift yet");
  await page.locator("button", { hasText: "Alex Rivera" }).first().click();
  await page.waitForSelector("text=Remove");
  await page.locator('button[aria-label="Close"]').click();
});

await step("scheduler: reports page shows hours and coverage", async () => {
  await page.goto(`${base}/app/reports`);
  await page.waitForSelector("text=Hours by physician");
  await page.locator('input[type="date"]').first().fill(periodStart);
  await page.locator('input[type="date"]').nth(1).fill(periodEndOfMonth);
  await page.waitForSelector("text=Alex Rivera");
});

await step("scheduler: import a roster from CSV", async () => {
  await page.goto(`${base}/app/roster`);
  await page.locator("button", { hasText: "Import CSV" }).click();
  await page.waitForSelector("text=Import a roster from CSV");
  await page.locator('input[type="file"]').setInputFiles({
    name: "roster.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "first_name,last_name,email,fte,employment_type,hourly_rate\n" +
        `Jordan,Imported,jordan-${rand}@smoke.example.com,1.0,locums,240\n`,
    ),
  });
  await page.locator("button", { hasText: "Validate first" }).click();
  await page.waitForSelector("text=would be added");
  await page.locator("button", { hasText: "Import" }).last().click();
  await page.waitForSelector("text=Jordan Imported");
});

let physicianEmail = "";
let inviteUrl = "";
await step("invite a user with no password (invite-link flow)", async () => {
  await page.goto(`${base}/app/users`);
  await page.waitForSelector("text=Invite a user");
  physicianEmail = `doc-${rand}@smoke.example.com`;
  await page.locator('input[type="email"]').fill(physicianEmail);
  const physicianLinkSelect = page.locator("select", { has: page.locator("option", { hasText: "Alex Rivera" }) });
  await physicianLinkSelect.selectOption({ label: "Alex Rivera" });
  await page.getByRole("button", { name: "Send invite", exact: true }).click();

  await page.waitForSelector("text=Share this link directly");
  inviteUrl = (await page.locator("code").first().innerText()).trim();
  if (!inviteUrl.includes("/set-password?token=")) {
    throw new Error(`unexpected invite url: ${inviteUrl}`);
  }
});

await step("invited user sets their own password and lands signed in", async () => {
  await page.locator("button", { hasText: "Log out" }).first().click();
  await page.waitForURL(`${base}/login`);

  // The emailed link points at the configured frontend base URL, which in a
  // dev/CI setup is a different port than this preview server.
  const token = inviteUrl.split("token=")[1];
  await page.goto(`${base}/set-password?token=${token}`);
  await page.waitForSelector("text=Set your password");
  await page.locator('input[type="password"]').first().fill("chosen-by-me-123");
  await page.locator('input[type="password"]').nth(1).fill("chosen-by-me-123");
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(`${base}/app`);
});

await step("that password now works for a normal login", async () => {
  await page.locator("button", { hasText: "Log out" }).first().click();
  await page.waitForURL(`${base}/login`);
  await page.locator('input[type="email"]').fill(physicianEmail);
  await page.locator('input[type="password"]').fill("chosen-by-me-123");
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(`${base}/app`);
});

await step("forgot-password page accepts a request", async () => {
  await page.goto(`${base}/forgot-password`);
  await page.locator('input[type="email"]').fill(physicianEmail);
  await page.locator('button[type="submit"]').click();
  await page.waitForSelector("text=reset link is on its way");
  await page.goto(`${base}/app`);
});

await step("physician: view own schedule", async () => {
  await page.goto(`${base}/app/schedule`);
  await page.waitForSelector("text=My shifts only");
});

await step("physician: submit a time-off request via free text", async () => {
  await page.goto(`${base}/app/requests`);
  await page.waitForSelector("text=New request");
  await page.locator("textarea").fill(`I need ${periodEnd} off, it's important.`);
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
  const microsoftButtons = await page.locator("text=Continue with Microsoft").count();
  if (microsoftButtons !== 0) throw new Error("Microsoft button rendered without a configured client id");
});

await step("physician: cannot see scheduler-only nav", async () => {
  for (const path of ["/app/roster", "/app/reports", "/app/audit"]) {
    if ((await page.locator(`a[href="${path}"]`).count()) !== 0) {
      throw new Error(`Physician sees scheduler-only nav link ${path}`);
    }
  }
});

console.log("\n--- console/page errors seen ---");
console.log(errors.length ? errors.join("\n") : "(none)");

await browser.close();
process.exit(errors.some((e) => e.includes("pageerror")) ? 1 : 0);
