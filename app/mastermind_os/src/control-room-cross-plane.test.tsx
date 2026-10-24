// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { decodeCrossPlaneRead } from "./control-room-cross-plane";
import { decodeControlRoomRead } from "./control-room";
import { ControlRoomPanel } from "./ControlRoomPanel";
import { controlRoomFixture } from "./test-fixtures";

const legacy = () => ({
  control_room: controlRoomFixture(), capabilities: {},
  composed_at: "2026-10-24T12:00:00Z", refresh_in_flight: false,
  live_builds_active: false, state_refresh_error: null, source_validity: {},
});
const document = () => ({
  schema: "mastermind.executive_cross_plane_view.v1", state: "DEGRADED",
  evaluated_at: "2026-10-24T12:00:01Z", stale_after_seconds: 600,
  source_receipt: { semantic_hash: "a".repeat(64) },
  execution: { state: "NOT_PROJECTED", reason: "never guessed from Linear" },
  admission: null, finding_counts: {}, unavailable_sources: [{ owner: "slack" }],
  digest_check: { state: "VERIFIED" }, unattributed_findings: [],
  unknowns: [{ reason: "missing Executive observation" }],
  capability: { read_only: true, effect: "NONE" },
  cards: [{
    workstream: "WS:AGENT-OS", identities: {}, findings: [], finding_counts: {},
    github: { available: true, pull_requests: [{
      repository: "mastermindx-market-intelligence/Mastermind", number: 1515,
      delivery: { state: "open", ci: "success", draft: true },
      proof: { declared_completion: "BUILT_NOT_PROVEN", proof_state: null },
      linked_linear_issue_id: null,
    }] },
    linear: { available: true, issues: [{ issue_id: "MAS-6", status: "In Progress" }] },
  }],
});
const bound = (doc: unknown = document()) => ({
  schema: "mastermind.control_room_cross_plane_read.v1", state: "AVAILABLE",
  reason_code: null, document: doc,
});
afterEach(cleanup);

describe("existing signed Control Room cross-plane evidence", () => {
  it("keeps the strict seven-field legacy payload and shows not installed, not zero drift", () => {
    const result = decodeControlRoomRead(legacy());
    expect(result.crossPlane).toEqual({ state: "UNAVAILABLE", reason: "NOT_INSTALLED" });
  });
  it("retains only exact source PRs, explicit native links and non-liveness", () => {
    const result = decodeControlRoomRead({ ...legacy(), cross_plane: bound() });
    expect(result.crossPlane.state).toBe("AVAILABLE");
    if (result.crossPlane.state !== "AVAILABLE") throw Error("should be available");
    expect(result.crossPlane.viewState).toBe("DEGRADED");
    expect(result.crossPlane.cards[0].pullRequests[0].linkedIssue).toBeNull();
    expect(result.crossPlane.cards[0].pullRequests[0].declaredCompletion).toBe("BUILT_NOT_PROVEN");
    expect(result.crossPlane.cards[0].pullRequests[0].proofState).toBeNull();
    expect(result.crossPlane.unavailableCount).toBe(1);
    expect(Object.isFrozen(result.crossPlane.cards)).toBe(true);
    render(<ControlRoomPanel
      state={{ ...result, ownerRevision: 1 }} canRefresh={false}
      onRefresh={vi.fn()} onOpen={vi.fn()}
    />);
    expect(screen.getByRole("region", { name: "Cross-plane source evidence" }).textContent)
      .toContain("Native Linear link: not established");
    expect(screen.getByText(/Execution not projected/i)).toBeTruthy();
    expect(screen.getByText(/BUILT_NOT_PROVEN/)).toBeTruthy();
  });
  it("retains an explicit owner failure without a fake empty success", () => {
    expect(decodeCrossPlaneRead({ schema: "mastermind.control_room_cross_plane_read.v1",
      state: "UNAVAILABLE", reason_code: "source_unavailable", document: null,
    })).toEqual({ state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" });
  });
  it("refuses foreign schemas, liveness fabrication, injected links and unbounded arrays", () => {
    const invalid = [
      { ...bound(), injected: "auth-bypass" },
      bound({ ...document(), schema: "not-session-truth" }),
      bound({ ...document(), execution: { state: "RUNNING" } }),
      bound({ ...document(), capability: { effect: "MERGE", read_only: false } }),
      bound({ ...document(), cards: Array(33).fill(document().cards[0]) }),
      bound({ ...document(), evaluated_at: "2031-not-a-date" }),
      bound({ ...document(), cards: [{ ...document().cards[0], github: {
        pull_requests: [{ ...document().cards[0].github.pull_requests[0],
          linked_linear_issue_id: "similar title" }],
      } }] }),
    ];
    for (const value of invalid)
      expect(() => decodeControlRoomRead({ ...legacy(), cross_plane: value }))
        .toThrow("CONTROL_ROOM_CROSS_PLANE_INVALID");
  });
});
