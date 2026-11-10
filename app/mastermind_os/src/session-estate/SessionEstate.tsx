/** Bounded Session Estate read+inspect presentation.
 *
 * Presentation only over the detached Control Room projection handed in by
 * the owner: no fetching, storage, dispatch, timers or lifecycle effects live
 * here. Authentication, refresh authority and every runtime effect stay with
 * their existing owners. A saved binding is an observation; it never proves a
 * running session.
 */
import { useId, useState } from "react";
import type { ReactNode } from "react";
import { decodeControlRoomActionPayload, type ControlRoomState } from "../control-room";
import "./session-estate.css";

export type SessionEstateLocale = "en" | "zh-CN";

type AvailableRead = Extract<ControlRoomState, { state: "AVAILABLE" }>;
type AvailableNavigation = Extract<AvailableRead["navigation"], { state: "AVAILABLE" }>;
type Binding = AvailableNavigation["bindings"][number];

const INITIAL_ROWS = 8;

const EN = {
  title: "Sessions",
  boundAnswer: (n: number) =>
    `${n} saved session ${n === 1 ? "connection" : "connections"} supplied · total unknown`,
  emptyAnswer: "No saved session connections were supplied. The estate total is unknown.",
  caution: "Saved connections do not confirm that a session is running.",
  pending: "Session information is not available yet.",
  unavailable: "Session information is unavailable.",
  ownerReason: (reason: string) => `Why unavailable: ${reason}`,
  navInvalid: "Session information could not be displayed.",
  sourceDetails: "Technical details",
  observedAt: "Observed at",
  publication: "Publication sequence",
  freshness: "Source validity",
  freshnessQualified: "Source validity details supplied; current availability is not established.",
  freshnessUnknown: "Current session availability is not established by this read.",
  notReported: "not reported",
  searchLabel: "Find a session connection",
  searchPlaceholder: "provider, role, work reference or seat",
  listHeading: "Saved connections",
  shown: (shown: number, total: number) => `Showing ${shown} of ${total}.`,
  noMatch: "No bindings match this search.",
  showAll: (n: number) => `Show all ${n} bindings`,
  showFewer: (n: number) => `Show the first ${n} bindings`,
  inspect: "Inspect",
  detailHeading: "Connection details",
  fieldBindingId: "Binding id",
  fieldRole: "Role",
  fieldProvider: "Provider",
  fieldSeat: "Seat reference",
  fieldWorkRef: "Work reference",
  fieldRoot: "Mission root",
  fieldLocator: "Locator kind",
  fieldObserved: "Observed at",
  fieldVerified: "Last verified",
  fieldStatus: "Binding status",
  statusBound: "Work reference present in this supplied project list",
  statusUnbound: "Work reference outside this supplied project list",
  fieldConflicts: "Conflicts",
  noConflicts: "None observed for this binding.",
  conflictGroup: (ids: readonly string[]) =>
    `Ambiguous group (${ids.length}): ${ids.join(", ")}`,
  missionHeading: "Work details",
  openMission: "Open work details",
  openSession: "Open session",
  sessionUnavailable: "Opening this session is unavailable. Refresh the source or check the session controls.",
  openNote: "Read navigation only; it does not open or activate any runtime surface.",
  suppressUnbound: "This binding is outside the current supplied project list, so no mission was guessed.",
  suppressConflict:
    "This binding sits in a conflicting work/role group, so no exact mission is offered.",
  suppressNoProgram: "No project is supplied for this work reference.",
  suppressMultiProgram:
    "Several projects share this work reference, so the mission is ambiguous.",
  suppressRootConflict: "The root candidates for this work reference conflict.",
  suppressRootUnresolved: "The root job for this work reference is not resolved.",
  suppressNoRootJobId: "The resolved programme carries no root job identifier.",
  invalidated: "The selected binding is no longer present in the current read. Inspect another binding.",
  placeholder: "Select a saved connection to see its details.",
  refresh: "Refresh",
  refreshing: "Refreshing…",
  technical: "Technical details",
  advanced: "Advanced session controls",
  controlsHeld: "A session action remains unresolved. Advanced controls stay paused.",
} as const;
type Copy = { [K in keyof typeof EN]: (typeof EN)[K] extends (...args: infer A) => string
  ? (...args: A) => string : string };

