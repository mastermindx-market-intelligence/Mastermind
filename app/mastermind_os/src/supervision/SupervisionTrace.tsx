import type { ReactNode } from "react";
import { normalizeSelection } from "../mission";
import type {
  EvidenceRef,
  MissionDocument,
  MissionSelection,
} from "../mission";
import "./supervision-trace.css";

/**
 * Bounded supervision, trace and recovery presentation for exactly one
 * selected mission observation (AT26/30/31/32 scope).
 *
 * This component owns no effects, fetches, storage, retries, cancellation,
 * clocks, provider selection or read state. It presents only fields carried
 * by the provided MissionDocument, never merges owners, never infers
 * liveness or acceptance, and never offers a command. The optional read
 * button forwards one activation to the host-provided callback; the host
 * owns every read and the App owns the page h1.
 */
export interface SupervisionTraceProps {
  /** Observation to present. Shown only when it exactly matches `selection`. */
  document: MissionDocument | null;
  /** Selected scope. A document that does not match it is fully withheld. */
  selection: MissionSelection | null;
  locale?: "en" | "zh-CN";
  /** Host-owned read. Invoked exactly once per button activation, never on mount. */
  onReadCurrent?: () => void;
}

type Translate = (en: string, zh: string) => string;

/** Number of source evidence items shown before the counted expansion. */
const EVIDENCE_BOUND = 8;

/**
 * Refuse any observation that is not exactly the selected mission: the work
 * reference, the root id, a RESOLVED singleton candidate and a non-ambiguous
 * root must all match. Anything else renders unavailable without owner data.
 */
function scopeMatches(
  document: MissionDocument,
  selection: MissionSelection,
): boolean {
  return (
    document.program.work_ref === selection.workRef &&
    document.mission.root_job_id === selection.rootJobId &&
    document.mission.runtime_root_state === "RESOLVED" &&
    document.mission.root_job_ambiguous === false &&
    document.mission.root_job_candidates.length === 1 &&
    document.mission.root_job_candidates[0] === selection.rootJobId
  );
}

/** Raw machine codes stay in details, displayed lower-cased with spaces. */
function machineCode(value: string): string {
  return value.toLowerCase().replace(/_/g, " ");
}

function Code({ value }: { value: string }) {
  return <code className="mm-supervision-trace__code">{machineCode(value)}</code>;
}

function UnknownValue({ chinese }: { chinese: boolean }) {
  return (
    <span className="mm-supervision-trace__unknown">
      {chinese ? "未知" : "Unknown"}
    </span>
  );
}

function NotReported({ chinese }: { chinese: boolean }) {
  return (
    <span className="mm-supervision-trace__unknown">
      {chinese ? "未报告" : "Not reported"}
    </span>
  );
}

/** Boolean owner facts keep reported-yes, reported-no and unreported separate. */
function observedFlag(value: boolean | null, chinese: boolean): ReactNode {
  if (value === true) return chinese ? "已报告：是" : "Reported: yes";
  if (value === false) return chinese ? "已报告：否" : "Reported: no";
  return <NotReported chinese={chinese} />;
}

/** Armed flags are separate observations, never readiness claims. */
function armedFlag(value: boolean | null, chinese: boolean): ReactNode {
  if (value === true) return chinese ? "已报告为已武装" : "Reported armed";
  if (value === false) return chinese ? "已报告为未武装" : "Reported not armed";
  return <NotReported chinese={chinese} />;
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mm-supervision-trace__fact">
      <span className="mm-supervision-trace__fact-label">{label}</span>
      <span className="mm-supervision-trace__fact-value">{children}</span>
    </div>
  );
}

interface HeldSource {
  en: string;
  zh: string;
}

/**
 * Every owner that independently reports an unknown effect. The headline is
 * derived only from these source facts, so completed or accepted fields
 * elsewhere never clear it.
 */
