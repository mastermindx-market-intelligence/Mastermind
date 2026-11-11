#!/usr/bin/env node
/** Pack a complete build of server 0.1.7, with its maintained production externals.
 * Run after `vp run --filter t3 build` in the trusted, pinned source tree.
 * node pack_server.mjs --source SOURCE_ROOT --root SERVER_ROOT --release-ID ID
 */
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { pathToFileURL } from "node:url";

// Attack finding 4: a CLI refusal must be ONE operator-readable line. Every
// `throw` below (a designed refusal) would otherwise escape as a multi-line
// Node stack trace. This handler prints the message with a pack_server:
// prefix and exits 1 — the runbook's "one line" is then literally true.
process.on("uncaughtException", (err) => {
  console.error(`pack_server: ${err.message}`);
  process.exit(1);
});

const args = process.argv.slice(2);
const flag = (name) => args[args.indexOf(`--${name}`) + 1];
if (args.length !== 6 || process.platform !== "darwin" || process.arch !== "arm64" ||
    !flag("source") || !flag("root") || !flag("release-ID")) {
  throw new Error("usage: --source SOURCE --root ROOT --release-ID ID (darwin-arm64)");
}
const source = fs.realpathSync(flag("source"));
const root = fs.realpathSync(flag("root"));
const id = flag("release-ID");
if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,60}$/.test(id)) throw new Error("unsafe release ID");
function privateDir(dir) {
  const info = fs.lstatSync(dir);
  if (!info.isDirectory() || info.uid !== process.getuid() || (info.mode & 0o077)) {
    throw new Error(`private current-user-owned mode 0700 directory required: ${dir}`);
  }
}
privateDir(root);
// Scope is containment, not equality: a server root nested INSIDE ~/.t3 is as
// out of scope as ~/.t3 itself (attack finding 7).
const realT3 = fs.realpathSync(path.join(os.homedir(), ".t3"));
if (root === realT3 || root.startsWith(realT3 + path.sep)) throw new Error("~/.t3 is out of scope");
for (const name of ["apps/server/dist/bin.mjs", "apps/server/dist/claude-history-worker.mjs",
  "apps/server/dist/client/index.html", "apps/server/package.json", "package.json",
  "pnpm-workspace.yaml", "scripts/build-desktop-artifact.ts", "scripts/lib/cli-external-packages.ts"]) {
  if (!fs.statSync(path.join(source, name)).isFile()) throw new Error(`missing built source input: ${name}`);
}
const runtime = path.join(root, "runtime");
fs.mkdirSync(runtime, { recursive: true, mode: 0o700 });
privateDir(runtime);
const configDir = path.join(root, "config");
fs.mkdirSync(configDir, { recursive: true, mode: 0o700 });
privateDir(configDir);
const target = path.join(runtime, id);
const configPath = path.join(configDir, "server-runtime.json");
const configTmp = configPath + ".new";
// F25: one packer at a time per root. A wx lock file holding the pid; a
// lock left by a KILLED run is recognized (pid gone) and taken over, a lock
// held by a LIVE process refuses in one line.
const lockPath = path.join(runtime, ".packing.lock");
function packLockHeldByLiveProcess() {
  let holder = 0;
  try { holder = parseInt(fs.readFileSync(lockPath, "utf8").trim(), 10); } catch { /* unreadable */ }
  if (!Number.isInteger(holder) || holder <= 0) return false;
  try { process.kill(holder, 0); return true; } // alive and ours
  catch (err) { if (err.code === "EPERM") return true; /* ESRCH: dead */ return false; }
}
function acquirePackLock() {
  try {
    const fd = fs.openSync(lockPath, "wx", 0o600);
    fs.writeFileSync(fd, String(process.pid) + "\n");
    fs.closeSync(fd);
    return;
  } catch (err) {
    if (err.code !== "EEXIST") throw err;
  }
  if (packLockHeldByLiveProcess()) {
    throw new Error("another pack is already running for this root; let it finish before retrying");
  }
  // Dead holder: take over by ATOMIC rename (attack finding 10). Two racing
  // takers cannot both win — the loser's rename hits ENOENT and its next
  // open hits the winner's lock. The lock path itself is NEVER unlinked:
  // that could remove a lock a concurrent packer had just legitimately
  // re-acquired in the unlink window.
  const tombstone = `${lockPath}.dead-${process.pid}`;
  try {
    fs.renameSync(lockPath, tombstone);
  } catch (err) {
    if (err.code === "ENOENT") {
      throw new Error("another pack acquired the packing lock while we were taking it over; re-run pack");
    }
    throw err;
  }
  try { fs.unlinkSync(tombstone); } catch { /* already gone */ }
  try {
    const fd = fs.openSync(lockPath, "wx", 0o600);
    fs.writeFileSync(fd, String(process.pid) + "\n");
    fs.closeSync(fd);
  } catch (err) {
    if (err.code === "EEXIST") {
      throw new Error("another pack acquired the packing lock while we were taking it over; re-run pack");
    }
    throw err;
  }
}
acquirePackLock();
// Everything from here on runs under the lock; the finally releases it no
// matter which refusal fires, so a refused run leaves no lock debris.
let stage = "";
let activated = false;
try {
  // Leftovers with this packer's own prefix are debris from a killed run (we
  // hold the lock, so no live packer owns them) — remove before working.
  // Takeover tombstones (.packing.lock.dead-*) are always debris too: the
  // rename that created one already orphaned the lock itself.
  for (const name of fs.readdirSync(runtime)) {
    if (name.startsWith(".packing.lock.dead-")) {
      fs.rmSync(path.join(runtime, name), { force: true });
      continue;
    }
    if (name.startsWith(".packing-")) {
      const leftover = path.join(runtime, name);
      if (!fs.lstatSync(leftover).isDirectory()) {
        throw new Error(`unexpected runtime leftover (not a directory): ${leftover}`);
      }
      fs.rmSync(leftover, { recursive: true, force: true });
    }
  }
  function refuseExisting() {
    let hint = "inspect before retrying";
    if (fs.existsSync(target) && !fs.existsSync(configPath) && fs.existsSync(configTmp)) {
      hint = `a previous pack published ${target} but could not install its config receipt; ` +
        `finish by hand: mv ${configTmp} ${configPath}`;
    }
    throw new Error(`packed runtime or its receipt already exists; ${hint}`);
  }
  if (fs.existsSync(target) || fs.existsSync(configPath)) refuseExisting();
  // F24: a failed install must leave its log AND name it — the old `wx` write
  // failed with EEXIST on the second failure, masking the install error itself.
  function writeFailureLog(base, content) {
    const candidates = [base];
    for (let n = 2; n <= 100; n++) candidates.push(base.replace(/\.log$/, `-${n}.log`));
    for (const candidate of candidates) {
      try {
        fs.writeFileSync(candidate, content, { mode: 0o600, flag: "wx" });
        return candidate;
      } catch (err) {
        if (err.code !== "EEXIST") throw err;
      }
    }
    throw new Error(`cannot write a unique failure log beside ${base}`);
  }
  stage = fs.mkdtempSync(path.join(runtime, ".packing-"));
  const dist = path.join(stage, "dist");
  const deps = path.join(stage, "production");
  fs.cpSync(path.join(source, "apps/server/dist"), dist, { recursive: true });
  fs.mkdirSync(deps, { mode: 0o700 });
  const load = async (name) => import(pathToFileURL(path.join(source, name)).href);
  const {
    createStagePatchedDependencies,
    createStageWorkspaceConfig,
    resolveFffNativeDependencies,
    STAGE_INSTALL_ARGS,
  } = await load("scripts/build-desktop-artifact.ts");
  const { resolveCatalogDependencies } = await load("scripts/lib/resolve-catalog.ts");
  const { selectCliRuntimeExternalDependencies } = await load("scripts/lib/cli-external-packages.ts");
  const yaml = (await import(pathToFileURL(path.join(source,
    "apps/server/node_modules/yaml/dist/index.js")).href)).default;
  const workspace = yaml.parse(fs.readFileSync(path.join(source, "pnpm-workspace.yaml"), "utf8"));
  const catalog = workspace.catalog || {};
  const serverPackage = JSON.parse(fs.readFileSync(path.join(source, "apps/server/package.json")));
  const rootPackage = JSON.parse(fs.readFileSync(path.join(source, "package.json")));
  const resolved = (record) => resolveCatalogDependencies(record, catalog, "apps/server");
  const serverDeps = resolved(serverPackage.dependencies);
  const fffVersion = serverDeps["@ff-labs/fff-node"];
  if (!fffVersion) throw new Error(" maintained fff version is required");
  const dependencies = {
    ...selectCliRuntimeExternalDependencies(serverDeps),
    ...resolveFffNativeDependencies("mac", "arm64", fffVersion),
  };
  const patches = createStagePatchedDependencies(workspace.patchedDependencies || {}, dependencies);
  const stageWorkspace = {
    ...createStageWorkspaceConfig({ platform: "mac", arch: "arm64",
      allowBuilds: workspace.allowBuilds || {}, patchedDependencies: patches,
      overrides: resolved(workspace.overrides || {}) }),
    nodeLinker: "hoisted",
    publicHoistPattern: ["@cursor/sdk-*"],
    minimumReleaseAgeExclude: workspace.minimumReleaseAgeExclude || [],
    strictPeerDependencies: workspace.strictPeerDependencies ?? true,
    peerDependencyRules: workspace.peerDependencyRules || {},
    permissions: workspace.permissions || {},
  };
  fs.writeFileSync(path.join(deps, "package.json"), JSON.stringify({
    name: "tsh-packed-server", version: serverPackage.version, private: true,
    packageManager: rootPackage.packageManager, type: "module", dependencies,
  }, null, 2) + "\n");
  fs.writeFileSync(path.join(deps, "pnpm-workspace.yaml"), yaml.stringify(stageWorkspace));
  if (Object.keys(patches).length) fs.cpSync(path.join(source, "patches"), path.join(deps, "patches"), { recursive: true });
  console.log(`PACKInstallingProductionExternals=${Object.keys(dependencies).length}`);
  const install = spawnSync(path.join(source, "node_modules/.bin/vp"), STAGE_INSTALL_ARGS, {
    cwd: deps, env: { ...process.env, CI: "1" }, encoding: "utf8", timeout: 900000,
    maxBuffer: 2 * 1024 * 1024,
  });
  if (install.error) throw install.error;
  if (install.status !== 0) {
    const where = writeFailureLog(path.join(runtime, `${id}-install-failure.log`),
      install.stdout + install.stderr);
    throw new Error(`production dependency install failed (exit ${install.status}): ${where}`);
  }
  const nm = path.join(deps, "node_modules");
  for (const name of [".pnpm", ".modules.yaml", ".pnpm-workspace-state-v1.json", ".bin",
    "package.json", "pnpm-workspace.yaml", "pnpm-lock.yaml", "patches"]) {
    fs.rmSync(path.join(deps, name), { recursive: true, force: true });
  }
  // The maintained hoisted install contains real files; remove pnpm metadata
  // and every nested .bin, retaining only the runtime-essential externals.
  function validateTree(dir, nested = false) {
    for (const item of fs.readdirSync(dir, withFileTypesOption())) {
      const file = path.join(dir, item.name);
      if (item.isSymbolicLink()) throw new Error(`symlink to source/pnpm refused: ${file}`);
      if (item.isDirectory()) {
        if (item.name === ".bin") { fs.rmSync(file, { recursive: true, force: true }); continue; }
        validateTree(file, nested || item.name.endsWith(".node"));
      } else if (item.name.endsWith(".map")) fs.unlinkSync(file);
    }
  }
  function withFileTypesOption() { return { withFileTypes: true }; }
  validateTree(nm);
  const prebuilds = path.join(nm, "node-pty/prebuilds");
  if (fs.existsSync(prebuilds)) {
    for (const name of fs.readdirSync(prebuilds)) {
      if (name !== "darwin-arm64") fs.rmSync(path.join(prebuilds, name), { recursive: true, force: true });
    }
  }
  for (const name of ["playwright-core/package.json", "node-pty/package.json",
    "@ff-labs/fff-node/package.json", "@cursor/sdk/package.json"]) {
    if (!fs.statSync(path.join(nm, name)).isFile()) throw new Error(`missing production external: ${name}`);
  }
  fs.renameSync(nm, path.join(dist, "node_modules"));
  fs.rmSync(deps, { recursive: true, force: true });
  const files = [];
  function hashes(dir, base = dir) {
    for (const item of fs.readdirSync(dir, withFileTypesOption()).sort((a, b) => a.name.localeCompare(b.name))) {
      const file = path.join(dir, item.name);
      if (item.isDirectory()) hashes(file, base);
      else if (item.isFile()) {
        const bytes = fs.readFileSync(file);
        files.push({ path: path.relative(base, file), bytes: bytes.length,
          sha256: createHash("sha256").update(bytes).digest("hex") });
      } else throw new Error(`non-regular runtime asset: ${file}`);
    }
  }
  hashes(dist);
  const finalDist = path.join(target, "dist");
  const receipt = {
    schemaVersion: 2, kind: "t3-packed-server-runtime",
    version: serverPackage.version, sourceRevision: "0770446 + text-delta patch",
    sourceAtBuild: source, buildCommand: "vp run --filter t3 build",
    productionDependencyCommand: STAGE_INSTALL_ARGS.join(" "),
    productionDependencies: dependencies,
    buildDir: finalDist, serverBin: path.join(finalDist, "bin.mjs"), stateDbPath: path.join(root, "home/userdata/statev2.sqlite"),
    platform: "darwin", architecture: "arm64",
    runtimeAssets: "bundled server, web client, workers, production externals, optional native monitor",
  };
  fs.writeFileSync(path.join(dist, "BUILD_RECEIPT.json"), JSON.stringify(receipt, null, 2) + "\n", { mode: 0o600 });
  fs.writeFileSync(path.join(stage, "file-digests.json"), JSON.stringify(files, null, 2) + "\n", { mode: 0o600 });
  // F12: everything that can fail while writing is done BEFORE the single
  // publishing rename, so a refusal publishes nothing. The config receipt
  // (the file the resolver reads) is staged first and moved into place with a
  // rename after the tree lands; a crash between the two renames leaves the
  // tree published, the config receipt one `mv` away, and the next run's
  // refusal says exactly that.
  try { fs.unlinkSync(configTmp); } catch (e) { if (e.code !== "ENOENT") throw e; }
  fs.writeFileSync(configTmp, JSON.stringify(receipt, null, 2) + "\n", { mode: 0o600 });
  fs.renameSync(stage, target);
  activated = true;
  try {
    fs.renameSync(configTmp, configPath);
  } catch (err) {
    throw new Error(`packed runtime published at ${target} but its config receipt could not be installed: ${err.message}; finish by hand: mv ${configTmp} ${configPath}`);
  }
  console.log(`PACKED version=${serverPackage.version} server=${receipt.serverBin} files=${files.length}`);
} finally {
  if (!activated && stage) fs.rmSync(stage, { recursive: true, force: true });
  try { fs.unlinkSync(lockPath); } catch { /* holder handover */ }
}

// Rename has no symlink traversal semantics and all stages remain in private
// current-user-owned runtime directories. This helper is never executed from
// a downloaded archive.
