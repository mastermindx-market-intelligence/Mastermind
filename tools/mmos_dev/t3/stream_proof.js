#!/usr/bin/env node
// Stream proof for MMOS lane T1: send the counting prompt through the stock
// web client and record, from inside the page, every change of the assistant
// message text until the turn completes. Verdict rule: PASS only if >= 8 text
// changes spread over >= 2 seconds before completion.
// Usage: node stream_proof.js <base> <outDir> [prompt]
const fs = require("fs");
const path = require("path");
const { chromium } = require(path.join(
  process.env.HOME,
  ".mastermind/mmos-dev/t3/tooling/node_modules/playwright-core",
));
const BASE = process.argv[2];
const OUT = process.argv[3];
const PROMPT =
  process.argv[4] ||
  "Count from 1 to 40, one number per line, with a short word after each.";
const EXEC = path.join(
  process.env.HOME,
  "Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
);
const POLL_MS = 200;
const QUIET_MS = 6000;

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const context = await chromium.launchPersistentContext(
    path.join(process.env.HOME, ".mastermind/mmos-dev/t3/browser-profile"),
    { headless: true, executablePath: EXEC },
  );
  const page = context.pages()[0] || (await context.newPage());
  let sentAt = 0;
  const wsFrames = [];
  page.on("websocket", (ws) => {
    ws.on("framereceived", (f) => {
      if (sentAt) wsFrames.push({ tMs: Date.now() - sentAt, len: f.payload.length });
    });
  });
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 30000 });
  const box = page.getByRole("textbox").first();
  await box.waitFor({ state: "visible", timeout: 30000 });
  await box.click();
  await box.fill(PROMPT);
  const submit = page.getByRole("button", { name: "Submit message" });
  await submit.waitFor({ state: "visible", timeout: 10000 });
  const modelLabel = await page
    .getByRole("button", { name: /GLM|Claude|Deepseek|GPT|Kimi|model/i })
    .first()
    .textContent()
    .catch(() => "unknown");
  const sentAt2 = Date.now();
  sentAt = sentAt2;
  await submit.click();
  // Poll from the first moment after send; the draft becomes a thread while
  // the first turn may already be streaming.
  const events = [];
  let lastLen = -1;
  let lastChangeAt = 0;
  let stopSeen = false;
  let finalLen = 0;
  let threadUrlPath = new URL(page.url()).pathname;
  while (Date.now() - sentAt < 300000) {
    const sample = await page.evaluate(() => {
      const nodes = document.querySelectorAll('[data-message-role="assistant"]');
      const last = nodes[nodes.length - 1];
      const stop = document.querySelector(
        'button[aria-label*="top" i], button[title*="top" i], button[aria-label*="nterrupt" i]',
      );
      return {
        len: last ? last.textContent.length : 0,
        stopVisible: !!stop,
        assistantCount: nodes.length,
      };
    });
    const nowPath = new URL(page.url()).pathname;
    if (nowPath !== threadUrlPath && /\/[0-9a-f-]{36}\/[0-9a-f-]{36}/.test(nowPath)) {
      threadUrlPath = nowPath;
    }
    if (sample.len !== lastLen) {
      events.push({ tMs: Date.now() - sentAt, textLength: sample.len });
      lastLen = sample.len;
      lastChangeAt = Date.now();
    }
    if (sample.stopVisible) stopSeen = true;
    finalLen = sample.len;
    const quietFor = Date.now() - lastChangeAt;
    const ranOnce = events.length > 1 && !sample.stopVisible && quietFor >= QUIET_MS;
    if (ranOnce || (events.length > 1 && quietFor >= 30000)) break;
    await page.waitForTimeout(POLL_MS);
  }
  const spanMs =
    events.length >= 2 ? events[events.length - 1].tMs - events[0].tMs : 0;
  const changes = Math.max(0, events.length - 1); // exclude the first appearance
  const verdict =
    changes >= 8 && spanMs >= 2000
      ? "PASS"
      : `FAIL: ${changes} text changes over ${spanMs} ms (need >=8 over >=2000 ms)`;
  const turnFrames = wsFrames.filter((f) => f.tMs >= 0 && f.tMs <= (events[events.length - 1]?.tMs ?? 0) + QUIET_MS);
  const result = {
    when: new Date().toISOString(),
    prompt: PROMPT,
    modelLabel: (modelLabel || "").trim(),
    threadUrlPath,
    assistantMessagesSeen: events.length > 0 ? 1 : 0,
    textChangeEvents: events,
    textChangeCount: changes,
    spanMs,
    stopButtonSeenWhileGenerating: stopSeen,
    finalTextLength: finalLen,
    webSocket: {
      note: "frames received by the page during the turn (timestamps + sizes only)",
      frameCount: turnFrames.length,
      firstAtMs: turnFrames[0]?.tMs ?? null,
      lastAtMs: turnFrames[turnFrames.length - 1]?.tMs ?? null,
      sampleFirst20: turnFrames.slice(0, 20),
    },
    verdict,
    verdictRule: "PASS only if >=8 text changes spread over >=2s before completion",
  };
  const suffix = process.argv[5] ? "_" + process.argv[5] : "";
  fs.writeFileSync(path.join(OUT, "stream_proof" + suffix + ".json"), JSON.stringify(result, null, 2));
  console.log(
    "STREAM_PROOF" + (suffix ? " [" + suffix + "]" : ""),
    verdict,
    "changes=" + changes,
    "spanMs=" + spanMs,
    "wsFrames=" + result.webSocket.frameCount,
    "thread=" + threadUrlPath,
  );
  await context.close();
})().catch((e) => {
  console.error("STREAM_PROOF_FAILED", e.message);
  process.exit(1);
});
