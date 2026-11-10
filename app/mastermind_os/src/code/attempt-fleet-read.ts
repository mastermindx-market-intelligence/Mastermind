/** One-shot bounded reads for the Code workbench (HC07).
 *
 *  Copies the read discipline of src/resources/T3AttemptFleetBlock.tsx and
 *  src/planning/RetainedActivityInspector.tsx — abort on identity change,
 *  epoch/auth revalidation after every await, owned-result identity match
 *  before display — without their markup. Read-only: this module never
 *  launches, sends to or interrupts a T3 thread, and it invents no second
 *  transport; it only calls readers the host already exposes. */
import { useEffect, useRef, useState } from "react";
import {
  validT3AttemptId,
  type T3AttemptFleetRead,
} from "../resources/t3-attempt-fleet-contract";
import {
  validActivitySelection,
  type ActivityRead,
  type ActivitySelection,
} from "../planning/retained-activity";

/** The read-only host surface the workbench consumes, narrowed structurally.
 *  The reference IS the host (no wrapper), so effect identity stays stable. */
export interface CodeHostView {
  readT3AttemptFleet?: (
    request: { attemptId: string; signal: AbortSignal },
  ) => Promise<T3AttemptFleetRead>;
  readRetainedActivity?: (
    request: ActivitySelection & { signal: AbortSignal },
  ) => Promise<ActivityRead>;
  invalidationGeneration?: () => number;
  auth?: { getState: () => { status: unknown; acquisition?: unknown } };
}

/** Structural narrowing; anything without these optional members is honestly
 *  "not connected" — never an error and never a fabricated host. */
export function codeHostView(host: unknown): CodeHostView | null {
  if (!host || typeof host !== "object") return null;
  return host as CodeHostView;
}

function signedIn(view: CodeHostView | null): boolean {
  const auth = view?.auth?.getState();
  return (
    auth?.status === "signed_in" && (auth as { acquisition?: unknown }).acquisition === true
  );
}

export type FleetReadState =
  | { state: "NOT_STARTED" }
  | { state: "PENDING" }
  | T3AttemptFleetRead;

interface FleetOwned {
  view: CodeHostView;
  reader: NonNullable<CodeHostView["readT3AttemptFleet"]>;
  epoch: number;
  attemptId: string;
  read: FleetReadState;
}

/** One bounded per-attempt fleet read; `refresh` re-runs it under the same
 *  guards. Everything else (refusal, unavailable, unknown fields) is returned
 *  as the typed document and rendered honestly downstream. */
export function useT3AttemptFleetRead(host: unknown, attemptId: string | null): {
  read: FleetReadState;
  permitted: boolean;
  selectable: boolean;
  refresh: () => void;
} {
  const view = codeHostView(host);
  const reader = view?.readT3AttemptFleet;
  const epoch = view?.invalidationGeneration?.();
  const permitted =
    !!view && !!reader && Number.isSafeInteger(epoch) && signedIn(view);
  const selectable = validT3AttemptId(attemptId);
  const [owned, setOwned] = useState<FleetOwned | null>(null);
  const abort = useRef<AbortController | null>(null);
  const current = useRef<{ view: CodeHostView | null; reader?: CodeHostView["readT3AttemptFleet"] }>({ view });
  current.current = { view, reader };
  const visible =
    owned && owned.view === view && owned.reader === reader &&
    owned.epoch === epoch && owned.attemptId === attemptId
      ? owned.read
      : { state: "NOT_STARTED" as const };

  const run = () => {
    if (!view || !reader || !permitted || epoch === undefined || !selectable || !attemptId) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    const origin = { view, reader, epoch, attemptId };
    const valid = () =>
      !controller.signal.aborted &&
      current.current.view === view &&
      current.current.reader === reader &&
      view.invalidationGeneration?.() === epoch &&
      signedIn(view);
    setOwned({ ...origin, read: { state: "PENDING" } });
    void (async () => {
      try {
        const read = await reader.call(view, { attemptId, signal: controller.signal });
        if (valid()) setOwned({ ...origin, read });
      } catch {
        if (valid())
          setOwned({ ...origin, read: { state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" } });
      }
    })();
  };

  useEffect(() => {
    abort.current?.abort();
    setOwned(null);
    run();
    return () => {
      abort.current?.abort();
    };
    // Identity-change trigger only; run/refresh close over the current render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, reader, attemptId]);

  return { read: visible, permitted, selectable, refresh: run };
}

export type ActivityReadState =
  | { state: "NOT_STARTED" }
  | { state: "PENDING" }
  | { state: "READ"; read: ActivityRead }
  | { state: "FAILED" };

interface ActivityOwned {
  view: CodeHostView;
  reader: NonNullable<CodeHostView["readRetainedActivity"]>;
  epoch: number;
  selection: ActivitySelection;
  read: ActivityReadState;
}

const isActivityRead = (value: unknown): value is ActivityRead =>
  !!value && typeof value === "object" &&
  ((value as { availability?: unknown }).availability === "AVAILABLE" ||
    (value as { availability?: unknown }).availability === "UNAVAILABLE");

/** One bounded retained-activity read for the attempt's activity trail. Only
 *  runs when the host exposes the reader AND the selection ids are projected;
 *  otherwise the trail stays honestly not retained — never a fake stream. */
export function useRetainedActivityRead(
  host: unknown,
  selection: ActivitySelection | null,
): ActivityReadState {
  const view = codeHostView(host);
  const reader = view?.readRetainedActivity;
  const epoch = view?.invalidationGeneration?.();
  const ready =
    !!view && !!reader && Number.isSafeInteger(epoch) && signedIn(view) &&
    validActivitySelection(selection);
  const work = selection?.work_ref, root = selection?.root_job_id;
  const job = selection?.job_id, attempt = selection?.attempt_id;
  const [owned, setOwned] = useState<ActivityOwned | null>(null);
  const abort = useRef<AbortController | null>(null);
  const current = useRef<{ view: CodeHostView | null; reader?: CodeHostView["readRetainedActivity"] }>({ view });
  current.current = { view, reader };
  const visible =
    owned && owned.view === view && owned.reader === reader &&
    owned.epoch === epoch &&
    owned.selection.work_ref === work && owned.selection.root_job_id === root &&
    owned.selection.job_id === job && owned.selection.attempt_id === attempt
      ? owned.read
      : { state: "NOT_STARTED" as const };

  useEffect(() => {
    abort.current?.abort();
    setOwned(null);
    if (!ready || !view || !reader || epoch === undefined || !selection) return;
    const controller = new AbortController();
    abort.current = controller;
    const origin = { view, reader, epoch, selection };
    const valid = () =>
      !controller.signal.aborted &&
      current.current.view === view &&
      current.current.reader === reader &&
      view.invalidationGeneration?.() === epoch &&
      signedIn(view);
    setOwned({ ...origin, read: { state: "PENDING" } });
    void (async () => {
      try {
        const read = await reader.call(view, { ...selection, signal: controller.signal });
        if (!valid()) return;
        setOwned({ ...origin, read: isActivityRead(read) ? { state: "READ", read } : { state: "FAILED" } });
      } catch {
        if (valid()) setOwned({ ...origin, read: { state: "FAILED" } });
      }
    })();
    return () => {
      abort.current?.abort();
    };
    // Field-level selection deps mirror RetainedActivityInspector.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, reader, work, root, job, attempt, ready]);

  return visible;
}
