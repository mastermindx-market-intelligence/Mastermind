#!/usr/bin/env node
// Diagnostic: classify every WebSocket frame received during one turn, and
// track assistant text growth, to see whether message-update events stream.
// Records frame type tags and sizes only (payload text never stored whole).
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
  "Count from 1 to 40, one number per line, with a short word after each. Put a blank line between every number.";
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
  const frames = [];
  const textSamples = [];
  let sentAt = 0;
  page.on("websocket", (ws) => {
    ws.on("framereceived", (f) => {
      let tag = "nonjson";
      try {
        const p = JSON.parse(f.payload);
        const describeItem = (x) => {
          if (!x || typeof x !== "object") return String(x).slice(0, 20);
          const parts = [x._tag || x.type || "obj"];
          for (const k of ["event", "message", "turnItem", "thread", "item"]) {
            const v = x[k];
            if (v && typeof v === "object") {
              const bits = [v._tag || v.type || v.role || "?"];
              if (typeof v.text === "string") bits.push("text=" + v.text.length);
              if ("streaming" in v) bits.push("streaming=" + v.streaming);
              if ("status" in v) bits.push("status=" + v.status);
              parts.push(k + "{" + bits.join(",") + "}");
            }
          }
          return parts.join(" ");
        };
        const describe = (v) => {
          if (Array.isArray(v)) return v.slice(0, 4).map(describeItem).join(" || ");
          if (v && typeof v === "object") return describeItem(v);
          return String(v).slice(0, 30);
        };
        tag = (p._tag || p.type || "?") + " " + describe(p.values ?? p.value ?? p.success);
      } catch {}
      frames.push({ tMs: sentAt ? Date.now() - sentAt : -1, len: f.payload.length, tag: String(tag).slice(0, 110) });
    });
  });
  await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 30000 });
  const box = page.getByRole("textbox").first();
  await box.waitFor({ state: "visible", timeout: 30000 });
  await box.click();
  await box.fill(PROMPT);
  await page.getByRole("button", { name: "Submit message" }).click();
  sentAt = Date.now();
  let lastSig = "";
  let lastChange = Date.now();
  while (Date.now() - sentAt < 180000) {
    const rows = await page.evaluate(() => {
      const out = [];
      for (const el of document.querySelectorAll("[data-timeline-row-id]")) {
        out.push({
          kind: el.getAttribute("data-timeline-row-kind") || "?",
          role: el.getAttribute("data-message-role") || "",
          len: el.textContent.length,
        });
      }
      const live = document.querySelector("[data-live-text], [data-streaming-text]");
      return { rows: out, liveLen: live ? live.textContent.length : -1 };
    });
    const sig = JSON.stringify(rows);
    if (sig !== lastSig) {
      textSamples.push({ tMs: Date.now() - sentAt, rows: rows.rows, liveLen: rows.liveLen });
      lastSig = sig;
      lastChange = Date.now();
    }
    if (textSamples.length > 1 && Date.now() - lastChange > 8000) break;
    await page.waitForTimeout(120);
  }
  fs.writeFileSync(
    OUT,
    JSON.stringify(
      {
        when: new Date().toISOString(),
        prompt: PROMPT,
        threadUrlPath: new URL(page.url()).pathname,
        textSamples,
        frames: frames.filter((f) => f.tMs >= 0),
      },
      null,
      2,
    ),
  );
  console.log("DIAG_DONE frames=", frames.length, "textSamples=", textSamples.length);
  await context.close();
})().catch((e) => {
  console.error("DIAG_FAILED", e.message);
  process.exit(1);
});
