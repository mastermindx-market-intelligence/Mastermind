#!/usr/bin/env node
// pack_server.test.mjs — behavior tests for pack_server.mjs (TSHc F12/F24/F25).
// Run: node --test tools/mmos_team_server/pack_server.test.mjs   (node >= 23.6)
//
// Every case drives pack_server.mjs as a real child process against a fake
// source tree (fake vp, fake yaml, canned .ts modules) and a fake HOME, so
// containment, publication order, leftover cleanup, the packing lock and
// failure-log naming are exercised end to end — no monkeypatching.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const here = path.dirname(fileURLToPath(import.meta.url));
const PACK = path.join(here, "pack_server.mjs");
const ID = "server-0.1.7-fake";

if (parseInt(process.versions.node.split(".")[0], 10) < 23) {
  console.error(`SKIP: pack_server.mjs imports .ts natively; node >= 23.6 required, found ${process.versions.node}`);
  process.exit(77);
}

const CATALOG = {
  "playwright-core": "1.2.3", "node-pty": "1.0.0",
  "@ff-labs/fff-node": "2.0.0", "@cursor/sdk": "0.1.0",
};

function makeSourceTree(source) {
  const w = (rel, content, mode) => {
    const file = path.join(source, rel);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, content);
    if (mode) fs.chmodSync(file, mode);
  };
  // "type": "module" so the fake yaml .js and the .ts modules import as ESM,
  // exactly like the real T3 source root.
  w("package.json", JSON.stringify({ name: "t3", type: "module", packageManager: "vp@9.0.0" }) + "\n");
  w("pnpm-workspace.yaml", "packages:\n  - apps/*\n");
  w("apps/server/package.json", JSON.stringify({
    name: "server", version: "0.1.7-fake",
    dependencies: {
      "@ff-labs/fff-node": "catalog:", "playwright-core": "catalog:",
      "node-pty": "catalog:", "@cursor/sdk": "catalog:",
    },
  }) + "\n");
  w("apps/server/dist/bin.mjs", "console.log('server');\n");
  w("apps/server/dist/claude-history-worker.mjs", "console.log('worker');\n");
  w("apps/server/dist/client/index.html", "<html></html>\n");
  w("scripts/build-desktop-artifact.ts", `
export const STAGE_INSTALL_ARGS = ["install", "--prod", "--fake"];
export function createStagePatchedDependencies() { return {}; }
export function createStageWorkspaceConfig(cfg) { return { ...cfg }; }
export function resolveFffNativeDependencies(platform, arch, version) {
  return { "@ff-labs/fff-node": version };
}
`);
  w("scripts/lib/resolve-catalog.ts", `
export function resolveCatalogDependencies(record, catalog) {
  const out = {};
  for (const [name, spec] of Object.entries(record || {})) {
    out[name] = spec === "catalog:" ? (catalog[name] || "0.0.0") : spec;
  }
  return out;
}
`);
  w("scripts/lib/cli-external-packages.ts", `
export function selectCliRuntimeExternalDependencies(serverDeps) {
  const out = {};
  for (const name of ["playwright-core", "node-pty", "@cursor/sdk"]) {
    if (serverDeps[name]) out[name] = serverDeps[name];
  }
  return out;
}
`);
  w("apps/server/node_modules/yaml/dist/index.js", `
export default {
  parse() { return { catalog: ${JSON.stringify(CATALOG)} }; },
  stringify(value) { return JSON.stringify(value); },
};
`);
  // The fake package manager: builds exactly the hoisted production externals
  // pack_server.mjs requires, plus debris (a nested .bin, a .map, a
  // linux-x64 prebuild) the packer must strip. PACKTEST_VP_FAIL=1 forces a
  // failing install for the F24 failure-log tests.
  w("node_modules/.bin/vp", `#!/bin/sh
if [ -n "\${PACKTEST_VP_FAIL:-}" ]; then
  echo "fake vp: forced failure" >&2
  exit 3
fi
set -e
mkdir -p node_modules/playwright-core node_modules/node-pty/prebuilds/linux-x64 \\
  node_modules/@ff-labs/fff-node node_modules/@cursor/sdk node_modules/.bin
echo '{"name":"playwright-core","version":"1.2.3"}' > node_modules/playwright-core/package.json
echo 'export const pw = 1;' > node_modules/playwright-core/index.js
echo 'map' > node_modules/playwright-core/index.js.map
echo '{"name":"node-pty","version":"1.0.0"}' > node_modules/node-pty/package.json
echo binary > node_modules/node-pty/prebuilds/linux-x64/pty.node
echo '{"name":"@ff-labs/fff-node","version":"2.0.0"}' > node_modules/@ff-labs/fff-node/package.json
echo '{"name":"@cursor/sdk","version":"0.1.0"}' > node_modules/@cursor/sdk/package.json
printf '#!/bin/sh\\nexec true\\n' > node_modules/.bin/tool
exit 0
`, 0o755);
}

