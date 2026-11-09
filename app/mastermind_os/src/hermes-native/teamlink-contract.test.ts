import { describe, expect, it } from "vitest";
import {
  TeamLinkContractError, advanceDelivery, followupRequiresNewKey, isExpired,
  isPingPongEcho, mayForward, mintMessageId, parseContextPacket,
  parseTeamLinkMessage, requiresModelTurn, verifyDuplicate,
} from "./teamlink-contract";

const LATER = "2026-11-09T18:00:00Z";

const principal = (side: "hermes_profile" | "t3_host_thread", id: string, thread_ref: string | null = null) =>
  ({ side, id, thread_ref });
const correlation = () => ({
  root_run_ref: null, immediate_parent_run_ref: null, logical_child_key: null,
  preview_id: null, decision_id: "dec-42", attempt_ref: null,
  fence_counter: 3, request_digest: "ab".repeat(32),
});
export const message = (over: Record<string, unknown> = {}) => ({
  schema: "TeamLinkMessage.v1",
  message_id: "tlm-" + "0".repeat(32),
  operation_key: "wo19-teamlink-check-1",
  correlation: correlation(),
  from: principal("hermes_profile", "engineering"),
  to: principal("t3_host_thread", "m2studio", "th_ready_9"),
  kind: "instruction",
  intent: "actionable",
  body: "Run the WO-19 dry-run and report the unattributed count.",
  context_refs: ["DEC:TEAMLINK-V1-DESIGN"],
  reply_to: null,
  hop_count: 0,
  max_hops: 3,
  delivery_state: "admitted",
  expires_at: LATER,
  ...over,
});
const packet = (over: Record<string, unknown> = {}) => ({
  schema: "ContextPacket.v1",
  packet_id: "tlp-" + "1".repeat(32),
  objective: "Finish the Hermes Rev5 roster lane.",
  accepted_decisions: [
    { decision_id: "dec-42", summary: "TeamLink v1 shapes adopted", ledger_row: "job_execution_decision:918" },
    { decision_id: "dec-43", ledger_row: null },
  ],
  outstanding_dependencies: [
    { what: "Executive MCP seam on 8731 revived", owner: "gateway-oncall", ref: "TEAMLINK_CENSUS row 3" }],
  source_revision: { branch: "t3/hermes-roster-continuity", head: "bbfad42da" },
  active_work_ownership: [
    { work_ref: "PR-2180-native-path", owner: "director-b", lease_expires_at: LATER },
    { work_ref: "wo19-prep", owner: "director-a", lease_expires_at: null }],
  unresolved_effects: [
    { effect_ref: "PR-2182-publication", state: "EFFECT_UNKNOWN",
      rule: "do not retry or publish through another account" }],
  next_action: "Adopt the design field names; no transport.",
  since_packet_id: "tlp-" + "f".repeat(32),
  delta: { added: ["dec-43"], changed: [], removed: [] },
  expires_at: LATER,
  ...over,
});

const reject = (code: string | null, fn: () => unknown) => {
  if (code === null) { expect(fn).toThrow(TeamLinkContractError); return; }
  expect(fn).toThrow(expect.objectContaining({ code }) as Error);
};

describe("TeamLinkMessage.v1 shape", () => {
  it("adopts the design's snake_case field names verbatim", () => {
    const parsed = parseTeamLinkMessage(message());
    expect(parsed.operation_key).toBe("wo19-teamlink-check-1");
    expect(parsed.to.thread_ref).toBe("th_ready_9");
    expect(parsed.correlation.fence_counter).toBe(3);
  });
  it("reply_to is optional; a status ping may carry an all-null correlation", () => {
    const minimal = message({ kind: "status", intent: "informational",
      correlation: Object.fromEntries(["root_run_ref", "immediate_parent_run_ref",
        "logical_child_key", "preview_id", "decision_id", "attempt_ref",
        "fence_counter", "request_digest"].map(key => [key, null])) });
    delete (minimal as Record<string, unknown>).reply_to;
    expect(parseTeamLinkMessage(minimal).kind).toBe("status");
  });
  it("rejects every kind of drift with a typed code", () => {
    reject("INVALID_MESSAGE_SCHEMA", () => parseTeamLinkMessage(message({ schema: "TeamLinkMessage.v2" })));
    reject("INVALID_MESSAGE_FIELDS", () => parseTeamLinkMessage(message({ priority: "high" })));
    reject("MISSING_MESSAGE_FIELD", () => { const m = message(); delete m.intent; parseTeamLinkMessage(m); });
    reject("INVALID_MESSAGE_ID", () => parseTeamLinkMessage(message({ message_id: "tlm-XYZ" })));
    reject("INVALID_OPERATION_KEY", () => parseTeamLinkMessage(message({ operation_key: "bad key" })));
    reject("INVALID_KIND", () => parseTeamLinkMessage(message({ kind: "rumour" })));
    reject("INVALID_INTENT", () => parseTeamLinkMessage(message({ intent: "urgent" })));
    reject("INVALID_BODY", () => parseTeamLinkMessage(message({ body: "" })));
    reject("INVALID_CONTEXT_REFS", () => parseTeamLinkMessage(
      message({ context_refs: Array.from({ length: 33 }, (_, i) => `r${i}`) })));
    reject("INVALID_REPLY_TO", () => parseTeamLinkMessage(message({ reply_to: "tlm-nothex" })));
    reject("INVALID_HOP_COUNT", () => parseTeamLinkMessage(message({ hop_count: -1 })));
    reject("INVALID_MAX_HOPS", () => parseTeamLinkMessage(message({ max_hops: 9 })));
    reject("INVALID_DELIVERY_STATE", () => parseTeamLinkMessage(message({ delivery_state: "delivered" })));
    reject("INVALID_EXPIRES_AT", () => parseTeamLinkMessage(message({ expires_at: "next tuesday" })));
    reject("INVALID_CORRELATION_FIELDS", () => parseTeamLinkMessage(
      message({ correlation: { invented_key: "x" } })));
    reject("INVALID_REQUEST_DIGEST", () => parseTeamLinkMessage(
      message({ correlation: { ...correlation(), request_digest: "AB".repeat(32) } })));
    reject("INVALID_FENCE_COUNTER", () => parseTeamLinkMessage(
      message({ correlation: { ...correlation(), fence_counter: -1 } })));
    reject("INVALID_FROM_PRINCIPAL_SIDE", () => parseTeamLinkMessage(
      message({ from: principal("slack_workspace" as never, "acme") })));
  });
});