function heldSources(document: MissionDocument): HeldSource[] {
  const sources: HeldSource[] = [];
  if (document.transport.dispatch_state === "EFFECT_UNKNOWN") {
    sources.push({ en: "Transport dispatch state", zh: "传输分发状态" });
  }
  if (document.principal.current_worker?.effect_state === "effect_unknown") {
    sources.push({
      en: "Current worker effect state",
      zh: "当前工作代理效果状态",
    });
  }
  if (document.principal.current_sol_target?.effect_state === "effect_unknown") {
    sources.push({
      en: "Current Sol target effect state",
      zh: "当前 Sol 目标效果状态",
    });
  }
  if (document.transport.w3c?.state === "EFFECT_UNKNOWN") {
    sources.push({ en: "W3C transport state", zh: "W3C 传输状态" });
  }
  return sources;
}

function HeldBanner({
  document,
  chinese,
  t,
}: {
  document: MissionDocument;
  chinese: boolean;
  t: Translate;
}) {
  return (
    <div className="mm-supervision-trace__held" role="note">
      <strong>
        {t("Effect unknown — original operation held", "效果未知 — 原始操作保持未决")}
      </strong>
      <p>
        {t(
          "The sources below report an unknown effect for the original operation. Reading this view does not clear that unknown, and no new command is offered or inferred.",
          "以下来源报告原始操作的效果未知。读取本视图不会消除该未知状态；本视图不提供、也不推断任何新命令。",
        )}
      </p>
      <ul>
        {heldSources(document).map((source) => (
          <li key={source.en}>{t(source.en, source.zh)}</li>
        ))}
      </ul>
    </div>
  );
}

