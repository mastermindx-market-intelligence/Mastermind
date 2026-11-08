/** Private host-composition reader over the incumbent native Connection/Gateway.
 *
 * The installed Executive owner supplies the current principal/session binding.
 * These callbacks are host capabilities, never a wire format or a token verifier.
 * Browser cookies, frame context and session IDs cannot construct that authority.
 */
import type {Context} from "@deepseek-ai/cordis";
import type {} from "@deepseek-ai/dsh-client-connection";
import type {} from "@deepseek-ai/dsh-api-gateway";
import type {RemoteAccessBinding, RemoteAccessRole} from "@deepseek-ai/dsh-api-remote-access";
import type {SessionId} from "@deepseek-ai/dsh-session";
import type {PeerScope} from "@deepseek-ai/dsh-typert-protocol";
import type {PeerOptions} from "@deepseek-ai/dsh-client-connection";
import type {SessionPage, SessionPageRequest, SessionProjectionsValue} from "@deepseek-ai/dsh-api-session-controller";

export interface CompanySessionReadBinding {
  readonly principalScope: string;
  readonly authorizationGeneration: string;
  readonly workRef: string;
  readonly sessionId: SessionId;
  /** The incumbent authorization owner aborts this on retirement, including A→B→A. */
  readonly signal: AbortSignal;
  /** Synchronous current principal, expiry, project and native association guard. */
  readonly requireCurrent: () => void;
}

declare module "@deepseek-ai/dsh-typert-protocol" {
  interface PrincipalMap {
    /** Credential-free identity only; live permission remains with Executive. */
    "mastermind-company-read": {
      readonly kind: "mastermind-company-read";
      readonly principalScope: string;
      readonly authorizationGeneration: string;
      readonly workRef: string;
    };
  }
}

export type CompanyHistoryPageRequest = Omit<SessionPageRequest, "address">;
export interface CompanySessionReader {
  projections(signal?: AbortSignal): Promise<SessionProjectionsValue>;
  page(request: CompanyHistoryPageRequest, signal?: AbortSignal): Promise<SessionPage>;
  /** An actual native projection cut, without opening a follow/resume stream. */
  snapshotPage(signal?: AbortSignal): Promise<{
    readonly projections: SessionProjectionsValue;
    readonly page: SessionPage | null;
  }>;
  /** Retires this connection consumer, not the native Agent or its admitted work. */
  dispose(): Promise<void>;
}

const ROLE: RemoteAccessRole<"session"> = Object.freeze({
  name: "mastermind:exact-session-history",
  resource: "session",
  actions: Object.freeze(["session/page", "session/projections"] as const),
});
const unavailable = () => new Error("Company native session read is no longer current");
function text(value: unknown, limit: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= limit &&
    !/[\u0000-\u001f\u007f]/u.test(value);
}
function pageRequest(request: CompanyHistoryPageRequest, sessionId: SessionId): SessionPageRequest {
  if (!request || typeof request !== "object" || Array.isArray(request) ||
      Object.getPrototypeOf(request) !== Object.prototype ||
      Reflect.ownKeys(request).some(key => !["throughSeq", "beforeSeq", "maxMessages", "turnWindow"].includes(String(key)))) {
    throw new TypeError("Fixed native history page fields required");
  }
  // Copy only the native page contract before any await. The original Gateway
  // owns its codecs and cursor validation; callers never supply another address.
  return structuredClone({...request, address: {kind: "session" as const, sessionId}});
}

/** One policy registration in the existing host fiber; no session registry,
 * authentication service, listener, operation store or new transcript owner. */
export type CompanyReadPeerFactory = (owner: Context, options: PeerOptions) => PeerScope;

