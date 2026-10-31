import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import {
  decodeResultReferencesEnvelope,
  normalizeResultReferencesSelection,
  referenceSelection,
  type ResultReferenceRef,
  type ResultReferencesDocument,
  type ResultReferencesSelection,
} from "./result-references";
import {
  decodeResultEnvelope,
  normalizeResultSelection,
  type ResultEnvelopeDigestShape,
  type ResultSelection,
} from "./result";

// Presentation copy only. Identifiers, catalogue timestamps, freshness,
// mission state and result material stay verbatim.
const STATIC_ZH: Record<string, string> = {
  "Retained results": "保留的结果",
  "Retained result list": "保留结果列表",
  "Browse retained results for this project.":
    "浏览此项目保留的结果。",
  "Show retained results": "显示保留的结果",
  "Hide retained results": "收起保留的结果",
  "Refresh retained results": "刷新保留的结果",
  "Reading the retained list…": "正在读取保留列表…",
  "The retained list could not be read.": "无法读取保留列表。",
  "The retained list response was invalid.": "保留列表响应无效。",
  "The result source is unavailable.": "结果来源不可用。",
  "The result source changed while reading.": "读取时结果来源已更改。",
  "The retained list is over its display budget.": "保留列表超出显示预算。",
  "The reference index is unavailable.": "引用索引不可用。",
  "No retained results are listed for this workspace.": "此工作区没有列出保留结果。",
  "Retained as of": "保留目录时间",
  "unknown": "未知",
  "Catalogue freshness": "目录新鲜度",
  "Historical navigation does not establish a current Mission.": "历史结果导航不证明任务处于当前状态。",
  "Mission state": "任务状态",
  "Runtime observation": "运行时观测",
  "More retained results": "更多保留结果",
  "Index coverage": "索引覆盖范围",
  "Jobs without a retained result": "没有保留结果的任务",
  "Omitted jobs": "省略的任务",
  "Truncated": "已截断",
  "None": "无",
  "Yes": "是",
  "No": "否",
  "The source notes this list is partial.": "来源标注此列表为部分列表。",
  "Open retained result": "打开保留结果",
  "Role": "角色",
  "Attempt": "尝试",
  "Validation": "校验",
  "Unvalidated": "未校验",
  "Back to retained results": "返回保留结果",
  "Reading the exact result…": "正在读取精确结果…",
  "This exact result could not be read.": "无法读取该精确结果。",
  "This reference cannot be opened as an exact result.": "该引用无法作为精确结果打开。",
};

export interface RetainedResultsProps {
  /** Normalized (workRef, rootJobId) pair. Job, attempt and digest never
   * enter the list request; they only come back inside the returned index. */
  selection: ResultReferencesSelection;
  authGeneration: string | number;
  hostGeneration: string | number;
  locale: "en" | "zh-CN";
  /** Actual current mission state, displayed verbatim. Reading never
   * requires CURRENT and never promotes a retained list to currentness. */
  missionState: string;
  readReferences: (request: {
    workRef: string;
    rootJobId: string;
    signal: AbortSignal;
  }) => Promise<unknown>;
  readResult: (
    request: ResultSelection & { signal: AbortSignal },
  ) => Promise<unknown>;
  /** The parent's actual result renderer. This component renders no result
   * material of its own. */
  renderResult: (
    selection: ResultSelection,
    decodedResultEnvelope: ResultEnvelopeDigestShape,
  ) => ReactNode;
}

type ListState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "read"; document: ResultReferencesDocument }
  | { kind: "invalid" }
  | { kind: "error" };

type DetailState =
  | { kind: "idle" }
  | { kind: "loading"; selection: ResultSelection }
  | { kind: "read"; selection: ResultSelection; decoded: ResultEnvelopeDigestShape }
  | { kind: "unqualified" }
  | { kind: "invalid" }
  | { kind: "error" };

function unavailableText(reason: string): string {
  if (reason === "SOURCE_UNAVAILABLE") return "The result source is unavailable.";
  if (reason === "SOURCE_CHANGED") return "The result source changed while reading.";
  if (reason === "OVER_BUDGET") return "The retained list is over its display budget.";
  return "The reference index is unavailable.";
}

/** Existing fixed retained-result list read for one (workRef, rootJobId).
 * The parent keys this view by its exact auth/host/selection epoch; every
 * read is independently qualified and no read requires the mission to be
 * CURRENT or promotes anything to accepted. */