function OrchestrationTraceBlock({
  document,
  chinese,
  t,
}: {
  document: MissionDocument;
  chinese: boolean;
  t: Translate;
}) {
  const carrier = document.transport.carrier;
  const worker = document.principal.current_worker;
  const solTarget = document.principal.current_sol_target;
  const w3c = document.transport.w3c;
  const receipt = w3c === null ? null : w3c.source_receipt;
  return (
    <details className="mm-supervision-trace__block">
      <summary>
        <h3 className="mm-supervision-trace__block-title">
          {t("Orchestration trace", "编排追踪")}
        </h3>
      </summary>
      <p className="mm-supervision-trace__block-note">
        {t(
          "Observed current facts from each owner, listed separately. This is not a chronology: unreported facts stay unreported.",
          "来自各所有者的当前观测事实，分别列出。这不是时间线：未报告的事实保持未报告。",
        )}
      </p>
      <div className="mm-supervision-trace__facts">
        <Fact label={t("Dispatch state", "分发状态")}>
          <Code value={document.transport.dispatch_state} />
        </Fact>
        <Fact label={t("Dispatch reason", "分发原因")}>
          {document.transport.reason ?? <UnknownValue chinese={chinese} />}
        </Fact>
        <Fact label={t("Transport marked historical", "传输标记为历史")}>
          {document.transport.historical ? t("Yes", "是") : t("No", "否")}
        </Fact>
        <Fact label={t("Watch proven", "观察已证明")}>
          {observedFlag(document.transport.watch_proven, chinese)}
        </Fact>
        {carrier === null ? (
          <Fact label={t("Carrier", "载体")}>
            <NotReported chinese={chinese} />
          </Fact>
        ) : (
          <>
            <Fact label={t("Carrier state", "载体状态")}>
              {carrier.state === null ? (
                <UnknownValue chinese={chinese} />
              ) : (
                <Code value={carrier.state} />
              )}
            </Fact>
            <Fact label={t("Carrier reason", "载体原因")}>
              {carrier.reason ?? <UnknownValue chinese={chinese} />}
            </Fact>
            <Fact label={t("Carrier marked historical", "载体标记为历史")}>
              {carrier.historical === null ? (
                <NotReported chinese={chinese} />
              ) : carrier.historical ? (
                t("Yes", "是")
              ) : (
                t("No", "否")
              )}
            </Fact>
          </>
        )}
        {worker === null ? (
          <Fact label={t("Current worker", "当前工作代理")}>
            <NotReported chinese={chinese} />
          </Fact>
        ) : (
          <>
            <Fact label={t("Current worker id", "当前工作代理 ID")}>
              {worker.worker_id ?? <UnknownValue chinese={chinese} />}
            </Fact>
            <Fact label={t("Current attempt id", "当前尝试 ID")}>
              {worker.attempt_id ?? <UnknownValue chinese={chinese} />}
            </Fact>
            <Fact label={t("Current worker status", "当前工作代理状态")}>
              {worker.status === null ? (
                <UnknownValue chinese={chinese} />
              ) : (
                <Code value={worker.status} />
              )}
            </Fact>
            <Fact label={t("Current worker effect state", "当前工作代理效果状态")}>
              {worker.effect_state === null ? (
                <UnknownValue chinese={chinese} />
              ) : (
                <Code value={worker.effect_state} />
              )}
            </Fact>
            <Fact label={t("Current worker movement reason", "当前工作代理移动原因")}>
              {worker.movement_reason_code ?? <UnknownValue chinese={chinese} />}
            </Fact>
          </>
        )}
        {solTarget === null ? (
          <Fact label={t("Current Sol target", "当前 Sol 目标")}>
            <NotReported chinese={chinese} />
          </Fact>
        ) : (
          <>
            <Fact label={t("Sol target worker id", "Sol 目标工作代理 ID")}>
              {solTarget.worker_id ?? <UnknownValue chinese={chinese} />}
            </Fact>
            <Fact label={t("Sol target attempt id", "Sol 目标尝试 ID")}>
              {solTarget.attempt_id ?? <UnknownValue chinese={chinese} />}
            </Fact>
            <Fact label={t("Sol target status", "Sol 目标状态")}>
              {solTarget.status === null ? (
                <UnknownValue chinese={chinese} />
              ) : (
                <Code value={solTarget.status} />
              )}
            </Fact>
            <Fact label={t("Sol target effect state", "Sol 目标效果状态")}>
              {solTarget.effect_state === null ? (
                <UnknownValue chinese={chinese} />
              ) : (
                <Code value={solTarget.effect_state} />
              )}
            </Fact>
          </>
        )}
        {w3c === null ? (
          <Fact label={t("Terminal return (W3C)", "终局返回（W3C）")}>
            <NotReported chinese={chinese} />
          </Fact>
        ) : (
          <>
            <Fact label={t("W3C transport state", "W3C 传输状态")}>
              {w3c.state === null ? (
                <UnknownValue chinese={chinese} />
              ) : (
                <Code value={w3c.state} />
              )}
            </Fact>
            <Fact label={t("Terminal state", "终局状态")}>
              {w3c.terminal_state ?? <UnknownValue chinese={chinese} />}
            </Fact>
            <Fact label={t("Terminal applied", "终局已应用")}>
              {observedFlag(w3c.terminal_applied, chinese)}
            </Fact>
            <Fact label={t("Wake state", "唤醒状态")}>
              {w3c.wake_state ?? <UnknownValue chinese={chinese} />}
            </Fact>
            {receipt === null ? (
              <Fact label={t("Terminal source receipt", "终局来源回执")}>
                <NotReported chinese={chinese} />
              </Fact>
            ) : (
              <>
                <Fact label={t("Receipt observed at", "回执观测时间")}>
                  {receipt.observed_at ?? <UnknownValue chinese={chinese} />}
                </Fact>
                <Fact label={t("Receipt snapshot digest", "回执快照摘要")}>
                  {receipt.snapshot_digest ?? <UnknownValue chinese={chinese} />}
                </Fact>
              </>
            )}
          </>
        )}
      </div>
    </details>
  );
}

