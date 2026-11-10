#!/usr/bin/env node
// Queue proof for MMOS lane T1: while a long turn runs, send a second message
// through the stock client; record whether it queues or steers and what the
// page shows. Also captures provider-session starts before/after.
const fs = require("fs");
const path = require("path");
const os = require("os");
const { chromium } = require(path.join(
  process.env.HOME,
  ".mastermind/mmos-dev/t3/tooling/node_modules/playwright-core",
));
const BASE = process.argv[2];
const OUT = process.argv[3];
const EXEC = path.join(
  process.env.HOME,
  "Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
);
const CLAUDE_SESSIONS = path.join(
  os.homedir(),
  ".mastermind/mmos-dev/t3/claude-home/sessions",
);
const listSessions = () => {
  try {
    return fs.readdirSync(CLAUDE_SESSIONS).filter((f) => f.endsWith(".json")).length;
  } catch {
    return -1;
  }
};
(async () => {
  const context = await chromium.launchPersistentContext(
    path.join(os.homedir(), ".mastermind/mmos-dev/t3/browser-profile"),
    { headless: true, executablePath: EXEC },
  );
  const page = context.pages()[0] || (await context.newPage());
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 30000 });
  const box = page.getByRole("textbox").first();
  await box.waitFor({ state: "visible", timeout: 30000 });
  await box.click();
  await box.fill(
    "Write a 250-word story about a lighthouse keeper who counts waves. Take your time and write the full story.",
  );
  const submit = page.getByRole("button", { name: "Submit message" });
  await submit.click();
  const turnStartedAt = Date.now();
  await page.waitForTimeout(4000); // let the first turn get running
  const sessionsBeforeSecond = listSessions();
  // Send the second message while the first turn is still running.
  await box.click();
  await box.fill("After the story, list the keeper's three favorite numbers.");
  const secondSubmit = page.getByRole("button", { name: "Submit message" });
  const secondEnabled = await secondSubmit.isEnabled();
  const domBefore = await page.evaluate(() => ({
    queuedChips: Array.from(document.querySelectorAll("[data-queued], [data-queue]")).length,
    bodyHasQueueWord: document.body.innerText.toLowerCase().includes("queue"),
    bodyHasSteerWord: document.body.innerText.toLowerCase().includes("steer"),
    composerDisabled: !!document.querySelector("textarea[disabled], [contenteditable=false][role=textbox]"),
  }));
  if (secondEnabled) await secondSubmit.click().catch(() => {});
  await page.waitForTimeout(2500);
  const domAfter = await page.evaluate(() => ({
    queuedChips: Array.from(document.querySelectorAll("[data-queued], [data-queue]")).length,
    bodyHasQueueWord: document.body.innerText.toLowerCase().includes("queue"),
    queueContext: (document.body.innerText.match(/[^\n]*queue[^\n]*/gi) || []).slice(0, 3),
    userMessageCount: document.querySelectorAll('[data-message-role="user"]').length,
  }));
  // Wait for both turns to finish (conversation stops changing).
  let lastSig = "";
  let lastChange = Date.now();
  while (Date.now() - lastChange < 15000 && Date.now() - turnStartedAt < 300000) {
    await page.waitForTimeout(1000);
    const sig = await page.evaluate(() => document.querySelector('[data-workspace-area="conversation"]').innerText.length);
    if (sig !== lastSig) {
      lastSig = sig;
      lastChange = Date.now();
    }
  }
  const final = await page.evaluate(() => ({
    userMessages: document.querySelectorAll('[data-message-role="user"]').length,
    assistantMessages: document.querySelectorAll('[data-message-role="assistant"]').length,
    bodyHasFavoriteNumbers: document.body.innerText.includes("favorite numbers") || document.body.innerText.includes("story"),
    statusText: (document.body.innerText.match(/[^\n]*(running|working|queued)[^\n]*/gi) || []).slice(0, 3),
  }));
  fs.writeFileSync(
    OUT,
    JSON.stringify(
      {
        when: new Date().toISOString(),
        threadUrlPath: new URL(page.url()).pathname,
        secondSubmitEnabledWhileRunning: secondEnabled,
        domBeforeSecondSubmit: domBefore,
        domAfterSecondSubmit: domAfter,
        claudeSessionFiles: { beforeSecond: sessionsBeforeSecond, afterCompletion: listSessions() },
        final,
        turnTotalMs: Date.now() - turnStartedAt,
      },
      null,
      2,
    ),
  );
  console.log("QUEUE_PROOF_DONE secondEnabled=" + secondEnabled, "userMsgs=" + final.userMessages);
  await context.close();
})().catch((e) => {
  console.error("QUEUE_PROOF_FAILED", e.message);
  process.exit(1);
});
