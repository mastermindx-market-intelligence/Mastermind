#!/usr/bin/env node
// Restart proof for MMOS lane T1: stop the dev server and the browser, start
// both again with the same home and profile, open the same thread directly,
// and verify messages with no sign-in prompt and no new provider session.
// Usage: node restart_proof.js <base> <threadPath> <outJson>
const fs = require("fs");
const path = require("path");
const os = require("os");
const { execSync } = require("child_process");
const { chromium } = require(path.join(
  os.homedir(),
  ".mastermind/mmos-dev/t3/tooling/node_modules/playwright-core",
));
const BASE = process.argv[2];
const THREAD_PATH = process.argv[3];
const OUT = process.argv[4];
const DEV = path.join(os.hodir ?? os.homedir(), ".mastermind", "mmos-dev", "t3");
const EXEC = path.join(
  os.homedir(),
  "Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
);
const SCRIPT = path.join(
  os.homedir(),
  ".t3/worktrees/Mastermind/t3-25a4c4a8/tools/mmos_dev/t3_dev.sh",
);
const sessionsBefore = fs
  .readdirSync(path.join(DEV, "claude-home", "sessions"))
  .filter((f) => f.endsWith(".json")).length;
const providerLogsBefore = fs
  .readdirSync(path.join(DEV, "home/userdata/logs/provider"))
  .filter((f) => f.endsWith(".log")).length;

(async () => {
  const context = await chromium.launchPersistentContext(
    path.join(os.homedir(), ".mastermind/mmos-dev/t3/browser-profile"),
    { headless: true, executablePath: EXEC },
  );
  const page = context.pages()[0] || (await context.newPage());
  // Before: message counts on the thread.
  await page.goto(BASE + THREAD_PATH, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(2500);
  const before = await page.evaluate(() => ({
    user: document.querySelectorAll('[data-message-role="user"]').length,
    assistant: document.querySelectorAll('[data-message-role="assistant"]').length,
  }));
  const threadId = THREAD_PATH.split("/").filter(Boolean).pop();
  await context.close();
  // Stop and restart the server with the same home.
  execSync(`sh "${SCRIPT}" stop`, { stdio: "pipe" });
  execSync(`sh "${SCRIPT}" start`, { stdio: "pipe", timeout: 180000 });
  // Reopen the same thread with the same profile.
  const context2 = await chromium.launchPersistentContext(
    path.join(os.homedir(), ".mastermind/mmos-dev/t3/browser-profile"),
    { headless: true, executablePath: EXEC },
  );
  const page2 = context2.pages()[0] || (await context2.newPage());
  await page2.goto(BASE + THREAD_PATH, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page2.waitForTimeout(3000);
  const after = await page2.evaluate(() => ({
    user: document.querySelectorAll('[data-message-role="user"]').length,
    assistant: document.querySelectorAll('[data-message-role="assistant"]').length,
    onPairRoute: location.pathname.includes("/pair") || location.pathname.includes("/welcome"),
    signInVisible: !!document.querySelector("input#pairing-token, [aria-label*=airing i]"),
    bodyHasStory: document.body.innerText.includes("Edith"),
  }));
  const sessionsAfter = fs
    .readdirSync(path.join(DEV, "claude-home", "sessions"))
    .filter((f) => f.endsWith(".json")).length;
  const providerLogsAfter = fs
    .readdirSync(path.join(DEV, "home/userdata/logs/provider"))
    .filter((f) => f.endsWith(".log")).length;
  fs.writeFileSync(
    OUT,
    JSON.stringify(
      {
        when: new Date().toISOString(),
        threadIdBefore: threadId,
        threadIdAfter: new URL(page2.url()).pathname.split("/").filter(Boolean).pop(),
        messagesBefore: before,
        messagesAfter: after,
        signInPromptShownAfterRestart: after.onPairRoute || after.signInVisible,
        providerSessionStartedByReopen: {
          claudeSessionFiles: { before: sessionsBefore, after: sessionsAfter },
          providerEventLogs: { before: providerLogsBefore, after: providerLogsAfter },
          started: sessionsAfter > sessionsBefore || providerLogsAfter > providerLogsBefore,
        },
        notes: "server stopped and started via t3_dev.sh; browser profile persisted",
      },
      null,
      2,
    ),
  );
  console.log(
    "RESTART_PROOF",
    after.onPairRoute ? "SIGNIN_SHOWN" : "STAYED_SIGNED_IN",
    "msgs",
    JSON.stringify(before),
    "->",
    JSON.stringify({ user: after.user, assistant: after.assistant }),
  );
  await context2.close();
})().catch((e) => {
  console.error("RESTART_PROOF_FAILED", e.message);
  process.exit(1);
});