function ReturnAcceptanceBlock({
  document,
  chinese,
  t,
}: {
  document: MissionDocument;
  chinese: boolean;
  t: Translate;
}) {
  return (
    <details className="mm-supervision-trace__block">
      <summary>
        <h3 className="mm-supervision-trace__block-title">
          {t("Return and acceptance", "返回与验收")}
        </h3>
      </summary>
      <div className="mm-supervision-trace__facts">
        <Fact label={t("Execution state", "执行状态")}>
          {document.execution.state === null ? (
            <UnknownValue chinese={chinese} />
          ) : (
            <Code value={document.execution.state} />
          )}
        </Fact>
        <Fact label={t("Summary presence", "摘要存在性")}>
          {document.execution.summary_present
            ? t("Reported present in source (presence only)", "已报告来源中存在（仅存在性）")
            : t("Reported absent", "已报告为不存在")}
        </Fact>
        <Fact label={t("Review required", "需要审查")}>
          {observedFlag(document.review.required, chinese)}
        </Fact>
        <Fact label={t("Review verdict", "审查结论")}>
          <Code value={document.review.verdict} />
        </Fact>
        <Fact label={t("Acceptance state", "验收状态")}>
          <Code value={document.acceptance.state} />
        </Fact>
        <Fact label={t("Acceptance owner", "验收所有者")}>
          {document.acceptance.owner ?? <UnknownValue chinese={chinese} />}
        </Fact>
        <Fact label={t("Acceptance artifact revision", "验收工件版本")}>
          {document.acceptance.artifact_revision ?? <UnknownValue chinese={chinese} />}
        </Fact>
      </div>
      <p className="mm-supervision-trace__footnote">
        {t(
          "Execution completion, a returned transport or a present summary does not imply acceptance. Acceptance is asserted only by the acceptance owner's own state.",
          "执行完成、已返回的传输或已存在的摘要都不意味着验收；验收仅由验收所有者自身状态断言。",
        )}
      </p>
      <p className="mm-supervision-trace__footnote">
        {t(
          "Summary presence only reports whether a summary field was present in the source; it does not make summary content or results available here.",
          "摘要存在性仅报告来源中是否存在摘要字段；此处不因此提供摘要内容或结果。",
        )}
      </p>
    </details>
  );
}

