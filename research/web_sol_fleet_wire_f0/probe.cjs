"use strict";
// Research fixture only. No Chrome, sockets, provider, or network is contacted.
const assert = require("node:assert/strict");
const {createHash, webcrypto} = require("node:crypto");
if (!globalThis.crypto) Object.defineProperty(globalThis, "crypto", {value: webcrypto});
const census = require(process.argv[2]);
async function sample(count, mode = "ordinary") {
  const inventory = Array.from({length: count}, (_, index) => ({
    id: index + 1, windowId: 1, active: index === 0,
    url: `https://chatgpt.com/c/fleet-synthetic-${index + 1}`,
    status: "complete", incognito: false,
    discarded: mode === "mixed" && index % 3 === 0,
    frozen: mode === "mixed" && index % 3 === 1,
  }));
  let probeCalls = 0;
  const tabs = {
    query: async () => inventory.map(tab => ({...tab})),
    get: async id => ({...inventory[id - 1]}),
    sendMessage: async (id, request, options) => {
      probeCalls++;
      assert.deepEqual(options, {frameId: 0});
      assert.equal(request.kind, "MMX_WEB_SOL_REPROBE");
      const expected = createHash("sha256").update(inventory[id - 1].url).digest("hex");
      assert.equal(request.expected_conversation_fingerprint, expected);
      return {kind: "MMX_WEB_SOL_PROBE", conversation_fingerprint: expected,
        observation: {schema: "mastermind.web_sol_surface_probe.v1",
          target_present: true, exact_conversation_loaded: true, page_responsive: true,
          document_ready_state: "complete", visibility: "visible", composer_available: true,
          generation_state: id % 2 ? "active" : "idle", auth_required: false,
          provider_error_present: false}};    },
  };
  const snapshot = await census.collect(tabs, "a".repeat(64));
  assert.equal(snapshot.initial_tab_count, count);
  assert.equal(snapshot.final_tab_count, count);
  assert.equal(snapshot.rows.length, Math.min(count, census.MAX_TABS));
  assert.equal(snapshot.omitted_tab_count, Math.max(0, count - census.MAX_TABS));
  assert.equal(snapshot.consistency, "STABLE_AT_BOUNDARIES");
  for (const row of snapshot.rows) {
    assert.equal(row.selected_model, null);
    assert.equal(row.selected_effort, null);
    assert.equal(row.served_model, null);
    assert.equal(row.document_binding, "UNVERIFIED");
  }
  return {fixture_tab_count: count, mode, probe_calls: probeCalls, snapshot};
}
(async () => {
  const cases = [];
  for (const count of [0, 1, 20, 64, 96, 128, 129]) cases.push(await sample(count));
  cases.push(await sample(128, "mixed"));
  process.stdout.write(JSON.stringify({max_tabs: census.MAX_TABS,
    concurrency: census.CONCURRENCY, cases}));
})().catch(() => {
  process.stderr.write("SYNTHETIC_COLLECTOR_ASSERTION_FAILED\n");
  process.exitCode = 1;
});