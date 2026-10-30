// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MetaCeoOffice } from "./MetaCeoOffice";
import { projectOffice, type OfficeInput, type ProjectionContext } from "./projection";
import { decodeMission } from "../mission";
import currentMission from "../fixtures/mission-v2-current-128c46f6.json";

afterEach(cleanup);
const selected = { workRef: "WS:ONE", rootJobId: "JOB-1" };
const bound: ProjectionContext = {
  authGeneration: 5,
  selection: selected,
  sessionRef: `fabric_attempt:${"a".repeat(64)}`,
  bindingGeneration: JSON.stringify(["executive-native-session", "principal", "epoch:1"]),
  revisions: { mission: "rev:1", programs: null, result: null, conversation: null },
};

function source(ctx: ProjectionContext, freshness: "CURRENT" | "STALE" = "CURRENT"): OfficeInput {
  const raw = structuredClone(currentMission);
  raw.read_state = {
    state: "CURRENT", reason_codes: [], usable_sections: raw.read_state.usable_sections,
  };
  return {
    programs: null, result: null, conversation: null,
    mission: {
      context: ctx,
      source: {
        owner: "EXECUTIVE_OS", ref: "mission:JOB-1", revision: "rev:1",
        observed_at: "2026-10-30T12:00:00Z", state: freshness, coverage: "COMPLETE",
      },
      value: decodeMission(raw, selected)!,
    },
  };
}
const native = <button type="button">Existing native continuation</button>;
function show(context: ProjectionContext, observed?: OfficeInput, withNative = true) {
  const projection = projectOffice(observed ?? source(context), context);
  return render(
    <MetaCeoOffice
      projection={projection}
      draft={{ text: "", context }}
      onDraftChange={vi.fn()}
      nativeContinuation={withNative ? native : null}
    />,
  );
}

describe("Meta-CEO Today canonical continuation placement", () => {
  it("presents the EXISTING owner controller once alongside an exact CURRENT Mission", () => {
    show(bound);
    const region = screen.getByRole("region", {
      name: "Continue the exact selected Executive session",
    });
    expect(within(region).getByRole("button", { name: "Existing native continuation" })).toBeTruthy();
    expect(region.textContent).toContain("not a worker result or acceptance");
    expect(screen.getByText("Owner-qualified session")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Send$/ })).toBeNull();
  });

  it("refuses exposing the command panel when no owner-bound target is present", () => {
    const ctx = { ...bound, sessionRef: null, bindingGeneration: null };
    show(ctx);
    expect(screen.queryByRole("region", {
      name: "Continue the exact selected Executive session",
    })).toBeNull();
    expect(screen.getByText("Read + preview only")).toBeTruthy();
  });

  it("refuses a stale Mission even with a nominally bound target", () => {
    show(bound, source(bound, "STALE"));
    expect(screen.queryByRole("button", { name: "Existing native continuation" })).toBeNull();
  });

  it("refuses an owner epoch mismatch rather than relabeling the prior Mission", () => {
    show({ ...bound, bindingGeneration: "new-epoch" }, source(bound));
    expect(screen.queryByRole("region", {
      name: "Continue the exact selected Executive session",
    })).toBeNull();
  });

  it("does not fabricate a control when the original owner does not supply it", () => {
    show(bound, undefined, false);
    expect(screen.queryByRole("button", { name: "Existing native continuation" })).toBeNull();
    expect(screen.getByText("Read + preview only")).toBeTruthy();
  });
});
