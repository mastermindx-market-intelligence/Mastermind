/**
 * Inbox Terminal sharing-request feed controller.
 *
 * Reads once per Inbox enablement and distinct native Terminal epoch; no
 * polling, timers, automatic or supplied retry. Presentation receives view
 * projections only: the actual issued requests stay private to this hook and
 * to the host, and review resolves a view back to its issued object by full
 * tuple, never from caller-supplied UUIDs. Host and status changes withdraw
 * the feed in the same render and abort the in-flight ticket. There is no
 * Auth0 dependency: sign-in actions go only to the distinct native Terminal
 * host, and a missing capability never triggers an auth action.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  TerminalSessionStatus,
  TerminalSharingFeedRead,
  TerminalSharingSource,
} from "../terminal/terminal-sharing-host";
import type {
  TerminalSharingCoverageState,
  TerminalSharingRequest,
} from "../terminal/terminal-sharing-contract";
import type { BriefSharingRequestView } from "./BriefSharingInbox";

export type TerminalSharingFeedState = "unavailable" | "loading" | "ready";

export interface TerminalSharingCoverageView {
  readonly state: TerminalSharingCoverageState;
  readonly reasonCodes: readonly string[];
}

export interface TerminalSharingFeedController {
  readonly state: TerminalSharingFeedState;
  readonly requests: readonly BriefSharingRequestView[];
  readonly coverage: TerminalSharingCoverageView | null;
  /** Public own Terminal status; opaque scope hashes only, never raw ids. */
  readonly session: TerminalSessionStatus | null;
  /** Resolves only for a view tuple present in the current live feed. */
  onReview(view: BriefSharingRequestView): Promise<void>;
  onConnect(): Promise<void>;
  onDisconnect(): Promise<void>;
}

const EMPTY_VIEWS: readonly BriefSharingRequestView[] = [];

function tupleKey(
  requestRef: string,
  revision: string,
  deliveryId: string,
  contentSha256: string,
): string {
  return [requestRef, revision, deliveryId, contentSha256].join("|");
}

/**
 * View projection only. `requestRevision` is the fixed immutable request
 * revision rendered as a string; `version` stays null because revision 1 is
 * never an artifact version, and `access` states the intended delivery
 * permission only, never a granted audience access.
 */
function toView(request: TerminalSharingRequest): BriefSharingRequestView {
  return {
    requestRef: request.request_ref,
    requestRevision: String(request.revision),
    deliveryId: request.delivery.delivery_id,
    contentSha256: request.delivery.content_sha256,
    title: request.delivery.title,
    version: null,
    audienceName: request.audience.name,
    audienceMemberCount: request.audience.member_count,
    access: "VIEW_ONLY",
  };
}

interface LiveFeed {
  readonly host: TerminalSharingSource;
  readonly principalScope: string;
  readonly sessionScope: string;
  readonly generation: number;
  readonly views: readonly BriefSharingRequestView[];
  readonly coverage: TerminalSharingCoverageView;
  /** Actual issued requests for this read, keyed by full tuple. */
  readonly issued: ReadonlyMap<string, TerminalSharingRequest>;
}

function toLiveFeed(host: TerminalSharingSource, read: TerminalSharingFeedRead): LiveFeed {
  const issued = new Map<string, TerminalSharingRequest>();
  for (const request of read.feed.requests) {
    issued.set(
      tupleKey(
        request.request_ref,
        String(request.revision),
        request.delivery.delivery_id,
        request.delivery.content_sha256,
      ),
      request,
    );
  }
  return {
    host,
    generation: read.generation,
    principalScope: read.feed.viewer.principal_scope,
    sessionScope: read.feed.viewer.session_scope,
    views: read.feed.requests.map(toView),
    coverage: {
      state: read.feed.coverage.state,
      reasonCodes: read.feed.coverage.reason_codes,
    },
    issued,
  };
}

function signedInSnapshot(status: TerminalSessionStatus | null): boolean {
  return (
    status !== null &&
    status.state === "SIGNED_IN" &&
    status.available &&
    status.principal_scope !== null &&
    status.session_scope !== null
  );
}

