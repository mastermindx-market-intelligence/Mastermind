/** Read-only presentation of a decoded bounded supervision read. This
 * component never fetches, stores, dispatches, starts or admits work, and it
 * auto-calls nothing: mission navigation happens only through the exact
 * RESOLVED ProgramCard root via the caller's own onOpenMission callback.
 * Reported freshness stays owner-reported evidence, never live authority.
 */
import { useId, useState } from "react";
import "./supervision-trace.css";
import type { SupervisionRead, SupervisionRow } from "./supervision-read";

export interface SupervisionLedgerProps {
  read: SupervisionRead;
  locale?: string;
  onOpenMission?: (workRef: string, rootJobId: string) => void;
}

/** First page size before a counted show-all. */
const PAGE = 8;
type RoleFilter = "all" | "chairman" | "ceo" | "coo" | "worker" | "unknown";
const ROLES: ReadonlyArray<[RoleFilter, string, string]> = [
  ["all", "All", "全部"],
  ["chairman", "Chairman", "主席"],
  ["ceo", "CEO", "CEO"],
  ["coo", "COO", "COO"],
  ["worker", "Worker", "工作者"],
  ["unknown", "Unknown", "未知"],
];

const matchesRole = (row: SupervisionRow, role: RoleFilter): boolean => {
  if (role === "all") return true;
  if (row.accountableSeat === role || row.owedSeat === role) return true;
  // A row that names no seat at all stays visible under Unknown.
  return role === "unknown" && row.accountableSeat === null && row.owedSeat === null;
};

const matchesSearch = (row: SupervisionRow, search: string): boolean =>
  !search ||
  [row.workRef, row.title, row.owedSeat, row.owedReason].some((value) =>
    value?.toLocaleLowerCase().includes(search),
  );

const HistoricalLabel = ({ value, zh }: { value: boolean | null; zh: boolean }) => {
  if (value === null) return <>{zh ? "历史: 未报告" : "historical: not reported"}</>;
  return <>{zh ? (value ? "历史: 是" : "历史: 否") : value ? "historical: yes" : "historical: no"}</>;
};

const WorkerEffect = ({ row, zh }: { row: SupervisionRow; zh: boolean }) => {
  if (row.workerEffect === "effect_unknown")
    return (
      <p role="status">
        <strong>{zh ? "原操作保持持有" : "Original operation held"}</strong>
        {" · "}effect_unknown
      </p>
    );
  if (row.workerEffect === "none")
    return <p>{zh ? "报告的工作效果: 无" : "Reported worker effect: none"}</p>;
  if (row.workerEffect === "applied")
    return <p>{zh ? "报告的工作效果: 已应用" : "Reported worker effect: applied"}</p>;
  return <p>{zh ? "工作效果未报告" : "Worker effect not reported"}</p>;
};

const Row = ({
  row,
  zh,
  onOpenMission,
}: {
  row: SupervisionRow;
  zh: boolean;
  onOpenMission?: (workRef: string, rootJobId: string) => void;
}) => {
  const label = row.title ?? row.workRef;
  const resolvable = row.rootState === "RESOLVED" && row.rootJobId !== null &&
    row.rootCandidates.length === 1 && row.rootCandidates[0] === row.rootJobId;
  const unresolved = row.workerEffect === "effect_unknown" || row.dispatchState === "EFFECT_UNKNOWN" || row.unresolvedEffect === true;
  const nextStep = row.nextActionWithheld ? null : row.nextAction ?? row.owedReason;
  return (
    <li>
      <div>
        <h3>{label}</h3>
        <code>{row.workRef}</code>
      </div>
      <p><strong>{zh ? "提供的下一步" : "Supplied next step"}</strong>: {nextStep ??
        (zh ? "此处未提供下一步" : "Next step unavailable here")}</p>
      <p>{zh ? "下一轮负责角色" : "Next responsible role"}: {row.owedSeat ?? (zh ? "未报告" : "not reported")}</p>
      {unresolved ? <p role="status"><strong>{zh ? "原操作保持持有" : "Original operation held"}</strong>
        {" · "}{zh ? "请勿再次发送、改换目标或创建替代请求。" : "Do not resend, choose another destination, or create a replacement."}</p> : null}
      {resolvable && onOpenMission && <button type="button"
        aria-label={`${zh ? "打开工作详情" : "Open work details"}: ${row.workRef}`}
        onClick={() => onOpenMission(row.workRef, row.rootJobId as string)}>
        {zh ? "打开工作详情" : "Open work details"}</button>}
      <details className="mm-supervision-trace__expand">
        <summary>{zh ? "来源详情" : "Source details"}</summary>
      <p>
        {zh ? "报告状态" : "Reported state"}: {row.state ?? (zh ? "未报告" : "not reported")}
      </p>
      <p>
        {zh ? "责任席位" : "Accountable seat"}:{" "}
        {row.accountableSeat ?? (zh ? "未报告" : "not reported")}
      </p>
      <p>
        {zh ? "应付回合" : "Owed turn"}: {row.owedSeat ?? (zh ? "未报告" : "not reported")}
        {row.owedReason ? ` — ${row.owedReason}` : ""}
      </p>
      <p>
        {zh ? "报告的新鲜度" : "Reported freshness"}: {row.freshness} ·{" "}
        {zh ? "查询状态" : "Query status"}: {row.queryStatus}
      </p>
      <p>
        {zh ? "根任务" : "Root"}: {row.rootState}
        {row.rootJobId ? ` · ${row.rootJobId}` : ""}
      </p>
      <p>
        {zh ? "调度" : "Dispatch"}: {row.dispatchState ?? (zh ? "未报告" : "not reported")} ·{" "}
        <HistoricalLabel value={row.dispatchHistorical} zh={zh} />
      </p>
      {!unresolved ? <WorkerEffect row={row} zh={zh} /> : null}
        <p>
          {zh ? "来源" : "Sources"} ({row.sources.length})
        </p>
        {row.sources.length === 0 && (
          <p>{zh ? "未提供来源回执。" : "No source receipts were supplied."}</p>
        )}
        {row.sources.map((source, index) => (
          <p key={`${source.owner}:${index}`}>
            <code>
              {source.owner} · {source.ref}
            </code>
            {" · "}
            <time dateTime={source.observedAt}>{source.observedAt}</time>
            {" · "}
            {source.freshness}
          </p>
        ))}
        {row.rootCandidates.length > 0 && (
          <p>
            {zh ? "根任务候选" : "Root candidates"}: {row.rootCandidates.join(", ")}
          </p>
        )}
        {row.nextActionWithheld ? (
          <p>
            {zh
              ? "下一步被来源保护隐藏；不显示被隐藏的文本。"
              : "Next action withheld by the source guard; the withheld text is not displayed."}
          </p>
        ) : (
          <p>
            {zh ? "下一步" : "Next action"}: {row.nextAction ?? (zh ? "未提供" : "not supplied")}
          </p>
        )}
      </details>
    </li>
  );
};

