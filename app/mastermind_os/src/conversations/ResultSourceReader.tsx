import { lazy, Suspense, useEffect, useLayoutEffect, useRef, useState } from "react";
const SourceMarkdown = lazy(() => import("./SourceMarkdown").then(module => ({ default: module.SourceMarkdown })));
import type { MissionResultRead } from "../host";
import { observedMissionAssociation } from "../workspace-contract";
import { decodeResultEnvelope, normalizeResultSelection, type ResultSelection } from "../result";
import { projectOffice, type OfficeProjection, type ProjectedRead } from "../meta-ceo/projection";
import type { DraftInsertion, DraftSource } from "./drafts";

// Translate presentation only; source excerpts, provenance labels and insertion identity stay verbatim.
const STATIC_ZH: Record<string, string> = {
  "Result source reader": "结果来源阅读器",
  "Result source": "结果来源",
  "Back to evidence": "返回证据",
  "A bounded Executive result. Review and acceptance remain separate.": "范围限定的 Executive 结果。审阅与接受仍相互独立。",
  "Reading the exact result…": "正在读取精确结果…",
  "Result content is unavailable. No excerpt can be added.": "结果内容不可用，无法添加摘录。",
  "observation · Freshness unverified · Acceptance not projected": "观察 · 新鲜度尚未验证 · 未提供接受状态",
  "Exact summary excerpt": "原文摘要摘录",
  "Source label for the draft": "草稿中的来源标注",
  "Add result summary to draft": "将结果摘要添加到草稿",
  "An eligible scoped draft is unavailable. Reading does not create one.": "没有符合条件的对应草稿。读取不会创建草稿。",
  "Undo source insertion": "撤销来源插入",
  "The draft has changed. Automatic removal is unavailable.": "草稿已更改，无法自动移除。",
  "Edit draft": "编辑草稿",
  "Return to evidence and reopen this result to review the current draft before adding.": "请返回证据并重新打开此结果，检查当前草稿后再添加。",
  "Read details": "读取详情",
  "Exact source details": "完整来源详情",
  "Work reference": "工作引用",
  "Root Job": "根作业",
  "Job": "作业",
  "Attempt": "尝试",
  "Result envelope digest": "结果封套摘要",
  "Owner": "所有者",
  "Role result digest": "角色结果摘要",
  "Locally acquired": "本地获取时间",
  "Source time": "来源时间",
  "Not supplied": "未提供",
  "Coverage": "覆盖范围",
  "Bounded result": "范围限定的结果",
  "Complete returned content": "返回内容完整",
  "Partial returned content": "返回内容不完整",
  "Added to draft · Not sent": "已添加到草稿 · 未发送",
  "The original draft changed or is unavailable. Return to review it before adding.": "原草稿已更改或不可用。请返回检查后再添加。",
  "Source insertion removed. Your original draft is preserved.": "已移除插入的来源，原草稿已保留。",
  "The draft changed. Edit the draft to preserve your newer text.": "草稿已更改。请编辑草稿以保留较新的文字。",
  "Recheck exact result": "重新核对精确结果",
  "Closing stops this display read. It does not stop work or resolve an original operation.": "关闭只停止本次显示读取，不会停止工作或确认原操作的结果。"
};

export interface ResultSourceReaderProps {
  locale?: "en" | "zh-CN";
  projection: OfficeProjection;
  selection: ResultSelection;
  readResult: MissionResultRead;
  draftRevision: number;
  draftInsertion: DraftInsertion | null;
  appendAvailable: boolean;
  onAppend: (source: DraftSource, expectedRevision: number) => boolean;
  onUndo: (identity: string, expectedRevision: number) => boolean;
  onEditDraft: () => void;
  onClose: () => void;
}
type SourceRead = ProjectedRead<NonNullable<OfficeProjection["result"]["value"]>>;
type ReadState = { kind: "loading" } | { kind: "unavailable" } | { kind: "read"; source: SourceRead };

/** Existing fixed Result read only. The parent keys this view by its exact
 * auth/selection/paired-observation boundary. No generic source URL or cache. */
