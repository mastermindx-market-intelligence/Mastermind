import { useLayoutEffect, useRef, useState } from "react";
import type { MissionSelection } from "../mission";
import type { OperationPointer } from "../orchestration/operation-controller";
import type { QualifiedSessionAnswer } from "../orchestration/executive-session-command-port";
import type { MountedExecutiveSessionBinding } from "../orchestration/os-executive-session-host";

type Row = Readonly<{
  read_ref: string; operation_key: string; request_ref: string;
  request_event_id: number; request_revision: string; requested_at: string;
  work_ref: string; root_job_id: string; target_ref: string;
  reference_only: true;
}>;
const SHA = /^[0-9a-f]{64}$/;
const KEY = /^session-continue-[0-9a-f]{64}$/;
const TARGET = /^fabric_attempt:[0-9a-f]{64}$/;
const READ = /^session-reply-[0-9a-f]{64}$/;
const CURSOR = /^[A-Za-z0-9_=-]{1,2048}$/;
// Each Runtime page reads at most 256 event metadata rows. Never let an
// automatic UI scan become an unbounded backend query or polling loop.
const MAX_SPARSE_PAGES_PER_ACTION = 4;

function validPage(raw: unknown, selection: MissionSelection): {
  references: Row[]; next_cursor: string | null; high_water: number;
} | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const envelope = raw as Record<string, unknown>;
  if (Object.keys(envelope).length !== 7 || envelope.schema !== "mastermind.os.executive.session_result.v1" ||
      envelope.operation !== "references" || envelope.ok !== true || envelope.effect !== "NONE" ||
      envelope.operation_key !== null || envelope.error !== null) return null;
  const d = envelope.data;
  if (!d || typeof d !== "object" || Array.isArray(d)) return null;
  const page = d as Record<string, unknown>;
  if (Object.keys(page).length !== 5 || page.schema !== "mastermind.session_reply_references.v1" ||
      !["COMPLETE", "PARTIAL"].includes(String(page.status)) ||
      !Array.isArray(page.references) || page.references.length > 16 ||
      !Number.isSafeInteger(page.high_water) || Number(page.high_water) < 0 ||
      (page.status === "PARTIAL") !== (typeof page.next_cursor === "string") ||
      (page.next_cursor !== null && (typeof page.next_cursor !== "string" || !CURSOR.test(page.next_cursor)))) return null;
  const rows: Row[] = [];
  for (const item of page.references) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return null;
    const r = item as Record<string, unknown>;
    if (Object.keys(r).length !== 10 ||
        !["read_ref", "operation_key", "request_ref", "request_event_id", "request_revision",
          "requested_at", "work_ref", "root_job_id", "target_ref", "reference_only"].every(k => Object.hasOwn(r,k)) ||
        r.reference_only !== true || r.work_ref !== selection.workRef ||
        r.root_job_id !== selection.rootJobId ||
        typeof r.operation_key !== "string" || !KEY.test(r.operation_key) ||
        typeof r.target_ref !== "string" || !TARGET.test(r.target_ref) ||
        typeof r.read_ref !== "string" || !READ.test(r.read_ref) ||
        typeof r.request_revision !== "string" || !SHA.test(r.request_revision) ||
        typeof r.request_ref !== "string" || r.request_ref.length > 256 ||
        typeof r.requested_at !== "string" || r.requested_at.length > 64 ||
        !Number.isSafeInteger(r.request_event_id) || Number(r.request_event_id) < 1 ||
        Number(r.request_event_id) > Number(page.high_water)) return null;
    // Capture the exact closed projection at validation time. Even a test
    // transport retaining and mutating its raw JSON frame afterward cannot
    // rewrite an original operation/read ref in the rendered click target.
    rows.push(Object.freeze({
      read_ref: r.read_ref as string,
      operation_key: r.operation_key as string,
      request_ref: r.request_ref as string,
      request_event_id: r.request_event_id as number,
      request_revision: r.request_revision as string,
      requested_at: r.requested_at as string,
      work_ref: r.work_ref as string,
      root_job_id: r.root_job_id as string,
      target_ref: r.target_ref as string,
      reference_only: true as const,
    }));
  }
  return { references: rows, next_cursor: page.next_cursor as string | null,
    high_water: Number(page.high_water) };
}