export function SupervisionLedger({
  read,
  locale = "en",
  onOpenMission,
}: SupervisionLedgerProps) {
  const zh = locale.toLowerCase().startsWith("zh");
  const [query, setQuery] = useState("");
  const [role, setRole] = useState<RoleFilter>("all");
  const [showAll, setShowAll] = useState(false);
  const searchId = useId();
  const roleId = useId();
  const search = query.trim().toLocaleLowerCase();

  const filtered = read.state === "AVAILABLE"
    ? read.rows.filter((row) => matchesRole(row, role) && matchesSearch(row, search))
    : [];
  const shown = showAll ? filtered : filtered.slice(0, PAGE);
  const header = zh ? "后续工作" : "Next steps";

  return (
    <section className="card" aria-label={header}>
      <h2>{header}</h2>
      <p>
        {zh
          ? "查看已提供的项目下一步。这些记录不能证明工作正在运行。"
          : "Review the supplied project next steps. These observations do not confirm that work is running."}
      </p>
      {read.state === "AVAILABLE" ? (
        <>
          <p>{zh ? `已提供 ${read.rows.length} 项 · 总数未知` : `${read.rows.length} supplied items · total unknown`}</p>
          <details className="mm-supervision-trace__expand">
            <summary>{zh ? "来源详情" : "Source details"}</summary>
          <p>
            {zh ? "生成时间" : "Generated at"}{" "}
            <time dateTime={read.generatedAt}>{read.generatedAt}</time>
          </p>
          <p>
            {zh
              ? `有界观察：${read.rows.length} 行 · 来源失败：${read.sourceFailureCount} · 来源问题：${read.issueCount}。计数仅用于诊断；为零不代表健康。`
              : `Bounded observations: ${read.rows.length} rows · source failures: ${read.sourceFailureCount} · source issues: ${read.issueCount}. Counts are diagnostic only; zero does not prove health.`}
          </p>
          </details>
          <div className="form-field">
            <label htmlFor={searchId}>{zh ? "搜索" : "Search"}</label>
            <input
              id={searchId}
              type="search"
              value={query}
              maxLength={160}
              autoComplete="off"
              placeholder={zh ? "查找工作项…" : "Find a work item…"}
              onChange={(event) => setQuery(event.currentTarget.value)}
            />
          </div>
          <div className="form-field">
            <label htmlFor={roleId}>{zh ? "角色" : "Role"}</label>
            <select
              id={roleId}
              value={role}
              onChange={(event) => setRole(event.currentTarget.value as RoleFilter)}
            >
              {ROLES.map(([value, en, zhText]) => (
                <option key={value} value={value}>
                  {zh ? zhText : en}
                </option>
              ))}
            </select>
          </div>
          <p aria-live="polite">
            {zh
              ? `显示 ${shown.length} / 共 ${filtered.length} 行`
              : `${shown.length} of ${filtered.length} shown`}
          </p>
          {read.rows.length === 0 ? (
            <p role="status">
              {zh
                ? "此有界快照没有监督行。这不代表全公司没有工作。"
                : "This bounded snapshot carries no supervision rows. It is not a company-wide zero."}
            </p>
          ) : filtered.length === 0 ? (
            <>
              <p role="status">
                {zh ? "没有符合当前搜索或角色筛选的行。" : "No rows match the current search or role filter."}
              </p>
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setRole("all");
                }}
              >
                {zh ? "清除筛选" : "Clear filters"}
              </button>
            </>
          ) : (
            <>
              <ul className="ccr-list" aria-label={zh ? "监督行" : "Supervision rows"}>
                {shown.map((row) => (
                  <Row key={row.workRef} row={row} zh={zh} onOpenMission={onOpenMission} />
                ))}
              </ul>
              {!showAll && filtered.length > shown.length && (
                <button type="button" onClick={() => setShowAll(true)}>
                  {zh ? `显示全部 ${filtered.length} 行` : `Show all ${filtered.length}`}
                </button>
              )}
            </>
          )}
        </>
      ) : (
        <p role="status">
          {read.reason === "SOURCE_UNAVAILABLE"
            ? zh
              ? "有界监督来源不可用。不推断任何职责状态。"
              : "The bounded supervision source is unavailable. No responsibility state is inferred."
            : zh
              ? "有界监督来源无效，整体不予显示。不显示部分账本或部分绿色状态。"
              : "The bounded supervision source was invalid and is withheld whole. No partial ledger or partial green is shown."}
        </p>
      )}
    </section>
  );
}

export default SupervisionLedger;
