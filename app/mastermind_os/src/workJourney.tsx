import { useState, type ReactNode } from "react";
import {
  allEvidence,
  type MissionDocument,
  type MissionSelection,
} from "./mission";
import "./workJourney.css";

type Locale = "en" | "zh-CN";

interface CopyTable {
  sourceSelectionUnavailable: string;
  titleReturned: string;
  titleWork: string;
  readCaveatLead: string;
  readCaveatTail: string;
  sectionResults: string;
  resultsNotSupplied: string;
  sectionReview: string;
  sectionAcceptance: string;
  sectionRelease: string;
  sectionReturn: string;
  sectionNextOwner: string;
  returnReceived: string;
  returnUnknown: string;
  labelDispatchState: string;
  labelReviewRequired: string;
  labelVerdict: string;
  labelAcceptanceState: string;
  labelAcceptanceRuling: string;
  labelReleaseState: string;
  rulingUnavailable: string;
  releaseNote: string;
  releaseUnknown: string;
  labelOwedSeat: string;
  labelOwedReason: string;
  labelNextAction: string;
  labelCurrentWorker: string;
  valueNotSupplied: string;
  activityDetailsTitle: string;
  activityNotSupplied: string;
  navOpenEvidence: string;
  navOpenJournal: string;
  evidenceTitle: string;
  evidenceEmpty: string;
  filterEmpty: string;
  filterAll: string;
  filterCurrent: string;
  filterPartial: string;
  filterHistorical: string;
  filterUnavailable: string;
  observedCount: (n: number) => string;
  seeAll: (n: number) => string;
  showFewer: string;
  ladderTitle: string;
  ladderRead: string;
  ladderDispatch: string;
  ladderReview: string;
  ladderAcceptance: string;
  ladderRelease: string;
  selectedSourceTitle: string;
  selectPrompt: string;
  truthBoundary: string;
  labelFacet: string;
  labelOwner: string;
  labelRef: string;
  labelField: string;
  labelRevision: string;
  labelSourceTime: string;
  labelObservedAt: string;
  labelFreshness: string;
  journalTitle: string;
  journalUnavailable: string;
  currentContextTitle: string;
  continuityTitle: string;
  continuityEmpty: string;
  sourceTuples: string;
  activityTitle: string;
}

