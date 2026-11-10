#!/usr/bin/env node
// Sign a headless Chromium into the dev T3 server through the supported
// one-time-token pairing path, persisting the profile. Never prints or stores
// the token: the pairing URL is read from the 0600 access file, its hash is
// used once in the browser and stripped from every recorded artifact.
// Usage: node signin.js <access.txt> <profileDir> <outDir> [executablePath]
const fs = require("fs");
const path = require("path");
const { chromium } = require(path.join(
  process.env.HOME,
  ".mastermind/mmos-dev/t3/tooling/node_modules/playwright-core",
));

const accessFile = process.argv[2];
const profileDir = process.argv[3];
const outDir = process.argv[4];
const executablePath =
  process.argv[5] ||
  path.join(
    process.env.HOME,
    "Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
  );

function safeUrl(u) {
  try {
    const url = new URL(u);
    url.hash = "";
    url.search = "";
    return url.toString();
  } catch {
    return "<invalid>";
  }
}

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const lines = fs.readFileSync(accessFile, "utf8").split("\n");
  const pairingLine = lines.find((l) => l.startsWith("Pairing URL:"));
  if (!pairingLine) throw new Error("no Pairing URL in access file");
  const pairingUrl = pairingLine.slice("Pairing URL:".length).trim();
  const responses = [];
  const context = await chromium.launchPersistentContext(profileDir, {
    headless: true,
    executablePath,
    args: ["--no-first-run", "--no-default-browser-check"],
  });
  const page = context.pages()[0] || (await context.newPage());
  page.on("response", (r) => {
    responses.push({ url: safeUrl(r.url()), status: r.status() });
  });
  const steps = [];
  steps.push({ step: "launch", headless: true, profile: profileDir });
  const nav = await page.goto(pairingUrl, { waitUntil: "domcontentloaded", timeout: 30000 });
  steps.push({ step: "navigate pairing URL", path: "/pair (hash carried the one-time token; not recorded)", status: nav ? nav.status() : null });
  // The page auto-submits the token, then replaces history to / and reloads.
  await page.waitForURL((u) => !u.pathname.includes("/pair"), { timeout: 30000 }).catch(() => {});
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(2000);
  steps.push({ step: "post-pairing page", url: safeUrl(page.url()), title: await page.title() });
  const cookies = await context.cookies();
  steps.push({
    step: "cookies",
    names: cookies.map((c) => c.name),
    domains: cookies.map((c) => c.domain),
  });
  const a11y = await page.locator("body").ariaSnapshot().catch(() => "<ariaSnapshot unavailable>");
  fs.writeFileSync(path.join(outDir, "signin_page_aria.txt"), a11y);
  fs.writeFileSync(
    path.join(outDir, "signin.json.tmp"),
    JSON.stringify(
      {
        when: new Date().toISOString(),
        steps,
        responses: responses.filter((r) => !r.url.includes("token")).slice(0, 40),
        note: "token/cookie values intentionally absent; cookie names only",
      },
      null,
      2,
    ),
  );
  await context.close();
  fs.renameSync(path.join(outDir, "signin.json.tmp"), path.join(outDir, "signin.json"));
  console.log("SIGNIN_DONE");
})().catch((e) => {
  console.error("SIGNIN_FAILED", e.message);
  process.exit(1);
});
