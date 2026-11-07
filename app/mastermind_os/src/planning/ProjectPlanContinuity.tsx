import { useState } from "react";
import type { ChangeEvent } from "react";
import type { ProjectPlanContinuityRead } from "./project-plan-continuity";
import "./project-plan-continuity.css";

export type ProjectPlanContinuityLocale = "en" | "zh-CN";

interface ProjectPlanContinuityProps {
  data: ProjectPlanContinuityRead;
  locale?: ProjectPlanContinuityLocale;
}

/** Read-only presenter for the already-decoded planning continuity projection:
 * what the captured sources record as the current plan baseline, and how
 * recorded proposals differ from it. Pure props in, markup out: no IO, no
 * fetches, no timers, no adoption/synthesis/launch controls and no retained
 * body copies; every rendered string is derived from the current `data` on
 * each render. Captured bodies, ids, rationales, reasons and source refs stay
 * authored data, never reserialized, trimmed or dangerously injected. */
export function ProjectPlanContinuity({ data, locale = "en" }: ProjectPlanContinuityProps) {
  const zh = locale === "zh-CN";
  const t = zh ? ZH_COPY : EN_COPY;
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);

  const adoption = data.adoption;
  const adoptionAvailable = adoption.state === "AVAILABLE";
  const declared = !adoptionAvailable && "declared_decision" in adoption
    ? adoption.declared_decision ?? null
    : null;
  const proposals = data.proposals;
  const items = proposals.state === "AVAILABLE" ? proposals.items : [];
  const recordedItems = items.filter(isRecordedProposal);
  // Selection is only ever an index hint: the lookup always re-runs against
  // the current props, so stale ids from other data fall back safely.
  const selectedEntry =
    items.find((item) => isRecordedProposal(item) && item.proposal_id === selectedProposalId) ??
    recordedItems[0] ??
    null;

  const statusText = adoptionAvailable
    ? adoption.adoption.display_revision
      ? t.statusAvailableRevision(adoption.adoption.display_revision)
      : t.statusAvailableNeutral
    : t.statusUnavailable;
  const baselineTitle = adoptionAvailable && adoption.adoption.display_revision
    ? adoption.adoption.display_revision
    : t.baselineTitle;

  const handleProposalChange = (event: ChangeEvent<HTMLSelectElement>) => {
    setSelectedProposalId(event.currentTarget.value);
  };

  return (
    <section className="mm-plan-continuity">
      <h3 className="mm-plan-continuity__heading">{t.heading}</h3>
      <p className="mm-plan-continuity__lede">{t.lede}</p>
      <p className="mm-plan-continuity__status">{statusText}</p>

      <div className="mm-plan-continuity__record">
        <h4 className="mm-plan-continuity__section-title">{baselineTitle}</h4>
        {adoptionAvailable ? (
          <>
            <dl className="mm-plan-continuity__facts">
              <div><dt>{t.decision}</dt><dd>{adoption.decision_ref}</dd></div>
              <div><dt>{t.decidedBy}</dt><dd>{adoption.decided_by}</dd></div>
              <div><dt>{t.decidedOn}</dt><dd>{adoption.decided_at}</dd></div>
            </dl>
            <details className="mm-plan-continuity__disclose">
              <summary>{t.viewCurrentPlan}</summary>
              <div className="mm-plan-continuity__disclosure-body">
                <pre className="mm-plan-continuity__pre">{adoption.content}</pre>
              </div>
            </details>
            <details className="mm-plan-continuity__disclose">
              <summary>{t.planningSources}</summary>
              <div className="mm-plan-continuity__disclosure-body">
                <SourceRefView label={t.decisionRecord} sourceRef={adoption.decision_source} t={t} />
                <SourceRefView label={t.adoptedPlan} sourceRef={adoption.adoption.adopted_source} t={t} />
                {adoption.adoption.proposal_source ? (
                  <SourceRefView label={t.proposalSource}
                    sourceRef={adoption.adoption.proposal_source} t={t} />
                ) : null}
                {adoption.adoption.predecessor ? (
                  <p className="mm-plan-continuity__meta-line">
                    {t.predecessor}: {adoption.adoption.predecessor}
                  </p>
                ) : null}
                {adoption.adoption.display_revision ? (
                  <p className="mm-plan-continuity__meta-line">
                    {t.displayRevision}: {adoption.adoption.display_revision}
                  </p>
                ) : null}
              </div>
            </details>
          </>
        ) : (
          <>
            <p className="mm-plan-continuity__explanation">
              {reasonText("adoption", adoption.reason, zh)}
            </p>
            {declared ? (
              <div className="mm-plan-continuity__declared">
                <h5 className="mm-plan-continuity__subsection-title">{t.declaredTitle}</h5>
                <p className="mm-plan-continuity__note">{t.declaredNote}</p>
                <dl className="mm-plan-continuity__facts">
                  <div><dt>{t.declaredDecision}</dt><dd>{declared.decision_ref}</dd></div>
                  <div><dt>{t.declaredBy}</dt><dd>{declared.decided_by}</dd></div>
                  <div><dt>{t.declaredOn}</dt><dd>{declared.decided_at}</dd></div>
                </dl>
                <details className="mm-plan-continuity__disclose">
                  <summary>{t.planningSources}</summary>
                  <div className="mm-plan-continuity__disclosure-body">
                    <SourceRefView label={t.declaredDecisionSource}
                      sourceRef={declared.decision_source} t={t} />
                    <SourceRefView label={t.declaredAdoptedSource}
                      sourceRef={declared.adoption.adopted_source} t={t} />
                    {declared.adoption.proposal_source ? (
                      <SourceRefView label={t.proposalSource}
                        sourceRef={declared.adoption.proposal_source} t={t} />
                    ) : null}
                    {declared.adoption.predecessor ? (
                      <p className="mm-plan-continuity__meta-line">
                        {t.predecessor}: {declared.adoption.predecessor}
                      </p>
                    ) : null}
                  </div>
                </details>
              </div>
            ) : null}
            <details className="mm-plan-continuity__source">
              <summary>{t.sourceDetails}</summary>
              <div className="mm-plan-continuity__disclosure-body">
                <p className="mm-plan-continuity__meta-line"><code>{adoption.reason}</code></p>
              </div>
            </details>
          </>
        )}
      </div>

      <div className="mm-plan-continuity__record">
        <h4 className="mm-plan-continuity__section-title">{t.proposalsTitle}</h4>
        {proposals.state === "AVAILABLE" ? (
          items.length === 0 ? (
            <>
              <p className="mm-plan-continuity__explanation">{t.emptyProposals}</p>
              <p className="mm-plan-continuity__note">{t.coverageCaveat}</p>
            </>
          ) : (
            <>
              {selectedEntry !== null && isRecordedProposal(selectedEntry) ? (
                <>
                  <label className="mm-plan-continuity__select-label">
                    <span>{t.selectLabel}</span>
                    <select
                      className="mm-plan-continuity__select"
                      value={selectedEntry.proposal_id}
                      onChange={handleProposalChange}
                    >
                      {recordedItems.map((item) => (
                        <option key={item.proposal_id} value={item.proposal_id}>
                          {item.proposal_id}
                        </option>
                      ))}
                    </select>
                  </label>
                  <RecordedProposalView
                    item={selectedEntry}
                    adoptionAvailable={adoptionAvailable}
                    zh={zh}
                    t={t}
                  />
                </>
              ) : null}
              <InvalidProposalList items={items} t={t} />
              <p className="mm-plan-continuity__note">{t.coverageCaveat}</p>
            </>
          )
        ) : (
          <>
            <p className="mm-plan-continuity__explanation">
              {reasonText("proposals", proposals.reason, zh)}
            </p>
            <details className="mm-plan-continuity__source">
              <summary>{t.sourceDetails}</summary>
              <div className="mm-plan-continuity__disclosure-body">
                <p className="mm-plan-continuity__meta-line"><code>{proposals.reason}</code></p>
              </div>
            </details>
          </>
        )}
      </div>

      <p className="mm-plan-continuity__footnote">{t.footnote}</p>
    </section>
  );
}

