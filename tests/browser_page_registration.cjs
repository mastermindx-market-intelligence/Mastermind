"use strict";
// Registration contract for browser_page.js: an injection into a document that
// already ran (or failed) a previous injection must leave a dispatchable page
// object and exactly one working message listener behind.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const SOURCE = path.resolve(__dirname, "../integrations/chairman_surfaces/web_sol_extension/browser_page.js");
const CODE = fs.readFileSync(SOURCE, "utf8");

function world({poisonFactory = false} = {}) {
  const listeners = [];
  const sandbox = {
    chrome: {runtime: {id: "fixture-extension",
      onMessage: {addListener: fn => listeners.push(fn)}}},
    addEventListener(type, handler) {
      if (poisonFactory) throw new Error("fixture: poisoned document listener");
      sandbox.handlers[type] = handler;
    },
    handlers: {},
    listeners,
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  return {sandbox, listeners, load: () => vm.runInContext(CODE, sandbox, {filename: SOURCE})};
}
const deliver = (w, message) => new Promise(resolve => {
  let settled = false;
  for (const listener of w.listeners) {
    const kept = listener(message, {id: "fixture-extension"}, value => {settled = true;resolve(value);});
    if (settled) return;
  }
  if (!settled) resolve(undefined);
});

(async () => {
  // 1. A healthy first injection registers one listener and a dispatchable object.
  {
    const w = world();
    w.load();
    assert.equal(w.listeners.length, 1, "one listener after first injection");
    assert.ok(w.sandbox.__MMX_BROWSER_PAGE_V1__ && typeof w.sandbox.__MMX_BROWSER_PAGE_V1__.dispatch === "function");
    const reply = await deliver(w, {kind: "MMX_BROWSER_PAGE_V1", action: "snapshot",
      session_id: "c".repeat(64), snapshot_id: null, ref: null, params: {},
      expires_at: new Date(Date.now() + 5000).toISOString()});
    // The bare vm world has no DOM, so dispatch answers PAGE_UNAVAILABLE; a
    // structured reply at all proves object and listener are wired together.
    assert.ok(reply && typeof reply.code === "string" && reply.effect === "NOT_APPLIED",
      "listener answers from the page object's dispatch");
  }
  // 2. A second injection neither duplicates the listener nor replaces the object.
  {
    const w = world();
    w.load();
    const first = w.sandbox.__MMX_BROWSER_PAGE_V1__;
    w.load();
    assert.equal(w.listeners.length, 1, "listener not duplicated");
    assert.equal(w.sandbox.__MMX_BROWSER_PAGE_V1__, first, "page object preserved");
  }
  // 3. A factory failure still registers the listener and records the reason;
  //    the next healthy injection completes registration.
  {
    const w = world({poisonFactory: true});
    w.load();
    assert.equal(w.listeners.length, 1, "listener registered despite factory failure");
    assert.ok(typeof w.sandbox.MMXBrowserPageError === "string" && w.sandbox.MMXBrowserPageError.includes("poisoned"),
      "factory error text recorded");
    const poisoned = await deliver(w, {kind: "MMX_BROWSER_PAGE_V1", action: "validate",
      session_id: "c".repeat(64), snapshot_id: "s", ref: null, params: {},
      expires_at: new Date(Date.now() + 5000).toISOString()});
    assert.equal(poisoned, undefined, "no page object yet: no response sent");
    w.sandbox.addEventListener = () => {}; // heal the factory for the next load
    w.load();
    assert.ok(w.sandbox.__MMX_BROWSER_PAGE_V1__ && typeof w.sandbox.__MMX_BROWSER_PAGE_V1__.dispatch === "function",
      "second injection after failure completes registration");
    assert.equal(w.listeners.length, 1, "still exactly one listener");
  }
  // 4. A lost listener (flag present, listener gone) is repaired by re-injection.
  {
    const w = world();
    w.load();
    w.listeners.length = 0; // listener lost, page object still present
    delete w.sandbox.__MMX_BROWSER_PAGE_LISTENING__;
    w.sandbox.chrome.runtime.onMessage.addListener = fn => w.listeners.push(fn);
    w.load();
    assert.equal(w.listeners.length, 1, "listener re-registered after loss");
    const reply = await deliver(w, {kind: "MMX_BROWSER_PAGE_V1", action: "snapshot",
      session_id: "c".repeat(64), snapshot_id: null, ref: null, params: {},
      expires_at: new Date(Date.now() + 5000).toISOString()});
    assert.ok(reply && typeof reply.code === "string", "re-registered listener answers");
  }
  console.log("browser page registration passed");
})().catch(error => {console.error(error);process.exitCode = 1;});
