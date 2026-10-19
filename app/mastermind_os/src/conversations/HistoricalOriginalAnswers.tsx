import { useEffect, useRef, useState } from "react";
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

function validPage(raw: unknown, selection: MissionSelection): {
  references: Row[]; next_cursor: string | null;
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
    rows.push(r as Row);
  }
  return { references: rows, next_cursor: page.next_cursor as string | null };
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
  const [rows, setRows] = useState<Row[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ row: Row; answer: QualifiedSessionAnswer } | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "unavailable">("idle");
  const epoch = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const reading = binding?.port.readOriginalReferences;
  const qualified = binding?.port.readQualifiedAnswer;

  useEffect(() => {
    epoch.current++;
    controller.current?.abort();
    controller.current = null;
    setRows([]); setCursor(null); setSelected(null); setState("idle");
    if (!binding || !selection || !principalScope || !generation || !reading || !qualified) return;
    const e = epoch.current;
    const c = new AbortController(); controller.current = c;
    setState("loading");
    void reading(selection,c.signal).then(raw => {
      if (c.signal.aborted || epoch.current !== e) return;
      const page = validPage(raw, selection);
      if (!page) { setState("unavailable"); return; }
      setRows(page.references); setCursor(page.next_cursor); setState("idle");
    }).catch(() => { if (!c.signal.aborted && epoch.current === e) setState("unavailable"); });
    return () => { c.abort(); epoch.current++; };
  }, [binding, selection?.workRef, selection?.rootJobId, principalScope, generation, authRevision, selectionSeq, reading, qualified]);

  const loadMore = () => {
    if (!selection || !reading || !cursor || state !== "idle") return;
    const e = epoch.current;
    const c = new AbortController(); controller.current?.abort(); controller.current = c;
    setState("loading");
    void reading(selection,c.signal,cursor).then(raw => {
      if (c.signal.aborted || epoch.current !== e) return;
      const page = validPage(raw, selection);
      if (!page || (page.next_cursor === cursor && page.references.length === 0)) {
        setState("unavailable"); return;
      }
      setRows(prev => {
        const seen = new Set(prev.map(row => row.read_ref));
        return [...prev,...page.references.filter(row => !seen.has(row.read_ref))].slice(0,128);
      });
      setCursor(page.next_cursor); setState("idle");
    }).catch(() => { if (!c.signal.aborted && epoch.current === e) setState("unavailable"); });
  };

  const open = (row: Row) => {
    if (!qualified || state === "loading") return;
    const e = epoch.current;
    const c = new AbortController(); controller.current?.abort(); controller.current = c;
    setSelected(null);
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

  if (!binding || !selection || !principalScope || !generation || !reading || !qualified) return null;
  return <section className="conversation-result" aria-label="Original answer references">
    <h3>Original answer history · READ only</h3>
    <p>Canonical request references only. An answer appears after a separate qualified read; original-parent consumption is not established.</p>
    {rows.map(row => <button key={row.read_ref} type="button"
      disabled={state === "loading" || row.read_ref === activeReadRef}
      onClick={() => open(row)}>Open original request · {row.requested_at}</button>)}
    {selected && <div aria-label="Historical original answer">
      <p>{selected.answer.text}</p>
      <p>Next step: {selected.answer.nextStep}</p>
      <code>{selected.answer.readRef}</code>
    </div>}
    {cursor && rows.length < 128 && <button type="button" disabled={state === "loading"} onClick={loadMore}>More original requests</button>}
    {state === "loading" && <p>Reading canonical references…</p>}
    {state === "unavailable" && <p>Historical reference or answer unavailable. No operation was resent.</p>}
  </section>;
}