type ContinuityItems =
  Extract<ProjectPlanContinuityRead["proposals"], { state: "AVAILABLE" }>["items"];
type RecordedProposal = Extract<ContinuityItems[number], { state: "RECORDED_PROPOSAL" }>;
type InvalidProposal = Extract<ContinuityItems[number], { state: "UNAVAILABLE" }>;

function isRecordedProposal(item: ContinuityItems[number]): item is RecordedProposal {
  return item.state === "RECORDED_PROPOSAL";
}

/** One recorded proposal: identity, authored rationale, truthful adoption
 * relation, the captured comparison (or its closed reason) and inert sources. */
function RecordedProposalView({ item, adoptionAvailable, zh, t }: {
  item: RecordedProposal;
  adoptionAvailable: boolean;
  zh: boolean;
  t: Copy;
}) {
  const referenced =
    item.adoption_relation === "CURRENT_DECISION_REFERENCES_PROPOSAL" && adoptionAvailable;
  const relationText = referenced ? t.statusReferenced
    : adoptionAvailable ? t.statusUnassociated : t.statusRecordedOnly;
  const comparison = item.comparison;

  return (
    <div className="mm-plan-continuity__proposal-detail">
      <dl className="mm-plan-continuity__facts">
        <div><dt>{t.proposal}</dt><dd>{item.proposal_id}</dd></div>
        <div><dt>{t.status}</dt><dd>{relationText}</dd></div>
      </dl>
      <p className="mm-plan-continuity__rationale">
        <span className="mm-plan-continuity__fact-key">{t.rationale}</span> {item.rationale}
      </p>
      {item.base_adoption ? (
        <p className="mm-plan-continuity__meta-line">{t.baseAdoption}: {item.base_adoption}</p>
      ) : null}
      <p className="mm-plan-continuity__meta-line">{t.evidence}: {item.evidence.length}</p>
      {comparison.state === "AVAILABLE" ? (
        <div className="mm-plan-continuity__comparison">
          <p className="mm-plan-continuity__explanation">{basisText(item.comparison_basis, zh)}</p>
          <p className="mm-plan-continuity__status">
            {comparison.identical ? `${t.identical} ` : ""}
            {`${t.linesAdded(comparison.added_lines)}, ${t.linesRemoved(comparison.removed_lines)}.`}
          </p>
          <details className="mm-plan-continuity__disclose">
            <summary>{t.comparePlans}</summary>
            <div className="mm-plan-continuity__disclosure-body">
              <h5 className="mm-plan-continuity__subsection-title">{t.diffTitle}</h5>
              <pre className="mm-plan-continuity__pre">{comparison.diff}</pre>
              <div className="mm-plan-continuity__bodies">
                <div className="mm-plan-continuity__body">
                  <h5 className="mm-plan-continuity__body-title">{t.baseTextTitle}</h5>
                  <pre className="mm-plan-continuity__pre">{comparison.base_text}</pre>
                </div>
                <div className="mm-plan-continuity__body">
                  <h5 className="mm-plan-continuity__body-title">{t.candidateTextTitle}</h5>
                  <pre className="mm-plan-continuity__pre">{comparison.candidate_text}</pre>
                </div>
              </div>
            </div>
          </details>
        </div>
      ) : (
        <div className="mm-plan-continuity__comparison-unavailable">
          <p className="mm-plan-continuity__explanation">{basisText(item.comparison_basis, zh)}</p>
          <p className="mm-plan-continuity__explanation">
            {reasonText("comparison", comparison.reason, zh)}
          </p>
          <details className="mm-plan-continuity__source">
            <summary>{t.sourceDetails}</summary>
            <div className="mm-plan-continuity__disclosure-body">
              <p className="mm-plan-continuity__meta-line"><code>{comparison.reason}</code></p>
            </div>
          </details>
        </div>
      )}
      <details className="mm-plan-continuity__disclose">
        <summary>{t.planningSources}</summary>
        <div className="mm-plan-continuity__disclosure-body">
      {item.evidence.length > 0 ? (
        <div className="mm-plan-continuity__evidence">
          {item.evidence.map((entry, index) => (
            <SourceRefView key={`${entry.content_sha256}:${index}`}
              label={t.evidenceRef(index + 1)} sourceRef={entry} t={t} />
          ))}
        </div>
      ) : null}
          <SourceRefView label={t.proposalSource} sourceRef={item.proposal_source} t={t} />
          <SourceRefView label={t.baseSource} sourceRef={item.base_source} t={t} />
          <p className="mm-plan-continuity__meta-line">
            {t.candidateSha}: <code>{item.candidate_sha256}</code>
          </p>
          {comparison.state === "AVAILABLE" ? (
            <SourceRefView label={t.comparisonBase} sourceRef={comparison.base_source} t={t} />
          ) : null}
        </div>
      </details>
    </div>
  );
}

