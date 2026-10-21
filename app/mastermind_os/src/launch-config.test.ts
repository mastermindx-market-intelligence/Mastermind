import { describe, expect, it } from "vitest";
import { decodeLaunchBindingConfig } from "./launch-config";
const manifest = { v: 1, workstream: "WS:CONFIG-FIXTURE", priority: 5,
  projects: [{ ref: "executive-infrastructure", label: "Fixture department" }],
  profiles: [{ ref: "research_only", label: "Research" }] };
describe("immutable operator launch configuration", () => {
  it("supplies exact choices and work identity without runtime defaults", () => {
    const config = decodeLaunchBindingConfig(JSON.stringify(manifest))!;
    expect(config.workstream).toBe(manifest.workstream);
    expect(config.projects).toEqual(manifest.projects);
    expect(Object.isFrozen(config.projects[0])).toBe(true);
    expect(decodeLaunchBindingConfig(undefined)).toBeNull();
  });
  it.each([{ ...manifest, token: "unaccepted" }, { ...manifest, workstream: "JOB-013" },
    { ...manifest, priority: 1.5 }, { ...manifest, projects: [] },
    { ...manifest, profiles: [{ ref: "arbitrary", label: "No" }] },
    { ...manifest, projects: [...manifest.projects, ...manifest.projects] },
    { ...manifest, attemptLimit: "1" }, { ...manifest, allowedWritePaths: ["src/file.ts"] }])(
    "fails closed on malformed or inconsistent manifest", (input) => {
      expect(decodeLaunchBindingConfig(JSON.stringify(input))).toBeNull();
    });
  it("requires explicit confined paths and validation for bounded code changes", () => {
    const bounded = { ...manifest, profiles: [{ ref: "bounded_code_change", label: "Bounded" }],
      allowedWritePaths: ["src/file.ts"], validation: { git_diff_check: true } };
    expect(decodeLaunchBindingConfig(JSON.stringify(bounded))).not.toBeNull();
    for (const path of ["/tmp/file", "../file", ".git/config", "src/../file"]) {
      expect(decodeLaunchBindingConfig(JSON.stringify({ ...bounded, allowedWritePaths: [path] }))).toBeNull();
    }
  });
});