function SupervisionBlock({
  document,
  chinese,
  t,
}: {
  document: MissionDocument;
  chinese: boolean;
  t: Translate;
}) {
  const owed = document.principal.owed_turn;
  const armed = document.mission.armed;
  const armedRows: Array<{
    key: string;
    en: string;
    zh: string;
    value: boolean | null;
  }> = [
    {
      key: "ceo_submit_armed",
      en: "CEO submit armed",
      zh: "CEO 提交武装",
      value: armed.ceo_submit_armed,
    },
    {
      key: "coo_autonomy_armed",
      en: "COO autonomy armed",
      zh: "COO 自主武装",
      value: armed.coo_autonomy_armed,
    },
    {
      key: "ceo_ingress_app_armed",
      en: "CEO ingress app armed",
      zh: "CEO 入口应用武装",
      value: armed.ceo_ingress_app_armed,
    },
    {
      key: "dialogue_bridge_armed",
      en: "Dialogue bridge armed",
      zh: "对话桥接武装",
      value: armed.dialogue_bridge_armed,
    },
    {
      key: "terminal_return_armed",
      en: "Terminal return armed",
      zh: "终局返回武装",
      value: armed.terminal_return_armed,
    },
  ];
  return (
    <details className="mm-supervision-trace__block">
      <summary>
        <h3 className="mm-supervision-trace__block-title">
          {t("Supervision", "监督")}
        </h3>
      </summary>
      <div className="mm-supervision-trace__facts">
        <Fact label={t("Accountable seat", "问责席位")}>
          {document.principal.accountable_seat === null ? (
            <UnknownValue chinese={chinese} />
          ) : (
            <Code value={document.principal.accountable_seat} />
          )}
        </Fact>
        {owed === null ? (
          <Fact label={t("Owed turn", "待回应轮次")}>
            <NotReported chinese={chinese} />
          </Fact>
        ) : (
          <>
            <Fact label={t("Owed turn seat", "待回应席位")}>
              {owed.seat === null ? (
                <UnknownValue chinese={chinese} />
              ) : (
                <Code value={owed.seat} />
              )}
            </Fact>
            <Fact label={t("Owed turn reason", "待回应原因")}>
              {owed.reason ?? <UnknownValue chinese={chinese} />}
            </Fact>
            {owed.source_refs.length === 0 ? (
              <Fact label={t("Owed turn source receipts", "待回应来源回执")}>
                <NotReported chinese={chinese} />
              </Fact>
            ) : (
              owed.source_refs.map((receiptRef, index) => (
                <Fact
                  key={`${receiptRef.owner}-${index}`}
                  label={`${t("Owed turn source", "待回应来源")} ${index + 1}`}
                >
                  <code className="mm-supervision-trace__code">{receiptRef.owner}</code>
                  {" · "}
                  <code className="mm-supervision-trace__code">{receiptRef.ref}</code>
                  {" · "}
                  {t("observed at", "观测时间")} {receiptRef.observed_at}
                  {" · "}
                  {t("freshness", "新鲜度")} <Code value={receiptRef.freshness} />
                </Fact>
              ))
            )}
          </>
        )}
        <Fact label={t("Next action (as provided by source)", "下一步（仅按来源提供）")}>
          {document.program.next_action ?? (
            <span className="mm-supervision-trace__unknown">
              {t("Not provided by the source; nothing is inferred here", "来源未提供；此处不作任何推断")}
            </span>
          )}
        </Fact>
        {armedRows.map((row) => (
          <Fact key={row.key} label={t(row.en, row.zh)}>
            {armedFlag(row.value, chinese)}
          </Fact>
        ))}
        <Fact label={t("Armed flags source", "武装标志来源")}>
          {armed.source === "control.json"
            ? "control.json"
            : t("No armed source was provided", "未提供武装标志来源")}
        </Fact>
      </div>
      <p className="mm-supervision-trace__footnote">
        {t(
          "Each armed flag is a separate reported observation. An armed flag is not an authorization and never combines into a readiness claim; no command is offered by this view.",
          "每个武装标志都是单独的报告观测。武装标志不是授权，也永远不会合并为就绪声明；本视图不提供任何命令。",
        )}
      </p>
    </details>
  );
}

function facetLabel(facet: string, t: Translate): string {
  const zh: Record<string, string> = {
    Program: "程序",
    Mission: "任务",
    Principal: "责任主体",
    Execution: "执行",
    Review: "审查",
    Transport: "传输",
    Acceptance: "验收",
    Posture: "姿态",
  };
  return t(facet, zh[facet] ?? facet);
}

function collectEvidence(
  document: MissionDocument,
): Array<{ facet: string; evidence: EvidenceRef }> {
  const groups: Array<[string, EvidenceRef[]]> = [
    ["Program", document.program.evidence],
    ["Mission", document.mission.evidence],
    ["Principal", document.principal.evidence],
    ["Execution", document.execution.evidence],
    ["Review", document.review.evidence],
    ["Transport", document.transport.evidence],
    ["Acceptance", document.acceptance.evidence],
    ["Posture", document.posture.evidence],
  ];
  return groups.flatMap(([facet, refs]) =>
    refs.map((evidence) => ({ facet, evidence })),
  );
}

function EvidenceItem({
  facet,
  evidence,
  chinese,
  t,
}: {
  facet: string;
  evidence: EvidenceRef;
  chinese: boolean;
  t: Translate;
}) {
  return (
    <li className="mm-supervision-trace__evidence-item">
      <span className="mm-supervision-trace__facet">{facetLabel(facet, t)}</span>
      <span>
        {t("owner", "所有者")}: <code className="mm-supervision-trace__code">{evidence.owner}</code>
      </span>
      {/* Raw refs are plain text; they never become hyperlinks. */}
      <span>
        {t("ref", "引用")}: <code className="mm-supervision-trace__code">{evidence.ref}</code>
      </span>
      <span>
        {t("field", "字段")}: {evidence.field}
      </span>
      <span>
        {t("revision", "修订")}:{" "}
        {evidence.source_revision ?? <UnknownValue chinese={chinese} />}
      </span>
      <span>
        {t("freshness", "新鲜度")}: <Code value={evidence.freshness_state} />
      </span>
      {evidence.source_time !== null && (
        <span>
          {t("source time", "来源时间")}: {evidence.source_time}
        </span>
      )}
      {evidence.observed_at !== null && (
        <span>
          {t("observed at", "观测时间")}: {evidence.observed_at}
        </span>
      )}
    </li>
  );
}

