#!/usr/bin/env node
// Two views of one thread (MMOS lane T1): open the same thread URL in two
// pages of the same browser profile; record duplicate submissions, provider
// session starts, and established connections to the server port.
// Usage: node two_views.js <base> <threadPath> <port> <outJson>
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
const PORT = process.argv[4];
const OUT = process.argv[5];
const DEV = path.join(os.homedir(), ".mastermind", "mmos-dev", "t3");
const EXEC = path.join(
  os.homedir(),
  "Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
);
const count = (dir, pred) => {
  try {
    return fs.readdirSync(dir).filter(pred).length;
  } catch {
    return -1;
  }
};
(async () => {
  const sessionsBefore = count(path.join(DEV, "claude-home", "sessions"), (f) => f.endsWith(".json"));
  const logsBefore = count(path.join(DEV, "home/userdata/logs/provider"), (f) => f.endsWith(".log"));
  const context = await chromium.launchPersistentContext(
    path.join(os.homedir(), ".mastermind/mmos-dev/t3/browser-profile"),
    { headless: true, executablePath: EXEC },
  );
  const page1 = context.pages()[0] || (await context.newPage());
  await page1.goto(BASE + THREAD_PATH, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page1.waitForTimeout(2500);
  const estOne = execSync(`netstat -an | grep ${PORT} | grep -c ESTABLISHED || true`)
    .toString()
    .trim();
  const page2 = await context.newPage();
  await page2.goto(BASE + THREAD_PATH, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page2.waitForTimeout(2500);
  const estTwo = execSync(`netstat -an | grep ${PORT} | grep -c ESTABLISHED || true`)
    .toString()
    .trim();
  const counts = await page2.evaluate(() => ({
    user: document.querySelectorAll('[data-message-role="user"]').length,
    assistant: document.querySelectorAll('[data-message-role="assistant"]').length,
  }));
  const counts1 = await page1.evaluate(() => ({
    user: document.querySelectorAll('[data-message-role="user"]').length,
    assistant: document.querySelectorAll('[data-message-role="assistant"]').length,
  }));
  const sessionsAfter = count(path.join(DEV, "claude-home", "sessions"), (f) => f.endsWith(".json"));
  const logsAfter = count(path.join(DEV, "home/userdata/logs/provider"), (f) => f.endsWith(".log"));
  fs.writeFileSync(
    OUT,
    JSON.stringify(
      {
        when: new Date().toISOString(),
        threadUrlPath: THREAD_PATH,
        establishedConnections: { onePage: estOne, twoPages: estTwo },
        messagesPage1: counts1,
        messagesPage2: counts2 = counts,
        duplicateSubmission:
          counts.user !== counts1.user || counts.assistant !== counts1.assistant,
        providerSessionStarted: {
          claudeSessionFiles: { before: sessionsBefore, after: sessionsAfter },
          providerEventLogs: { before: logsBefore, after: logsAfter },
          started: sessionsAfter > sessionsBefore || logsAfter > logsBefore,
        },
      },
      null,
      2,
    ),
  );
  console.log(
    "TWO_VIEWS est",
    estOne,
    "->",
    estTwo,
    "msgs",
    JSON.stringify(counts1),
    "/",
    JSON.stringify(counts),
  );
  await context.close();
})().catch((e) => {
  console.error("TWO_VIEWS_FAILED", e.message);
  process.exit(1);
});