const ZH: Copy = {
  title: "会话",
  boundAnswer: (n) => `已提供 ${n} 个保存的会话连接 · 总数未知`,
  emptyAnswer: "未提供保存的会话连接。会话总数未知。",
  caution: "保存的连接不能确认会话正在运行。",
  pending: "会话信息尚不可用。",
  unavailable: "会话信息不可用。",
  ownerReason: (reason) => `不可用原因：${reason}`,
  navInvalid: "无法显示会话信息。",
  sourceDetails: "技术详情",
  observedAt: "观察时间",
  publication: "发布序号",
  freshness: "来源有效性",
  freshnessQualified: "已提供来源有效性详情；尚未确认当前可用性。",
  freshnessUnknown: "此读取不能确认会话当前可用。",
  notReported: "未报告",
  searchLabel: "查找会话连接",
  searchPlaceholder: "提供方、角色、工作引用或席位",
  listHeading: "绑定列表",
  shown: (shown, total) => `已显示 ${shown} / ${total} 条。`,
  noMatch: "没有匹配此搜索的绑定。",
  showAll: (n) => `显示全部 ${n} 条绑定`,
  showFewer: (n) => `仅显示前 ${n} 条绑定`,
  inspect: "查看",
  detailHeading: "连接详情",
  fieldBindingId: "绑定标识",
  fieldRole: "角色",
  fieldProvider: "提供方",
  fieldSeat: "席位引用",
  fieldWorkRef: "工作引用",
  fieldRoot: "任务根",
  fieldLocator: "定位方式",
  fieldObserved: "观察时间",
  fieldVerified: "最近核验",
  fieldStatus: "绑定状态",
  statusBound: "工作引用在当前项目观察范围内",
  statusUnbound: "工作引用不在当前项目观察范围内",
  fieldConflicts: "冲突",
  noConflicts: "未观察到与此绑定相关的冲突。",
  conflictGroup: (ids) => `歧义分组（${ids.length} 条）：${ids.join("、")}`,
  missionHeading: "工作详情",
  openMission: "打开工作详情",
  openSession: "打开会话",
  sessionUnavailable: "暂时无法打开此会话。请刷新来源或检查会话控制。",
  openNote: "仅作只读导航；不会打开或激活任何运行时界面。",
  suppressUnbound: "该绑定不在当前项目观察范围内，因此不会猜测任务。",
  suppressConflict: "该绑定属于冲突的工作/角色分组，因此不提供精确任务导航。",
  suppressNoProgram: "未观察到该工作引用对应的项目。",
  suppressMultiProgram: "多个项目共用该工作引用，任务不唯一。",
  suppressRootConflict: "该工作引用的根任务候选相互冲突。",
  suppressRootUnresolved: "该工作引用的根任务尚未解析。",
  suppressNoRootJobId: "已解析的项目缺少根任务标识。",
  invalidated: "所选绑定已不在当前读取中。请查看其他绑定。",
  placeholder: "选择保存的连接以查看详情。",
  refresh: "刷新",
  refreshing: "刷新中…",
  technical: "技术详情",
  advanced: "高级会话操作",
  controlsHeld: "某项会话操作仍未确认结果。高级操作保持暂停。",
};

type SuppressionKind = "unbound" | "conflict" | "noProgram" | "multiProgram"
  | "rootConflict" | "rootUnresolved" | "noRootJobId";

function suppressionText(kind: SuppressionKind, copy: Copy): string {
  switch (kind) {
    case "unbound":
      return copy.suppressUnbound;
    case "conflict":
      return copy.suppressConflict;
    case "noProgram":
      return copy.suppressNoProgram;
    case "multiProgram":
      return copy.suppressMultiProgram;
    case "rootConflict":
      return copy.suppressRootConflict;
    case "rootUnresolved":
      return copy.suppressRootUnresolved;
    case "noRootJobId":
      return copy.suppressNoRootJobId;
  }
}

function matchesQuery(binding: Binding, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  return (
    binding.provider.toLowerCase().includes(needle) ||
    binding.role.toLowerCase().includes(needle) ||
    binding.work_ref.toLowerCase().includes(needle) ||
    (binding.seat_ref ?? "").toLowerCase().includes(needle)
  );
}

/** Exact-mission resolution over the passed read only. Every suppression
 * reason is explained; nothing is guessed from partial matches.
 */