export function createCompanySessionReadBridge(ctx: Context,
  createPeer: CompanyReadPeerFactory = (owner, options) => owner.connection.createPeer(options)): {
  open(binding: CompanySessionReadBinding): CompanySessionReader;
} {
  let active = true;
  const readers = new WeakMap<object, () => readonly RemoteAccessBinding[]>();
  ctx.remoteAccess.registerPolicy("mastermind-company-read", {
    bindings: principal => readers.get(principal)?.() ?? [],
  });
  ctx.effect(() => () => { active = false; }, "mastermind: native reader composition");

  return Object.freeze({
    open(binding: CompanySessionReadBinding): CompanySessionReader {
      if (!binding || !text(binding.principalScope, 256) ||
          !text(binding.authorizationGeneration, 256) ||
          !text(binding.sessionId, 256) || !text(binding.workRef, 131) || !/^WS:[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(binding.workRef) ||
          !(binding.signal instanceof AbortSignal) || typeof binding.requireCurrent !== "function") {
        throw new TypeError("Trusted current company session read binding required");
      }
      const {principalScope, authorizationGeneration, workRef, sessionId, signal, requireCurrent} = binding;
      const principal = Object.freeze({
        kind: "mastermind-company-read" as const, principalScope, authorizationGeneration, workRef,
      });
      let peer: PeerScope | undefined;
      let retired = false;
      let disposal: Promise<void> | undefined;
      const dispose = (): Promise<void> => {
        retired = true;
        readers.delete(principal);
        signal.removeEventListener("abort", onRetired);
        return disposal ??= peer?.dispose() ?? Promise.resolve();
      };
      const onRetired = (): void => { void dispose().catch(() => {}); };
      function current(): void {
        if (!active || retired || signal.aborted || peer?.signal.aborted ||
            binding.principalScope !== principalScope || binding.authorizationGeneration !== authorizationGeneration ||
            binding.workRef !== workRef || binding.sessionId !== sessionId ||
            binding.signal !== signal || binding.requireCurrent !== requireCurrent) {
          onRetired();
          throw unavailable();
        }
        try {
          const result: unknown = requireCurrent();
          // Promise-valued guards are not admission. Their rejections must not
          // become unhandled work while this synchronous boundary fails closed.
          if (result !== undefined) {
            if (result && typeof (result as PromiseLike<unknown>).then === "function")
              void Promise.resolve(result).catch(() => {});
            throw unavailable();
          }
        } catch {
          onRetired();
          throw unavailable();
        }
      }
      current();
      peer = createPeer(ctx, {principal, interactions: "none"});
      const exactPeer = peer;
      readers.set(principal, () => {
        try {
          current();
          return [{role: ROLE, resource: {kind: "session", id: sessionId}}];
        } catch { return []; }
      });
      signal.addEventListener("abort", onRetired, {once: true});
      exactPeer.ctx.effect(() => () => {
        retired = true;
        readers.delete(principal);
        signal.removeEventListener("abort", onRetired);
      }, "mastermind: current native reader");
      current();

      async function invoke(method: "page" | "projections", request: object, callerSignal?: AbortSignal): Promise<unknown> {
        current();
        const cancellation = AbortSignal.any([signal, exactPeer.signal, ...(callerSignal ? [callerSignal] : [])]);
        cancellation.throwIfAborted();
        const value = await ctx.typertGateway.invoke({
          namespace: "session", method, args: {request}, peer: exactPeer, signal: cancellation,
        });
        cancellation.throwIfAborted();
        current();
        return value;
      }
      const projections = (callerSignal?: AbortSignal): Promise<SessionProjectionsValue> =>
        invoke("projections", {sessionId}, callerSignal) as Promise<SessionProjectionsValue>;
      const page = (request: CompanyHistoryPageRequest, callerSignal?: AbortSignal): Promise<SessionPage> =>
        invoke("page", pageRequest(request, sessionId), callerSignal) as Promise<SessionPage>;
      return Object.freeze({
        projections,
        page,
        async snapshotPage(callerSignal?: AbortSignal) {
          const observed = await projections(callerSignal);
          current();
          if (observed === null || observed.kind !== "sequenced") return {projections: observed, page: null};
          const history = await page({throughSeq: observed.asOfSeq}, callerSignal);
          current();
          return {projections: observed, page: history};
        },
        dispose,
      });
    },
  });
}
