import { lazy, Suspense, useCallback, useLayoutEffect, useRef, useState } from "react";
import type { ProjectionContext } from "../meta-ceo/projection";
import { sameTarget } from "../meta-ceo/projection";
import { KnowledgeDraftCompanion, knowledgeDraftBinding, type KnowledgeDraftPort } from "./KnowledgeDraftCompanion";
import type { MissionHost } from "../host";
import type { ResultEnvelopeDigestShape, ResultSelection } from "../result";
import type { ResultReferencesSelection } from "../result-references";
import { RetainedResults } from "../RetainedResults";
const SourceMarkdown = lazy(() => import("../conversations/SourceMarkdown").then(module => ({ default: module.SourceMarkdown })));

// Presentation copy only. Result material, identifiers, digests, attempt ids,
// read receipts and catalogue timestamps stay verbatim. No acceptance, review
// or freshness promotion happens here: a read receipt is displayed as a
// receipt and freshness is labelled unverified.
const SOURCES_ZH: Record<string, string> = {
  "Retained result records": "保留的结果记录",
  "Retained result": "保留结果",
  "Retained result document": "保留结果文档",
  "Retained result provenance": "保留结果来源信息",
  "Formatted preview": "格式化预览",
  "Loading formatted preview…": "正在加载格式化预览…",
  "Returned role content (JSON)": "返回的角色内容（JSON）",
  "Proposed next actions": "建议的后续行动",
  "From this result; adoption not established": "来自此结果；尚未确立采纳状态",
  "Observation time": "观察时间",
  "Exact source details": "完整来源详情",
  "Reading does not record acceptance or release.": "读取不会记录接受或发布状态。",
  "Selection": "选择",
  "Role": "角色",
  "Attempt": "尝试",
  "Result digest": "结果摘要",
  "Execution status": "执行状态",
  "Content complete": "内容完整",
  "Yes": "是",
  "No": "否",
  "Omitted fields": "省略的字段",
  "None": "无",
  "Not supplied": "未提供",
  "Ownership": "所有权",
  "Executive": "执行方",
  "Source time": "来源时间",
  "Unknown": "未知",
  "Read receipt": "读取回执",
  "Unchanged during this read": "本次读取期间未发生变化",
  "Changed during this read": "本次读取期间发生变化",
  "Read state not known": "读取状态未知",
  "Runtime identity": "运行时标识",
  "Freshness": "新鲜度",
  "Not verified": "未验证",
  "This receipt proves the read happened. It does not verify that the content is current.":
    "该回执仅证明读取发生，不证明内容是最新的。",
  "This result's content is over its display budget.": "该结果的内容超出显示预算。",
  "The owner did not supply this result's content.": "所有者未提供该结果的内容。",
  "No draft action is available: the original scoped draft owner is unavailable because no existing draft port was supplied.":
    "没有可用的草稿操作：原始范围的草稿所有者不可用，因为未提供现有草稿端口。",
};

export interface KnowledgeSourcesProps {
  selection: ResultReferencesSelection;
  requestedResult?: ResultSelection;
  authGeneration: string | number;
  hostGeneration: string | number;
  locale: "en" | "zh-CN";
  missionState: string;
  context: ProjectionContext;
  draftPort?: KnowledgeDraftPort;
  onReaderChange?: (open: boolean) => void;
  readResultReferences: NonNullable<MissionHost["readResultReferences"]>;
  readResult: NonNullable<MissionHost["readResult"]>;
}
interface ReadWitness { selection: string; context: ProjectionContext; binding: string | null }
const sourceKey = (s: ResultSelection) => JSON.stringify([s.workRef, s.rootJobId, s.jobId, s.attemptId, s.resultEnvelopeDigest]);

