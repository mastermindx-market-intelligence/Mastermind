/** Finite Executive history reads on an inherited, already-connected port.
 * The original launcher supplies this capability and the exact association.
 * Frames carry no credential and cannot authenticate or select a session.
 */
import {createHash} from "node:crypto";
import {Duplex} from "node:stream";
import type {Context} from "@deepseek-ai/cordis";
import {createScope} from "@deepseek-ai/dsh-scope";
import type {SessionId} from "@deepseek-ai/dsh-session";
import {createCompanySessionReadBridge, type CompanySessionReader} from "./company-peer";
import {DONOR_SHA} from "./protocol";

/** The caller mounts this leaf inside its original Cordis composition. */
export const inject = ["connection", "remoteAccess", "typertGateway"] as const;

export interface InstalledNativeReadAssociation {
  readonly schema: "mastermind.dsh.native_read_association.v1";
  readonly work_ref: string;
  readonly root_job_id: string;
  readonly native_session_id: string;
  readonly owner_principal_scope: string;
  readonly composition_sha256: string;
  readonly native_package_sha256: string;
  readonly donor_sha: typeof DONOR_SHA;
}
export interface InstalledNativeReadSource {
  readonly association: InstalledNativeReadAssociation;
  readonly signal: AbortSignal;
  /** Actual native process/association custody, supplied by trusted composition. */
  readonly requireCurrent: () => void;
}
const REQUEST = "mastermind.dsh.native_read.v1";
const RESPONSE = "mastermind.dsh.native_read_result.v1";
// The incumbent private CeoIngress frame bounds, including each newline.
const REQUEST_BYTES = 8192, RESPONSE_BYTES = 32768;
const SHA = /^[0-9a-f]{64}$/u;
const plain = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && Object.getPrototypeOf(value) === Object.prototype;
function keys(value: unknown, expected: readonly string[]): value is Record<string, unknown> {
  return plain(value) && Object.keys(value).length === expected.length && expected.every(key => Object.hasOwn(value, key));
}
const canonical = (value: unknown): string => JSON.stringify(value, (_key, item: unknown) =>
  plain(item) ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
const hash = (value: unknown): string => createHash("sha256").update(canonical(value)).digest("hex");
const safe = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
function syncGuard(guard: () => void): void {
  const result: unknown = guard();
  if (result !== undefined) {
    if (result && typeof (result as PromiseLike<unknown>).then === "function")
      void Promise.resolve(result).catch(() => {});
    throw new Error("Native read source is unavailable");
  }
}
function association(value: InstalledNativeReadAssociation): void {
  if (!keys(value, ["schema", "work_ref", "root_job_id", "native_session_id", "owner_principal_scope",
      "composition_sha256", "native_package_sha256", "donor_sha"]) ||
      value.schema !== "mastermind.dsh.native_read_association.v1" || value.donor_sha !== DONOR_SHA ||
      typeof value.work_ref !== "string" || !/^WS:[A-Z0-9][A-Za-z0-9._-]{1,63}$/u.test(value.work_ref) ||
      typeof value.root_job_id !== "string" || !/^JOB-[0-9]{1,9}$/u.test(value.root_job_id) ||
      typeof value.native_session_id !== "string" || !value.native_session_id || value.native_session_id.length > 256 ||
      /[\u0000-\u001f\u007f\ud800-\udfff]/u.test(value.native_session_id) ||
      ![value.owner_principal_scope, value.composition_sha256, value.native_package_sha256]
        .every(value => typeof value === "string" && SHA.test(value))) {
    throw new TypeError("Exact installed native read association required");
  }
}
type Read = {kind: "snapshot"} | {kind: "page"; through_seq: number; before_seq: number | null; max_messages: number};
type Frame = {
  schema: typeof REQUEST; request_id: string; association_sha256: string;
  principal: {principal_scope: string; issued_at: number; expires_at: number};
  read: Read;
};
function frame(value: unknown): value is Frame {
  if (!keys(value, ["schema", "request_id", "association_sha256", "principal", "read"]) ||
      value.schema !== REQUEST || typeof value.request_id !== "string" || !SHA.test(value.request_id) ||
      typeof value.association_sha256 !== "string" || !SHA.test(value.association_sha256) ||
      !keys(value.principal, ["principal_scope", "issued_at", "expires_at"]) ||
      typeof value.principal.principal_scope !== "string" || !SHA.test(value.principal.principal_scope) ||
      !safe(value.principal.issued_at) || !safe(value.principal.expires_at) ||
      value.principal.issued_at >= value.principal.expires_at) return false;
  const read = value.read;
  if (keys(read, ["kind"]) && read.kind === "snapshot") return true;
  return keys(read, ["kind", "through_seq", "before_seq", "max_messages"]) && read.kind === "page" &&
    (safe(read.through_seq) || read.through_seq === -1) && (read.before_seq === null || safe(read.before_seq) && read.before_seq <= read.through_seq + 1) &&
    safe(read.max_messages) && read.max_messages >= 1 && read.max_messages <= 8;
}

/** One port in its existing Cordis fiber. No listener, retry, queue or native
 * session lifecycle is introduced. Concurrent/pipelined requests are refused. */
export function attachExecutiveReadPort(ctx: Context, port: Duplex, source: InstalledNativeReadSource): {
  dispose(): Promise<void>;
} {
  association(source.association);
  if (!(port instanceof Duplex) || port.destroyed || !port.readable || !port.writable ||
      !(source.signal instanceof AbortSignal) || typeof source.requireCurrent !== "function") {
    throw new TypeError("Inherited native duplex and trusted source required");
  }
  const selected = source.association, selectedDigest = hash(selected);
  const sourceSignal = source.signal, sourceGuard = source.requireCurrent;
  // Refuse before registering a policy or acquiring a child fiber.
  if (sourceSignal.aborted) throw new Error("Native read source is unavailable");
  syncGuard(sourceGuard);
  const lifetime = new AbortController();
  const scope = createScope(ctx, {});
  let bridge: ReturnType<typeof createCompanySessionReadBridge>;
  let retired = false, busy = false, buffer = Buffer.alloc(0);
  let reader: CompanySessionReader | undefined;
  let activeAnswer: Promise<void> | undefined;
  let disposal: Promise<void> | undefined;
  const closed = port.closed ? Promise.resolve() : new Promise<void>(resolve => port.once("close", resolve));

  function retire(): void {
    if (retired) return;
    retired = true;
    sourceSignal.removeEventListener("abort", onRetired);
    port.off("data", onData);
    lifetime.abort();
    port.destroy();
  }
  function dispose(): Promise<void> {
    // Publish the shared drain before abort/close can re-enter this function.
    disposal ??= Promise.resolve().then(() => scope.dispose());
    retire();
    return disposal;
  }
  const onRetired = (): void => { void dispose().catch(() => {}); };
  function current(): void {
    if (retired || lifetime.signal.aborted || sourceSignal.aborted || port.destroyed ||
        source.association !== selected || source.signal !== sourceSignal ||
        source.requireCurrent !== sourceGuard || hash(selected) !== selectedDigest) {
      onRetired(); throw new Error("Native read source is unavailable");
    }
    try { syncGuard(sourceGuard); }
    catch { onRetired(); throw new Error("Native read source is unavailable"); }
  }

  async function answer(request: Frame): Promise<void> {
    const invocation = new AbortController();
    const signal = AbortSignal.any([invocation.signal, lifetime.signal, sourceSignal]);
    const expiry = setTimeout(() => invocation.abort(),
      Math.min(2**31-1, Math.max(0, request.principal.expires_at * 1000-Date.now())));
    expiry.unref();
    const requireRead = (): void => {
      current(); signal.throwIfAborted();
      const now = Date.now() / 1000;
      if (request.association_sha256 !== selectedDigest ||
          request.principal.principal_scope !== selected.owner_principal_scope ||
          !(request.principal.issued_at <= now && now < request.principal.expires_at))
        throw new Error("Native read invocation is unavailable");
    };
    let status: "READ" | "UNAVAILABLE" | "PAGE_TOO_LARGE" = "UNAVAILABLE";
    let data: {projections: unknown; page: unknown} | null = null;
    try {
      requireRead();
      reader = bridge.open({
        principalScope: request.principal.principal_scope,
        // A finite invocation label only; never the frontend authorization epoch.
        authorizationGeneration: request.request_id,
        workRef: selected.work_ref, sessionId: selected.native_session_id as SessionId,
        signal, requireCurrent: requireRead,
      });
      if (request.read.kind === "snapshot") {
        const projections = await reader.projections(signal);
        const page = projections?.kind === "sequenced"
          ? await reader.page({throughSeq: projections.asOfSeq, maxMessages: 8}, signal) : null;
        data = {projections, page};
      } else {
        const read = request.read;
        data = {projections: null, page: await reader.page({
          throughSeq: read.through_seq, maxMessages: read.max_messages,
          ...(read.before_seq === null ? {} : {beforeSeq: read.before_seq}),
        }, signal)};
      }
      requireRead();
      status = "READ";
    } catch {
      data = null;
    } finally {
      clearTimeout(expiry);
      invocation.abort();
      await reader?.dispose();
      reader = undefined;
    }
    current();
    const response = () => Buffer.from(JSON.stringify({
      schema: RESPONSE, request_id: request.request_id, association_sha256: selectedDigest, status, data,
    }) + "\n");
    let raw = response();
    if (raw.byteLength > RESPONSE_BYTES) {
      status = "PAGE_TOO_LARGE"; data = null; raw = response();
    }
    // The principal may have expired during disposal/serialization.
    const now = Date.now() / 1000;
    if (status === "READ" && !(request.principal.issued_at <= now && now < request.principal.expires_at)) {
      status = "UNAVAILABLE"; data = null; raw = response();
    }
    current();
    await new Promise<void>((resolve, reject) => {
      const onClosed = (): void => done(new Error("Native read port closed"));
      const done = (error?: Error | null): void => {
        port.off("close", onClosed); port.off("error", done);
        if (error) reject(error); else resolve();
      };
      port.once("close", onClosed); port.once("error", done);
      if (port.destroyed) { onClosed(); return; }
      port.write(raw, done);
    });
  }

  function onData(chunk: unknown): void {
    try {
      current();
      if (busy || !Buffer.isBuffer(chunk) || buffer.byteLength + chunk.byteLength > REQUEST_BYTES) {
        onRetired(); return;
      }
      buffer = Buffer.concat([buffer, chunk]);
      const end = buffer.indexOf(10);
      if (end < 0) return;
      if (end !== buffer.byteLength - 1) { onRetired(); return; }
      const raw = new TextDecoder("utf-8", {fatal: true, ignoreBOM: true}).decode(buffer.subarray(0, end));
      buffer = Buffer.alloc(0);
      const request: unknown = JSON.parse(raw);
      // Canonical input rejects duplicate keys, alternate spellings and shadow fields.
      if (!frame(request) || canonical(request) !== raw) { onRetired(); return; }
      busy = true;
      activeAnswer = answer(request).catch(onRetired).finally(() => { busy = false; });
    } catch { onRetired(); }
  }
  port.on("end", onRetired);
  port.on("close", onRetired);
  port.on("error", onRetired);
  scope.ctx.effect(() => async () => {
    retire();
    // This cleanup never awaits its own scope. Public dispose and parent fiber
    // disposal share the donor's original quiescence boundary.
    await activeAnswer;
    await reader?.dispose();
    await closed;
    port.off("end", onRetired); port.off("close", onRetired); port.off("error", onRetired);
  }, "mastermind: inherited native read port");
  try {
    current();
    bridge = createCompanySessionReadBridge(scope.ctx);
    sourceSignal.addEventListener("abort", onRetired, {once: true});
    port.on("data", onData);
    current();
    return Object.freeze({dispose});
  } catch (error) {
    onRetired();
    throw error;
  }
}