describe("ContextPacket.v1 shape", () => {
  it("roundtrips a full packet and a minimum packet without since/delta", () => {
    expect(parseContextPacket(packet()).packet_id).toBe("tlp-" + "1".repeat(32));
    const minimal = packet();
    delete (minimal as Record<string, unknown>).since_packet_id;
    delete (minimal as Record<string, unknown>).delta;
    expect(parseContextPacket(minimal).objective).toBe("Finish the Hermes Rev5 roster lane.");
  });
  it("rejects drift: unknown effect state, bad ids, caps, delta keys", () => {
    reject("INVALID_PACKET_ID", () => parseContextPacket(packet({ packet_id: "tlm-" + "1".repeat(32) })));
    reject("MISSING_ACCEPTED_DECISIONS_FIELD", () => parseContextPacket(
      packet({ accepted_decisions: [{ summary: "no decision_id" }] })));
    reject("INVALID_EFFECT_STATE", () => parseContextPacket(packet(
      { unresolved_effects: [{ effect_ref: "e", state: "RESOLVED", rule: "r" }] })));
    reject("INVALID_SINCE_PACKET_ID", () => parseContextPacket(packet({ since_packet_id: "tlp-nothex" })));
    reject("INVALID_PACKET_DELTA_FIELDS", () => parseContextPacket(
      packet({ delta: { added: ["a"], moved: ["m"] } })));
    reject("INVALID_ACCEPTED_DECISIONS", () => parseContextPacket(packet(
      { accepted_decisions: Array.from({ length: 65 }, (_, i) => ({ decision_id: `d${i}` })) })));
    reject("MISSING_SOURCE_REVISION_FIELD", () => parseContextPacket(
      packet({ source_revision: { branch: "b" } })));
    reject("INVALID_LEASE_EXPIRES_AT", () => parseContextPacket(packet(
      { active_work_ownership: [{ work_ref: "w", owner: "o", lease_expires_at: "soon" }] })));
  });
  it("unresolved effects must be EFFECT_UNKNOWN — the packet is honest or invalid", () => {
    const parsed = parseContextPacket(packet());
    expect(parsed.unresolved_effects[0].state).toBe("EFFECT_UNKNOWN");
    expect(parsed.unresolved_effects[0].rule).toContain("do not retry");
  });
});

describe("deterministic mint (cross-language parity)", () => {
  it("produces the same ids the Python mint produced for these fixed vectors", async () => {
    await expect(mintMessageId("engineering", "wo19-teamlink-check-1",
      "Run the WO-19 dry-run and report the unattributed count.",
      ["DEC:COMMERCIAL-DATA-RIGHTS-CHAIRMAN-ATTESTATION-20261023", "sha256:" + "ab".repeat(32)]))
      .resolves.toBe("tlm-0b0e68856ac4439993fac4b6e166b593");
    await expect(mintMessageId("coo-bot", "roundtrip-a3", "状态 status ping 中文", []))
      .resolves.toBe("tlm-64a95e24a3ae74fba98f72b2f2aa1352");
  });
  it("same content ⇒ same id; changed content ⇒ different id", async () => {
    const once = await mintMessageId("engineering", "op-1", "body", ["r1"]);
    await expect(mintMessageId("engineering", "op-1", "body", ["r1"])).resolves.toBe(once);
    await expect(mintMessageId("engineering", "op-1", "body2", ["r1"])).resolves.not.toBe(once);
  });
  it("same operation_key + changed content is REFUSED as a duplicate", async () => {
    const original = parseTeamLinkMessage(message());
    const sameAgain = parseTeamLinkMessage(message());
    const alteredBody = "Run something else entirely.";
    const altered = parseTeamLinkMessage(message({
      body: alteredBody,
      message_id: await mintMessageId("engineering", "wo19-teamlink-check-1", alteredBody,
        ["DEC:TEAMLINK-V1-DESIGN"]) }));
    expect(verifyDuplicate(original, sameAgain)).toBe("same_message");
    expect(verifyDuplicate(original, altered)).toBe("refused_content_changed");
    expect(verifyDuplicate(original,
      parseTeamLinkMessage(message({ operation_key: "a-new-key-for-new-work" }))))
      .toBe("different_operation_key");
  });
});

