/** These small fixtures exercise only navigation; they do not impersonate the
 * separately validated full Programme document or any installed acceptance.
 */
import { describe, expect, it } from "vitest";
import { MAX_RESPONSE_BYTES } from "./public-config";
import { realControlRoomFixture } from "./test-fixtures";
import { decodeControlRoomRead } from "./control-room";
import {
  CONTROL_ROOM_DISCOVERY_UNAVAILABLE,
  decodeControlRoomDiscovery,
  decodeControlRoomNavigation,
} from "./control-room-navigation";

const REF = "WS:CCR-TEST";
const id = (n: number) => `${n.toString(16).padStart(8, "0")}-1111-4111-8111-111111111111`;
const binding = (overrides: Record<string, unknown> = {}): Record<string, unknown> => ({
  binding_id: id(1), work_ref: REF, role: "ceo", provider: "chatgpt",
  seat_ref: "chatgpt1", locator_kind: "chatgpt_managed_env",
  observed_at: "2026-10-19T00:00:00.123456Z", last_verified_at: null,
  ...overrides,
});
const conflict = (ids: string[], work_ref = REF, role = "ceo") => ({
  work_ref, role, binding_ids: ids,
});
const room = (
  bindings: Record<string, unknown>[] = [],
  unbound: Record<string, unknown>[] = [],
  conflicts: Record<string, unknown>[] = [],
) => ({
  schema: "mastermind.chairman_control_room.v1",
  sources: { bindings_path_present: true },
  work: [{ work_ref: REF, bindings, title: "Existing programme card" }],
  unbound_surfaces: unbound,
  binding_conflicts: conflicts,
});
const installed = () => ({ installed: true, version: "1.0", state: "PARTIAL", detail: "Observed on PATH" });
const absent = () => ({ installed: false, version: null, state: "NOT_INSTALLED", detail: "Not found" });
function available(raw: unknown, capabilities: unknown = {}) {
  const result = decodeControlRoomNavigation(raw, capabilities);
  expect(result.state).toBe("AVAILABLE");
  if (result.state !== "AVAILABLE") throw new Error("Expected navigation fixture to decode");
  return result;
}
function unavailable(raw: unknown, capabilities: unknown = {}) {
  expect(decodeControlRoomNavigation(raw, capabilities)).toEqual({
    state: "UNAVAILABLE", reason: "CONTROL_ROOM_NAVIGATION_INVALID",
  });
}