/** Items the decoder could not read stay visible as notices with their exact
 * source details; they are never silently dropped and never counted as
 * readable proposals. Above eight rows the notices fold into a counted
 * disclosure so a long capture never becomes a wall of cards. */
function InvalidProposalList({ items, t }: { items: ContinuityItems; t: Copy }) {
  const invalid = items.filter((item): item is InvalidProposal => !isRecordedProposal(item));
  if (invalid.length === 0) return null;
  const notices = invalid.map((item, index) => (
    <li key={`${item.proposal_source.content_sha256}:${index}`} className="mm-plan-continuity__invalid-entry">
      <InvalidProposalView item={item} t={t} />
    </li>
  ));
  if (invalid.length > 8) {
    return (
      <details className="mm-plan-continuity__disclose">
        <summary>{t.moreItems(invalid.length)}</summary>
        <ul className="mm-plan-continuity__invalid-list">{notices}</ul>
      </details>
    );
  }
  return <ul className="mm-plan-continuity__invalid-list">{notices}</ul>;
}

function InvalidProposalView({ item, t }: { item: InvalidProposal; t: Copy }) {
  return (
    <div className="mm-plan-continuity__invalid-item">
      <p className="mm-plan-continuity__explanation">{t.invalidNotice}</p>
      <details className="mm-plan-continuity__source">
        <summary>{t.sourceDetails}</summary>
        <div className="mm-plan-continuity__disclosure-body">
          <p className="mm-plan-continuity__meta-line"><code>{item.reason}</code></p>
          <SourceRefView label={t.proposalSource} sourceRef={item.proposal_source} t={t} />
        </div>
      </details>
    </div>
  );
}

