import { describe, expect, it } from "vitest";
import { parseTeamRoster } from "./team-roster-contract";

const bot = (over: Record<string, unknown> = {}) => ({
  id: "engineering", displayName: "Engineering", role: "operator",
  profilePath: "/Users/operator/.hermes/profiles/engineering", managed: true, host: "m2studio",
  gateway: { observed: true, source: "control_socket_identify", instanceId: "gw-1",
    authorityEpoch: 4, codeVersion: "0.23.0", pid: 1234, state: "ready" },
  readiness: "ready", readinessReason: "GATEWAY_READY", lastActivity: "2026-11-09T10:00:00Z",
  activitySummary: "ran the WO-19 dry-run", ...over,
});
const roster = (over: Record<string, unknown> = {}) => ({
  schema: "mastermind.team_roster/v1", generatedAt: "2026-11-09T12:00:00Z",
  host: "m2studio", bots: [bot()], ...over,
});

describe("team roster contract (mastermind.team_roster/v1)", () => {
  it("parses an observed bot and keeps unknown facts unknown, with reasons", () => {
    const parsed = parseTeamRoster(roster({ bots: [bot(),
      bot({ id: "coo", displayName: "COO", gateway: { observed: false, source: "none",
        instanceId: null, authorityEpoch: null, codeVersion: null, pid: null, state: null },
        readiness: "unknown", readinessReason: "NO_GATEWAY_LOCK",
        lastActivity: null, activitySummary: null, activityReason: "NO_STATE_DB" })] }));
    expect(parsed.bots[0].gateway.source).toBe("control_socket_identify");
    expect(parsed.bots[0].lastActivity).toBe("2026-11-09T10:00:00Z");
    const unknown = parsed.bots[1];
    expect(unknown.readiness).toBe("unknown");
    expect(unknown.readinessReason).toBe("NO_GATEWAY_LOCK");
    expect(unknown.lastActivity).toBeNull();
    expect(unknown.activityReason).toBe("NO_STATE_DB");
  });
  it("unobserved activity without a reason is invalid, and so is a reason on observed activity", () => {
    expect(() => parseTeamRoster(roster({ bots: [bot({ lastActivity: null, activitySummary: null })] })))
      .toThrow("NATIVE_RESPONSE_INVALID");
    expect(() => parseTeamRoster(roster({ bots: [bot({ activityReason: "SOME_REASON" })] })))
      .toThrow("NATIVE_RESPONSE_INVALID");
  });
  it("fails closed on drift: unknown fields, bad ids, closed sets, caps", () => {
    const boom = (value: unknown) => expect(() => parseTeamRoster(value)).toThrow("NATIVE_RESPONSE_INVALID");
    boom(roster({ schema: "mastermind.team_roster/v2" }));
    boom(roster({ priority: 1 }));
    boom(roster({ host: "not a host!" }));
    boom(roster({ generatedAt: "yesterday" }));
    boom(roster({ bots: [bot({ id: "Bad ID" })] }));
    boom(roster({ bots: [bot(), bot()] })); // duplicate ids
    boom(roster({ bots: Array.from({ length: 65 }, (_, i) => bot({ id: `bot-${i}` })) }));
    boom(roster({ bots: [bot({ readiness: "healthy", readinessReason: "FINE" })] }));
    boom(roster({ bots: [bot({ readinessReason: "lowercase" })] }));
    boom(roster({ bots: [bot({ lastActivity: "20261109T1200Z" })] })); // shape, not range, is checked
    boom(roster({ bots: [bot({ profilePath: "relative/path" })] }));
    boom(roster({ bots: [bot({ gateway: { observed: false, source: "control_socket_identify",
      instanceId: null, authorityEpoch: null, codeVersion: null, pid: null, state: null } })] }));
    boom(roster({ bots: [bot({ gateway: { observed: true, source: "guessed", instanceId: "gw",
      authorityEpoch: 1, codeVersion: null, pid: 1, state: null } })] }));
    boom(roster({ bots: ["not-a-bot"] }));
  });
  it("bounds the roster to at most 64 bots (the 256 KiB byte cap sits above every field-legal roster and is defense-in-depth)", () => {
    // 64 bots × the largest field-legal row ≈ 100 KiB, under the cap: the
    // byte cap only ever trips on input that is already shape-invalid.
    const full = roster({ bots: Array.from({ length: 64 }, (_, i) => bot({
      id: `bot-${i}`, displayName: "x".repeat(240), role: "r".repeat(160),
      activitySummary: "y".repeat(240), profilePath: "/Users/operator/.hermes/profiles/"
        + "p".repeat(200) + `-${i}` })) });
    expect(parseTeamRoster(full).bots).toHaveLength(64);
  });
});