export function ResultSourceReader({ projection, selection, readResult, draftRevision,
  draftInsertion, appendAvailable, onAppend, onUndo, onEditDraft, onClose, locale = "en" }: ResultSourceReaderProps) {
  const t = (text: string) => locale === "zh-CN" ? STATIC_ZH[text] ?? text : text;
  const [read, setRead] = useState<ReadState>({ kind: "loading" });
  const [notice, setNotice] = useState("");
  const [formatted, setFormatted] = useState(false);
  const originalDraftRevision = useRef(draftRevision);
  const busy = useRef(false), abort = useRef<AbortController | null>(null);
  const region = useRef<HTMLElement>(null);
  const actionStatus = useRef<HTMLParagraphElement>(null);
  useLayoutEffect(() => { if (notice) actionStatus.current?.focus(); }, [notice]);
  const acquire = async () => {
    if (busy.current) return;
    busy.current = true;
    const controller = new AbortController(); abort.current = controller;
    setRead({ kind: "loading" }); setNotice(""); setFormatted(false);
    try {
      const exact = normalizeResultSelection(selection);
      const context = structuredClone(projection.context);
      const association = projection.mission.source.state === "CURRENT" &&
        ["CURRENT", "STALE"].includes(projection.conversation.source.state) &&
        observedMissionAssociation(projection.conversation.value, projection.mission.value, context.selection);
      if (!exact || !association || exact.jobId !== association.job_id || exact.attemptId !== association.attempt_id ||
          exact.workRef !== context.selection?.workRef || exact.rootJobId !== context.selection?.rootJobId)
        throw new Error("RESULT_SELECTION_UNQUALIFIED");
      const raw = await readResult({ ...exact, signal: controller.signal });
      if (controller.signal.aborted || abort.current !== controller) return;
      const value = decodeResultEnvelope(raw, exact);
      if (!value) throw new Error("RESULT_RESPONSE_INVALID");
      context.revisions.result = exact.resultEnvelopeDigest;
      const qualified = projectOffice({
        mission: { context, source: projection.mission.source, value: projection.mission.value },
        conversation: { context, source: projection.conversation.source, value: projection.conversation.value },
        programs: null,
        result: { context, value, source: {
          owner: "EXECUTIVE_OS", ref: JSON.stringify(exact), revision: exact.resultEnvelopeDigest,
          observed_at: new Date().toISOString(), observed_at_kind: "LOCAL_ACQUISITION",
          state: "CURRENT", coverage: "BOUNDED_RESULT",
        } },
      }, context).result;
      setRead({ kind: "read", source: qualified });
    } catch {
      if (!controller.signal.aborted && abort.current === controller) setRead({ kind: "unavailable" });
    } finally {
      if (abort.current === controller) busy.current = false;
    }
  };
  useEffect(() => {
    region.current?.focus();
    void acquire();
    return () => { abort.current?.abort(); abort.current = null; busy.current = false; };
  }, []);
  const qualified = read.kind === "read" ? read.source : null;
  const value = qualified && ["CURRENT", "STALE"].includes(qualified.source.state) ? qualified.value : null;
  const result = value?.result;
  const summary = result?.availability === "AVAILABLE" ? result.content?.summary : null;
  const sourceLabel = qualified ? `Executive ${result?.role ?? "bounded"} result · ${selection.workRef} · ${selection.jobId} · Revision ${selection.resultEnvelopeDigest} · ${qualified.source.state} observation · Freshness unverified · Acceptance not projected` : "";
  const source: DraftSource | null = summary && result && qualified ? {
    identity: JSON.stringify([selection, result.role_result_digest, summary, sourceLabel, qualified.source.state, qualified.source.revision]),
    excerpt: summary,
    label: sourceLabel,
  } : null;
  const added = source && draftInsertion?.source.identity === source.identity ? draftInsertion : null;
  const unchanged = draftRevision === originalDraftRevision.current;
  const canUndo = !!added && draftRevision === added.revision;
  return <section ref={region} tabIndex={-1} className="conversation-companion conversation-result-reader"
    role="region" aria-label={t("Result source reader")} onKeyDown={event => {
      if (event.key === "Escape" && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) {
        event.stopPropagation(); onClose();
      }
    }}>
    <header><h2>{t("Result source")}</h2><button type="button" onClick={onClose}>{t("Back to evidence")}</button></header>
    <p>{selection.workRef} · {selection.jobId}</p>
    <p>{t("A bounded Executive result. Review and acceptance remain separate.")}</p>
    {read.kind === "loading" ? <p role="status">{t("Reading the exact result…")}</p> : <>
      {!summary ? <p role="status">{t("Result content is unavailable. No excerpt can be added.")}</p> : <>
        <p>{qualified!.source.state} {t("observation · Freshness unverified · Acceptance not projected")}</p>
        <h3>{t("Exact summary excerpt")}</h3>
        <div className="source-preview-controls">
          <button type="button" aria-pressed={formatted} onClick={() => setFormatted(value => !value)}>
            {formatted ? (locale === "zh-CN" ? "查看原文" : "View exact source")
              : (locale === "zh-CN" ? "格式化预览" : "Formatted preview")}
          </button>
        </div>
        {formatted ? <>
          <p className="source-preview-note">{locale === "zh-CN"
            ? "仅格式展示。摘录保留原文；图片与链接不会自动加载或打开。"
            : "Presentation only. Excerpts retain the original text. Images and links do not load or open from this preview."}</p>
          <Suspense fallback={<p role="status">{locale === "zh-CN" ? "正在加载格式化预览…" : "Loading formatted preview..."}</p>}>
            <SourceMarkdown source={summary} locale={locale} />
          </Suspense>
        </> : <blockquote className="conversation-source-excerpt">{summary}</blockquote>}
        <details><summary>{t("Source label for the draft")}</summary><p>{source!.label}</p></details>
        <button type="button" disabled={!appendAvailable || !!added || !unchanged} onKeyDown={event => {
          if (event.key === "Enter" && (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229)) event.preventDefault();
        }} onClick={() => {
          if (!source || !appendAvailable || added || !unchanged) return;
          setNotice(onAppend(source, originalDraftRevision.current)
            ? "Added to draft · Not sent"
            : "The original draft changed or is unavailable. Return to review it before adding.");
        }}>{t("Add result summary to draft")}</button>
        {!appendAvailable && <p>{t("An eligible scoped draft is unavailable. Reading does not create one.")}</p>}
        {canUndo ? <button type="button" onClick={() => {
          setNotice(onUndo(added!.source.identity, draftRevision)
            ? "Source insertion removed. Your original draft is preserved."
            : "The draft changed. Edit the draft to preserve your newer text.");
        }}>{t("Undo source insertion")}</button> : (added || !unchanged) && <>
          <p>{t("The draft has changed. Automatic removal is unavailable.")}</p><button type="button" onClick={onEditDraft}>{t("Edit draft")}</button>
        </>}
        {!added && !unchanged && <p>{t("Return to evidence and reopen this result to review the current draft before adding.")}</p>}
      </>}
      {qualified?.reason && <details><summary>{t("Read details")}</summary><p>{qualified.reason}</p></details>}
    </>}
    <details><summary>{t("Exact source details")}</summary>
      <dl><dt>{t("Work reference")}</dt><dd>{selection.workRef}</dd><dt>{t("Root Job")}</dt><dd>{selection.rootJobId}</dd>
        <dt>{t("Job")}</dt><dd>{selection.jobId}</dd><dt>{t("Attempt")}</dt><dd>{selection.attemptId}</dd>
        <dt>{t("Result envelope digest")}</dt><dd>{selection.resultEnvelopeDigest}</dd>
        {summary && <><dt>{t("Owner")}</dt><dd>{qualified!.source.owner}</dd><dt>{t("Role result digest")}</dt><dd>{result!.role_result_digest}</dd>
          <dt>{t("Locally acquired")}</dt><dd>{qualified!.source.observed_at}</dd><dt>{t("Source time")}</dt><dd>{t("Not supplied")}</dd>
          <dt>{t("Coverage")}</dt><dd>{t("Bounded result")} · {t(result!.content_complete ? "Complete returned content" : "Partial returned content")}</dd></>}
      </dl>
    </details>
    {(notice || added) && <p ref={actionStatus} tabIndex={-1} role="status">{t(notice || "Added to draft · Not sent")}</p>}
    <button type="button" disabled={read.kind === "loading"} onClick={() => { void acquire(); }}>{t("Recheck exact result")}</button>
    <p>{t("Closing stops this display read. It does not stop work or resolve an original operation.")}</p>
  </section>;
}
