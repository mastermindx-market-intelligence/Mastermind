import { describe, expect, it } from "vitest";
import {
  parseTeamRoster,
  readTeamRoster,
  type TeamRosterEntry,
} from "./team-roster-contract";

function bot(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    botId: "bot-alpha",
    displayName: "Alpha Bot",
    role: "Research",
    profile: null,
    gatewayInstance: "gw-1",
    host: "m2studio",
    readiness: "ready",
    readinessReason: null,
    lastActivity: "2026-11-09T00:00:00Z",
    activitySummary: "Reading regime data",
    ...extra,
  };
}
function roster(bots: Record<string, unknown>[]) {
  return { schema: "mastermind.team_roster.v1", bots };
}

describe("mastermind.team_roster/v1 fail-closed parser", () => {
  it("accepts a full roster and trims nothing silently", () => {
    const view = parseTeamRoster(
      roster([
        bot(),
        bot({
          botId: "bot-beta",
          displayName: "Beta",
          role: "Ops",
          readiness: "degraded",
          readinessReason: "gateway reconnecting",
          gatewayInstance: null,
          host: null,
          lastActivity: null,
          activitySummary: null,
          profile: "https://example.com/beta",
        }),
        bot({
          botId: "bot-gamma",
          displayName: "Gamma",
          readiness: "unknown",
          readinessReason: "no reading in 48h",
          lastActivity: null,
        }),
      ]),
    );
    expect(view.schema).toBe("mastermind.team_roster.v1");
    expect(view.bots.map((entry) => entry.botId)).toEqual([
      "bot-alpha",
      "bot-beta",
      "bot-gamma",
    ]);
    const beta = view.bots[1] as TeamRosterEntry;
    expect(beta.readiness).toBe("degraded");
    expect(beta.readinessReason).toBe("gateway reconnecting");
    expect(beta.lastActivity).toBeNull();
  });
  it("rejects wrong schema, unknown keys, missing keys and non-array bots", () => {
    expect(() =>
      parseTeamRoster({ schema: "mastermind.team_roster.v2", bots: [] }),
    ).toThrow("TEAM_ROSTER_INVALID");
    expect(() =>
      parseTeamRoster({
        schema: "mastermind.team_roster.v1",
        bots: [],
        extra: true,
      }),
    ).toThrow("TEAM_ROSTER_INVALID");
    expect(() =>
      parseTeamRoster({ schema: "mastermind.team_roster.v1" }),
    ).toThrow("TEAM_ROSTER_INVALID");
    expect(() =>
      parseTeamRoster({ schema: "mastermind.team_roster.v1", bots: {} }),
    ).toThrow("TEAM_ROSTER_INVALID");
  });
  it("rejects bad bot ids, readiness values and activity timestamps", () => {
    expect(() =>
      parseTeamRoster(roster([bot({ botId: "has space" })])),
    ).toThrow("TEAM_ROSTER_INVALID");
    expect(() =>
      parseTeamRoster(roster([bot({ readiness: "healthy" })])),
    ).toThrow("TEAM_ROSTER_INVALID");
    expect(() =>
      parseTeamRoster(roster([bot({ lastActivity: "yesterday" })])),
    ).toThrow("TEAM_ROSTER_INVALID");
    expect(() => parseTeamRoster(roster([bot({ botId: "" })]))).toThrow(
      "TEAM_ROSTER_INVALID",
    );
  });
  it("requires a reason exactly when readiness is not ready", () => {
    expect(() =>
      parseTeamRoster(roster([bot({ readinessReason: "stale reason" })])),
    ).toThrow("TEAM_ROSTER_INVALID");
    expect(() =>
      parseTeamRoster(
        roster([bot({ readiness: "degraded", readinessReason: null })]),
      ),
    ).toThrow("TEAM_ROSTER_INVALID");
    expect(() =>
      parseTeamRoster(
        roster([bot({ readiness: "unknown", readinessReason: "no reading" })]),
      ),
    ).not.toThrow();
  });
  it("rejects duplicate bot ids", () => {
    expect(() => parseTeamRoster(roster([bot(), bot()]))).toThrow(
      "TEAM_ROSTER_INVALID",
    );
  });
});

describe("readTeamRoster through the host facade", () => {
  it("reports NOT_CONNECTED without a source and stays honest on failures", () => {
    expect(readTeamRoster(undefined)).toEqual({
      kind: "UNAVAILABLE",
      reason: "TEAM_ROSTER_SOURCE_NOT_CONNECTED",
    });
    expect(readTeamRoster({})).toEqual({
      kind: "UNAVAILABLE",
      reason: "TEAM_ROSTER_SOURCE_NOT_CONNECTED",
    });
    expect(readTeamRoster({ teamRoster: {} })).toEqual({
      kind: "UNAVAILABLE",
      reason: "TEAM_ROSTER_SOURCE_NOT_CONNECTED",
    });
    const failing = {
      teamRoster: {
        read: () => {
          throw new Error("offline");
        },
      },
    };
    expect(readTeamRoster(failing)).toEqual({
      kind: "UNAVAILABLE",
      reason: "TEAM_ROSTER_SOURCE_READ_FAILED",
    });
    const empty = { teamRoster: { read: () => null } };
    expect(readTeamRoster(empty)).toEqual({
      kind: "UNAVAILABLE",
      reason: "TEAM_ROSTER_SOURCE_EMPTY",
    });
    const invalid = {
      teamRoster: {
        read: () => ({
          schema: "mastermind.team_roster.v1",
          bots: [bot({ readiness: "maybe" })],
        }),
      },
    };
    expect(readTeamRoster(invalid)).toEqual({
      kind: "UNAVAILABLE",
      reason: "TEAM_ROSTER_SOURCE_INVALID",
    });
  });
  it("returns an AVAILABLE roster only for fully verified data", () => {
    const host = { teamRoster: { read: () => roster([bot()]) } };
    const read = readTeamRoster(host);
    expect(read.kind).toBe("AVAILABLE");
    if (read.kind !== "AVAILABLE") return;
    expect(read.roster.bots[0]!.displayName).toBe("Alpha Bot");
  });
});