function fixture() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "packtest-"));
  const home = fs.mkdtempSync(path.join(tmp, "home-"));
  fs.mkdirSync(path.join(home, ".t3"), { mode: 0o755 }); // realpathSync target
  const source = path.join(tmp, "source");
  makeSourceTree(source);
  const root = path.join(tmp, "root");
  fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  fs.chmodSync(root, 0o700);
  return { tmp, home, source, root };
}

function pack(source, root, home, extraEnv = {}) {
  return spawnSync(process.execPath,
    [PACK, "--source", source, "--root", root, "--release-ID", ID], {
      encoding: "utf8", timeout: 120000,
      env: { ...process.env, HOME: home, ...extraEnv },
    });
}

const runtimeEntries = (root) => fs.readdirSync(path.join(root, "runtime"));
// pre-creating runtime/ by hand must still land the 0700 the packer requires
const makeRuntime = (root) => {
  fs.mkdirSync(path.join(root, "runtime"), { recursive: true });
  fs.chmodSync(path.join(root, "runtime"), 0o700);
};

test("success: packs, strips debris, writes a schema-2 receipt, cleans the lock", () => {
  const { tmp, home, source, root } = fixture();
  try {
    const run = pack(source, root, home);
    assert.equal(run.status, 0, `pack failed:\n${run.stderr}`);
    assert.match(run.stdout, /PACKED version=0\.1\.7-fake/);
    const receipt = JSON.parse(fs.readFileSync(path.join(root, "config", "server-runtime.json"), "utf8"));
    assert.equal(receipt.schemaVersion, 2);
    assert.equal(receipt.kind, "t3-packed-server-runtime");
    const dist = path.join(root, "runtime", ID, "dist");
    assert.ok(fs.statSync(path.join(dist, "node_modules", "playwright-core", "package.json")).isFile());
    assert.ok(fs.statSync(path.join(dist, "node_modules", "@cursor", "sdk", "package.json")).isFile());
    // debris the packer must strip
    assert.ok(!fs.existsSync(path.join(dist, "node_modules", ".bin")));
    assert.ok(!fs.existsSync(path.join(dist, "node_modules", "playwright-core", "index.js.map")));
    assert.ok(!fs.existsSync(path.join(dist, "node_modules", "node-pty", "prebuilds", "linux-x64")));
    // receipts inside the published tree, staging gone, lock released
    assert.ok(fs.statSync(path.join(root, "runtime", ID, "dist", "BUILD_RECEIPT.json")).isFile());
    assert.ok(fs.statSync(path.join(root, "runtime", ID, "file-digests.json")).isFile());
    assert.deepEqual(runtimeEntries(root), [ID]);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("containment: a root inside ~/.t3 is refused", () => {
  const { tmp, home, source } = fixture();
  try {
    const nested = path.join(home, ".t3", "nested", "root");
    fs.mkdirSync(nested, { recursive: true, mode: 0o700 });
    const run = pack(source, nested, home);
    assert.notEqual(run.status, 0);
    assert.match(run.stderr, /out of scope/);
    // nothing staged or published inside the refused root's runtime
    assert.ok(!fs.existsSync(path.join(nested, "runtime")));
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("F12: a conflicting config receipt refuses before anything is published", () => {
  const { tmp, home, source, root } = fixture();
  try {
    fs.mkdirSync(path.join(root, "config"), { mode: 0o700 });
    fs.writeFileSync(path.join(root, "config", "server-runtime.json"), "{}\n");
    const run = pack(source, root, home);
    assert.notEqual(run.status, 0);
    assert.match(run.stderr, /already exists/);
    assert.match(run.stderr, /inspect before retrying/);
    // runtime exists but holds no tree, no staging, no lock debris
    assert.deepEqual(runtimeEntries(root), []);
    // the pre-existing receipt is untouched
    assert.equal(fs.readFileSync(path.join(root, "config", "server-runtime.json"), "utf8"), "{}\n");
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("F12: a tree published without its receipt names the hand-recovery mv", () => {
  const { tmp, home, source, root } = fixture();
  try {
    makeRuntime(root);
    fs.mkdirSync(path.join(root, "runtime", ID, "dist"), { recursive: true });
    fs.mkdirSync(path.join(root, "config"), { mode: 0o700 });
    fs.writeFileSync(path.join(root, "config", "server-runtime.json.new"), "{}\n");
    const run = pack(source, root, home);
    assert.notEqual(run.status, 0);
    assert.match(run.stderr, /already exists/);
    assert.match(run.stderr, new RegExp(
      `finish by hand: mv .*server-runtime\\.json\\.new .*server-runtime\\.json`));
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("F25: leftovers from a killed run are cleaned and the pack succeeds", () => {
  const { tmp, home, source, root } = fixture();
  try {
    makeRuntime(root);
    fs.mkdirSync(path.join(root, "runtime", ".packing-deadrun", "x"), { recursive: true });
    fs.writeFileSync(path.join(root, "runtime", ".packing-deadrun", "x", "junk"), "half a pack\n");
    const run = pack(source, root, home);
    assert.equal(run.status, 0, `pack failed:\n${run.stderr}`);
    assert.match(run.stdout, /PACKED/);
    assert.ok(!fs.existsSync(path.join(root, "runtime", ".packing-deadrun")));
    assert.deepEqual(runtimeEntries(root), [ID]);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("F25: a stale lock from a dead packer is taken over", () => {
  const { tmp, home, source, root } = fixture();
  try {
    const gone = spawnSync("/usr/bin/true", []);
    makeRuntime(root);
    fs.writeFileSync(path.join(root, "runtime", ".packing.lock"), `${gone.pid}\n`);
    const run = pack(source, root, home);
    assert.equal(run.status, 0, `pack failed:\n${run.stderr}`);
    assert.match(run.stdout, /PACKED/);
    assert.deepEqual(runtimeEntries(root), [ID]);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("F25: a live packer's lock refuses a second run in one line", () => {
  const { tmp, home, source, root } = fixture();
  try {
    makeRuntime(root);
    fs.writeFileSync(path.join(root, "runtime", ".packing.lock"), `${process.pid}\n`);
    const run = pack(source, root, home);
    assert.notEqual(run.status, 0);
    assert.match(run.stderr, /another pack is already running for this root/);
    // the live holder's lock is untouched and nothing was staged
    assert.equal(fs.readFileSync(path.join(root, "runtime", ".packing.lock"), "utf8"),
      `${process.pid}\n`);
    assert.deepEqual(runtimeEntries(root), [".packing.lock"]);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("F24: a second failed install still writes its log; the error stays the install error", () => {
  const { tmp, home, source, root } = fixture();
  try {
    const first = pack(source, root, home, { PACKTEST_VP_FAIL: "1" });
    assert.notEqual(first.status, 0);
    assert.match(first.stderr, /production dependency install failed \(exit 3\)/);
    assert.match(first.stderr, /-install-failure\.log/);
    assert.ok(!first.stderr.includes("EEXIST"), `EEXIST leaked into the message:\n${first.stderr}`);
    const second = pack(source, root, home, { PACKTEST_VP_FAIL: "1" });
    assert.notEqual(second.status, 0);
    assert.match(second.stderr, /production dependency install failed \(exit 3\)/);
    assert.match(second.stderr, /-install-failure-2\.log/);
    assert.ok(!second.stderr.includes("EEXIST"), `EEXIST leaked into the message:\n${second.stderr}`);
    assert.ok(fs.statSync(path.join(root, "runtime", `${ID}-install-failure.log`)).isFile());
    assert.ok(fs.statSync(path.join(root, "runtime", `${ID}-install-failure-2.log`)).isFile());
    // neither failed run published a tree or left staging debris
    assert.ok(!fs.existsSync(path.join(root, "runtime", ID)));
    assert.ok(!runtimeEntries(root).some((name) => name.startsWith(".packing-")));
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});