const COPY: Record<Locale, CopyTable> = {
  en: {
    sourceSelectionUnavailable:
      "Source selection does not match this document; nothing is shown.",
    titleReturned: "Returned work",
    titleWork: "Work detail",
    readCaveatLead: "Source read state: ",
    readCaveatTail: " — values may be stale or incomplete.",
    sectionResults: "Retained results",
    resultsNotSupplied: "No result panel was supplied.",
    sectionReview: "Review",
    sectionAcceptance: "Acceptance",
    sectionRelease: "Release",
    sectionReturn: "Return",
    sectionNextOwner: "Next owner",
    returnReceived: "Returned evidence received.",
    returnUnknown: "Return not established.",
    labelDispatchState: "Dispatch state",
    labelReviewRequired: "Review required",
    labelVerdict: "Verdict",
    labelAcceptanceState: "Acceptance state",
    labelAcceptanceRuling: "Acceptance ruling",
    labelReleaseState: "Release state",
    rulingUnavailable: "Unavailable",
    releaseNote: "Not established; no release proof supplied.",
    releaseUnknown: "Unverified",
    labelOwedSeat: "Owed turn seat",
    labelOwedReason: "Reason",
    labelNextAction: "Next action",
    labelCurrentWorker: "Current worker",
    valueNotSupplied: "Not supplied",
    activityDetailsTitle: "Session activity and context",
    activityNotSupplied: "No activity panel was supplied.",
    navOpenEvidence: "Open evidence",
    navOpenJournal: "Open journal",
    evidenceTitle: "Evidence",
    evidenceEmpty: "No evidence references were supplied in this observation; this does not establish that none exist.",
    filterEmpty: "No observed references match this filter.",
    filterAll: "All",
    filterCurrent: "Current",
    filterPartial: "Partial",
    filterHistorical: "Historical",
    filterUnavailable: "Unavailable",
    observedCount: (n) => `${n} observed references`,
    seeAll: (n) => `See all ${n}`,
    showFewer: "Show fewer",
    ladderTitle: "Status ladder",
    ladderRead: "Read",
    ladderDispatch: "Dispatch",
    ladderReview: "Review",
    ladderAcceptance: "Acceptance",
    ladderRelease: "Release",
    selectedSourceTitle: "Selected source detail",
    selectPrompt: "Select an evidence row to inspect its exact source tuple.",
    truthBoundary:
      "Selection here is navigation only. Acceptance and release keep their original owners; no implementation or release documents are implied.",
    labelFacet: "Facet",
    labelOwner: "Owner",
    labelRef: "Ref",
    labelField: "Field",
    labelRevision: "Source revision",
    labelSourceTime: "Source time",
    labelObservedAt: "Observed at",
    labelFreshness: "Freshness",
    journalTitle: "Project journal",
    journalUnavailable: "Journal unavailable — no event stream was supplied.",
    currentContextTitle: "Supplied context",
    continuityTitle: "Continuity sources",
    continuityEmpty: "No AGENT_OS evidence references were supplied.",
    sourceTuples: "Source tuples",
    activityTitle: "Activity",
  },
  "zh-CN": {
    sourceSelectionUnavailable: "来源选择与当前文档不匹配，不显示任何内容。",
    titleReturned: "已返回的工作",
    titleWork: "工作详情",
    readCaveatLead: "源读取状态：",
    readCaveatTail: " — 数值可能过期或不完整。",
    sectionResults: "保留结果",
    resultsNotSupplied: "未提供结果面板。",
    sectionReview: "评审",
    sectionAcceptance: "验收",
    sectionRelease: "发布",
    sectionReturn: "返回",
    sectionNextOwner: "下一责任方",
    returnReceived: "已收到返回证据。",
    returnUnknown: "尚未建立返回事实。",
    labelDispatchState: "派发状态",
    labelReviewRequired: "需要评审",
    labelVerdict: "评审结论",
    labelAcceptanceState: "验收状态",
    labelAcceptanceRuling: "验收裁决",
    labelReleaseState: "发布状态",
    rulingUnavailable: "不可用",
    releaseNote: "未建立；未提供发布证明。",
    releaseUnknown: "未验证",
    labelOwedSeat: "待轮席位",
    labelOwedReason: "原因",
    labelNextAction: "下一步动作",
    labelCurrentWorker: "当前执行者",
    valueNotSupplied: "未提供",
    activityDetailsTitle: "会话活动与上下文",
    activityNotSupplied: "未提供活动面板。",
    navOpenEvidence: "查看证据",
    navOpenJournal: "查看日志",
    evidenceTitle: "证据",
    evidenceEmpty: "本次观察未提供证据引用；这不代表不存在证据。",
    filterEmpty: "没有已观察引用符合此筛选条件。",
    filterAll: "全部",
    filterCurrent: "当前",
    filterPartial: "部分",
    filterHistorical: "历史",
    filterUnavailable: "不可用",
    observedCount: (n) => `已观察引用 ${n} 条`,
    seeAll: (n) => `查看全部 ${n} 条`,
    showFewer: "收起",
    ladderTitle: "状态阶梯",
    ladderRead: "读取",
    ladderDispatch: "派发",
    ladderReview: "评审",
    ladderAcceptance: "验收",
    ladderRelease: "发布",
    selectedSourceTitle: "所选来源详情",
    selectPrompt: "选择一条证据行，以查看其确切来源元组。",
    truthBoundary:
      "此处的选择仅用于导航。验收与发布仍归原有责任方；不暗示任何实现或发布文档。",
    labelFacet: "维度",
    labelOwner: "所有者",
    labelRef: "引用",
    labelField: "字段",
    labelRevision: "来源修订",
    labelSourceTime: "来源时间",
    labelObservedAt: "观察时间",
    labelFreshness: "新鲜度",
    journalTitle: "项目日志",
    journalUnavailable: "日志不可用 — 未提供事件流。",
    currentContextTitle: "已提供的上下文",
    continuityTitle: "延续来源",
    continuityEmpty: "未提供 AGENT_OS 证据引用。",
    sourceTuples: "来源元组",
    activityTitle: "活动",
  },
};