/** Skip empty global-ledger pages without claiming that REQUESTED implies REPLIED.
 * One user action reads at most four finite 256-event windows. The high water
 * is immutable across every cursor hop, and progress must strictly advance. */
async function readSparsePages(
  reading: NonNullable<MountedExecutiveSessionBinding["port"]["readOriginalReferences"]>,
  selection: MissionSelection, signal: AbortSignal,
  initialCursor: string | null = null, expectedWatermark: number | null = null,
): Promise<{ references: Row[]; next_cursor: string | null; high_water: number }> {
  let cursor = initialCursor;
  let highWater = expectedWatermark;
  const visited = new Set<string>();
  for (let pageNo = 0; pageNo < MAX_SPARSE_PAGES_PER_ACTION; pageNo++) {
    if (signal.aborted) throw new Error("READ_CANCELLED");
    const raw = await reading(selection, signal, cursor ?? undefined);
    if (signal.aborted) throw new Error("READ_CANCELLED");
    const page = validPage(raw, selection);
    if (!page || (highWater !== null && page.high_water !== highWater)) {
      throw new Error("HISTORICAL_PAGE_INVALID");
    }
    highWater ??= page.high_water;
    if (page.next_cursor !== null &&
        (page.next_cursor === cursor || visited.has(page.next_cursor))) {
      throw new Error("HISTORICAL_CURSOR_NO_PROGRESS");
    }
    if (page.references.length > 0 || page.next_cursor === null) {
      return { ...page, high_water: highWater };
    }
    visited.add(page.next_cursor);
    cursor = page.next_cursor;
  }
  if (highWater === null) throw new Error("HISTORICAL_PAGE_MISSING");
  return { references: [], next_cursor: cursor, high_water: highWater };
}