/** Exact captured source identity as inert text: repository, path, commit and
 * content SHA-256. Never a link, never resolved, never fetched. */
function SourceRefView({ label, sourceRef, t }: { label: string; sourceRef: unknown; t: Copy }) {
  const fields = sourceRefFields(sourceRef);
  if (fields === null) return null;
  return (
    <div className="mm-plan-continuity__source-group">
      <span className="mm-plan-continuity__source-name">{label}</span>
      <div className="mm-plan-continuity__source-fields">
        <span className="mm-plan-continuity__source-field">
          <span className="mm-plan-continuity__source-key">{t.repository}</span> <code>{fields.repository}</code>
        </span>
        <span className="mm-plan-continuity__source-field">
          <span className="mm-plan-continuity__source-key">{t.path}</span> <code>{fields.path}</code>
        </span>
        <span className="mm-plan-continuity__source-field">
          <span className="mm-plan-continuity__source-key">{t.commit}</span> <code>{fields.commit}</code>
        </span>
        <span className="mm-plan-continuity__source-field">
          <span className="mm-plan-continuity__source-key">{t.contentSha}</span> <code>{fields.content_sha256}</code>
        </span>
      </div>
    </div>
  );
}

function sourceRefFields(sourceRef: unknown): {
  repository: string; path: string; commit: string; content_sha256: string;
} | null {
  if (typeof sourceRef !== "object" || sourceRef === null) return null;
  const candidate = sourceRef as Record<string, unknown>;
  const repository = candidate.repository;
  const path = candidate.path;
  const commit = candidate.commit;
  const content_sha256 = candidate.content_sha256;
  if (typeof repository !== "string" || typeof path !== "string" ||
      typeof commit !== "string" || typeof content_sha256 !== "string") return null;
  return { repository, path, commit, content_sha256 };
}