function SourceEvidenceBlock({
  document,
  chinese,
  t,
}: {
  document: MissionDocument;
  chinese: boolean;
  t: Translate;
}) {
  const evidence = collectEvidence(document);
  const head = evidence.slice(0, EVIDENCE_BOUND);
  const tail = evidence.slice(EVIDENCE_BOUND);
  return (
    <details className="mm-supervision-trace__block">
      <summary>
        <h3 className="mm-supervision-trace__block-title">
          {t("Source evidence", "来源证据")}
        </h3>
      </summary>
      {evidence.length === 0 ? (
        <p className="mm-supervision-trace__block-note">
          {t(
            "No source evidence items were provided in this observation.",
            "本观测未提供来源证据条目。",
          )}
        </p>
      ) : (
        <>
          <p className="mm-supervision-trace__count">
            {t(
              `Showing the first ${head.length} of ${evidence.length} source evidence items.`,
              `显示 ${evidence.length} 条来源证据中的前 ${head.length} 条。`,
            )}
          </p>
          <ul className="mm-supervision-trace__evidence">
            {head.map((item, index) => (
              <EvidenceItem
                key={`${item.facet}-${index}`}
                facet={item.facet}
                evidence={item.evidence}
                chinese={chinese}
                t={t}
              />
            ))}
          </ul>
          {tail.length > 0 && (
            <details className="mm-supervision-trace__expand">
              <summary>
                {t(
                  `Show the remaining ${tail.length} source evidence items`,
                  `显示其余 ${tail.length} 条来源证据`,
                )}
              </summary>
              <ul className="mm-supervision-trace__evidence">
                {tail.map((item, index) => (
                  <EvidenceItem
                    key={`${item.facet}-tail-${index}`}
                    facet={item.facet}
                    evidence={item.evidence}
                    chinese={chinese}
                    t={t}
                  />
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </details>
  );
}

function MissingnessBlock({
  document,
  chinese,
  t,
}: {
  document: MissionDocument;
  chinese: boolean;
  t: Translate;
}) {
  return (
    <details className="mm-supervision-trace__block">
      <summary>
        <h3 className="mm-supervision-trace__block-title">
          {t("Missing fields", "缺失字段")}
        </h3>
      </summary>
      {document.missingness.length === 0 ? (
        <p className="mm-supervision-trace__block-note">
          {t(
            "No missingness entries were reported in this observation.",
            "本观测未报告缺失条目。",
          )}
        </p>
      ) : (
        <ul className="mm-supervision-trace__missing">
          {document.missingness.map((entry, index) => (
            <li key={`${entry.target_field}-${index}`}>
              <code className="mm-supervision-trace__code">{entry.target_field}</code>
              {" · "}
              <Code value={entry.missingness_class} />
              {" · "}
              {t("producer", "生产者")}:{" "}
              {entry.producer_owner ?? <UnknownValue chinese={chinese} />}
              {" · "}
              {entry.reason}
            </li>
          ))}
        </ul>
      )}
      <p className="mm-supervision-trace__footnote">
        {t(
          "Listed missingness describes this observation only. This view does not claim that every producer is connected or that unlisted fields are complete.",
          "缺失说明仅描述本观测。本视图不声称所有生产者均已连接，也不声称未列出的字段完整。",
        )}
      </p>
    </details>
  );
}

export function SupervisionTrace({
  document,
  selection,
  locale = "en",
  onReadCurrent,
}: SupervisionTraceProps) {
  const chinese = locale === "zh-CN";
  const t: Translate = (en, zh) => (chinese ? zh : en);
  return (
    <section
      className="mm-supervision-trace"
      aria-label={t("Supervision and trace", "监督与追踪")}
    >
      <h2 className="mm-supervision-trace__title">
        {t("Supervision & trace", "监督与追踪")}
      </h2>
      {document && selection && scopeMatches(document, selection) ? (
        <>
          <p className="mm-supervision-trace__scope">
            {t("Scope", "范围")}:{" "}
            <code className="mm-supervision-trace__code">{document.program.work_ref}</code>
            {" · "}
            {t("root", "根任务")}:{" "}
            <code className="mm-supervision-trace__code">{selection.rootJobId}</code>
            {" · "}
            {t("Read state", "读取状态")}: <Code value={document.read_state.state} />
          </p>
          <p className="mm-supervision-trace__scope">
            {t("Generated at", "生成时间")}:{" "}
            {document.generated_at ?? <UnknownValue chinese={chinese} />}
          </p>
          {heldSources(document).length > 0 && (
            <HeldBanner document={document} chinese={chinese} t={t} />
          )}
          {document.read_state.state === "UNAVAILABLE" && (
            <p className="mm-supervision-trace__caveat" role="note">
              {t("This source is unavailable. Retained fields do not establish the current state.",
                "此来源不可用。保留字段不能证明当前状态。")}
            </p>
          )}
          {(document.read_state.state === "HISTORICAL" ||
            document.read_state.state === "PARTIAL") && (
            <p className="mm-supervision-trace__caveat" role="note">
              {document.read_state.state === "HISTORICAL"
                ? t(
                    "This observation is marked historical: the facts below were reported by an earlier observation and are not asserted to describe the current state.",
                    "本观测被标记为历史：以下事实来自较早的一次观测，不因此断言它们描述当前状态。",
                  )
                : t(
                    "This observation is partial: only the fields shown were reported, and absence elsewhere is not evidence of completion or of a current state.",
                    "本观测为部分：仅报告了所示字段；其他位置的缺失不构成完成或当前状态的证据。",
                  )}
            </p>
          )}
          {(document.transport.historical ||
            document.transport.carrier?.historical === true) && (
            <p className="mm-supervision-trace__caveat" role="note">
              {t(
                "A transport or carrier record in this observation is marked historical; it may describe a previous attempt rather than the current one.",
                "本观测中的传输或载体记录被标记为历史；它可能描述先前的尝试而非当前尝试。",
              )}
            </p>
          )}
          <OrchestrationTraceBlock document={document} chinese={chinese} t={t} />
          <ReturnAcceptanceBlock document={document} chinese={chinese} t={t} />
          <SupervisionBlock document={document} chinese={chinese} t={t} />
          <SourceEvidenceBlock document={document} chinese={chinese} t={t} />
          <MissingnessBlock document={document} chinese={chinese} t={t} />
        </>
      ) : (
        <p className="mm-supervision-trace__unavailable" role="status">
          {document === null
            ? t(
                "No mission observation is available for the selected scope. Source details are withheld until an exactly matching observation is provided.",
                "所选范围当前没有可用的任务观测。在提供完全匹配的观测之前，来源细节一律隐藏。",
              )
            : t(
                "The provided observation does not exactly match the selected mission: the work reference, the resolved singleton root candidate and an unambiguous root must all match. Source details are withheld.",
                "提供的观测与所选任务不完全匹配：工作引用、已解析的单一根候选以及无歧义的根任务必须全部匹配。来源细节一律隐藏。",
              )}
        </p>
      )}
      {onReadCurrent && selection && normalizeSelection(selection) ? (
        <div className="mm-supervision-trace__read">
          <button type="button" className="mm-supervision-trace__read-button"
            onClick={() => onReadCurrent()}>
            {t("Read current mission", "读取当前任务")}
          </button>
          <span className="mm-supervision-trace__read-note">
            {t("Read the selected work from its existing source.", "从已有来源读取所选工作。")}
          </span>
        </div>
      ) : null}
    </section>
  );
}