function KnowledgeResult({ selection, decoded, locale, context, draftPort, witness, onReaderChange }: {
  selection: ResultSelection; decoded: ResultEnvelopeDigestShape; locale: "en" | "zh-CN";
  context: ProjectionContext; draftPort?: KnowledgeDraftPort; witness: ReadWitness | null;
  onReaderChange?: (open: boolean) => void;
}) {
  useLayoutEffect(() => {
    onReaderChange?.(true);
    return () => { onReaderChange?.(false); };
  }, [onReaderChange]);
  const [formatted, setFormatted] = useState(false);
  const t = (value: string) => locale === "zh-CN" ? SOURCES_ZH[value] ?? value : value;
  const view = decoded.result, content = view?.content, observation = decoded.source_observation;
  const runtime = observation.runtime;
  const contentSentence = decoded.availability === "CONTENT_OVER_BUDGET"
    ? t("This result's content is over its display budget.") : decoded.availability === "UNAVAILABLE"
      ? t("The owner did not supply this result's content.") : null;
  const sourceLabel = `Executive ${view?.role ?? "bounded"} result · ${selection.workRef} · ${selection.jobId} · Revision ${selection.resultEnvelopeDigest} · ${view?.content_complete ? "Complete returned content" : "Partial returned content"} · Freshness unverified · Acceptance not projected`;
  const source = decoded.availability === "AVAILABLE" && content?.summary ? {
    identity: JSON.stringify([selection, view?.role_result_digest, content.summary, sourceLabel]),
    excerpt: content.summary, label: sourceLabel,
  } : null;
  const exactWitness = witness?.selection === sourceKey(selection) ? witness : null;
  return <div className="knowledge-result">
    <article className="knowledge-result-document" aria-label={t("Retained result document")}>
      <p className="knowledge-eyebrow">{view?.role ?? t("Retained result")} · {selection.jobId}</p>
      <h1 className="knowledge-result-title">{t("Retained result")}</h1>
      {contentSentence && <p className="knowledge-result-note" data-state="UNAVAILABLE">{contentSentence}</p>}
      {content && <>
        <p className="knowledge-result-summary">{content.summary}</p>
        <div className="knowledge-result-preview"><button type="button" aria-expanded={formatted} onClick={() => setFormatted(value => !value)}>{t("Formatted preview")}</button>
          {formatted && <Suspense fallback={<p role="status">{t("Loading formatted preview…")}</p>}><SourceMarkdown source={content.summary} locale={locale} /></Suspense>}</div>
        {content.next_actions.length > 0 && <section aria-label={t("Proposed next actions")}>
          <h3 className="knowledge-result-label">{t("Proposed next actions")}</h3>
          <p className="knowledge-result-note">{t("From this result; adoption not established")}</p>
          <ul className="knowledge-result-actions">{content.next_actions.map((action, i) => <li key={i}>{action}</li>)}</ul>
        </section>}
        <details className="knowledge-result-json"><summary>{t("Returned role content (JSON)")}</summary>
          <pre>{JSON.stringify(content.role_result, null, 2)}</pre></details>
      </>}
      <p className="knowledge-result-note">{t("Reading does not record acceptance or release.")}</p>
    </article>
    <aside className="knowledge-result-companion" aria-label={t("Retained result provenance")}>
      <p className="knowledge-eyebrow">{t("Retained result provenance")}</p>
      <dl><dt>{t("Ownership")}</dt><dd>EXECUTIVE_OS</dd>
        <dt>{t("Source time")}</dt><dd>{t("Not supplied")}</dd>
        <dt>{t("Observation time")}</dt><dd>{t("Not supplied")}</dd>
        <dt>{t("Freshness")}</dt><dd>{t("Not verified")}</dd>
        <dt>{t("Content complete")}</dt><dd>{view ? t(view.content_complete ? "Yes" : "No") : t("Not supplied")}</dd>
      </dl>
      <p className="knowledge-muted">{t("This receipt proves the read happened. It does not verify that the content is current.")}</p>
      <details><summary>{t("Exact source details")}</summary><dl>
        <dt>{t("Selection")}</dt><dd>{selection.workRef} · {selection.rootJobId} · {selection.jobId}</dd>
        <dt>{t("Role")}</dt><dd>{view?.role ?? t("Not supplied")}</dd>
        <dt>{t("Attempt")}</dt><dd>{selection.attemptId}</dd>
        <dt>{t("Result digest")}</dt><dd>{selection.resultEnvelopeDigest}</dd>
        <dt>{t("Execution status")}</dt><dd>{view?.execution_status ?? t("Not supplied")}</dd>
        <dt>{t("Omitted fields")}</dt><dd>{view?.omitted.length ? view.omitted.join(", ") : t("None")}</dd>
        <dt>{t("Read receipt")}</dt><dd>{observation.state === "SAME" ? t("Unchanged during this read") : t("Read state not known")}</dd>
        {runtime && <><dt>{t("Runtime identity")}</dt><dd>{runtime.source_identity} · {runtime.before}→{runtime.after}</dd></>}
      </dl>{decoded.reason_codes.length > 0 && <p className="knowledge-result-codes">{decoded.reason_codes.join(" · ")}</p>}</details>
      <KnowledgeDraftCompanion source={source} selection={selection} locale={locale}
        context={exactWitness?.context ?? context} readBinding={exactWitness?.binding ?? null} port={draftPort} />
    </aside>
  </div>;
}

/** Existing index/detail readers retain their exact decoder and lifetime rules.
 * This wrapper witnesses only the original local draft destination around the
 * read. A changed destination disables insertion; it never widens the read. */
export function KnowledgeSources(props: KnowledgeSourcesProps) {
  const current = useRef(props); current.current = props;
  const witness = useRef<ReadWitness | null>(null);
  const guardedRead = useCallback<NonNullable<MissionHost["readResult"]>>(async request => {
    const started = current.current;
    const context = structuredClone(started.context);
    const binding = knowledgeDraftBinding(context, started.draftPort);
    const raw = await started.readResult(request);
    const now = current.current;
    if (request.signal.aborted || context.authGeneration !== now.context.authGeneration ||
        !sameTarget(context, now.context) || started.hostGeneration !== now.hostGeneration ||
        started.readResult !== now.readResult) throw new Error("READ_CANCELLED");
    const after = knowledgeDraftBinding(now.context, now.draftPort);
    witness.current = { selection: sourceKey(request), context, binding: binding !== null && after === binding ? binding : null };
    return raw;
  }, []);
  const t = (value: string) => props.locale === "zh-CN" ? SOURCES_ZH[value] ?? value : value;
  return <section className="knowledge-sources" aria-label={t("Retained result records")}>
    <RetainedResults selection={props.selection} requestedResult={props.requestedResult} authGeneration={props.authGeneration}
      hostGeneration={props.hostGeneration} locale={props.locale} missionState={props.missionState}
      readReferences={props.readResultReferences} readResult={guardedRead}
      renderResult={(selection, decoded) => <KnowledgeResult key={sourceKey(selection)}
        selection={selection} decoded={decoded} locale={props.locale} context={props.context}
        draftPort={props.draftPort} witness={witness.current} onReaderChange={props.onReaderChange} />} />
  </section>;
}