const EN_COPY = {
  heading: "Plan comparison",
  lede: "What the captured planning sources record about the current plan baseline, and how recorded proposals differ from it.",
  statusAvailableRevision: (revision: string) => `The current plan baseline is available (revision ${revision}).`,
  statusAvailableNeutral: "The current plan baseline is available (recorded baseline).",
  statusUnavailable: "The current plan baseline is not available from the captured sources.",
  baselineTitle: "Recorded baseline",
  decision: "Decision",
  decidedBy: "Decided by",
  decidedOn: "Decision date",
  viewCurrentPlan: "View current plan",
  planningSources: "Planning sources",
  sourceDetails: "Source details",
  comparePlans: "Compare plans",
  selectLabel: "Recorded proposal to inspect",
  proposal: "Proposal",
  status: "Status",
  rationale: "Rationale",
  evidence: "Evidence",
  evidenceRef: (index: number) => `Evidence ${index}`,
  statusReferenced: "Referenced by the current adoption decision.",
  statusUnassociated: "Recorded proposal; not referenced by the current adoption decision.",
  statusRecordedOnly: "Recorded proposal.",
  baseAdoption: "Base decision",
  identical: "The proposal text is identical to the base text.",
  diffTitle: "Diff",
  baseTextTitle: "Base text",
  candidateTextTitle: "Proposal text",
  proposalsTitle: "Recorded proposals",
  emptyProposals: "No proposal is available from the captured planning sources.",
  coverageCaveat: "This listing covers only the planning sources captured with this record; proposals recorded elsewhere are not included.",
  declaredTitle: "Adoption recorded; plan content unavailable",
  declaredNote: "The adoption decision is recorded, but its plan content is unavailable in this read.",
  declaredDecision: "Declared decision",
  declaredBy: "Declared by",
  declaredOn: "Decision date",
  moreItems: (count: number) => `More recorded items (${count})`,
  invalidNotice: "A recorded proposal could not be read from the captured sources.",
  footnote: "Read-only view of already-captured planning records; nothing here adopts, writes, or fetches.",
  repository: "Repository",
  path: "Path",
  commit: "Commit",
  contentSha: "Content SHA-256",
  decisionRecord: "Decision record",
  adoptedPlan: "Adopted plan",
  proposalSource: "Proposal source",
  baseSource: "Base source",
  comparisonBase: "Comparison base",
  candidateSha: "Candidate content SHA-256",
  declaredDecisionSource: "Decision record (declared)",
  declaredAdoptedSource: "Adopted plan (declared)",
  predecessor: "Predecessor decision",
  displayRevision: "Displayed revision",
  linesAdded: (count: number) => `${count} ${count === 1 ? "line" : "lines"} added`,
  linesRemoved: (count: number) => `${count} ${count === 1 ? "line" : "lines"} removed`,
};

const ZH_COPY: Copy = {
  heading: "计划对比",
  lede: "已捕获的规划来源记录了怎样的当前计划基线，记录的提案与它有何差异。",
  statusAvailableRevision: (revision: string) => `当前计划基线可用（修订 ${revision}）。`,
  statusAvailableNeutral: "当前计划基线可用（记录的基线）。",
  statusUnavailable: "当前计划基线无法从已捕获的来源中读取。",
  baselineTitle: "记录的基线",
  decision: "决定",
  decidedBy: "决定人",
  decidedOn: "决定日期",
  viewCurrentPlan: "查看当前计划",
  planningSources: "规划来源",
  sourceDetails: "来源详情",
  comparePlans: "对比计划",
  selectLabel: "要查看的已记录提案",
  proposal: "提案",
  status: "状态",
  rationale: "理由",
  evidence: "证据",
  evidenceRef: (index: number) => `证据 ${index}`,
  statusReferenced: "被当前采纳决定引用。",
  statusUnassociated: "已记录的提案；未被当前采纳决定引用。",
  statusRecordedOnly: "已记录的提案。",
  baseAdoption: "基线决定",
  identical: "提案文本与基线文本相同。",
  diffTitle: "差异",
  baseTextTitle: "基线文本",
  candidateTextTitle: "提案文本",
  proposalsTitle: "记录的提案",
  emptyProposals: "已捕获的规划来源中没有可读取的提案。",
  coverageCaveat: "这份列表只覆盖随此记录一起捕获的规划来源；其他地方记录的提案不包含在内。",
  declaredTitle: "已记录采纳；计划内容不可用",
  declaredNote: "已记录采纳决定，但此次读取无法提供其计划内容。",
  declaredDecision: "声明的决定",
  declaredBy: "声明人",
  declaredOn: "决定日期",
  moreItems: (count: number) => `更多已记录条目（${count}）`,
  invalidNotice: "无法从已捕获的来源中读取某条已记录的提案。",
  footnote: "已捕获规划记录的只读视图；此处不会采纳、写入或抓取。",
  repository: "仓库",
  path: "路径",
  commit: "提交",
  contentSha: "内容 SHA-256",
  decisionRecord: "决定记录",
  adoptedPlan: "已采纳计划",
  proposalSource: "提案来源",
  baseSource: "基线来源",
  comparisonBase: "对比基线",
  candidateSha: "候选内容 SHA-256",
  declaredDecisionSource: "决定记录（声明）",
  declaredAdoptedSource: "已采纳计划（声明）",
  predecessor: "前序决定",
  displayRevision: "显示修订号",
  linesAdded: (count: number) => `新增 ${count} 行`,
  linesRemoved: (count: number) => `删除 ${count} 行`,
};

type Copy = typeof EN_COPY;

