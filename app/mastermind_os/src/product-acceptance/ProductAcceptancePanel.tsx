import { useEffect, useLayoutEffect, useReducer, useRef, useState } from "react";
import type { MissionHost } from "../host";
import { decodeMissionv4, type MissionSelection, type Missionv4Document } from "../mission";
import { decodeOriginalAcceptanceBody, guardAcceptanceRead, ownerObservation, sameAcceptanceObservation, type ProductAcceptanceOwner } from "./owner-observation";

interface Props {
  host: MissionHost | undefined;
  selection: MissionSelection | null;
  selectionGeneration: number;
  currentSelectionGeneration: () => number;
  currentHost: () => MissionHost | undefined;
  authRevision: number;
  enabled: boolean;
  locale: string;
}
type View = { kind: "UNAVAILABLE" } | {
  kind: "PENDING" | "READY"; token: string; flight: number;
  host: MissionHost; owner: ProductAcceptanceOwner | undefined;
  document?: Missionv4Document;
};

/** Read-only receipt from the optional real owner attachment; never creates work. */
export function ProductAcceptancePanel(props: Props) {
  const { host, selection, selectionGeneration, authRevision, enabled, locale } = props;
  const originalRead = host?.readOriginalMissionV4;
  // The full-body owner route does not depend on the legacy selector-first attachment.
  const owner = originalRead ? undefined : host?.productAcceptanceOwner;
  const [revision, refresh] = useReducer((n: number) => n + 1, 0);
  const [view, setView] = useState<View>({ kind: "UNAVAILABLE" });
  const sequence = useRef(0), controller = useRef<AbortController | null>(null);
  const current = useRef(props); current.current = props;
  const observation = ownerObservation(owner);
  const auth = host?.auth?.getState();
  const hostGeneration = host?.invalidationGeneration?.();
  const available = enabled && auth?.status === "signed_in" && auth.acquisition && !!selection
    && (!!originalRead || (!!host?.readMissionV4 && !!observation
      && observation.selector.workRef === selection.workRef && observation.selector.rootJobId === selection.rootJobId));
  const token = JSON.stringify([selection, selectionGeneration, authRevision, hostGeneration, observation, !!originalRead, available]);

  useLayoutEffect(() => {
    const invalidate = () => {
      sequence.current++;
      controller.current?.abort();
      setView({ kind: "UNAVAILABLE" });
      refresh();
    };
    let releaseOwner: (() => void) | undefined, releaseAuth: (() => void) | undefined;
    try {
      releaseOwner = owner?.subscribe(invalidate);
      releaseAuth = host?.auth?.subscribe(invalidate);
    } catch { invalidate(); }
    return () => {
      sequence.current++;
      controller.current?.abort();
      releaseOwner?.(); releaseAuth?.();
    };
  }, [host, owner]);

  useEffect(() => {
    const flight = ++sequence.current, abort = new AbortController();
    controller.current = abort;
    const captured = ownerObservation(owner);
    const selectionEpoch = selectionGeneration;
    const sourceEpoch = host?.invalidationGeneration?.();
    const isCurrent = () => {
      const p = current.current, state = host?.auth?.getState();
      return !abort.signal.aborted && sequence.current === flight && p.enabled
        && p.host === host && p.currentHost() === host && (originalRead || host?.productAcceptanceOwner === owner)
        && p.selectionGeneration === selectionEpoch && p.currentSelectionGeneration() === selectionEpoch
        && p.selection?.workRef === selection?.workRef && p.selection?.rootJobId === selection?.rootJobId
        && p.authRevision === authRevision && host?.invalidationGeneration?.() === sourceEpoch
        && state?.status === "signed_in" && state.acquisition
        && host?.readOriginalMissionV4 === originalRead
        && (originalRead && !owner ? captured === null : sameAcceptanceObservation(captured, ownerObservation(owner)));
    };
    if (!available || !host || !selection || (!originalRead && (!owner || !captured || !host.readMissionV4)) || !isCurrent()) {
      setView({ kind: "UNAVAILABLE" });
      return () => { abort.abort(); };
    }
    let guard: ReturnType<typeof guardAcceptanceRead> | undefined;
    try { if (!originalRead) guard = guardAcceptanceRead(owner, captured!.selector, isCurrent); }
    catch { setView({ kind: "UNAVAILABLE" }); return () => { abort.abort(); }; }
    const read = host.readMissionV4;
    setView({ kind: "PENDING", token, flight, host, owner });
    void Promise.resolve().then(() => {
      if (!isCurrent()) return null;
      guard?.check();
      return originalRead
        ? originalRead.call(host, { workRef: selection.workRef, rootJobId: selection.rootJobId, signal: abort.signal })
        : read!.call(host, { ...captured!.selector, signal: abort.signal });
    }).then(raw => {
      if (!isCurrent()) return;
      guard?.check();
      const document = originalRead
        ? decodeOriginalAcceptanceBody(raw, { workRef: selection.workRef, rootJobId: selection.rootJobId })
        : decodeMissionv4(raw, { workRef: captured!.selector.workRef, rootJobId: captured!.selector.rootJobId }, captured!.selector.requestMessageKey);
      setView(document ? { kind: "READY", token, flight, host, owner, document } : { kind: "UNAVAILABLE" });
    }).catch(() => {
      if (sequence.current === flight) setView({ kind: "UNAVAILABLE" });
    }).finally(() => guard?.dispose());
    return () => { abort.abort(); guard?.dispose(); };
  }, [host, owner, originalRead, token, revision]);

  const live = available && view.kind !== "UNAVAILABLE" && view.token === token && view.flight === sequence.current
    && view.host === host && view.owner === owner && current.current.currentHost() === host
    && current.current.currentSelectionGeneration() === selectionGeneration;
  const document = live && view.kind === "READY" ? view.document : undefined;
  const receipt = document?.product_acceptance.receipt;
  const zh = locale.startsWith("zh");
  const state = receipt ? "PRODUCT_ACCEPTED" : live && view.kind === "PENDING" ? "PENDING" : "UNAVAILABLE";
  return <section className="card" aria-label={zh ? "产品验收凭据" : "Product acceptance receipt"}>
    <div className="section-title"><h2>{zh ? "产品验收" : "Product acceptance"}</h2>
      <span className={`state ${receipt ? "" : "state-unavailable"}`}>{state}</span></div>
    <p className="muted">{receipt
      ? zh ? "已核验当前任务的原始验收及父任务结果凭据。" : "The original acceptance and parent result are verified for this selected mission."
      : state === "PENDING"
        ? zh ? "正在读取当前任务的验收凭据。" : "Reading the selected mission’s acceptance receipt."
        : zh ? "当前任务尚无可用的验收凭据。" : "A qualified acceptance receipt is unavailable for this selected mission."}</p>
    {receipt && document ? <details className="reason-details"><summary>{zh ? "凭据详情" : "Receipt details"}</summary><dl>
      <dt>{zh ? "项目" : "Work"}</dt><dd>{document.product_acceptance.selection.work_ref}</dd>
      <dt>{zh ? "根任务" : "Root job"}</dt><dd>{document.product_acceptance.selection.root_job_id}</dd>
      <dt>{zh ? "结果任务" : "Subject job"}</dt><dd>{receipt.subject_job_id}</dd>
      <dt>{zh ? "结果摘要" : "Subject result digest"}</dt><dd><code>{receipt.subject_result_envelope_digest}</code></dd>
      <dt>{zh ? "父任务结果摘要" : "Parent result digest"}</dt><dd><code>{receipt.parent_result_envelope_digest}</code></dd>
      <dt>{zh ? "来源连续性" : "Source continuity"}</dt><dd>{receipt.source_continuity.disposition}</dd>
    </dl></details> : document?.product_acceptance.reason_codes.length ? <details className="reason-details"><summary>{zh ? "来源详情" : "Source details"}</summary>
      <code>{document.product_acceptance.reason_codes.join(" · ")}</code></details> : null}
  </section>;
}