describe("delivery, hops, expiry, wake, echo, settle", () => {
  it("chain is monotonic; same state is a no-op; unknown sits outside the chain", () => {
    expect(advanceDelivery("admitted", "picked_up")).toBe("picked_up");
    expect(advanceDelivery("executed", "replied")).toBe("replied");
    expect(advanceDelivery("consumed", "consumed")).toBe("consumed");
    expect(advanceDelivery("picked_up", "unknown")).toBe("unknown");
    expect(advanceDelivery("unknown", "unknown")).toBe("unknown");
    expect(advanceDelivery("unknown", "executed")).toBe("executed");
    expect(() => advanceDelivery("executed", "admitted"))
      .toThrow(expect.objectContaining({ code: "DELIVERY_REGRESSION" }) as Error);
    expect(() => advanceDelivery("delivered", "admitted")).toThrow(TeamLinkContractError);
  });
  it("a forward whose hop_count would reach max_hops is a hop_breach", () => {
    const now = new Date("2026-11-09T12:00:00Z");
    expect(mayForward(parseTeamLinkMessage(message({ hop_count: 0 })), now)).toEqual([true, ""]);
    expect(mayForward(parseTeamLinkMessage(message({ hop_count: 1 })), now)).toEqual([true, ""]);
    expect(mayForward(parseTeamLinkMessage(message({ hop_count: 2 })), now)).toEqual([false, "hop_breach"]);
    expect(mayForward(parseTeamLinkMessage(message({ hop_count: 0, max_hops: 0 })), now))
      .toEqual([false, "hop_breach"]);
    expect(mayForward(parseTeamLinkMessage(message({ hop_count: 6, max_hops: 8 })), now)).toEqual([true, ""]);
  });
  it("an expired actionable message is dead even below max_hops", () => {
    const now = new Date("2026-11-09T12:00:00Z");
    const dead = parseTeamLinkMessage(message({ expires_at: "2026-11-09T11:00:00Z" }));
    expect(isExpired(dead, now)).toBe(true);
    expect(mayForward(dead, now)).toEqual([false, "expired"]);
    expect(isExpired(parseTeamLinkMessage(message()), now)).toBe(false);
    expect(isExpired({ expires_at: null as unknown as string }, now)).toBe(true);
  });
  it("only actionable requires a model turn", () => {
    expect(requiresModelTurn(parseTeamLinkMessage(message()))).toBe(true);
    expect(requiresModelTurn(parseTeamLinkMessage(message({ intent: "informational" })))).toBe(false);
  });
  it("a mirror of what we just sent to the same peer is a ping-pong echo", () => {
    const sent = parseTeamLinkMessage(message());
    const echo = parseTeamLinkMessage(message({
      from: sent.to, to: sent.from, kind: sent.kind, intent: sent.intent, reply_to: sent.reply_to }));
    expect(isPingPongEcho(sent, echo)).toBe(true);
    expect(isPingPongEcho(sent, parseTeamLinkMessage(message({ kind: "answer" })))).toBe(false);
    expect(isPingPongEcho(sent, parseTeamLinkMessage(message({ reply_to: sent.message_id })))).toBe(false);
  });
  it("answers settle: the subject is closed until a NEW operation_key", () => {
    const question = parseTeamLinkMessage(message({ kind: "question" }));
    expect(followupRequiresNewKey(question, parseTeamLinkMessage(message({ kind: "question" })))).toBe(true);
    expect(followupRequiresNewKey(question,
      parseTeamLinkMessage(message({ kind: "question", operation_key: "fresh-work-key" })))).toBe(false);
  });
  it("the packet is a cache: expired means re-fetch, never act", () => {
    expect(isExpired(parseContextPacket(packet()), new Date("2026-11-09T12:00:00Z"))).toBe(false);
    expect(isExpired(parseContextPacket(packet({ expires_at: "2026-11-09T11:00:00Z" })),
      new Date("2026-11-09T12:00:00Z"))).toBe(true);
  });
});
