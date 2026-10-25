// The module hook runs in a worker that copies the environment at process
// start. RAKAZO_PIN_ROOT has to be present before that process starts.
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildExecutionEnv, ensureDependencies, ensurePinCheckout } from "./qualify.mjs";

const registry = process.env.npm_config_registry ?? "";
const userconfig = process.env.npm_config_userconfig ?? "";
const canaryConfig = registry.includes("127.0.0.1:9")
  || registry.includes("canary-registry")
  || userconfig.includes("canary-npmrc");
if (process.env.NODE_OPTIONS || canaryConfig) {
  console.error("launcher-env leaked");
  process.exit(1);
}
console.log("launcher-env NODE_OPTIONS absent npm-config-canary absent");

const root = ensurePinCheckout();
ensureDependencies();
const child = spawnSync(
  process.execPath,
  ["--experimental-strip-types", "--import", "./register.mjs", "--test", "qualify.test.mjs"],
  {
    cwd: path.dirname(fileURLToPath(import.meta.url)),
    env: buildExecutionEnv({ pinRoot: root, source: root }),
    stdio: "inherit",
    timeout: 240_000,
  },
);
if (child.error) {
  console.error(child.error.message);
}
process.exit(child.status ?? 1);