interface CommonProps {
  document: MissionDocument;
  selection: MissionSelection;
  locale: Locale;
  generation: string | number;
}

function matchesSelection(
  doc: MissionDocument,
  selection: MissionSelection,
): boolean {
  return (
    doc.program.work_ref === selection.workRef &&
    doc.mission.root_job_id === selection.rootJobId &&
    !doc.mission.root_job_ambiguous &&
    doc.mission.runtime_root_state === "RESOLVED"
  );
}

function GateMessage({ copy, title }: { copy: CopyTable; title: string }) {
  return (
    <section className="mm-work-journey card">
      <h2 className="section-title">{title}</h2>
      <p className="muted empty">{copy.sourceSelectionUnavailable}</p>
    </section>
  );
}

function workHeading(doc: MissionDocument, copy: CopyTable): string {
  return doc.transport.dispatch_state === "RETURNED"
    ? copy.titleReturned
    : copy.titleWork;
}

function TupleRows(props: { rows: Array<[string, string]> }) {
  return (
    <dl className="mm-work-journey__kv">
      {props.rows.map(([label, value]) => (
        <div key={label} className="mm-work-journey__kvpair">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function FactStrip({doc, copy}: {doc: MissionDocument; copy: CopyTable}) {
  const facts = [
    [copy.sectionReturn, doc.transport.dispatch_state === "RETURNED" ? copy.returnReceived : copy.returnUnknown],
    [copy.sectionReview, doc.review.verdict],
    [copy.sectionAcceptance, doc.acceptance.state],
    [copy.sectionRelease, copy.releaseUnknown],
  ];
  return <section className="card mm-work-journey__facts" aria-label={copy.ladderTitle}>
    {facts.map(([name, value]) => <div key={name}>
      <h3>{name}</h3><p>{value}</p>
    </div>)}
  </section>;
}

export interface ProjectWorkDetailProps extends CommonProps {
  resultPanel?: ReactNode;
  activityPanel?: ReactNode;
  actionPanel?: ReactNode;
  onOpenEvidence?: () => void;
  onOpenJournal?: () => void;
}

export function ProjectWorkDetail(props: ProjectWorkDetailProps) {
  const copy = COPY[props.locale];
  if (!matchesSelection(props.document, props.selection)) {
    return (
      <GateMessage
        copy={copy}
        title={copy.titleWork}
      />
    );
  }
  const doc = props.document;
  const owed = doc.principal.owed_turn;
  const readCaveat =
    doc.read_state.state !== "CURRENT"
      ? `${copy.readCaveatLead}${doc.read_state.state}${copy.readCaveatTail}`
      : null;
  const answer = `${copy.labelDispatchState}: ${doc.transport.dispatch_state} · ${copy.labelVerdict}: ${doc.review.verdict} · ${copy.labelAcceptanceState}: ${doc.acceptance.state}`;
  return (
    <article className="mm-work-journey">
      <header className="mm-work-journey__head">
        <h2 className="section-title mm-work-journey__title">
          {workHeading(doc, copy)}
        </h2>
        <p className="mm-work-journey__answer">{answer}</p>
        {readCaveat !== null && (
          <p className="muted mm-work-journey__caveat">{readCaveat}</p>
        )}
      </header>
      <FactStrip doc={doc} copy={copy} />
      <div className="mm-work-journey__columns">
        <div className="mm-work-journey__main">
          <section className="mm-work-journey__block">
            <h3 className="mm-work-journey__blocktitle">
              {copy.sectionResults}
            </h3>
            {props.resultPanel === undefined ? (
              <p className="muted empty">{copy.resultsNotSupplied}</p>
            ) : (
              props.resultPanel
            )}
          </section>
        </div>
        <aside className="mm-work-journey__side">
          <section className="card mm-work-journey__card">
            <h3 className="section-title">{copy.sectionNextOwner}</h3>
            <TupleRows
              rows={[
                [
                  copy.labelOwedSeat,
                  owed === null || owed.seat === null
                    ? copy.valueNotSupplied
                    : owed.seat,
                ],
                [
                  copy.labelOwedReason,
                  owed === null || owed.reason === null
                    ? copy.valueNotSupplied
                    : owed.reason,
                ],
                [
                  copy.labelNextAction,
                  doc.program.next_action === null
                    ? copy.valueNotSupplied
                    : doc.program.next_action,
                ],
              ]}
            />
          </section>
        </aside>
      </div>
      <details className="mm-work-journey__details">
        <summary>{copy.sourceTuples}</summary>
        <TupleRows rows={[
          [copy.labelDispatchState, doc.transport.dispatch_state],
          [copy.labelReviewRequired, doc.review.required === null ? copy.valueNotSupplied : String(doc.review.required)],
          [copy.labelVerdict, doc.review.verdict],
          [copy.labelAcceptanceState, doc.acceptance.state],
          [copy.labelAcceptanceRuling, doc.acceptance.ruling ?? copy.rulingUnavailable],
          [copy.labelReleaseState, copy.releaseNote],
        ]} />
      </details>
      {props.actionPanel !== undefined && (
        <section className="mm-work-journey__actions">
          {props.actionPanel}
        </section>
      )}
      <div className="mm-work-journey__nav">
        {props.onOpenEvidence !== undefined && (
          <button
            type="button"
            className="mm-work-journey__btn"
            onClick={props.onOpenEvidence}
          >
            {copy.navOpenEvidence}
          </button>
        )}
        {props.onOpenJournal !== undefined && (
          <button
            type="button"
            className="mm-work-journey__btn"
            onClick={props.onOpenJournal}
          >
            {copy.navOpenJournal}
          </button>
        )}
      </div>
      <details className="mm-work-journey__details">
        <summary>{copy.activityDetailsTitle}</summary>
        {props.activityPanel === undefined ? (
          <p className="muted empty">{copy.activityNotSupplied}</p>
        ) : (
          props.activityPanel
        )}
      </details>
    </article>
  );
}

export interface ProjectEvidenceProps extends CommonProps {
  resultPanel?: ReactNode;
}

type EvidenceFilterKey =
  | "all"
  | "CURRENT"
  | "PARTIAL"
  | "HISTORICAL"
  | "UNAVAILABLE";

const FILTER_ORDER: EvidenceFilterKey[] = [
  "all",
  "CURRENT",
  "PARTIAL",
  "HISTORICAL",
  "UNAVAILABLE",
];

function filterLabel(key: EvidenceFilterKey, copy: CopyTable): string {
  if (key === "all") return copy.filterAll;
  if (key === "CURRENT") return copy.filterCurrent;
  if (key === "PARTIAL") return copy.filterPartial;
  if (key === "HISTORICAL") return copy.filterHistorical;
  return copy.filterUnavailable;
}

function EvidenceBody(props: {
  doc: MissionDocument;
  selection: MissionSelection;
  generation: string | number;
  locale: Locale;
  resultPanel?: ReactNode;
}) {
  const copy = COPY[props.locale];
  const rows = allEvidence(props.doc);
  const [prevInputs, setPrevInputs] = useState({
    doc: props.doc,
    selection: props.selection,
    generation: props.generation,
  });
  const [filter, setFilter] = useState<EvidenceFilterKey>("all");
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [showAll, setShowAll] = useState(false);
  if (
    prevInputs.doc !== props.doc ||
    prevInputs.selection !== props.selection ||
    prevInputs.generation !== props.generation
  ) {
    setPrevInputs({
      doc: props.doc,
      selection: props.selection,
      generation: props.generation,
    });
    setFilter("all");
    setSelectedIndex(null);
    setShowAll(false);
  }
  const countBy = (key: EvidenceFilterKey): number =>
    key === "all"
      ? rows.length
      : rows.filter((row) => row.evidence.freshness_state === key).length;
  const filtered =
    filter === "all"
      ? rows
      : rows.filter((row) => row.evidence.freshness_state === filter);
  const visible = showAll ? filtered : filtered.slice(0, 8);
  const selected =
    selectedIndex !== null && selectedIndex < filtered.length
      ? filtered[selectedIndex]
      : null;
  return (
    <article className="mm-work-journey">
      <header className="mm-work-journey__head">
        <h2 className="section-title mm-work-journey__title">
          {copy.evidenceTitle}
        </h2>
        <p className="muted mm-work-journey__note">{copy.truthBoundary}</p>
      </header>
      <p className="muted">{copy.ladderRead}: {props.doc.read_state.state}</p>
      <div className="mm-work-journey__evcols">
        <div className="mm-work-journey__main">
          <div
            className="segmented mm-work-journey__seg"
            role="group"
            aria-label={copy.evidenceTitle}
          >
            {FILTER_ORDER.map((key) => (
              <button
                key={key}
                type="button"
                className="mm-work-journey__segbtn"
                aria-pressed={filter === key}
                onClick={() => {
                  setFilter(key);
                  setSelectedIndex(null);
                }}
              >
                {filterLabel(key, copy)} ({countBy(key)})
              </button>
            ))}
          </div>
          <p className="muted mm-work-journey__note">
            {copy.observedCount(filtered.length)}
          </p>
          {filtered.length === 0 && <p className="empty">{rows.length === 0 ? copy.evidenceEmpty : copy.filterEmpty}</p>}
          <ul className="mm-work-journey__list">
            {visible.map((row, index) => (
              <li
                key={`${row.facet}:${row.evidence.owner}:${row.evidence.field}:${index}`}
              >
                <button
                  type="button"
                  className="mm-work-journey__row"
                  aria-pressed={selectedIndex === index}
                  onClick={() => setSelectedIndex(index)}
                >
                  <span className="badge">{row.facet}</span>
                  <span className="mm-work-journey__rowmain">
                    {row.evidence.owner} · {row.evidence.field}
                  </span>
                  <span className="badge">{row.evidence.freshness_state}</span>
                </button>
              </li>
            ))}
          </ul>
          {filtered.length > 8 && (
            <button
              type="button"
              className="mm-work-journey__btn"
              onClick={() => setShowAll(!showAll)}
            >
              {showAll ? copy.showFewer : copy.seeAll(filtered.length)}
            </button>
          )}
        </div>
        <aside className="mm-work-journey__side">
          <section className="card mm-work-journey__card" aria-live="polite">
            <h3 className="section-title">{copy.selectedSourceTitle}</h3>
            {selected === null ? (
              <p className="muted empty">{copy.selectPrompt}</p>
            ) : (
              <TupleRows
                rows={[
                  [copy.labelFacet, selected.facet],
                  [copy.labelOwner, selected.evidence.owner],
                  [copy.labelRef, selected.evidence.ref],
                  [copy.labelField, selected.evidence.field],
                  [
                    copy.labelRevision,
                    selected.evidence.source_revision === null
                      ? copy.rulingUnavailable
                      : selected.evidence.source_revision,
                  ],
                  [
                    copy.labelSourceTime,
                    selected.evidence.source_time === null
                      ? copy.rulingUnavailable
                      : selected.evidence.source_time,
                  ],
                  [
                    copy.labelObservedAt,
                    selected.evidence.observed_at === null
                      ? copy.rulingUnavailable
                      : selected.evidence.observed_at,
                  ],
                  [copy.labelFreshness, selected.evidence.freshness_state],
                ]}
              />
            )}
          </section>
          <FactStrip doc={props.doc} copy={copy} />
        </aside>
      </div>
      {props.resultPanel !== undefined && (
        <section className="mm-work-journey__block">
          <h3 className="mm-work-journey__blocktitle">
            {copy.sectionResults}
          </h3>
          {props.resultPanel}
        </section>
      )}
    </article>
  );
}

export function ProjectEvidence(props: ProjectEvidenceProps) {
  const copy = COPY[props.locale];
  if (!matchesSelection(props.document, props.selection)) {
    return <GateMessage copy={copy} title={copy.evidenceTitle} />;
  }
  return (
    <EvidenceBody
      doc={props.document}
      selection={props.selection}
      generation={props.generation}
      locale={props.locale}
      resultPanel={props.resultPanel}
    />
  );
}

export interface ProjectJournalProps extends CommonProps {
  activityPanel?: ReactNode;
}

export function ProjectJournal(props: ProjectJournalProps) {
  const copy = COPY[props.locale];
  const [expanded, setExpanded] = useState(false);
  const [epoch, setEpoch] = useState({document: props.document, generation: props.generation, work: props.selection.workRef, root: props.selection.rootJobId});
  if (epoch.document !== props.document || epoch.generation !== props.generation || epoch.work !== props.selection.workRef || epoch.root !== props.selection.rootJobId) {
    setEpoch({document: props.document, generation: props.generation, work: props.selection.workRef, root: props.selection.rootJobId});
    setExpanded(false);
  }
  if (!matchesSelection(props.document, props.selection)) {
    return <GateMessage copy={copy} title={copy.journalTitle} />;
  }
  const doc = props.document;
  const continuity = allEvidence(doc).filter(
    (row) => row.evidence.owner === "AGENT_OS",
  );
  const owed = doc.principal.owed_turn;
  const currentWorker = doc.principal.current_worker;
  return (
    <article className="mm-work-journey">
      <header className="mm-work-journey__head">
        <h2 className="section-title mm-work-journey__title">
          {copy.journalTitle}
        </h2>
        <p className="muted empty">{copy.journalUnavailable}</p>
      </header>
      <div className="mm-work-journey__columns">
        <section className="card mm-work-journey__card">
          <h3 className="section-title">{copy.currentContextTitle}</h3>
          <p className="muted">{copy.readCaveatLead}{doc.read_state.state}{doc.read_state.state !== "CURRENT" ? copy.readCaveatTail : ""}</p>
          <TupleRows
            rows={[
              [
                copy.labelOwedSeat,
                owed === null || owed.seat === null
                  ? copy.valueNotSupplied
                  : owed.seat,
              ],
              [
                copy.labelOwedReason,
                owed === null || owed.reason === null
                  ? copy.valueNotSupplied
                  : owed.reason,
              ],
              [
                copy.labelCurrentWorker,
                currentWorker === null || currentWorker.worker_id === null
                  ? copy.valueNotSupplied
                  : currentWorker.worker_id,
              ],
              [
                copy.labelNextAction,
                doc.program.next_action === null
                  ? copy.valueNotSupplied
                  : doc.program.next_action,
              ],
            ]}
          />
        </section>
        <section className="card mm-work-journey__card">
          <h3 className="section-title">{copy.continuityTitle}</h3>
          {continuity.length === 0 ? (
            <p className="muted empty">{copy.continuityEmpty}</p>
          ) : (
            <ul className="mm-work-journey__list">
              {(expanded ? continuity : continuity.slice(0, 8)).map((row, index) => (
                <li
                  key={`${row.evidence.owner}:${row.evidence.field}:${index}`}
                  className="mm-work-journey__continuity"
                >
                  <span className="badge">{row.facet}</span>
                  <span className="mm-work-journey__rowmain">
                    {row.evidence.owner} · {row.evidence.field}
                  </span>
                  <details className="mm-work-journey__tuple">
                    <summary>{copy.sourceTuples}</summary>
                    <TupleRows
                      rows={[
                        [copy.labelOwner, row.evidence.owner],
                        [copy.labelRef, row.evidence.ref],
                        [copy.labelField, row.evidence.field],
                        [
                          copy.labelRevision,
                          row.evidence.source_revision === null
                            ? copy.rulingUnavailable
                            : row.evidence.source_revision,
                        ],
                        [
                          copy.labelSourceTime,
                          row.evidence.source_time === null
                            ? copy.rulingUnavailable
                            : row.evidence.source_time,
                        ],
                        [
                          copy.labelObservedAt,
                          row.evidence.observed_at === null
                            ? copy.rulingUnavailable
                            : row.evidence.observed_at,
                        ],
                        [copy.labelFreshness, row.evidence.freshness_state],
                      ]}
                    />
                  </details>
                </li>
              ))}
            </ul>
          )}
          {continuity.length > 8 && <button type="button" onClick={() => setExpanded(!expanded)}>{expanded ? copy.showFewer : copy.seeAll(continuity.length)}</button>}
        </section>
      </div>
      <details className="mm-work-journey__details">
        <summary>{copy.activityTitle}</summary>
        {props.activityPanel === undefined ? (
          <p className="muted empty">{copy.activityNotSupplied}</p>
        ) : (
          props.activityPanel
        )}
      </details>
    </article>
  );
}
