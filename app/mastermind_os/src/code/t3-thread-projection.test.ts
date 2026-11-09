import { describe, expect, it } from "vitest";
import { parseT3ThreadList, readT3ThreadProjection, t3ThreadUrl } from "./t3-thread-projection";

function thread(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    threadId: "abc123", environment: "m2studio", title: "Fix fabric launch",
    runState: "running", lastActivity: "2026-11-09T00:00:00Z",
    prLink: "https://github.com/acme/repo/pull/12", repository: "acme/repo",
    companyManaged: true,
    ...extra,
  };
}
function list(threads: Record<string, unknown>[]) {
  return { schema: "mastermind.t3_thread_projection_list.v1", threads };
}

describe("mastermind.t3_thread_projection/v1 fail-closed parser", () => {
  it("accepts a full projection and normalizes nothing silently", () => {
    const view = parseT3ThreadList(list([
      thread(),
      thread({ threadId: "idle-1", environment: "chatgpt1", runState: "idle", prLink: null, repository: null, lastActivity: null, title: null, companyManaged: false }),
      thread({ threadId: "blocked-1", runState: "blocked" }),
      thread({ threadId: "unknown-1", runState: "unknown" }),
    ]));
    expect(view.threads.map(item => item.threadId)).toEqual(["abc123", "idle-1", "blocked-1", "unknown-1"]);
    expect(view.threads[1]!.prLink).toBeNull();
    expect(view.threads[1]!.title).toBeNull();
  });
  it("rejects wrong schema, unknown keys, missing keys and non-array threads", () => {
    expect(() => parseT3ThreadList({ schema: "mastermind.t3_thread_projection_list.v2", threads: [] })).toThrow("T3_PROJECTION_INVALID");
    expect(() => parseT3ThreadList({ schema: "mastermind.t3_thread_projection_list.v1", threads: [], extra: 1 })).toThrow("T3_PROJECTION_INVALID");
    expect(() => parseT3ThreadList({ schema: "mastermind.t3_thread_projection_list.v1" })).toThrow("T3_PROJECTION_INVALID");
    expect(() => parseT3ThreadList({ schema: "mastermind.t3_thread_projection_list.v1", threads: "none" })).toThrow("T3_PROJECTION_INVALID");
  });
  it("rejects bad ids, environments, run states, timestamps and non-https links", () => {
    expect(() => parseT3ThreadList(list([thread({ threadId: "bad id" })]))).toThrow("T3_PROJECTION_INVALID");
    expect(() => parseT3ThreadList(list([thread({ environment: "not allowed!" })]))).toThrow("T3_PROJECTION_INVALID");
    expect(() => parseT3ThreadList(list([thread({ runState: "fast" })]))).toThrow("T3_PROJECTION_INVALID");
    expect(() => parseT3ThreadList(list([thread({ lastActivity: "now" })]))).toThrow("T3_PROJECTION_INVALID");
    expect(() => parseT3ThreadList(list([thread({ prLink: "http://insecure.example/pr/1" })]))).toThrow("T3_PROJECTION_INVALID");
    expect(() => parseT3ThreadList(list([thread({ companyManaged: "yes" })]))).toThrow("T3_PROJECTION_INVALID");
  });
  it("rejects duplicate environment/thread identity pairs", () => {
    expect(() => parseT3ThreadList(list([thread(), thread()]))).toThrow("T3_PROJECTION_INVALID");
    expect(() => parseT3ThreadList(list([thread(), thread({ environment: "chatgpt2" })]))).not.toThrow();
  });
});

describe("t3ThreadUrl deep link", () => {
  it("builds the documented T3 thread scheme with exact-path encoding", () => {
    expect(t3ThreadUrl("m2studio", "abc123")).toBe("https://app.t3.codes/threads/m2studio/abc123");
    expect(t3ThreadUrl("remote host", "th/ead")).toBe("https://app.t3.codes/threads/remote%20host/th%2Fead");
  });
});

describe("readT3ThreadProjection through the host facade", () => {
  it("reports NOT_CONNECTED without a source and fails closed on every defect", () => {
    expect(readT3ThreadProjection(undefined)).toEqual({ kind: "UNAVAILABLE", reason: "T3_PROJECTION_SOURCE_NOT_CONNECTED" });
    expect(readT3ThreadProjection({})).toEqual({ kind: "UNAVAILABLE", reason: "T3_PROJECTION_SOURCE_NOT_CONNECTED" });
    const failing = { t3ThreadProjection: { read: () => { throw new Error("down"); } } };
    expect(readT3ThreadProjection(failing)).toEqual({ kind: "UNAVAILABLE", reason: "T3_PROJECTION_SOURCE_READ_FAILED" });
    const empty = { t3ThreadProjection: { read: () => undefined } };
    expect(readT3ThreadProjection(empty)).toEqual({ kind: "UNAVAILABLE", reason: "T3_PROJECTION_SOURCE_EMPTY" });
    const invalid = { t3ThreadProjection: { read: () => list([thread({ runState: "zooming" })]) } };
    expect(readT3ThreadProjection(invalid)).toEqual({ kind: "UNAVAILABLE", reason: "T3_PROJECTION_SOURCE_INVALID" });
  });
  it("returns AVAILABLE only for a verified list", () => {
    const host = { t3ThreadProjection: { read: () => list([thread()]) } };
    const read = readT3ThreadProjection(host);
    expect(read.kind).toBe("AVAILABLE");
    if (read.kind !== "AVAILABLE") return;
    expect(read.list.threads[0]!.threadId).toBe("abc123");
  });
});