export function RetainedResults({
  selection,
  authGeneration,
  hostGeneration,
  locale,
  missionState,
  readReferences,
  readResult,
  renderResult,
}: RetainedResultsProps) {
  const t = (value: string) =>
    locale === "zh-CN" ? STATIC_ZH[value] ?? value : value;
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"list" | "detail">("list");
  const [list, setList] = useState<ListState>({ kind: "idle" });
  const [detail, setDetail] = useState<DetailState>({ kind: "idle" });
  const listAbort = useRef<AbortController | null>(null);
  const detailAbort = useRef<AbortController | null>(null);
  const listBusy = useRef(false);
  const identity = [
    String(authGeneration),
    String(hostGeneration),
    selection.workRef,
    selection.rootJobId,
  ].join("\u0000");
  const identityRef = useRef(identity);
  const navigated = useRef(false);
  const region = useRef<HTMLElement>(null);
  const listHeading = useRef<HTMLHeadingElement>(null);
  const back = useRef<HTMLButtonElement>(null);

  // Epoch change (auth, host generation or selection, including A-B-A):
  // clear and abort before paint and deny every late reply from the old epoch.
  useLayoutEffect(() => {
    if (identityRef.current === identity) return;
    identityRef.current = identity;
    listAbort.current?.abort();
    detailAbort.current?.abort();
    listAbort.current = null;
    detailAbort.current = null;
    listBusy.current = false;
    navigated.current = false;
    setOpen(false);
    setView("list");
    setList({ kind: "idle" });
    setDetail({ kind: "idle" });
  }, [identity]);

  useEffect(
    () => () => {
      listAbort.current?.abort();
      detailAbort.current?.abort();
    },
    [],
  );

  useLayoutEffect(() => {
    if (!navigated.current) return;
    if (view === "detail") back.current?.focus();
    else listHeading.current?.focus();
  }, [view, open]);

  const stopList = () => {
    listAbort.current?.abort();
    listAbort.current = null;
    listBusy.current = false;
  };

  const loadList = () => {
    if (listBusy.current) return;
    const normalized = normalizeResultReferencesSelection(selection);
    if (!normalized) {
      setList({ kind: "invalid" });
      return;
    }
    const controller = new AbortController();
    listAbort.current = controller;
    listBusy.current = true;
    setList({ kind: "loading" });
    void (async () => {
      try {
        // Only the normalized (workRef, rootJobId) pair leaves this view; no
        // job, attempt, digest, URL or path enters the list request.
        const raw = await readReferences({
          workRef: normalized.workRef,
          rootJobId: normalized.rootJobId,
          signal: controller.signal,
        });
        if (controller.signal.aborted || listAbort.current !== controller)
          return;
        const document = decodeResultReferencesEnvelope(raw, normalized);
        if (!document) {
          setList({ kind: "invalid" });
          return;
        }
        setList({ kind: "read", document });
      } catch {
        if (!controller.signal.aborted && listAbort.current === controller)
          setList({ kind: "error" });
      } finally {
        if (listAbort.current === controller) listBusy.current = false;
      }
    })();
  };

  const toggle = () => {
    if (open) {
      // Closing stops this display read only. It stops no work and accepts
      // no result.
      stopList();
      detailAbort.current?.abort();
      detailAbort.current = null;
      navigated.current = false;
      setView("list");
      setDetail({ kind: "idle" });
      setList({ kind: "idle" });
      setOpen(false);
      return;
    }
    setOpen(true);
    loadList();
  };

  const refresh = () => {
    stopList();
    loadList();
  };

  const openReference = (ref: ResultReferenceRef) => {
    const normalized = normalizeResultReferencesSelection(selection);
    const candidate = normalized ? referenceSelection(ref, normalized) : null;
    const exact = candidate ? normalizeResultSelection(candidate) : null;
    if (!normalized || !exact) {
      setDetail({ kind: "unqualified" });
      setView("detail");
      navigated.current = true;
      return;
    }
    const controller = new AbortController();
    detailAbort.current?.abort();
    detailAbort.current = controller;
    setDetail({ kind: "loading", selection: exact });
    setView("detail");
    navigated.current = true;
    void (async () => {
      try {
        const raw = await readResult({ ...exact, signal: controller.signal });
        if (controller.signal.aborted || detailAbort.current !== controller)
          return;
        // The existing exact-result decoder qualifies this read on its own.
        // A list read is never required to share its runtime generation.
        const decoded = decodeResultEnvelope(raw, exact);
        if (!decoded) {
          setDetail({ kind: "invalid" });
          return;
        }
        setDetail({ kind: "read", selection: exact, decoded });
      } catch {
        if (!controller.signal.aborted && detailAbort.current === controller)
          setDetail({ kind: "error" });
      }
    })();
  };

  const backToResults = () => {
    detailAbort.current?.abort();
    detailAbort.current = null;
    setDetail({ kind: "idle" });
    setView("list");
  };

  const onKeyDown = (event: ReactKeyboardEvent) => {
    if (event.key === "Escape" && view === "detail") {
      event.stopPropagation();
      backToResults();
    }
  };

  const readDocument = list.kind === "read" ? list.document : null;
  const refs = readDocument?.index?.refs ?? [];

  const renderReference = (ref: ResultReferenceRef) => (
                  <li
                    key={[ref.job_id, ref.attempt_id, ref.result_envelope_digest].join(
                      "/",
                    )}
                  >
                    <button className="button" onClick={() => openReference(ref)}>
                      {t("Open retained result")} — {ref.job_id}
                    </button>
                    <small>
                      {t("Role")}: {ref.orchestration_role}{" · "}
                      {t("Validation")}: {t("Unvalidated")}
                      <details>
                        <summary>{t("Attempt")}</summary>
                        <code>{ref.attempt_id}</code>
                      </details>
                    </small>
                  </li>
  );
  return (
    <section
      className="card"
      ref={region}
      tabIndex={-1}
      onKeyDown={onKeyDown}
      aria-label={t("Retained results")}
    >
      <h2 className="section-title">{t("Retained results")}</h2>
      <p className="muted">
        {t("Browse retained results for this project.")}
      </p>
      <button
        className="button"
        aria-expanded={open}
        aria-controls="retained-results-panel"
        onClick={toggle}
      >
        {open ? t("Hide retained results") : t("Show retained results")}
      </button>
      {open ? (
        <div id="retained-results-panel">
          <h4 className="section-title" ref={listHeading} tabIndex={-1}>
            {t("Retained result list")}
          </h4>
          <p className="muted">
            {t("Mission state")}: {missionState}
            {" · "}{t("Historical navigation does not establish a current Mission.")}
          </p>
          {readDocument && readDocument.availability === "AVAILABLE" ? (
            <p className="muted">
              {t("Retained as of")}{" "}
              {readDocument.catalogue.generated_at ?? t("unknown")}
              {" · "}
              {t("Catalogue freshness")}: {readDocument.catalogue.freshness}
              {" · "}{t("Runtime observation")}: {readDocument.source_observation.state}
            </p>
          ) : null}
          <button className="button" onClick={refresh}>
            {t("Refresh retained results")}
          </button>
          {list.kind === "loading" ? (
            <p className="muted" role="status">
              {t("Reading the retained list…")}
            </p>
          ) : null}
          {list.kind === "error" ? (
            <p className="muted" role="status">
              {t("The retained list could not be read.")}
            </p>
          ) : null}
          {list.kind === "invalid" ? (
            <p className="muted" role="status">
              {t("The retained list response was invalid.")}
            </p>
          ) : null}
          {readDocument && readDocument.availability === "UNAVAILABLE" ? (
            <p className="muted" role="status">
              {t(
                unavailableText(
                  readDocument.reason_codes[0] ?? "REFERENCE_INDEX_UNAVAILABLE",
                ),
              )}
            </p>
          ) : null}
          {readDocument &&
          readDocument.availability === "AVAILABLE" &&
          readDocument.index &&
          (readDocument.index.truncated ||
            readDocument.index.availability === "PARTIAL") ? (
            <p className="muted">{t("The source notes this list is partial.")}</p>
          ) : null}
          {readDocument && readDocument.availability === "AVAILABLE" ? (
            refs.length === 0 ? (
              <p className="muted">
                {t("No retained results are listed for this workspace.")}
              </p>
            ) : (
              <ul className="items">
                {refs.slice(0, 8).map(renderReference)}
              </ul>
            )
          ) : null}
          {readDocument?.availability === "AVAILABLE" && refs.length > 8 ? (
            <details>
              <summary>{t("More retained results")} ({refs.length - 8})</summary>
              <ul className="items">{refs.slice(8).map(renderReference)}</ul>
            </details>
          ) : null}
          {readDocument?.availability === "AVAILABLE" && readDocument.index ? (
            <details>
              <summary>{t("Index coverage")}</summary>
              <dl>
                <dt>{t("Jobs without a retained result")}</dt>
                <dd>{readDocument.index.absent_job_ids.join(", ") || t("None")}</dd>
                <dt>{t("Omitted jobs")}</dt>
                <dd>{readDocument.index.omitted_job_ids.join(", ") || t("None")}</dd>
                <dt>{t("Truncated")}</dt>
                <dd>{t(readDocument.index.truncated ? "Yes" : "No")}</dd>
              </dl>
            </details>
          ) : null}
          {view === "detail" ? (
            <div>
              <button ref={back} className="button" onClick={backToResults}>
                {t("Back to retained results")}
              </button>
              {detail.kind === "loading" ? (
                <p className="muted" role="status">
                  {t("Reading the exact result…")}
                </p>
              ) : null}
              {detail.kind === "error" || detail.kind === "invalid" ? (
                <p className="muted" role="status">
                  {t("This exact result could not be read.")}
                </p>
              ) : null}
              {detail.kind === "unqualified" ? (
                <p className="muted" role="status">
                  {t("This reference cannot be opened as an exact result.")}
                </p>
              ) : null}
              {detail.kind === "read"
                ? renderResult(detail.selection, detail.decoded)
                : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
