/** A transient view of the incumbent native event replay, never a receipt,
 * message store, retry queue, or authority to submit/settle an operation. */
export interface NativeLiveTarget {
  sessionId: string;
  admissionId: string;
  authorityEpoch: number;
  executionGeneration: number | null;
}
export interface NativeLiveFrame extends NativeLiveTarget {
  schema: "mastermind.hermes_native_stream.v1";
  authGeneration: number;
  replayEpoch: string;
  sequence: number;
  state: "live" | "complete" | "interrupted";
  text: string;
  activity: "working" | "responding" | "tool";
  code: string | null;
}
const keys = ["schema", "authGeneration", "sessionId", "admissionId", "authorityEpoch", "executionGeneration",
  "replayEpoch", "sequence", "state", "text", "activity", "code"];
const id = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$/;
const integer = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
function invalid(): never { throw new Error("NATIVE_STREAM_INVALID"); }
export function decodeLiveFrame(value: unknown): NativeLiveFrame {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  const v = value as Record<string, unknown>;
  if (Object.keys(v).length !== keys.length || keys.some(key => !(key in v)) || v.schema !== "mastermind.hermes_native_stream.v1" ||
    !["sessionId", "admissionId", "replayEpoch"].every(key => typeof v[key] === "string" && id.test(v[key])) ||
    ![v.authGeneration, v.authorityEpoch, v.sequence].every(integer) ||
    v.executionGeneration !== null && !integer(v.executionGeneration) ||
    !["live", "complete", "interrupted"].includes(v.state as string) ||
    !["working", "responding", "tool"].includes(v.activity as string) ||
    v.code !== null && (typeof v.code !== "string" || !/^NATIVE_[A-Z_]{1,80}$/.test(v.code)) ||
    typeof v.text !== "string" || new TextEncoder().encode(v.text).length > 262144 ||
    /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(v.text)) return invalid();
  return v as unknown as NativeLiveFrame;
}

/** Bind the whole observation to a single sign-in, native owner, admission and
 * replay epoch. An old view cannot contribute text to the next conversation. */
export function liveFrameGuard(target: NativeLiveTarget, authGeneration: number) {
  let replay: string | null = null;
  let sequence = -1;
  let generation = target.executionGeneration;
  let previousText: string | null = null;
  let closed = false;
  return (value: unknown): NativeLiveFrame => {
    const frame = decodeLiveFrame(value);
    if (closed || frame.authGeneration !== authGeneration || frame.sessionId !== target.sessionId ||
      frame.admissionId !== target.admissionId || frame.authorityEpoch !== target.authorityEpoch ||
      replay !== null && frame.replayEpoch !== replay || frame.sequence < sequence ||
      frame.sequence === sequence && previousText !== null && frame.text !== previousText ||
      generation !== null && frame.executionGeneration !== generation) return invalid();
    replay = frame.replayEpoch; sequence = frame.sequence; previousText = frame.text;
    if (frame.executionGeneration !== null) generation = frame.executionGeneration;
    closed = frame.state !== "live";
    return frame;
  };
}
