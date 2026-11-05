import { useEffect, useId, useRef, useState } from "react";
import { allEvidence, type EvidenceRef } from "../mission";
import type { OfficeProjection, SourceState } from "../meta-ceo/projection";
import { normalizeResultSelection, type ResultSelection } from "../result";
import { normalizeResultReferencesSelection } from "../result-references";
import type { MissionHost } from "../host";
import { KnowledgeSources } from "./KnowledgeSources";
import type { KnowledgeDraftPort } from "./KnowledgeDraftCompanion";
import "./knowledge.css";

export interface SourceNavigation {
  owner: EvidenceRef["owner"]; ref: string; revision: string; mode: "current" | "history";
}
export interface KnowledgeProps {
  projection: OfficeProjection;
  requestedResult?: ResultSelection;
  onReturnToSearch?: () => void;
  /** Existing source-navigation owner only. This component never resolves a ref
   * into a guessed URL, reads another source, or mutates the original record. */
  onOpenSource?: (source: SourceNavigation) => void;
  /** Existing host retained-result readers. The retained-result band mounts only
   * when both are supplied together with a normalizable selection and a host
   * generation; otherwise this view names exactly what is missing and never
   * claims an owner denial that no owner reported. */
  readResultReferences?: MissionHost["readResultReferences"];
  readResult?: MissionHost["readResult"];
  locale?: "en" | "zh-CN";
  /** The caller's actual host generation. Falls back to the projection context's
   * binding generation only when that is a string or number. */
  hostGeneration?: string | number;
  draftPort?: KnowledgeDraftPort;
}

// Presentation copy only. Identifiers, revisions and observed times stay verbatim.
const KNOWLEDGE_ZH: Record<string, string> = {
  "Not available here": "此处暂不可用",
  "Source details": "来源详情",
  "References from the selected work only. Other records may not appear here.": "仅显示所选工作提供的引用，其他记录可能未列出。",
  "Saved results aren’t available in this view yet.": "此视图暂时无法查看已保存的结果。",
  "Knowledge": "知识",
  "Back to search results": "返回搜索结果",
  "Knowledge source": "知识来源",
  "A library that grows with you": "与你一同成长的资料库",
  "Keep what matters.": "留住重要的内容。",
  "Build on what you know.": "在已知之上继续构建。",
  "Useful work, with its sources and qualification intact.": "有用的成果，保留其来源与限定条件。",
  "Search supplied knowledge": "搜索已提供的知识",
  "Find an owner, reference or field": "查找所有者、引用或字段",
  "Selected Mission scope": "所选任务范围",
  "Company-wide coverage is not established.": "未建立全公司范围的覆盖。",
  "01 · Decisions": "01 · 决策",
  "02 · Discoveries": "02 · 发现",
  "03 · Evidence": "03 · 证据",
  "The choices shaping the company.": "塑造公司的那些选择。",
  "Findings worth returning to.": "值得回顾的发现。",
  "Follow the supplied references.": "沿着已提供的引用追查。",
  "Owner index unavailable": "所有者索引不可用",
  "Source unavailable": "来源不可用",
  "Decision, discovery, handoff and contract indexes are unavailable. Evidence references do not supply their record content.":
    "决策、发现、交接与合同索引不可用。证据引用不提供其记录内容。",
  "Retained result records": "保留的结果记录",
  "No project selection is supplied, so retained result records have no scope to read.":
    "未提供项目选择，保留结果记录没有可读取的范围。",
  "The supplied project selection does not qualify as a retained-result scope.":
    "所提供的项目选择不符合保留结果读取的范围要求。",
  "Retained result reading is not available here: the host result functions were not supplied.":
    "此处无法读取保留结果：未提供宿主结果函数。",
  "Retained result reading is not available here: no host generation was supplied for this view.":
    "此处无法读取保留结果：未为此视图提供宿主世代。",
  "This is a missing capability, not a source denial: no owner reported access denial.":
    "这是能力缺失，而非来源拒绝：没有任何所有者报告访问被拒绝。",
  "Supplied knowledge references": "已提供的知识引用",
  "Supplied references": "已提供的引用",
  "Owner order retained": "保持所有者顺序",
  "Retained history. Currentness has not been established.": "保留的历史。尚未确立当前性。",
  "A qualified source is not available.": "没有可用的合格来源。",
  "No source reference collection was supplied.": "未提供来源引用集合。",
  "Missing or private knowledge is never reconstructed from conversation history.":
    "缺失或私有的知识绝不会从对话历史中重建。",
  "No supplied references match this search.": "没有已提供的引用匹配此搜索。",
  "No references were supplied. This does not establish zero knowledge.":
    "未提供任何引用。这不代表知识为零。",
  "Evidence reference": "证据引用",
  "Inspect": "查看",
  "Exact source reference": "精确来源引用",
  "Close source context": "关闭来源上下文",
  "Selected source reference": "所选来源引用",
  "Canonical owner": "规范所有者",
  "Type": "类型",
  "Exact ref": "精确引用",
  "Revision": "修订",
  "Not supplied": "未提供",
  "Source time": "来源时间",
  "Observed": "观测时间",
  "Referenced by selected Mission": "由所选任务引用",
  "Coverage": "覆盖范围",
  "Supplied Mission evidence references": "已提供的任务证据引用",
  "Derived from": "推导自",
  "Original record content has not been supplied. This derived reference view is not a canonical record or proof of a direct project relationship.":
    "尚未提供原始记录内容。此派生引用视图不是规范记录，也不能证明存在直接的项目关系。",
  "Open original source": "打开原始来源",
  "A qualified source and its existing navigation owner are required to open the original.":
    "打开原始来源需要合格的来源及其现有的导航所有者。",
  "Follow the source": "跟随来源",
  "Useful knowledge.": "有用的知识。",
  "Visible provenance.": "可见的出处。",
  "Inspect a supplied reference to see its owner, revision, observed time and exact source context.":
    "查看一条已提供的引用，了解其所有者、修订、观测时间与精确来源上下文。",
  "Source clocks remain separate. A return remains separate from acceptance.":
    "来源时钟保持独立。返回仍与验收相互独立。",
  "Knowledge is not model memory. Search and inspection change presentation only; durable changes return to the canonical owner.":
    "知识不是模型记忆。搜索与检查只改变呈现；持久变更交回规范所有者。",
};

