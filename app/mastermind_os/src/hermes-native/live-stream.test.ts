import { describe, expect, it } from "vitest";
import { decodeLiveFrame, liveFrameGuard, type NativeLiveFrame } from "./live-stream";

const target = { sessionId: "logical-session", admissionId: "original", authorityEpoch: 2, executionGeneration: null };
const frame = (extra: Partial<NativeLiveFrame> = {}): NativeLiveFrame => ({ ...target,
  schema: "mastermind.hermes_native_stream.v1", authGeneration: 7, replayEpoch: "epoch", sequence: 1,
  state: "live", text: "Hello 🌱", activity: "responding", code: null, executionGeneration: 3, ...extra });

describe("native live render boundary", () => {
  it("binds queued-to-started once and allows equal-sequence terminal evidence", () => {
    const read = liveFrameGuard(target, 7);
    read(frame({ executionGeneration: null, sequence: 0, text: "" }));
    expect(read(frame()).text).toBe("Hello 🌱");
    expect(read(frame({ state: "complete" })).state).toBe("complete");
    expect(() => read(frame({ sequence: 2 }))).toThrow("NATIVE_STREAM_INVALID");
  });
  it.each([
    { authGeneration: 8 }, { sessionId: "another" }, { admissionId: "foreign" },
    { authorityEpoch: 3 }, { executionGeneration: 4 }, { replayEpoch: "restarted" },
    { sequence: 0 }, { text: "different text at the same sequence" },
  ])("rejects crossed or regressed views: %j", change => {
    const read = liveFrameGuard(target, 7); read(frame());
    expect(() => read(frame(change))).toThrow("NATIVE_STREAM_INVALID");
  });
  it("rejects extra native payloads, invalid text and unbounded output", () => {
    expect(() => decodeLiveFrame({ ...frame(), toolResult: "private" })).toThrow();
    expect(() => decodeLiveFrame(frame({ text: "x".repeat(262145) }))).toThrow();
    expect(() => decodeLiveFrame(frame({ text: "\u0000" }))).toThrow();
    expect(() => decodeLiveFrame(frame({ sequence: Number.MAX_SAFE_INTEGER + 1 }))).toThrow();
  });
});
