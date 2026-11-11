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
if (root === fs.realpathSync(path.join(os.homedir(), ".t3"))) throw new Error("~/.t3 is out of scope");
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
if (fs.existsSync(target) || fs.existsSync(configPath)) {
  throw new Error("packed runtime or its receipt already exists; inspect before retrying");
}
const stage = fs.mkdtempSync(path.join(runtime, ".packing-"));
let activated = false;
try {
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
    const where = path.join(runtime, `${id}-install-failure.log`);
    fs.writeFileSync(where, install.stdout + install.stderr, { mode: 0o600, flag: "wx" });
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
    schemaVersion: 1, kind: "t3-packed-server-runtime",
    version: serverPackage.version, sourceRevision: "0770446 + text-delta patch",
    sourceAtBuild: source, buildCommand: "vp run --filter t3 build",
    productionDependencyCommand: STAGE_INSTALL_ARGS.join(" "),
    productionDependencies: dependencies,
    buildDir: finalDist, serverBin: path.join(finalDist, "bin.mjs"), stateDbPath: path.join(root, "home/state/statev2.sqlite"),
    platform: "darwin", architecture: "arm64",
    runtimeAssets: "bundled server, web client, workers, production externals, optional native monitor",
  };
  fs.writeFileSync(path.join(dist, "BUILD_RECEIPT.json"), JSON.stringify(receipt, null, 2) + "\n", { mode: 0o600 });
  fs.writeFileSync(path.join(stage, "file-digests.json"), JSON.stringify(files, null, 2) + "\n", { mode: 0o600 });
  fs.renameSync(stage, target);
  activated = true;
  fs.writeFileSync(configPath, JSON.stringify(receipt, null, 2) + "\n", { mode: 0o600, flag: "wx" });
  console.log(`PACKED version=${serverPackage.version} server=${receipt.serverBin} files=${files.length}`);
} finally {
  if (!activated) fs.rmSync(stage, { recursive: true, force: true });
}

// Rename has no symlink traversal semantics and all stages remain in private
// current-user-owned runtime directories. This helper is never executed from
// a downloaded archive.