/** Stateless historic READ presentation. Never touches the pending pointer store. */
export function HistoricalOriginalAnswers({
  binding, selection, principalScope, generation, authRevision, selectionSeq,
  activeReadRef,
}: {
  binding: MountedExecutiveSessionBinding | null;
  selection: MissionSelection | null;
  principalScope: string | null;
  generation: string | null;
  authRevision: number;
  selectionSeq: number;
  activeReadRef?: string | null;
}) {
  // A historical answer is source-backed but also owner-bound. An auth/mission
  // transition must withhold the PREVIOUS render's answer synchronously,
  // before a passive effect could clear stale React state.
  const [qualifiedEpoch, setQualifiedEpoch] = useState<{
    binding: MountedExecutiveSessionBinding;
    scope: string; generation: string; authRevision: number;
    selectionSeq: number; workRef: string; rootJobId: string;
  } | null>(null);
  const renderIsQualified = !!qualifiedEpoch && !!selection && !!binding &&
    qualifiedEpoch.binding === binding &&
    qualifiedEpoch.scope === principalScope &&
    qualifiedEpoch.generation === generation &&
    qualifiedEpoch.authRevision === authRevision &&
    qualifiedEpoch.selectionSeq === selectionSeq &&
    qualifiedEpoch.workRef === selection.workRef &&
    qualifiedEpoch.rootJobId === selection.rootJobId;
  const [rows, setRows] = useState<Row[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [watermark, setWatermark] = useState<number | null>(null);
  const [selected, setSelected] = useState<{ row: Row; answer: QualifiedSessionAnswer } | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "unavailable">("idle");
  const epoch = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const reading = binding?.port.readOriginalReferences;
  const qualified = binding?.port.readQualifiedAnswer;

  useLayoutEffect(() => {
    epoch.current++;
    controller.current?.abort();
    controller.current = null;
    setQualifiedEpoch(null);
    setRows([]); setCursor(null); setWatermark(null); setSelected(null); setState("idle");
    if (!binding || !selection || !principalScope || !generation || !reading || !qualified) return;
    setQualifiedEpoch({binding,scope:principalScope,generation,authRevision,
      selectionSeq,workRef:selection.workRef,rootJobId:selection.rootJobId});
    const e = epoch.current;
    const c = new AbortController(); controller.current = c;
    setState("loading");
    void readSparsePages(reading,selection,c.signal).then(page => {
      if (c.signal.aborted || epoch.current !== e) return;
      setRows(page.references); setCursor(page.next_cursor);
      setWatermark(page.high_water); setState("idle");
    }).catch(() => { if (!c.signal.aborted && epoch.current === e) setState("unavailable"); });
    return () => { c.abort(); epoch.current++; };
  }, [binding, selection?.workRef, selection?.rootJobId, principalScope, generation, authRevision, selectionSeq, reading, qualified]);

  // A process restart deliberately invalidates old signed cursors. Offer a
  // fresh FIRST-PAGE user-triggered READ instead of retrying an expired
  // cursor or requiring navigation away from the selected conversation.
  // No historical selection, SEND, pending pointer or parent ACK is mutated.
  const reload = () => {
    if (!renderIsQualified || !selection || !reading || state === "loading") return;
    const e = epoch.current;
    const c = new AbortController();
    controller.current?.abort(); controller.current = c;
    setRows([]); setCursor(null); setWatermark(null); setSelected(null);
    setState("loading");
    void readSparsePages(reading,selection,c.signal).then(page => {
      if (c.signal.aborted || epoch.current !== e) return;
      setRows(page.references); setCursor(page.next_cursor);
      setWatermark(page.high_water); setState("idle");
    }).catch(() => {
      if (!c.signal.aborted && epoch.current === e) setState("unavailable");
    });
  };

  const loadMore = () => {
    if (!renderIsQualified || !selection || !reading || !cursor || state !== "idle") return;
    const e = epoch.current;
    const c = new AbortController(); controller.current?.abort(); controller.current = c;
    setState("loading");
    void readSparsePages(reading,selection,c.signal,cursor,watermark).then(page => {
      if (c.signal.aborted || epoch.current !== e) return;
      setRows(prev => {
        const seen = new Set(prev.map(row => row.read_ref));
        return [...prev,...page.references.filter(row => !seen.has(row.read_ref))].slice(0,128);
      });
      setCursor(page.next_cursor); setWatermark(page.high_water);
      setState("idle");
    }).catch(() => { if (!c.signal.aborted && epoch.current === e) setState("unavailable"); });
  };

  const open = (row: Row) => {
    if (!renderIsQualified || !qualified || state === "loading") return;
    const e = epoch.current;
    const c = new AbortController(); controller.current?.abort(); controller.current = c;
    setSelected(null); setState("loading");
    const pointer: OperationPointer = {
      operationKey: row.operation_key, targetKey: row.target_ref, kind: "message",
    };
    void qualified(pointer,c.signal).then(read => {
      if (c.signal.aborted || epoch.current !== e) return;
      if (read.receipt.disposition !== "accepted" || !read.answer ||
          read.answer.parentConsumed !== false || read.answer.readRef !== row.read_ref) {
        setState("unavailable"); return;
      }
      setSelected({row,answer:read.answer}); setState("idle");
    }).catch(() => { if (!c.signal.aborted && epoch.current === e) setState("unavailable"); });
  };

  if (!renderIsQualified || !binding || !selection || !principalScope || !generation || !reading || !qualified) return null;
  return <section className="conversation-result" aria-label="Original answer references">
    <h3>Original answer history · READ only</h3>
    <p>Canonical request references only. An answer appears after a separate qualified read; original-parent consumption is not established.</p>
    {rows.map(row => <button key={row.read_ref} type="button"
      disabled={state === "loading" || row.read_ref === activeReadRef}
      onClick={() => open(row)}>Open original request · {row.requested_at}</button>)}
    {selected && selected.row.read_ref !== activeReadRef && <div aria-label="Historical original answer">
      <p>{selected.answer.text}</p>
      <p>Next step: {selected.answer.nextStep}</p>
      <code>{selected.answer.readRef}</code>
    </div>}
    {cursor && rows.length < 128 && <button type="button" disabled={state === "loading"} onClick={loadMore}>More original requests</button>}
    {state === "loading" && <p>Reading canonical references…</p>}
    {state === "unavailable" && <>
      <p>Historical reference or answer unavailable. No operation was resent.</p>
      <button type="button" onClick={reload}>Reload original references</button>
    </>}
  </section>;
}
