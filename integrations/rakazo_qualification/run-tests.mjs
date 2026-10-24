// The module hook runs in a worker that copies the environment at process
// start. RAKAZO_PIN_ROOT has to be present before that process starts.
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildExecutionEnv, ensureDependencies, ensurePinCheckout } from "./qualify.mjs";

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
