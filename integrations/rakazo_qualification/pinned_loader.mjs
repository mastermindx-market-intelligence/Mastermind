import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const qualificationDir = path.dirname(fileURLToPath(import.meta.url));

function requirePinRoot() {
  const root = process.env.RAKAZO_PIN_ROOT;
  if (!root) throw new Error("RAKAZO_PIN_ROOT is not set");
  return root;
}

export async function resolve(specifier, context, nextResolve) {
  const parent = context.parentURL ? fileURLToPath(context.parentURL) : "";
  if (
    specifier === "zod" ||
    specifier === "croner" ||
    specifier === "@orpc/contract" ||
    specifier.startsWith("@orpc/")
  ) {
    return nextResolve(specifier, {
      ...context,
      parentURL: pathToFileURL(path.join(qualificationDir, "package.json")).href,
    });
  }

  const root = process.env.RAKAZO_PIN_ROOT || "";
  if (specifier === "@rakazo/contracts") {
    const pinned = requirePinRoot();
    return {
      url: pathToFileURL(path.join(pinned, "packages/contracts/src/index.ts")).href,
      shortCircuit: true,
    };
  }
  if (specifier === "@rakazo/core/node/desktop-runtime") {
    const pinned = requirePinRoot();
    return {
      url: pathToFileURL(path.join(pinned, "packages/core/src/node/desktop-runtime.ts")).href,
      shortCircuit: true,
    };
  }
  if (
    root &&
    parent.endsWith(`${path.sep}packages${path.sep}db${path.sep}src${path.sep}computers.ts`)
  ) {
    if (specifier === "./client.js") {
      return {
        url: pathToFileURL(path.join(qualificationDir, "db_client_stub.mjs")).href,
        shortCircuit: true,
      };
    }
    if (specifier === "./row-security.js") {
      return {
        url: pathToFileURL(path.join(qualificationDir, "row_security_stub.mjs")).href,
        shortCircuit: true,
      };
    }
  }
  if (root && specifier.endsWith(".js") && (parent === root || parent.startsWith(`${root}${path.sep}`))) {
    const candidate = path.resolve(path.dirname(parent), specifier.slice(0, -3) + ".ts");
    if (existsSync(candidate)) {
      return { url: pathToFileURL(candidate).href, shortCircuit: true };
    }
  }
  return nextResolve(specifier, context);
}