describe("Control Room navigation observation", () => {
  it("keeps exact attached and unbound handles without creating work cards", () => {
    const raw = room([binding()], [binding({ binding_id: id(2), work_ref: "JOB:original-root" })]);
    const result = available(raw);
    expect(result.bindings.map(row => row.binding_id)).toEqual([id(1), id(2)]);
    expect(result.unboundBindingIds).toEqual([id(2)]);
    expect(result.bindings[1].work_ref).toBe("JOB:original-root");
    expect(raw.work).toHaveLength(1);
    expect(result.capabilities).toEqual({});
    expect(result).not.toHaveProperty("authorized");
    expect(result).not.toHaveProperty("programs");
  });

  it("preserves unknown empty census and the owner's absent-input observation", () => {
    const raw = room();
    raw.sources.bindings_path_present = false;
    expect(available(raw).bindingsPathPresent).toBe(false);
    expect(available(raw).capabilities).toEqual({});
    raw.work[0].bindings.push(binding());
    unavailable(raw);
  });

  it("detaches and freezes all returned navigation containers and rows", () => {
    const row = binding();
    const caps = { codex: installed() };
    const result = available(room([row]), caps);
    row.seat_ref = "changed after decoding";
    caps.codex.detail = "changed after decoding";
    expect(result.bindings[0].seat_ref).toBe("chatgpt1");
    expect(result.capabilities.codex?.detail).toBe("Observed on PATH");
    for (const value of [result, result.bindings, result.bindings[0], result.unboundBindingIds,
      result.conflicts, result.capabilities, result.capabilities.codex])
      expect(Object.isFrozen(value)).toBe(true);
  });

  it("uses the source UUID shape without requiring a version-four nibble", () => {
    const exact = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE";
    expect(available(room([binding({ binding_id: exact })])).bindings[0].binding_id).toBe(exact);
  });

  it.each([
    ["missing timestamp", () => { const row = binding(); delete row.observed_at; return row; }],
    ["raw locator", () => binding({ locator: { session_id: id(4) } })],
    ["extra authority field", () => binding({ authorized: true })],
    ["wrong provider-kind pair", () => binding({ locator_kind: "codex_session" })],
    ["unsupported provider", () => binding({ provider: "aionui" })],
    ["unknown role", () => binding({ role: "release_owner" })],
    ["empty local handle", () => binding({ binding_id: "" })],
    ["malformed work reference", () => binding({ work_ref: "WS:with whitespace" })],
    ["trailing-newline handle", () => binding({ binding_id: `${id(1)}\n` })],
    ["trailing-newline work reference", () => binding({ work_ref: `${REF}\n` })],
    ["non-UTC timestamp", () => binding({ observed_at: "2026-10-19T00:00:00+00:00" })],
    ["impossible calendar timestamp", () => binding({ observed_at: "2026-02-30T00:00:00Z" })],
    ["invalid verification timestamp", () => binding({ last_verified_at: false })],
    ["lone surrogate", () => binding({ seat_ref: "seat-\ud800" })],
  ] as const)("withholds malformed summary: %s", (_name, create) => unavailable(room([create()])));

  it.each([null, "", " \t\n"])("requires a nonblank ChatGPT seat: %j", seat_ref => {
    unavailable(room([binding({ seat_ref })]));
  });

  it("preserves an empty optional non-ChatGPT seat and a UTC verification observation", () => {
    const result = available(room([binding({
      provider: "codex", locator_kind: "codex_session", seat_ref: "",
      last_verified_at: "2026-10-19T00:00:01Z",
    })]));
    expect(result.bindings[0].seat_ref).toBe("");
    expect(result.bindings[0].last_verified_at).toBe("2026-10-19T00:00:01Z");
  });

  it("rejects duplicate local handles across attached and unbound rows", () => {
    unavailable(room([binding()], [binding({ work_ref: "PR:1600" })]));
  });

  it("rejects an attached row under a different work card", () => {
    unavailable(room([binding({ work_ref: "WS:OTHER" })]));
  });

  it("rejects an unbound row whose source work card is present", () => {
    unavailable(room([], [binding()]));
  });

  it("rejects repeated source work-card identities even without any binding", () => {
    const raw = room();
    raw.work.push({ ...raw.work[0], bindings: [] });
    unavailable(raw);
  });

  it("accepts distinct ChatGPT seats for the same work and role without a conflict", () => {
    const result = available(room([
      binding(), binding({ binding_id: id(2), seat_ref: "chatgpt2" }),
    ]));
    expect(result.bindings).toHaveLength(2);
    expect(result.conflicts).toEqual([]);
  });

  it("retains the whole three-row ChatGPT group when one seat is duplicated", () => {
    const rows = [binding(), binding({ binding_id: id(2), seat_ref: "chatgpt2" }),
      binding({ binding_id: id(3), seat_ref: "chatgpt1" })];
    const result = available(room(rows, [], [conflict([id(3), id(1), id(2)])]));
    expect(result.bindings).toHaveLength(3);
    expect(result.conflicts[0].binding_ids).toEqual([id(3), id(1), id(2)]);
    expect(Object.isFrozen(result.conflicts[0])).toBe(true);
    expect(Object.isFrozen(result.conflicts[0].binding_ids)).toBe(true);
    unavailable(room(rows, [], [conflict([id(1), id(3)])]));
  });

  it.each(["codex", "claude_code"] as const)("requires complete mixed-provider conflict groups: %s", provider => {
    const other = binding({ binding_id: id(2), provider,
      locator_kind: provider === "codex" ? "codex_session" : "claude_code_session", seat_ref: null });
    expect(available(room([binding(), other], [], [conflict([id(1), id(2)])])).conflicts).toHaveLength(1);
    unavailable(room([binding(), other]));
  });

  it("uses the same whole-group law for multiple non-ChatGPT unbound rows", () => {
    const a = binding({ provider: "codex", locator_kind: "codex_session", seat_ref: null, work_ref: "PR:1600" });
    const b = { ...a, binding_id: id(2), seat_ref: "different optional seat" };
    const result = available(room([], [a, b], [conflict([id(2), id(1)], "PR:1600")]));
    expect(result.unboundBindingIds).toEqual([id(1), id(2)]);
    expect(result.conflicts).toHaveLength(1);
    unavailable(room([], [a, b]));
  });

  it.each([
    ["missing group", []],
    ["orphan id", [conflict([id(1), id(9)])]],
    ["repeated id", [conflict([id(1), id(1)])]],
    ["wrong role", [conflict([id(1), id(2)], REF, "coo")]],
    ["duplicate group", [conflict([id(1), id(2)]), conflict([id(2), id(1)])]],
    ["unknown conflict field", [{ ...conflict([id(1), id(2)]), winner: id(1) }]],
  ] as const)("withholds contradictory declarations: %s", (_name, declared) => {
    unavailable(room([binding(), binding({ binding_id: id(2) })], [], [...declared]));
  });

  it("rejects an invented conflict between independent seats", () => {
    unavailable(room([binding(), binding({ binding_id: id(2), seat_ref: "chatgpt2" })],
      [], [conflict([id(1), id(2)])]));
  });

  it("accepts the actual census states without turning PARTIAL into a proof", () => {
    const result = available(room(), {
      chatgpt: absent(), claude_code: installed(), claude_desktop: absent(),
      cursor_agent: absent(), codex: installed(),
      aionui: { installed: true, version: null, state: "UNSUPPORTED", detail: "Observation only" },
    });
    expect(result.capabilities.claude_code?.state).toBe("PARTIAL");
    expect(result.capabilities.aionui?.state).toBe("UNSUPPORTED");
  });

  it.each([
    null, [], { unknown: installed() }, { codex: { ...installed(), state: "PROVEN" } },
    { codex: { ...installed(), installed: false } },
    { codex: { ...absent(), version: "not a missing-install observation" } },
    { aionui: { ...absent(), state: "NOT_INSTALLED" } },
    { codex: { ...installed(), token: "not a census field" } },
  ])("withholds only navigation for a malformed census", caps => unavailable(room([binding()]), caps));

  it("does not read getters, change programme data or freeze an input on failure", () => {
    const raw = room([binding()]);
    const before = raw.work[0];
    let calls = 0;
    Object.defineProperty(raw.work[0].bindings[0], "seat_ref", {
      enumerable: true, get() { calls++; return "chatgpt1"; },
    });
    unavailable(raw);
    expect(calls).toBe(0);
    expect(raw.work[0]).toBe(before);
    expect(raw.work[0].title).toBe("Existing programme card");
    expect(Object.isFrozen(raw)).toBe(false);
  });

  it("withholds oversized consumed strings using the existing UTF-8 response bound", () => {
    unavailable(room(), { codex: { ...installed(), detail: "é".repeat(MAX_RESPONSE_BYTES / 2) } });
  });

  it("matches the existing 500-work-card read bound", () => {
    const raw = room();
    raw.work = Array.from({ length: 500 }, (_, n) => ({ work_ref: `WS:fixture-${n}`, bindings: [], title: "Existing" }));
    available(raw);
    raw.work.push({ work_ref: "WS:fixture-500", bindings: [], title: "Existing" });
    unavailable(raw);
  });
});

