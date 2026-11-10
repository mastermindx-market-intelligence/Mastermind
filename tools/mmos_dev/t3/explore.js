#!/usr/bin/env node
// Dump the signed-in client's landing state: URL, aria snapshot, and link
// hrefs, to discover onboarding/thread-flow selectors. No secrets involved.
const path = require("path");
const { chromium } = require(path.join(
  process.env.HOME,
  ".mastermind/mmos-dev/t3/tooling/node_modules/playwright-core",
));
const BASE = process.argv[2] || "http://127.0.0.1:3790";
const EXEC = path.join(
  process.env.HOME,
  "Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
);
(async () => {
  const context = await chromium.launchPersistentContext(
    path.join(process.env.HOME, ".mastermind/mmos-dev/t3/browser-profile"),
    { headless: true, executablePath: EXEC },
  );
  const page = context.pages()[0] || (await context.newPage());
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForLoadState("networkidle", { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(1500);
  // Close onboarding dialog if present
  for (const label of ["Close", "Skip"]) {
    const btn = page.getByRole("button", { name: label, exact: true });
    if (await btn.count()) {
      await btn.first().click().catch(() => {});
      await page.waitForTimeout(800);
    }
  }
  console.log("URL:", page.url());
  const links = await page.evaluate(() =>
    Array.from(document.querySelectorAll("a[href]"))
      .map((a) => a.getAttribute("href"))
      .filter((h) => h && h.startsWith("/")),
  );
  console.log("LINKS:", JSON.stringify([...new Set(links)].slice(0, 25)));
  const buttons = await page.evaluate(() =>
    Array.from(document.querySelectorAll("button"))
      .map((b) => (b.getAttribute("aria-label") || b.textContent || "").trim())
      .filter(Boolean),
  );
  console.log("BUTTONS:", JSON.stringify([...new Set(buttons)].slice(0, 40)));
  const aria = await page.locator("body").ariaSnapshot();
  console.log("ARIA_FIRST_80_LINES:\n" + aria.split("\n").slice(0, 80).join("\n"));
  await context.close();
})().catch((e) => {
  console.error("EXPLORE_FAILED", e.message);
  process.exit(1);
});