export function useTerminalSharing(
  host: TerminalSharingSource | null,
  enabled: boolean,
): TerminalSharingFeedController {
  const [observed, setObserved] = useState<{ host: TerminalSharingSource | null; status: TerminalSessionStatus | null }>(() =>
    ({ host, status: host === null ? null : host.getState() }),
  );
  // Never apply the previous capability's status to a new host, even before effects run.
  const status = observed.host === host ? observed.status : host?.getState() ?? null;
  const [read, setRead] = useState<LiveFeed | null>(null);
  const [pending, setPending] = useState(false);

  const hostRef = useRef<TerminalSharingSource | null>(host);
  const liveReadRef = useRef<LiveFeed | null>(null);
  const startedRef = useRef<{ host: TerminalSharingSource; key: string } | null>(null);
  const ticketRef = useRef<{ ticket: number; controller: AbortController } | null>(null);
  const ticketSeqRef = useRef(0);

  // Follow the host's own status; the distinct Terminal epoch drives reads.
  useEffect(() => {
    if (host === null) {
      setObserved({ host, status: null });
      return;
    }
    setObserved({ host, status: host.getState() });
    return host.subscribe(status => setObserved({ host, status }));
  }, [host]);

  const active = host !== null && enabled && signedInSnapshot(status);

  // One read per Inbox activation and own status generation. Status or host
  // changes withdraw the feed in the same render, abort the old ticket and
  // ignore its stale completion; a dropped or failed read is never retried.
  useEffect(() => {
    if (!active || host === null || status === null) {
      const live = ticketRef.current;
      if (live !== null) live.controller.abort();
      ticketRef.current = null;
      startedRef.current = null;
      liveReadRef.current = null;
      setRead(null);
      setPending(false);
      return;
    }
    const key = `e${enabled ? 1 : 0}|g${status.generation}|p${status.principal_scope}|s${status.session_scope}`;
    const started = startedRef.current;
    if (started !== null && started.host === host && started.key === key) return;
    const previous = ticketRef.current;
    if (previous !== null) previous.controller.abort();
    const ticket = ++ticketSeqRef.current;
    const controller = new AbortController();
    ticketRef.current = { ticket, controller };
    startedRef.current = { host, key };
    liveReadRef.current = null;
    setRead(null);
    setPending(true);
    host
      .readRequests({ signal: controller.signal })
      .then((result) => {
        const live = ticketRef.current;
        if (live === null || live.ticket !== ticket) return; // stale completion
        ticketRef.current = null;
        setPending(false);
        if (result === null) {
          setRead(null); // dropped read: withdrawn, no automatic retry
          return;
        }
        const next = toLiveFeed(host, result);
        liveReadRef.current = next;
        setRead(next);
      })
      .catch(() => {
        const live = ticketRef.current;
        if (live === null || live.ticket !== ticket) return; // stale completion
        ticketRef.current = null;
        setPending(false);
        setRead(null); // closed failure: withdrawn, no automatic retry
      });
    // `status` is a dependency: only its distinct generation starts a read.
  }, [host, enabled, status, active]);

  hostRef.current = host;

  // Rows stay visible only while they belong to the current activation and
  // the current own status generation; any host or status change withdraws
  // them in the same render, before the replacement read resolves.
  const live = read !== null && active && status !== null && read.host === host &&
    read.generation === status.generation && read.principalScope === status.principal_scope &&
    read.sessionScope === status.session_scope;
  liveReadRef.current = live ? read : null;
  const requests = live ? read.views : EMPTY_VIEWS;
  const coverage = live ? read.coverage : null;

  let state: TerminalSharingFeedState = "unavailable";
  if (host !== null && enabled && active && live) state = "ready";
  else if (host !== null && enabled && active && pending) state = "loading";

  const onReview = useCallback(
    async (view: BriefSharingRequestView): Promise<void> => {
      const currentHost = hostRef.current;
      const source = liveReadRef.current;
      // No live feed or unknown tuple resolves to nothing; caller-supplied
      // views never mint a request.
      if (currentHost === null || source === null) return;
      const issued = source.issued.get(
        tupleKey(
          view.requestRef,
          view.requestRevision,
          view.deliveryId,
          view.contentSha256,
        ),
      );
      if (issued === undefined) return;
      await currentHost.reviewRequest(issued);
    },
    [],
  );

  const onConnect = useCallback((): Promise<void> => {
    const currentHost = hostRef.current;
    // A missing capability never triggers an auth action.
    if (currentHost === null) return Promise.resolve();
    return currentHost.connect();
  }, []);

  const onDisconnect = useCallback((): Promise<void> => {
    const currentHost = hostRef.current;
    if (currentHost === null) return Promise.resolve();
    return currentHost.disconnect();
  }, []);

  return {
    state,
    requests,
    coverage,
    session: status,
    onReview,
    onConnect,
    onDisconnect,
  };
}