const discovery = () => ({
  chatgpt_environments: {
    multilogin: [{ workspace_id: id(10), folder_id: id(20), profile_id: id(30), running: false }],
    gologin: [{ profile_id: "0123456789abcdef01234567", running: true }],
  },
  claude_code_sessions: [{ project_dir: "-Users-owner-work-tree", session_id: "directory-derived-name", mtime: -0.25 }],
  codex_sessions: [{ session_id: "rollout-directory-derived-name", date: "archive-month-day" }],
  cursor: { supported: false, note: "Locate an existing thread, then bind explicitly." },
});
function discoveryUnavailable(raw: unknown) {
  expect(() => decodeControlRoomDiscovery(raw)).toThrow(CONTROL_ROOM_DISCOVERY_UNAVAILABLE);
}

describe("Control Room Discovery observation", () => {
  it("retains directory-derived strings and finite fractional/negative mtime", () => {
    const raw = discovery();
    const result = decodeControlRoomDiscovery(raw);
    expect(result).toEqual(raw);
    expect(result.claude_code_sessions[0].project_dir).toBe("-Users-owner-work-tree");
    expect(result.claude_code_sessions[0].session_id).toBe("directory-derived-name");
    expect(result.claude_code_sessions[0].mtime).toBe(-0.25);
    expect(result.codex_sessions[0].date).toBe("archive-month-day");
    expect(result).not.toHaveProperty("schema");
    expect(result).not.toHaveProperty("authorized");
  });

  it("preserves different workspaces sharing a Multilogin folder/profile pair", () => {
    const raw = discovery();
    raw.chatgpt_environments.multilogin.push({ ...raw.chatgpt_environments.multilogin[0], workspace_id: id(11) });
    expect(decodeControlRoomDiscovery(raw).chatgpt_environments.multilogin.map(row => row.workspace_id))
      .toEqual([id(10), id(11)]);
  });

  it("accepts empty candidate lists without manufacturing a presence proof", () => {
    const raw = discovery();
    raw.chatgpt_environments.multilogin = [];
    raw.chatgpt_environments.gologin = [];
    raw.claude_code_sessions = [];
    raw.codex_sessions = [];
    expect(decodeControlRoomDiscovery(raw)).toEqual(raw);
  });

  it("detaches and deeply freezes the complete returned candidate document", () => {
    const raw = discovery();
    const result = decodeControlRoomDiscovery(raw);
    raw.chatgpt_environments.multilogin[0].running = true;
    raw.claude_code_sessions[0].session_id = "changed";
    expect(result.chatgpt_environments.multilogin[0].running).toBe(false);
    expect(result.claude_code_sessions[0].session_id).toBe("directory-derived-name");
    for (const value of [result, result.chatgpt_environments, result.chatgpt_environments.multilogin,
      result.chatgpt_environments.multilogin[0], result.chatgpt_environments.gologin,
      result.chatgpt_environments.gologin[0], result.claude_code_sessions, result.claude_code_sessions[0],
      result.codex_sessions, result.codex_sessions[0], result.cursor])
      expect(Object.isFrozen(value)).toBe(true);
  });

  it.each(["multilogin", "gologin", "claude", "codex"] as const)("accepts the source cap and refuses cap + 1 for %s", kind => {
    const raw = discovery();
    const cap = kind === "multilogin" || kind === "gologin" ? 200 : 40;
    const setLength = (length: number) => {
      if (kind === "multilogin") raw.chatgpt_environments.multilogin = Array.from({ length }, () => ({ workspace_id: id(10), folder_id: id(20), profile_id: id(30), running: false }));
      else if (kind === "gologin") raw.chatgpt_environments.gologin = Array.from({ length }, () => ({ profile_id: "0123456789abcdef01234567", running: false }));
      else if (kind === "claude") raw.claude_code_sessions = Array.from({ length }, () => ({ project_dir: "slug", session_id: "stem", mtime: 0.125 }));
      else raw.codex_sessions = Array.from({ length }, () => ({ session_id: "stem", date: "a-b-c" }));
    };
    setLength(cap);
    expect(() => decodeControlRoomDiscovery(raw)).not.toThrow();
    setLength(cap + 1);
    discoveryUnavailable(raw);
  });

  it.each([NaN, Infinity, -Infinity])("rejects nonfinite mtime: %s", mtime => {
    const raw = discovery();
    raw.claude_code_sessions[0].mtime = mtime;
    discoveryUnavailable(raw);
  });

  it("requires closed canonical fields and cursor supported exactly false", () => {
    discoveryUnavailable({ ...discovery(), schema: "invented" });
    discoveryUnavailable({ ...discovery(), cursor: { supported: true, note: "Observed" } });
    discoveryUnavailable({ ...discovery(), cursor: { supported: false } });
    const raw = discovery();
    discoveryUnavailable({ ...raw, chatgpt_environments: { ...raw.chatgpt_environments, multilogin: [
      { ...raw.chatgpt_environments.multilogin[0], display_name: "not directory-derived" },
    ] } });
    discoveryUnavailable({ ...raw, claude_code_sessions: [{ project_dir: "slug", session_id: "stem", mtime: "0" }] });
  });

  it("does not accept noncanonical managed-environment IDs or coerce booleans", () => {
    const raw = discovery();
    discoveryUnavailable({ ...raw, chatgpt_environments: { ...raw.chatgpt_environments,
      gologin: [{ profile_id: "ABCDEF0123456789ABCDEF01", running: false }],
    } });
    discoveryUnavailable({ ...raw, chatgpt_environments: { ...raw.chatgpt_environments,
      multilogin: [{ ...raw.chatgpt_environments.multilogin[0], workspace_id: "display-name" }],
    } });
    discoveryUnavailable({ ...raw, chatgpt_environments: { ...raw.chatgpt_environments,
      gologin: [{ profile_id: "0123456789abcdef01234567", running: 1 }],
    } });
  });

  it.each(["\ud800", "\udc00"])("rejects lone surrogate scalar values", note => {
    discoveryUnavailable({ ...discovery(), cursor: { supported: false, note } });
  });

  it("accepts paired Unicode and rejects sparse/non-JSON candidate rows", () => {
    const raw = discovery();
    raw.cursor.note = "Existing observation 🔎";
    expect(decodeControlRoomDiscovery(raw).cursor.note).toBe(raw.cursor.note);
    const sparse: unknown[] = Array(1);
    discoveryUnavailable({ ...raw, codex_sessions: sparse });
    discoveryUnavailable({ ...raw, codex_sessions: [{ session_id: "stem", date: undefined }] });
  });

  it("honors the complete canonical Discovery JSON byte ceiling, including wrappers", () => {
    const raw = discovery();
    raw.cursor.note = "";
    const overhead = new TextEncoder().encode(JSON.stringify(raw)).byteLength;
    raw.cursor.note = "x".repeat(MAX_RESPONSE_BYTES - overhead);
    expect(new TextEncoder().encode(JSON.stringify(raw)).byteLength).toBe(MAX_RESPONSE_BYTES);
    expect(() => decodeControlRoomDiscovery(raw)).not.toThrow();
    raw.cursor.note += "x";
    discoveryUnavailable(raw);
    raw.cursor.note = "é".repeat(MAX_RESPONSE_BYTES / 2);
    discoveryUnavailable(raw);
  });
});