function referenceState(ref: EvidenceRef, parent: SourceState): SourceState {
  if (ref.freshness_state === "UNAVAILABLE") return "UNAVAILABLE";
  if (ref.freshness_state === "PARTIAL" || !ref.owner || !ref.ref || !ref.source_revision || !ref.observed_at) return "UNKNOWN";
  return parent === "STALE" || ref.freshness_state === "HISTORICAL" ? "STALE" : "CURRENT";
}

// Stable, small identity token per supplied function. A replaced host method
// changes the epoch even when the caller passes a same-shaped host object.
const FN_EPOCH = new WeakMap<(...args: never[]) => unknown, number>();
let FN_SEQ = 0;
function fnEpoch(fn: unknown): string {
  if (typeof fn !== "function") return "absent";
  const f = fn as (...args: never[]) => unknown;
  let n = FN_EPOCH.get(f);
  if (n === undefined) { n = ++FN_SEQ; FN_EPOCH.set(f, n); }
  return `fn${n}`;
}

function KnowledgeBody({ projection, onOpenSource, readResultReferences, readResult,
  locale = "en", hostGeneration, draftPort, requestedResult, onReturnToSearch }: KnowledgeProps) {
  const t = (value: string) => (locale === "zh-CN" ? KNOWLEDGE_ZH[value] ?? value : value);
  const [query, setQuery] = useState("");
  const [readerActive, setReaderActive] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const searchId = useId(), search = useRef<HTMLInputElement>(null);
  const detail = useRef<HTMLElement>(null), trigger = useRef<HTMLButtonElement | null>(null);
  const context = projection.context;
  const source = projection.mission.source;
  const retained = source.state === "CURRENT" || source.state === "STALE";
  const mission = retained ? projection.mission.value : null;
  // v3 adds a Result index; these are the unchanged canonical v2 evidence fields.
  const refs = mission ? allEvidence({ ...mission, schema: "mastermind.mission_workspace.v2" }) : [];
  const selected = selectedId === null ? null : refs[selectedId] ?? null;
  const term = query.trim().toLocaleLowerCase();
  const visible = refs.map((row, index) => ({ ...row, index })).filter(({ facet, evidence: e }) =>
    !term || `${facet}\n${e.owner}\n${e.ref}\n${e.field}\n${e.source_revision ?? ""}`.toLocaleLowerCase().includes(term));
  const selectedState = selected ? referenceState(selected.evidence, source.state) : null;
  const canOpen = selected && onOpenSource && (selectedState === "CURRENT" || selectedState === "STALE");
  useEffect(() => { if (selectedId !== null) detail.current?.focus(); }, [selectedId]);
  const close = () => {
    setSelectedId(null);
    (trigger.current?.isConnected ? trigger.current : search.current)?.focus();
  };

  // Retained-result band qualification: a normalizable selection, both host
  // readers, and a real host generation (prop, else string/number binding
  // generation). Current Mission state is never required to read history.
  const hostGen = hostGeneration !== undefined ? hostGeneration
    : typeof context.bindingGeneration === "string" || typeof context.bindingGeneration === "number"
      ? context.bindingGeneration : null;
  const normalizedSelection = context.selection
    ? normalizeResultReferencesSelection({ workRef: context.selection.workRef, rootJobId: context.selection.rootJobId })
    : null;
  const missionState = source.state === "CURRENT" ? "CURRENT" : source.state === "STALE" ? "HISTORICAL" : "UNAVAILABLE";
  const sourcesCopy = !context.selection
    ? "No project selection is supplied, so retained result records have no scope to read."
    : !normalizedSelection
      ? "The supplied project selection does not qualify as a retained-result scope."
      : !readResultReferences || !readResult
        ? "Retained result reading is not available here: the host result functions were not supplied."
        : "Retained result reading is not available here: no host generation was supplied for this view.";

  return <section className={`atelier-knowledge${readerActive ? " knowledge-reader-active" : ""}`} lang={locale} aria-label={t("Knowledge")}>
    {onReturnToSearch && <button type="button" className="button knowledge-return" onClick={onReturnToSearch}>{t("Back to search results")}</button>}
    <header className="knowledge-heading" aria-hidden={readerActive}><p className="knowledge-eyebrow">{t("A library that grows with you")}</p>
      <h1>{t("Keep what matters.")}<br />{t("Build on what you know.")}</h1>
      <p>{t("Useful work, with its sources and qualification intact.")}</p>
      <div className="knowledge-search"><label htmlFor={searchId}>{t("Search supplied knowledge")}</label>
        <input ref={search} id={searchId} type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder={t("Find an owner, reference or field")} /></div>
    </header>
    <section className="knowledge-source" aria-label={t("Knowledge source")}><span data-state={source.state}>{source.coverage === "NOT_PROJECTED" ? t("Not available here") : source.state}</span>
      <p>{t("References from the selected work only. Other records may not appear here.")}</p>
      <details><summary>{t("Source details")}</summary><p>{source.state} · {source.coverage}</p></details></section>
    <div className="knowledge-collections">
      <section><p className="knowledge-eyebrow">{t("01 · Decisions")}</p><h2>{t("The choices shaping the company.")}</h2><p>{t("Owner index unavailable")}</p></section>
      <section><p className="knowledge-eyebrow">{t("02 · Discoveries")}</p><h2>{t("Findings worth returning to.")}</h2><p>{t("Owner index unavailable")}</p></section>
      <section><p className="knowledge-eyebrow">{t("03 · Evidence")}</p><h2>{t("Follow the supplied references.")}</h2>
        <p>{mission ? (locale === "zh-CN" ? `${refs.length} 条已提供的引用` : `${refs.length} references supplied`) : t("Source unavailable")}</p></section>
    </div>
    <p className="knowledge-muted">{t("Decision, discovery, handoff and contract indexes are unavailable. Evidence references do not supply their record content.")}</p>
    {normalizedSelection && readResultReferences && readResult && hostGen !== null
      ? <KnowledgeSources selection={normalizedSelection} requestedResult={requestedResult} authGeneration={context.authGeneration}
        hostGeneration={hostGen} locale={locale} missionState={missionState} context={context} draftPort={draftPort} onReaderChange={setReaderActive}
        readResultReferences={readResultReferences} readResult={readResult} />
      : <section className="knowledge-sources knowledge-sources-empty" aria-label={t("Retained result records")}>
        <p className="knowledge-eyebrow">{t("Retained result records")}</p>
        <p>{t("Saved results aren’t available in this view yet.")}</p>
        <details><summary>{t("Source details")}</summary><p>{t(sourcesCopy)}</p></details>
      </section>}
    <div className="knowledge-layout">
      <section className="knowledge-list" aria-label={t("Supplied knowledge references")}>
        <div className="knowledge-section-title"><h2>{t("Supplied references")}</h2><p>{t("Owner order retained")}</p></div>
        {source.state === "STALE" && <p className="knowledge-history">{t("Retained history. Currentness has not been established.")}</p>}
        {!mission ? <div className="knowledge-empty"><h3>{t("A qualified source is not available.")}</h3>
          <p>{projection.mission.reason ?? t("No source reference collection was supplied.")}</p>
          <p>{t("Missing or private knowledge is never reconstructed from conversation history.")}</p></div>
          : visible.length ? <ul>{visible.map(({ facet, evidence, index }) => <li key={`${facet}:${index}`}>
            <div><p className="knowledge-eyebrow">{t("Evidence reference")} · {evidence.owner}</p>
              <h3>{facet} · {evidence.field}</h3><p className="knowledge-ref">{evidence.ref}</p></div>
            <div className="knowledge-row-action"><span data-state={referenceState(evidence, source.state)}>{referenceState(evidence, source.state)}</span>
              <button type="button" aria-label={`${t("Inspect")} ${facet} · ${evidence.field}`} onClick={event => {
                trigger.current = event.currentTarget;
                if (selectedId === index) detail.current?.focus();
                else setSelectedId(index);
              }}>{t("Inspect")}</button></div>
          </li>)}</ul> : <p className="knowledge-empty">{term ? t("No supplied references match this search.") : t("No references were supplied. This does not establish zero knowledge.")}</p>}
      </section>
      <aside className="knowledge-companion">
        {selected ? <section ref={detail} tabIndex={-1} aria-label={t("Selected source reference")} onKeyDown={event => { if (event.key === "Escape") close(); }}>
          <div className="knowledge-section-title"><p className="knowledge-eyebrow">{t("Exact source reference")}</p><button type="button" onClick={close}>{t("Close source context")}</button></div>
          <h2>{selected.facet} · {selected.evidence.field}</h2>
          <p data-state={selectedState ?? "UNKNOWN"}>{selectedState}</p>
          <dl><dt>{t("Canonical owner")}</dt><dd>{selected.evidence.owner}</dd>
            <dt>{t("Type")}</dt><dd>{t("Evidence reference")}</dd><dt>{t("Exact ref")}</dt><dd>{selected.evidence.ref}</dd>
            <dt>{t("Revision")}</dt><dd>{selected.evidence.source_revision ?? t("Not supplied")}</dd>
            <dt>{t("Source time")}</dt><dd>{selected.evidence.source_time ?? t("Not supplied")}</dd>
            <dt>{t("Observed")}</dt><dd>{selected.evidence.observed_at ?? t("Not supplied")}</dd>
            <dt>{t("Referenced by selected Mission")}</dt><dd>{context.selection?.workRef} · {context.selection?.rootJobId}</dd>
            <dt>{t("Coverage")}</dt><dd>{t("Supplied Mission evidence references")}</dd>
            <dt>{t("Derived from")}</dt><dd>{source.owner} · {source.ref} · {source.revision}</dd></dl>
          <p>{t("Original record content has not been supplied. This derived reference view is not a canonical record or proof of a direct project relationship.")}</p>
          <button type="button" disabled={!canOpen} onClick={() => {
            if (canOpen) onOpenSource!({ owner: selected.evidence.owner, ref: selected.evidence.ref,
              revision: selected.evidence.source_revision!, mode: selectedState === "STALE" ? "history" : "current" });
          }}>{t("Open original source")}</button>
          {!canOpen && <p className="knowledge-muted">{t("A qualified source and its existing navigation owner are required to open the original.")}</p>}
        </section> : <section><p className="knowledge-eyebrow">{t("Follow the source")}</p><h2>{t("Useful knowledge.")}<br />{t("Visible provenance.")}</h2>
          <p>{t("Inspect a supplied reference to see its owner, revision, observed time and exact source context.")}</p>
</section>}
        <p className="knowledge-boundary">{t("Knowledge is not model memory. Search and inspection change presentation only; durable changes return to the canonical owner.")}</p>
      </aside>
    </div>
  </section>;
}

export function Knowledge(props: KnowledgeProps) {
  const { context, mission } = props.projection;
  // Root epoch: auth, selection, session, binding, mission revision, source
  // clock, the caller's host generation and the identity of the supplied host
  // methods. Any change remounts the whole body before paint, so RetainedResults
  // additionally aborts and clears within the same epoch discipline, and no
  // old-owner content survives into the new epoch.
  const epoch = JSON.stringify([context.authGeneration, context.selection, context.sessionRef,
    context.bindingGeneration, context.revisions.mission, mission.source.state,
    props.hostGeneration === undefined ? null : props.hostGeneration,
    fnEpoch(props.readResultReferences), fnEpoch(props.readResult),
    props.requestedResult === undefined ? null : normalizeResultSelection(props.requestedResult) ?? "invalid"]);
  return <KnowledgeBody key={epoch} {...props} />;
}