const REASON_COPY: Record<string, Record<string, [string, string]>> = {
  adoption: {
    NOT_DECLARED: [
      "No current plan adoption is declared in the captured sources.",
      "已捕获的来源中没有声明当前计划采纳。",
    ],
    SOURCE_UNAVAILABLE: [
      "The sources that would record the current plan adoption could not be read.",
      "记录当前计划采纳的来源无法读取。",
    ],
    LINEAGE_INVALID: [
      "The recorded plan lineage could not be followed to a valid current adoption.",
      "记录的计划脉络无法追溯到有效的当前采纳。",
    ],
    PROPOSAL_MISMATCH: [
      "The recorded adoption does not match the proposal it refers to.",
      "记录的采纳与其引用的提案不一致。",
    ],
    CONTENT_OVER_BUDGET: [
      "The recorded baseline content exceeds the presentation budget, so it is not shown here.",
      "记录的基线内容超出展示预算，因此不在此显示。",
    ],
  },
  proposals: {
    SOURCE_UNAVAILABLE: [
      "The sources that would list recorded proposals could not be read.",
      "列出已记录提案的来源无法读取。",
    ],
    LINEAGE_INVALID: [
      "The recorded plan lineage could not be followed, so recorded proposals are not shown.",
      "记录的计划脉络无法追溯，因此不显示已记录的提案。",
    ],
    RECORD_INVALID: [
      "The captured proposal records could not be decoded, so recorded proposals are not shown.",
      "已捕获的提案记录无法解码，因此不显示已记录的提案。",
    ],
    CONTENT_OVER_BUDGET: [
      "The captured proposal listing exceeds the presentation budget, so it is not shown here.",
      "已捕获的提案列表超出展示预算，因此不在此显示。",
    ],
  },
  comparison: {
    SOURCE_UNAVAILABLE: [
      "This comparison is not shown because a comparison source could not be read.",
      "对比来源无法读取，因此不显示此对比。",
    ],
    SOURCE_BYTES_MISMATCH: [
      "This comparison is not shown because the captured bytes did not match the recorded hashes.",
      "捕获的字节与记录的哈希不一致，因此不显示此对比。",
    ],
    INVALID_CONTENT: [
      "This comparison is not shown because captured content could not be decoded.",
      "捕获的内容无法解码，因此不显示此对比。",
    ],
    CONTENT_OVER_BUDGET: [
      "This comparison is not shown because its content exceeds the presentation budget.",
      "对比内容超出展示预算，因此不显示。",
    ],
    STALE_PREDECESSOR: [
      "This comparison is not shown because the recorded predecessor plan is stale and may no longer match this proposal.",
      "记录的前序计划已过期，可能不再匹配此提案，因此不显示此对比。",
    ],
    PROPOSAL_MISMATCH: [
      "This comparison is not shown because the recorded proposal does not match the recorded comparison base.",
      "记录的提案与记录的对比基线不一致，因此不显示此对比。",
    ],
  },
};

const REASON_FALLBACK: Record<string, [string, string]> = {
  adoption: [
    "The current plan baseline is not available from the captured sources.",
    "无法从已捕获的来源中读取当前计划基线。",
  ],
  proposals: [
    "Recorded proposals are not available from the captured sources.",
    "无法从已捕获的来源中获得已记录的提案。",
  ],
  comparison: [
    "This comparison is not available from the captured sources.",
    "无法从已捕获的来源中获得此对比。",
  ],
};

const BASIS_COPY: Record<string, [string, string]> = {
  ADOPTED_CONTENT: [
    "Compared against the adopted plan content.",
    "与已采纳的计划内容对比。",
  ],
  RECORDED_SOURCE: [
    "Compared against the recorded planning source.",
    "与已记录的规划来源对比。",
  ],
  RECORDED_PREDECESSOR: [
    "Compared against the recorded predecessor plan.",
    "与已记录的前序计划对比。",
  ],
  DECLARED_ADOPTION_SOURCE: [
    "Compared against the declared adoption source (declaration only).",
    "与声明的采纳来源对比（仅声明）。",
  ],
};

const BASIS_FALLBACK: [string, string] = [
  "Comparison basis recorded by the captured planning sources.",
  "由已捕获的规划来源记录的对比依据。",
];

function reasonText(
  kind: "adoption" | "proposals" | "comparison",
  reason: string,
  zh: boolean,
): string {
  const entry = REASON_COPY[kind][reason] ?? REASON_FALLBACK[kind];
  return zh ? entry[1] : entry[0];
}

function basisText(basis: string, zh: boolean): string {
  const entry = BASIS_COPY[basis] ?? BASIS_FALLBACK;
  return zh ? entry[1] : entry[0];
}