describe("navigation within the original full State projection", () => {
  const state = () => ({
    control_room: realControlRoomFixture(), capabilities: {},
    composed_at: "2026-10-19T00:00:00Z", refresh_in_flight: false,
    live_builds_active: false, state_refresh_error: null, source_validity: {},
  });
  it("keeps the actual reducer's Programme and navigation observations together", () => {
    const raw = state(), decoded = decodeControlRoomRead(raw);
    expect(decoded.state).toBe("AVAILABLE");
    expect(decoded.programs).toHaveLength(raw.control_room.work.length);
    expect(decoded.navigation.state).toBe("AVAILABLE");
  });
  it.each(["capabilities", "locator"] as const)(
    "retains exact valid Programme cards when %s navigation is malformed", defect => {
      const raw = state(), expected = decodeControlRoomRead(raw).programs;
      if (defect === "capabilities")
        Object.assign(raw, { capabilities: null });
      else Object.assign(raw.control_room.work[0].bindings[0],
        { locator: { session_id: "must not be projected" } });
      const decoded = decodeControlRoomRead(raw);
      expect(decoded.programs).toEqual(expected);
      expect(decoded.navigation).toEqual({
        state: "UNAVAILABLE", reason: "CONTROL_ROOM_NAVIGATION_INVALID",
      });
    },
  );
  it("keeps malformed Programme source fatal to the full State read", () => {
    const raw = state();
    raw.control_room.work[0].work_ref = "WS:invalid reference";
    expect(() => decodeControlRoomRead(raw)).toThrow("CONTROL_ROOM_SOURCE_UNAVAILABLE");
  });
});
