#!/usr/bin/env node
// Lane T7 — headless Chromium driver for the Team roster on the team T3
// server (127.0.0.1:3780). Reuses the mmos-dev playwright-core install.
// Modes:
//   pair <accessFile> <profileDir> <outJson>
//       One-time-token pairing (token read from the 0600 file in-process,
//       never printed or recorded). No screenshot of the pairing page.
//   rename <profileDir> <threadUrl> <threadId> <currentTitle> <newTitle>
//            <outJson>
//       Rename exactly that thread through its web-client menu; verify its
//       durable identity and leave pin state untouched. No screenshot.
//   pin <profileDir> <threadUrl> <outJson> <shotPng>
//       Open a deep thread URL, right-click its sidebar row, click the
//       "Pin thread" menu item, verify the Pinned marker, screenshot.
//   snapshot <profileDir> <url> <outJson> <shotPng> [label]
//       Dump the sidebar roster DOM state at a 1280x800 viewport + shot.
//   livetext <profileDir> <threadUrl> <promptFile> <outJson>
//       Send a prompt in the thread and record every distinct state of the
//       answer text in the DOM (sample interval 120 ms).
//   answer <profileDir> <threadUrl> <answerFile> <outJson> <shotPng> [keepQueued]
//       Answer the question a teammate is waiting on in its thread (the T3
//       CLI has no command for this); optionally drop duplicate queued
//       messages first.
const fs = require("fs");
const path = require("path");
const { chromium } = require(path.join(
  process.env.HOME,
  ".mastermind/mmos-dev/t3/tooling/node_modules/playwright-core",
));

const EXECUTABLE = path.join(
  process.env.HOME,
  "Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
);

async function launch(profileDir) {
  return chromium.launchPersistentContext(profileDir, {
    headless: true,
    executablePath: EXECUTABLE,
    viewport: { width: 1280, height: 800 },
    args: ["--no-first-run", "--no-default-browser-check"],
  });
}

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

async function sidebarState(page) {
  return page.evaluate(() => {
    const rows = [...document.querySelectorAll(
      '[data-testid="sidebar-row-card"], [data-testid="sidebar-row-slim"]')];
    const out = [];
    for (const row of rows) {
      // Card rows carry the full accessibility label (title + meta); the
      // visible title line is the first element whose text appears twice
      // (title + sr-only echo). Fall back to the row aria-label.
      const status = [...row.querySelectorAll('[role="status"]')]
        .map((n) => n.textContent.trim())
        .filter((t) => t && t !== "Pinned");
      const accent = row.querySelector("[data-provider-accent-color]");
      const badge = accent ? accent.lastElementChild : null;
      const leaves = [...row.querySelectorAll("span, div")]
        .filter((n) => n.children.length === 0 && n.textContent.trim());
      const titleNode = leaves
        .filter((n) => n.getBoundingClientRect().width > 40)
        .find((n) => n.textContent.includes("—")) ||
        leaves.filter((n) => n.getBoundingClientRect().width > 40)[0] ||
        null;
      const rect = titleNode ? titleNode.getBoundingClientRect() : null;
      const ariaLabel = row.getAttribute("aria-label");
      out.push({
        ariaLabel,
        title: titleNode ? titleNode.textContent.trim() : null,
        truncated: titleNode
          ? titleNode.scrollWidth > titleNode.clientWidth + 1
          : null,
        titleBox: rect
          ? { w: Math.round(rect.width), h: Math.round(rect.height) }
          : null,
        statuses: [
          ...status,
          ...(ariaLabel || "").split(", ").slice(1),
        ].filter((t) => t && t !== "Pinned"),
        pinned: !!row.querySelector('[aria-label="Pinned"], [aria-label="Unpin thread"]'),
        woke: !!row.querySelector('[aria-label="Dismiss Woke notification"]'),
        accentColor: accent
          ? accent.getAttribute("data-provider-accent-color")
          : null,
        badgeInitials: badge ? badge.textContent.trim() : null,
        badgeBackground: badge ? getComputedStyle(badge).backgroundColor : null,
        rowTestid: row.getAttribute("data-testid"),
      });
    }
    const toggle = document.querySelector('[aria-label="Toggle main sidebar"]');
    // The sidebar panel is the nearest common ancestor of the thread rows.
    let listParent = null;
    if (rows.length) {
      let node = rows[0];
      while (node && !rows.every((r) => node.contains(r))) node = node.parentElement;
      listParent = node;
    }
    return {
      url: location.pathname,
      rows: out,
      toggleButton: !!toggle,
      sidebarWidth: listParent
        ? Math.round(listParent.getBoundingClientRect().width)
        : null,
      sidebarExpanded: listParent
        ? listParent.getBoundingClientRect().width > 100
        : false,
    };
  });
}