function resolveMission(
  read: AvailableRead,
  navigation: AvailableNavigation,
  binding: Binding,
): { kind: "resolved"; rootJobId: string } | { kind: SuppressionKind } {
  if (navigation.unboundBindingIds.includes(binding.binding_id)) {
    return { kind: "unbound" };
  }
  const conflicted = navigation.conflicts.some(
    (group) =>
      group.binding_ids.includes(binding.binding_id) ||
      (group.work_ref === binding.work_ref && group.role === binding.role),
  );
  if (conflicted) return { kind: "conflict" };
  const candidates = read.programs.filter((program) => program.workRef === binding.work_ref);
  if (candidates.length === 0) return { kind: "noProgram" };
  if (candidates.length > 1) return { kind: "multiProgram" };
  const program = candidates[0];
  if (!program) return { kind: "noProgram" };
  if (program.rootState === "CONFLICT") return { kind: "rootConflict" };
  if (program.rootState !== "RESOLVED") return { kind: "rootUnresolved" };
  if (!program.rootJobId) return { kind: "noRootJobId" };
  if (program.rootCandidates.length !== 1 || program.rootCandidates[0] !== program.rootJobId)
    return { kind: "rootConflict" };
  return { kind: "resolved", rootJobId: program.rootJobId };
}

function DetailBody({
  read,
  navigation,
  binding,
  copy,
  onOpenMission,
  canOpenSurface,
  onOpenSurface,
}: {
  readonly read: AvailableRead;
  readonly navigation: AvailableNavigation;
  readonly binding: Binding;
  readonly copy: Copy;
  readonly onOpenMission: (workRef: string, rootJobId: string) => void;
  readonly canOpenSurface: boolean;
  readonly onOpenSurface?: (payload: Readonly<Record<string, unknown>>) => void;
}) {
  const conflictGroups = navigation.conflicts.filter(
    (group) => group.work_ref === binding.work_ref && group.role === binding.role,
  );
  const unbound = navigation.unboundBindingIds.includes(binding.binding_id);
  const resolution = resolveMission(read, navigation, binding);
  const canOpen = canOpenSurface && !!onOpenSurface && binding.provider !== "chatgpt";
  return (
    <div className="session-estate__detail-body">
      <p>{binding.provider} · {binding.role}</p>
      <p>{unbound ? copy.statusUnbound : copy.statusBound}</p>
      <details className="session-estate__source">
        <summary>{copy.technical}</summary>
      <dl className="session-estate__fields">
        <div className="session-estate__field">
          <dt>{copy.fieldBindingId}</dt>
          <dd>
            <code className="session-estate__code">{binding.binding_id}</code>
          </dd>
        </div>
        <div className="session-estate__field">
          <dt>{copy.fieldWorkRef}</dt>
          <dd>
            <code className="session-estate__code">{binding.work_ref}</code>
          </dd>
        </div>
        <div className="session-estate__field">
          <dt>{copy.fieldRole}</dt>
          <dd>{binding.role}</dd>
        </div>
        <div className="session-estate__field">
          <dt>{copy.fieldProvider}</dt>
          <dd>{binding.provider}</dd>
        </div>
        <div className="session-estate__field">
          <dt>{copy.fieldSeat}</dt>
          <dd>{binding.seat_ref ?? copy.notReported}</dd>
        </div>
        <div className="session-estate__field">
          <dt>{copy.fieldLocator}</dt>
          <dd>{binding.locator_kind}</dd>
        </div>
        <div className="session-estate__field">
          <dt>{copy.fieldObserved}</dt>
          <dd>{binding.observed_at}</dd>
        </div>
        <div className="session-estate__field">
          <dt>{copy.fieldVerified}</dt>
          <dd>{binding.last_verified_at ?? copy.notReported}</dd>
        </div>
        {resolution.kind === "resolved" ? <div className="session-estate__field">
          <dt>{copy.fieldRoot}</dt><dd><code>{resolution.rootJobId}</code></dd>
        </div> : null}
        <div className="session-estate__field">
          <dt>{copy.fieldConflicts}</dt>
          <dd>
            {conflictGroups.length === 0 ? (
              copy.noConflicts
            ) : (
              <ul className="session-estate__conflicts">
                {conflictGroups.map((group) => (
                  <li key={`${group.work_ref}:${group.role}`}>
                    {copy.conflictGroup(group.binding_ids)}
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </div>
      </dl>
      </details>
      <div className="session-estate__mission">
        <button type="button" className="button session-estate__open" disabled={!canOpen}
          onClick={() => {
            if (!canOpen || !onOpenSurface) return;
            onOpenSurface(decodeControlRoomActionPayload({ binding_id: binding.binding_id }, "open"));
          }}>{copy.openSession}</button>
        {!canOpen ? <p className="session-estate__note">{copy.sessionUnavailable}</p> : null}
        <h4 className="session-estate__mission-title">{copy.missionHeading}</h4>
        {resolution.kind === "resolved" ? (
          <>
            <button
              type="button"
              className="button session-estate__open"
              onClick={() => onOpenMission(binding.work_ref, resolution.rootJobId)}
            >
              {copy.openMission}
            </button>
            <p className="session-estate__note">{copy.openNote}</p>
          </>
        ) : (
          <p className="session-estate__note">{suppressionText(resolution.kind, copy)}</p>
        )}
      </div>
    </div>
  );
}

export function SessionEstate({
  state,
  locale = "en",
  canRefresh,
  onRefresh,
  onOpenMission,
  children,
  controlsHeld = false,
  canOpenSurface = false,
  onOpenSurface,
}: {
  readonly state: ControlRoomState;
  readonly locale?: SessionEstateLocale;
  readonly canRefresh: boolean;
  readonly onRefresh: () => void;
  readonly onOpenMission: (workRef: string, rootJobId: string) => void;
  readonly children?: ReactNode;
  /** Actual command-owner hold, independent of saved-connection observations. */
  readonly controlsHeld?: boolean;
  /** Current incumbent action-owner eligibility, independent of read data. */
  readonly canOpenSurface?: boolean;
  /** Existing guarded owner; no URL, session identity or Runtime grant is derived here. */
  readonly onOpenSurface?: (payload: Readonly<Record<string, unknown>>) => void;
}) {
  const copy = locale === "zh-CN" ? ZH : EN;
  const titleId = useId();
  const listId = useId();
  const detailId = useId();
  const searchId = useId();
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Explicit refresh only; the owner owns the actual effect.
  const refreshDisabled =
    !canRefresh || state.state === "PENDING" || state.refreshPending === true;

  const available = state.state === "AVAILABLE" ? state : null;
  const navigation = available ? available.navigation : null;
  const nav = navigation && navigation.state === "AVAILABLE" ? navigation : null;

  const answer = !available
    ? state.state === "PENDING"
      ? copy.pending
      : copy.unavailable
    : !nav
      ? copy.navInvalid
      : nav.bindings.length === 0
        ? copy.emptyAnswer
        : copy.boundAnswer(nav.bindings.length);

  const bindings = nav ? nav.bindings : [];
  const filtered = bindings.filter((binding) => matchesQuery(binding, query));
  const visible = showAll ? filtered : filtered.slice(0, INITIAL_ROWS);
  // Always re-derived from the current read: a removed binding never keeps
  // its old row data alive here.
  const selected = selectedId
    ? (bindings.find((binding) => binding.binding_id === selectedId) ?? null)
    : null;

  return (
    <section className="session-estate card" aria-labelledby={titleId}>
      <header className="session-estate__head">
        <div className="session-estate__headline">
          <h2 id={titleId} className="session-estate__title">
            {copy.title}
          </h2>
          <p className="session-estate__answer" role={!available || !nav ? "status" : undefined}>{answer}</p>
        </div>
        <button
          type="button"
          className="button session-estate__refresh"
          onClick={onRefresh}
          disabled={refreshDisabled}
        >
          {state.refreshPending ? copy.refreshing : copy.refresh}
        </button>
      </header>
      <p className="session-estate__caution">{copy.caution}</p>
      {controlsHeld ? <p role="status" className="session-estate__caution">{copy.controlsHeld}</p> : null}
      {available ? (
        <details className="details session-estate__source">
          <summary>{copy.sourceDetails}</summary>
          <dl className="session-estate__source-list">
            {navigation?.state === "UNAVAILABLE" ? <div className="session-estate__source-row">
              <dt>{copy.ownerReason("")}</dt><dd><code>{navigation.reason}</code></dd>
            </div> : null}
            <div className="session-estate__source-row">
              <dt>{copy.observedAt}</dt>
              <dd>{available.observedAt ?? copy.notReported}</dd>
            </div>
            <div className="session-estate__source-row">
              <dt>{copy.publication}</dt>
              <dd>{available.publicationSeq ?? copy.notReported}</dd>
            </div>
            <div className="session-estate__source-row">
              <dt>{copy.freshness}</dt>
              <dd>
                {available.freshness === "OWNER_QUALIFIED"
                  ? copy.freshnessQualified
                  : copy.freshnessUnknown}
              </dd>
            </div>
          </dl>
        </details>
      ) : null}
      {!available ? (
        state.state === "UNAVAILABLE" ? (
          <details className="session-estate__source">
            <summary>{copy.sourceDetails}</summary>
            <p className="session-estate__note">{copy.ownerReason(state.reason)}</p>
          </details>
        ) : null
      ) : !nav ? null : (
        <div className="session-estate__grid">
          <div className="session-estate__list" aria-labelledby={listId}>
            <h3 id={listId} className="session-estate__list-title">
              {copy.listHeading}
            </h3>
            <label className="session-estate__search-label" htmlFor={searchId}>
              {copy.searchLabel}
            </label>
            <input
              id={searchId}
              className="session-estate__search"
              type="search"
              value={query}
              placeholder={copy.searchPlaceholder}
              onChange={(event) => setQuery(event.target.value)}
            />
            <p className="session-estate__count">{copy.shown(visible.length, filtered.length)}</p>
            {filtered.length === 0 ? (
              <p className="session-estate__empty">{copy.noMatch}</p>
            ) : (
              <>
                <ul className="session-estate__rows">
                  {visible.map((binding) => {
                    const isSelected = binding.binding_id === selectedId;
                    const projects = available.programs.filter(p => p.workRef === binding.work_ref);
                    const projectTitle = projects.length === 1 ? projects[0].title : null;
                    return (
                      <li
                        key={binding.binding_id}
                        data-testid={`session-estate-row-${binding.binding_id}`}
                        className={
                          isSelected
                            ? "session-estate__row session-estate__row--selected"
                            : "session-estate__row"
                        }
                        aria-current={isSelected ? "true" : undefined}
                      >
                        <span className="session-estate__row-main">
                          <span className="session-estate__row-ref">{projectTitle || binding.work_ref}</span>
                          {projectTitle ? <span className="session-estate__row-meta">{binding.work_ref}</span> : null}
                          <span className="session-estate__row-meta">
                            {binding.provider} · {binding.role}
                          </span>
                          {binding.seat_ref ? (
                            <span className="session-estate__row-meta">{binding.seat_ref}</span>
                          ) : null}
                        </span>
                        <button
                          type="button"
                          className="button session-estate__inspect"
                          onClick={() => setSelectedId(binding.binding_id)}
                        >
                          {copy.inspect}
                          <span className="session-estate__visually-hidden">
                            {` ${binding.binding_id}`}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
                {filtered.length > INITIAL_ROWS ? (
                  <button
                    type="button"
                    className="button session-estate__toggle"
                    onClick={() => setShowAll(!showAll)}
                  >
                    {showAll ? copy.showFewer(INITIAL_ROWS) : copy.showAll(filtered.length)}
                  </button>
                ) : null}
              </>
            )}
          </div>
          <section className="session-estate__detail-panel" aria-labelledby={detailId}>
            <h3 id={detailId} className="session-estate__detail-title">
              {copy.detailHeading}
            </h3>
            {!selectedId ? (
              <p className="session-estate__placeholder">{copy.placeholder}</p>
            ) : !selected ? (
              <p className="session-estate__invalidated" role="status">
                {copy.invalidated}
              </p>
            ) : (
              <DetailBody
                read={available}
                navigation={nav}
                binding={selected}
                copy={copy}
                onOpenMission={onOpenMission}
                canOpenSurface={canOpenSurface && !controlsHeld && !state.refreshPending}
                onOpenSurface={onOpenSurface}
              />
            )}
          </section>
        </div>
      )}
      {children ? <details className="session-estate__controls session-estate__source">
        <summary>{copy.advanced}</summary>{children}
      </details> : null}
    </section>
  );
}
