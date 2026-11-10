#!/usr/bin/env node
/** Qualify the installed upstream adapter against an ephemeral loopback fixture.
 * No Hermes server, Paperclip company, bot, provider or credential store is called.
 * This is a transport/component test, never a live-agent migration receipt.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { pathToFileURL } from "node:url";

const args = process.argv.slice(2);
if (args.length !== 4 || args[0] !== "--adapter-root" || args[2] !== "--expected-execute-sha256" ||
    !path.isAbsolute(args[1]) || !/^[0-9a-f]{64}$/.test(args[3])) {
  throw new Error("explicit installed adapter root and inspected execute SHA-256 required");
}
const root = args[1];
const executable = path.join(root, "dist/gateway/server/execute.js");
const digest = bytes => createHash("sha256").update(bytes).digest("hex");
const before = digest(await readFile(executable));
assert.equal(before, args[3], "installed adapter changed before qualification");
const pkg = JSON.parse(await readFile(path.join(root, "package.json"), "utf8"));
const adapter = await import(pathToFileURL(executable).href);
const checks = [];
const keyBase = { strategy: "issue", companyId: "company-fixture", agentId: "agent-fixture", runId: "pc-run-1", issueId: "issue-a" };
assert.equal(adapter.resolveSessionKey(keyBase), adapter.resolveSessionKey({ ...keyBase, runId: "pc-run-2" }));
assert.notEqual(adapter.resolveSessionKey(keyBase), adapter.resolveSessionKey({ ...keyBase, issueId: "issue-b" }));
assert.equal(adapter.resolveSessionKey({ ...keyBase, strategy: "none" }), null);
checks.push("issue_keys_are_stable_per_issue_and_separate_across_issues");
let serial = 0;
const originalFetch = globalThis.fetch;

async function runCase(mode, overrides = {}) {
  const n = ++serial;
  const requests = [], logs = [], meta = [];
  const nativeRun = `native-fixture-${n}`;
  const prefix = "/p/qualification";
  let stopped = false;
  let dispatched = 0;
  const server = http.createServer(async (req, res) => {
    let text = "";
    for await (const chunk of req) {
      text += chunk;
      if (text.length > 65536) { req.destroy(); return; }
    }
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch { res.writeHead(400).end(); return; }
    requests.push({ method: req.method, path: req.url, headers: { ...req.headers }, body });
    const json = (status, value) => {
      res.writeHead(status, { "content-type": "application/json" }); res.end(JSON.stringify(value));
    };
    if (req.method === "POST" && req.url === `${prefix}/v1/runs`) {
      if (mode === "create_disconnect") { req.socket.destroy(); return; }
      if (mode === "auth_denied") { json(401, { error: "fixture denial" }); return; }
      if (mode === "missing_run") { json(200, { status: "queued" }); return; }
      json(200, { run_id: nativeRun, status: "running" }); return;
    }
    if (req.method === "POST" && req.url === `${prefix}/v1/runs/${nativeRun}/stop`) {
      stopped = true; json(200, { run_id: nativeRun, status: "stopped" }); return;
    }
    if (req.url === `${prefix}/v1/runs/${nativeRun}/events`) {
      // Force the incumbent original-run status fallback, not a replacement launch.
      json(503, { error: "fixture stream unavailable" }); return;
    }
    if (req.method === "GET" && req.url === `${prefix}/v1/runs/${nativeRun}`) {
      const status = stopped ? "stopped" : mode === "timeout" ? "running" : mode === "cancelled" ? "cancelled" : "completed";
      json(200, { run_id: nativeRun, status, session_id: "existing-hermes-session",
                 output: status === "completed" ? "fixture transport result" : "fixture pending or stopped" }); return;
    }
    json(404, { error: "fixture route not found" });
  });
  await new Promise((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
  const address = server.address();
  const origin = `http://127.0.0.1:${address.port}`;
  globalThis.fetch = (input, init) => {
    const url = new URL(typeof input === "string" || input instanceof URL ? input : input.url);
    if (url.origin !== origin || !url.pathname.startsWith(`${prefix}/v1/runs`)) {
      throw new Error("qualification refused non-fixture network target");
    }
    return originalFetch(input, init);
  };
  const ctx = {
    runId: `paperclip-fixture-${n}`,
    agent: { id: "agent-fixture", companyId: "company-fixture", name: "Fixture only" },
    runtime: {}, context: { issueId: "issue-fixture", taskId: "issue-fixture" },
    config: { apiBaseUrl: `${origin}${prefix}`, apiKey: "fixture-secret-not-a-real-key",
      timeoutSec: mode === "timeout" ? 0.08 : 2, pollIntervalMs: 250, eventReconnectMs: 250,
      sessionKeyStrategy: "none", payloadTemplate: { input: "fixture input", session_id: "existing-hermes-session" },
      ...overrides },
    onLog: async (_channel, text) => { logs.push(text); },
    onMeta: async value => { meta.push(value); },
    onDispatch: () => { dispatched++; },
  };
  try {
    const result = await adapter.execute(ctx);
    const creates = requests.filter(x => x.method === "POST" && x.path === `${prefix}/v1/runs`);
    assert.equal(creates.length, 1, "no implicit duplicate create");
    assert.equal(dispatched, 1);
    assert.equal(creates[0].headers["idempotency-key"], ctx.runId);
    assert.equal(creates[0].body.session_id, "existing-hermes-session", "explicit original session retained");
    assert.equal(creates[0].headers.authorization, "Bearer fixture-secret-not-a-real-key");
    assert.ok(!logs.join("").includes("fixture-secret-not-a-real-key"), "secret not logged");
    return { result, requests, creates, logs, nativeRun, prefix, meta };
  } finally {
    globalThis.fetch = originalFetch;
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
}

const success = await runCase("success", { headers: { Authorization: "Bearer untrusted-override", "Idempotency-Key": "wrong-key" } });
assert.equal(success.result.exitCode, 0);
assert.equal(success.result.resultJson.run_id, success.nativeRun);
assert.equal(success.result.sessionParams.hermesSessionId, "existing-hermes-session");
assert.ok(success.requests.some(x => x.method === "GET" && x.path.endsWith(success.nativeRun)));
checks.push("explicit_native_session_and_profile_route_are_preserved");
checks.push("stream_failure_recovers_original_run_without_duplicate_create");
checks.push("critical_headers_cannot_be_overridden_and_fixture_secret_is_redacted");

const cancelled = await runCase("cancelled");
assert.equal(cancelled.result.exitCode, 1);
assert.equal(cancelled.result.errorCode, "hermes_gateway_cancelled");
checks.push("native_cancellation_is_not_reported_as_success");

const timeout = await runCase("timeout");
assert.equal(timeout.result.timedOut, true);
assert.equal(timeout.result.resultJson.run_id, timeout.nativeRun);
assert.equal(timeout.requests.filter(x => x.method === "POST" && x.path.endsWith("/stop")).length, 1);
checks.push("timeout_stops_and_reads_only_the_original_run");

const denied = await runCase("auth_denied");
assert.equal(denied.result.exitCode, 1);
assert.equal(denied.result.errorCode, "hermes_gateway_auth_failed");
assert.equal(denied.requests.length, 1);
checks.push("authentication_denial_is_terminal_without_fallback_or_replay");

const disconnected = await runCase("create_disconnect");
assert.equal(disconnected.result.exitCode, 1);
assert.equal(disconnected.requests.length, 1);
checks.push("lost_create_response_is_not_automatically_replayed");

const malformed = await runCase("missing_run");
assert.equal(malformed.result.exitCode, 1);
assert.equal(malformed.result.errorCode, "hermes_gateway_protocol_error");
assert.equal(malformed.requests.length, 1);
checks.push("missing_original_run_identity_is_not_accepted");

assert.equal(digest(await readFile(executable)), before, "installed adapter changed during qualification");
console.log(JSON.stringify({ schema: "mastermind.paperclip_hermes_transport_qualification.v1", status: "PASS",
  adapter_version: pkg.version, execute_sha256: before, checks,
  fixture_http_cases: serial, live_hermes_requests: 0, live_paperclip_mutations: 0, model_calls: 0,
  qualification_scope: "INSTALLED_ADAPTER_WITH_EPHEMERAL_LOOPBACK_GATEWAY_FIXTURE",
  native_bot_adoption: "UNPROVEN", mission_accepted: false }));