async function openThread(page, url) {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForSelector(
    '[data-testid="sidebar-row-card"], [data-testid="sidebar-row-slim"]',
    { timeout: 45000 });
  await page.waitForTimeout(1500);
}

async function writeOut(outPath, payload) {
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  const tmp = outPath + ".tmp";
  fs.writeFileSync(tmp, JSON.stringify(payload, null, 2));
  fs.renameSync(tmp, outPath);
}

async function modePair(accessFile, profileDir, outJson) {
  const lines = fs.readFileSync(accessFile, "utf8").split("\n");
  const pairingLine = lines.find((l) => l.startsWith("Pairing URL:"));
  const tokenLine = lines.find((l) => l.startsWith("Token:"));
  if (!pairingLine || !tokenLine) throw new Error("no pairing data in access file");
  const pairingUrl = pairingLine.slice("Pairing URL:".length).trim();
  const token = tokenLine.slice("Token:".length).trim();
  const context = await launch(profileDir);
  const page = context.pages()[0] || (await context.newPage());
  await page.goto(pairingUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForTimeout(3000);
  if (page.url().includes("/pair")) {
    // The fragment auto-submit did not complete; use the page's own paste
    // flow: fill the token input and click Continue.
    const input = page.getByRole("textbox").first();
    await input.waitFor({ state: "visible", timeout: 15000 });
    await input.fill(token);
    await page.getByRole("button", { name: "Continue" }).click();
  }
  await page
    .waitForURL((u) => !u.pathname.includes("/pair"), { timeout: 45000 })
    .catch(() => {});
  await page.waitForLoadState("networkidle", { timeout: 45000 }).catch(() => {});
  await page.waitForTimeout(2000);
  const cookies = (await context.cookies()).map((c) => c.name);
  const landed = safeUrl(page.url());
  await context.close();
  await writeOut(outJson, {
    when: new Date().toISOString(),
    landed,
    cookieNames: cookies,
    note: "pairing token used once in-page; never printed, logged or stored",
  });
  console.log("PAIR_DONE");
}

async function modePin(profileDir, threadUrl, titleContains, outJson, shotPng) {
  const context = await launch(profileDir);
  const page = context.pages()[0] || (await context.newPage());
  await openThread(page, threadUrl);
  const before = await sidebarState(page);
  // Right-click the row whose title matches, then click "Pin thread".
  const target = page
    .locator('[data-testid="sidebar-row-card"], [data-testid="sidebar-row-slim"]')
    .filter({ hasText: titleContains })
    .first();
  await target.waitFor({ state: "visible", timeout: 20000 });
  await target.click({ button: "right" });
  const item = page.getByRole("menuitem", { name: "Pin thread" });
  await item.waitFor({ state: "visible", timeout: 15000 });
  await item.click();
  await page.waitForTimeout(2500);
  const after = await sidebarState(page);
  await page.screenshot({ path: shotPng });
  await context.close();
  await writeOut(outJson, {
    when: new Date().toISOString(),
    url: safeUrl(threadUrl),
    titleContains,
    pinnedTitles: after.rows.filter((r) => r.pinned).map((r) => r.title),
    before: before.rows.map((r) => ({ title: r.title, pinned: r.pinned })),
    after: after.rows.map((r) => ({ title: r.title, pinned: r.pinned })),
  });
  console.log("PIN_DONE");
}

async function modeRename(profileDir, threadUrl, threadId, currentTitle,
                          newTitle, outJson) {
  // Title-length policy (24-char sidebar fit, allow_long_titles opt-in) is
  // owned by team_roster.py, which knows the spec's regime; this driver only
  // checks what it needs to target a thread safely.
  if (!threadId) throw new Error("durable thread id is required");
  const context = await launch(profileDir);
  try {
    const page = context.pages()[0] || (await context.newPage());
    await openThread(page, threadUrl);
    // The visible row may start with the pinned separator, so select the row
    // that contains the exact current title. Confirm its durable identity
    // against the persisted environmentId:threadId row key, never by title.
    const target = page.locator(`[data-sidebar-row="${CSS.escape(
      `${new URL(threadUrl).pathname.split("/").filter(Boolean)[0]}:${threadId}`)}"]`);
    await target.waitFor({ state: "visible", timeout: 20000 });
    if (await target.count() !== 1)
      throw new Error(`expected exactly one durable row for ${threadId}`);
    const before = await sidebarState(page);
    if (before.rows.filter((r) => r.title === currentTitle).length !== 1)
      throw new Error(`roster title is not exactly one visible row: ${currentTitle}`);
    await target.click({ button: "right" });
    const item = page.getByRole("menuitem", { name: "Rename thread", exact: true });
    await item.waitFor({ state: "visible", timeout: 15000 });
    await item.click();
    const input = page.getByRole("textbox", { name: "Thread title", exact: true });
    await input.waitFor({ state: "visible", timeout: 15000 });
    await input.fill(newTitle);
    await input.press("Enter");
    await input.waitFor({ state: "hidden", timeout: 15000 });
    await page.waitForFunction(
      ({ key, title }) => {
        const row = document.querySelector(`[data-sidebar-row="${CSS.escape(key)}"]`);
        return row && [...row.querySelectorAll("span, div")]
          .some((n) => n.children.length === 0 && n.textContent.trim() === title);
      },
      { key: await target.getAttribute("data-sidebar-row"), title: newTitle },
      { timeout: 20000 },
    );
    await page.waitForTimeout(1500);
    const after = await sidebarState(page);
    const row = after.rows.filter((r) => r.title === newTitle);
    if (row.length !== 1) throw new Error("rename did not read back exactly one row");
    if (!decodeURIComponent(page.url()).includes(threadId))
      throw new Error("renamed thread URL no longer matches durable id");
    const beforeRow = before.rows.find((r) => r.title === currentTitle);
    if (row[0].pinned !== (beforeRow && beforeRow.pinned))
      throw new Error("rename changed pin state");
    await writeOut(outJson, {
      when: new Date().toISOString(),
      threadId,
      title: newTitle,
      oldTitle: currentTitle,
      pinned: row[0].pinned,
      verifiedBy: "data-sidebar-row environmentId:threadId and deep-thread URL",
    });
    console.log(`RENAME_DONE ${threadId} ${newTitle}`);
  } finally {
    await context.close();
  }
}

async function modeSnapshot(profileDir, url, outJson, shotPng, label) {
  const context = await launch(profileDir);
  const page = context.pages()[0] || (await context.newPage());
  await openThread(page, url);
  const state = await sidebarState(page);
  const aria = await page
    .locator("body")
    .ariaSnapshot()
    .catch(() => "<ariaSnapshot unavailable>");
  await page.screenshot({ path: shotPng });
  await context.close();
  await writeOut(outJson, {
    when: new Date().toISOString(),
    label: label || "",
    url: safeUrl(url),
    viewport: "1280x800",
    sidebar: state,
    ariaExcerpt: aria.slice(0, 4000),
  });
  console.log("SNAPSHOT_DONE");
}

async function modeLivetext(profileDir, threadUrl, promptFile, outJson) {
  const prompt = fs.readFileSync(promptFile, "utf8");
  const context = await launch(profileDir);
  const page = context.pages()[0] || (await context.newPage());
  await openThread(page, threadUrl);
  const box = page.getByRole("textbox").first();
  await box.waitFor({ state: "visible", timeout: 30000 });
  await box.click();
  await box.fill(prompt);
  const submit = page.getByRole("button", { name: "Submit message" });
  await submit.waitFor({ state: "visible", timeout: 10000 });
  const sentAt = Date.now();
  await submit.click();
  const states = [];
  let lastText = null;
  let finalText = "";
  while (Date.now() - sentAt < 300000) {
    const sample = await page.evaluate(() => {
      const nodes = document.querySelectorAll('[data-message-role="assistant"]');
      const last = nodes[nodes.length - 1];
      const stop = document.querySelector(
        'button[aria-label*="top" i], button[aria-label*="nterrupt" i]');
      return {
        text: last ? last.textContent : "",
        stopVisible: !!stop,
      };
    });
    if (sample.text && sample.text !== lastText) {
      lastText = sample.text;
      states.push({
        tMs: Date.now() - sentAt,
        length: sample.text.length,
        head: sample.text.slice(0, 110),
        tail: sample.text.slice(-70),
      });
      finalText = sample.text;
    }
    const quiet = states.length > 1 && !sample.stopVisible &&
      Date.now() - sentAt > 20000 && sample.text === lastText;
    if (quiet) break;
    await page.waitForTimeout(120);
  }
  await context.close();
  await writeOut(outJson, {
    when: new Date().toISOString(),
    url: safeUrl(threadUrl),
    sampleIntervalMs: 120,
    distinctStates: states.length,
    states,
    finalLength: finalText.length,
  });
  console.log(`LIVETEXT_DONE states=${states.length}`);
}

async function pendingState(page) {
  return page.evaluate(() => {
    const queued = document.querySelectorAll(
      '[aria-label^="Queued message"]').length;
    const text = document.body.innerText;
    return {
      queued,
      needsInput: text.includes("Needs your input"),
      inputRequested: text.includes("Input requested"),
    };
  });
}

// answer <profileDir> <threadUrl> <answerFile> <outJson> <shotPng> [keepQueued]
//     Answer the question a teammate is waiting on in its thread, with the
//     text in <answerFile>. With keepQueued (a number), first remove queued
//     messages from the end until that many are left — the wake carrier can
//     queue the same message more than once behind a waiting turn.
async function modeAnswer(profileDir, threadUrl, answerFile, outJson, shotPng,
                          keepQueued) {
  const answer = fs.readFileSync(answerFile, "utf8").trim();
  if (!answer) throw new Error("empty answer");
  const context = await launch(profileDir);
  const page = context.pages()[0] || (await context.newPage());
  await openThread(page, threadUrl);
  await page.waitForTimeout(2500);
  const before = await pendingState(page);
  let removed = 0;
  if (keepQueued !== undefined) {
    const keep = Number(keepQueued);
    const items = page.locator('[aria-label^="Queued message"]');
    while ((await items.count()) > keep) {
      const n = await items.count();
      await items.nth(n - 1).getByRole("button", { name: /^Remove/ }).click();
      await page.waitForTimeout(800);
      if ((await items.count()) >= n) throw new Error("queued message not removed");
      removed += 1;
    }
  }
  if (!before.inputRequested && !before.needsInput) {
    await context.close();
    throw new Error("no question is waiting in this thread");
  }
  // The answer box is the thread's own editor (a contenteditable), which
  // shows an "answer" hint while a question is waiting.
  const box = page.locator('[data-testid="composer-editor"]');
  await box.waitFor({ state: "visible", timeout: 20000 });
  await box.click();
  await page.keyboard.type(answer, { delay: 2 });
  const submit = page.getByRole("button", { name: "Submit", exact: true });
  await submit.waitFor({ state: "visible", timeout: 10000 });
  await page.waitForFunction(
    () => [...document.querySelectorAll("button")]
      .some((b) => b.textContent.trim() === "Submit" && !b.disabled),
    null, { timeout: 10000 });
  await submit.click();
  await page.waitForTimeout(6000);
  const after = await pendingState(page);
  await page.screenshot({ path: shotPng });
  await context.close();
  await writeOut(outJson, {
    when: new Date().toISOString(),
    url: safeUrl(threadUrl),
    answerLength: answer.length,
    queuedRemoved: removed,
    before,
    after,
  });
  console.log(`ANSWER_DONE removed=${removed} needsInputAfter=${after.needsInput}`);
}

(async () => {
  const [mode, ...args] = process.argv.slice(2);
  if (mode === "answer") return modeAnswer(...args);
  if (mode === "pair") return modePair(...args);
  if (mode === "pin") return modePin(...args);
  if (mode === "rename") return modeRename(...args);
  if (mode === "snapshot") return modeSnapshot(...args);
  if (mode === "livetext") return modeLivetext(...args);
  throw new Error(`unknown mode ${mode}`);
})().catch((e) => {
  console.error("ROSTER_BROWSER_FAILED", e.message);
  process.exit(1);
});
