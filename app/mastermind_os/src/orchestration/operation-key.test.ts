import { describe, expect, it } from "vitest";
import {
  canonicalJson,
  intentIdForOperationKey,
  operationKeyForLaunch,
  requestRefForOperationKey,
  sha256Hex,
  type LaunchKeyMaterial,
} from "./operation-key";

const KEY_PATTERN = /^[a-z0-9][a-z0-9-]{2,95}$/;

const BASE: LaunchKeyMaterial = {
  principalScope: "scope-A",
  workstream: "WS:ALPHA",
  department: "research",
  execution_profile: "research_only",
  objective: "Ship the launch binding",
  priority: 0,
};

describe("T1 operation key", () => {
  it("is deterministic for the same material", () => {
    expect(operationKeyForLaunch(BASE)).toBe(operationKeyForLaunch({ ...BASE }));
  });

  it("changes when any hashed field changes", () => {
    const baseKey = operationKeyForLaunch(BASE);
    const variants: LaunchKeyMaterial[] = [
      { ...BASE, principalScope: "scope-B" },
      { ...BASE, workstream: "WS:BETA" },
      { ...BASE, department: "opsdesk" },
      { ...BASE, execution_profile: "bounded_code_change" },
      { ...BASE, objective: "A different objective" },
      { ...BASE, priority: 1 },
      { ...BASE, allowed_write_paths: ["src/example.ts"] },
      { ...BASE, validation: { git_diff_check: true } },
      { ...BASE, attempt_limit: 2 },
    ];
    const keys = new Set(variants.map((material) => operationKeyForLaunch(material)));
    expect(keys.size).toBe(variants.length);
    expect(keys.has(baseKey)).toBe(false);
  });

  it("excludes OwnerContext.generation from the key", () => {
    const withGenA = { ...BASE, generation: "gen-1" };
    const withGenB = { ...BASE, generation: "gen-2" };
    expect(operationKeyForLaunch(withGenA)).toBe(operationKeyForLaunch(BASE));
    expect(operationKeyForLaunch(withGenB)).toBe(operationKeyForLaunch(BASE));
  });

  it("has length 52 and matches the ingress operation_key pattern", () => {
    const key = operationKeyForLaunch(BASE);
    expect(key).toHaveLength(52);
    expect(key.startsWith("mmos-launch-")).toBe(true);
    expect(KEY_PATTERN.test(key)).toBe(true);
  });

  it("canonicalJson sorts keys at every depth and drops undefined", () => {
    expect(canonicalJson({ b: 1, a: 2 })).toBe('{"a":2,"b":1}');
    expect(canonicalJson({ b: { z: 1, a: 2 }, a: 0 })).toBe(
      '{"a":0,"b":{"a":2,"z":1}}',
    );
    expect(canonicalJson({ a: 1, b: undefined })).toBe('{"a":1}');
    expect(canonicalJson({ a: 1 })).toBe(canonicalJson({ b: undefined, a: 1 }));
    expect(canonicalJson(["b", "a"])).toBe('["b","a"]');
  });
});

describe("T2 intent-id vector", () => {
  it("pins req-1fe9203648cf225b24e729dba8fa9ad7 and auto-ed35746b0a835165994569a8dc713270 for the all-zero launch key", () => {
    const PINNED_KEY = "mmos-launch-" + "0".repeat(40);
    expect(requestRefForOperationKey(PINNED_KEY)).toBe(
      "req-1fe9203648cf225b24e729dba8fa9ad7",
    );
    expect(intentIdForOperationKey(PINNED_KEY)).toBe(
      "auto-ed35746b0a835165994569a8dc713270",
    );
  });

  it("matches echo -n test | shasum -a 256", () => {
    // Independently verified: `echo -n test | shasum -a 256`
    expect(sha256Hex("test")).toBe(
      "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    );
  });
});
