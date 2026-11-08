/** Closed original-Session body reader. No Agent, auth, profile or listener. */
import {join} from "node:path";
import {Context} from "@deepseek-ai/cordis";
import SessionStore, {SessionId} from "@deepseek-ai/dsh-session";
import * as JsonlPersistence from "@deepseek-ai/dsh-session-persistence-jsonl";
import {SqliteSessionQueryEngine} from "@deepseek-ai/dsh-session-query-sqlite";
import TypertRegistry from "@deepseek-ai/dsh-typert-registry";
import RemoteAccessService from "@deepseek-ai/dsh-api-remote-access";
import {TypertGatewayService} from "@deepseek-ai/dsh-api-gateway";
import {Peer} from "@deepseek-ai/dsh-client-connection";
import {Remote, RemoteError, TypertRemoteService} from "@deepseek-ai/dsh-typert-protocol";
import type {SessionPage, SessionPageRequest} from "@deepseek-ai/dsh-api-session-controller";
import {SessionHistoryController} from "mmx-pinned-native-history";
import type {Duplex} from "node:stream";
import {attachExecutiveReadPort, syncGuard, type InstalledNativeReadSource} from "./executive-read-port";

class ClosedSessionHistory extends TypertRemoteService {
  private readonly history: SessionHistoryController;
  constructor(ctx: Context, private readonly sessionId: string, private readonly requireCurrent: () => void) {
    super(ctx, "sessionController", {namespace: "session"});
    ctx.typert.resources.register("session", {field: "sessionId"});
    this.history = new SessionHistoryController(ctx, () => {
      throw new Error("Closed history cannot promote a Session");
    });
  }
  @Remote({name: "page", resources: {session: (request: SessionPageRequest) =>
    request.address.kind === "session" ? request.address.sessionId : request.address.childSessionId}})
  async page(request: SessionPageRequest, signal: AbortSignal): Promise<SessionPage> {
    this.requireCurrent();
    if (request.address.kind !== "session" || request.address.sessionId !== this.sessionId ||
        this.ctx.sessions.get(SessionId(this.sessionId)) !== undefined) {
      throw new RemoteError("remote-access/denied", "Closed native history binding differs", {});
    }
    const result = await this.history.page(request, signal);
    this.requireCurrent();
    return result;
  }
}

/** Trusted launcher inputs; frames cannot select a store or create a Session. */
export async function openClosedNativeHistory(
  home: string, port: Duplex, source: InstalledNativeReadSource,
): Promise<{dispose(): Promise<void>}> {
  const selected = source.association, sourceSignal = source.signal, sourceGuard = source.requireCurrent;
  syncGuard(sourceGuard);
  sourceSignal.throwIfAborted();
  const root = new Context(), life = new AbortController();
  let attached: ReturnType<typeof attachExecutiveReadPort> | undefined;
  let disposal: Promise<void> | undefined;
  const signal = AbortSignal.any([life.signal, sourceSignal]);
  const current = (): void => {
    signal.throwIfAborted();
    if (source.association !== selected || source.signal !== sourceSignal || source.requireCurrent !== sourceGuard)
      throw new Error("Closed native read owner changed");
    syncGuard(sourceGuard);
    signal.throwIfAborted();
  };
  const dispose = (): Promise<void> => {
    disposal ??= Promise.resolve().then(async () => {
      life.abort();
      // Drain the active answer and its persistence handle before root disposal.
      try {await attached?.dispose();}
      finally {await root.fiber.dispose();}
    });
    return disposal;
  };
  try {
    current();
    await root.plugin(TypertRegistry);
    await root.plugin(SessionStore);
    await root.plugin(JsonlPersistence, {root: join(home, "sessions"), compression: "zstd"});
    await root.plugin(SqliteSessionQueryEngine, {
      path: ":memory:", openAt: "never", preparedSessionCacheSize: 1, persistedReadConcurrency: 1,
    });
    await root.plugin(RemoteAccessService);
    await root.plugin(TypertGatewayService, {});
    await root.plugin({
      name: "mastermind-closed-session-page",
      inject: ["sessions", "sessionPersistence", "sessionQuery", "typert"],
      apply(ctx: Context) {new ClosedSessionHistory(ctx, source.association.native_session_id, current);},
    });
    await root.plugin({
      name: "mastermind-closed-session-port", inject: ["remoteAccess", "typertGateway"],
      apply(ctx: Context) {
        current();
        attached = attachExecutiveReadPort(ctx, port, {
          association: source.association, signal, requireCurrent: current,
        }, (owner, options) => new Peer(owner, options));
      },
    });
    current();
    if (attached === undefined) throw new Error("Closed native reader was not composed");
    return Object.freeze({dispose});
  } catch (error) {await dispose(); throw error;}
}
