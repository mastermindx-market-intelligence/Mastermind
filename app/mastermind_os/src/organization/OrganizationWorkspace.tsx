import type { OfficeProjection, ProjectionContext, SourceState } from "../meta-ceo/projection";
import { sameTarget } from "../meta-ceo/projection";
import type { ResultSelection } from "../result";
import { qualifyOrganizationMission } from "./organization-mission";
import { OrganizationMissionView } from "./OrganizationMissionView";
import { AdmittedPlanInspector, type AdmittedPlanInspectorProps } from "../planning/AdmittedPlanInspector";
import "./organization-workspace.css";

/** A view of the *existing* Hermes owner response, never an organization registry. */
export interface OrganizationObservation {
  readonly context: ProjectionContext;
  readonly missionRevision: string | null;
  readonly sourceState: SourceState;
  readonly value: unknown;
}

export type OrganizationPlanReader = Pick<AdmittedPlanInspectorProps,
  "read" | "readActivity" | "sourceGeneration" | "canRead">;

export interface OrganizationWorkspaceProps {
  readonly binding: ProjectionContext;
  readonly missionState: SourceState;
  readonly observation?: OrganizationObservation;
  /** The incumbent authenticated Office acquisition, never a second Mission fetch. */
  readonly missionProjection?: OfficeProjection;
  readonly loading?: boolean;
  readonly onOpenProjects?: () => void;
  readonly onOpenProject?: (selection: { workRef: string; rootJobId: string }) => void;
  readonly onInspectWorkerResult?: (selection: ResultSelection) => void;
  /** Relocate the incumbent plan reader here; do not mount a second plan reader. */
  readonly planReader?: OrganizationPlanReader;
  readonly locale?: "en" | "zh-CN";
}

type Seat = { key: string; title: string; reports_to: string; live_enrollment: "NOT_OBSERVED"; authority_grant: false };
type Context = {
  organization: { human_root: { key: "chairman"; title: string }; seats: Seat[];
    caller: { charter_key: string; advisory_reporting_path: string[] } };
  goal_lineage: {
    company_goal: { state: "NOT_PROJECTED" };
    workstream: { work_ref: string; title: string | null; state: string | null; next_action: string | null };
    execution_root: { selected_root_job_id: string; role_to_job_assignment: "NOT_ESTABLISHED"; job_status: string | null };
    evidence: { result_reference_count: number; review_verdict: string; acceptance_state: string | null;
      original_parent_consumption: "NOT_ESTABLISHED"; product_acceptance: "NOT_ESTABLISHED" };
    source: { mission_fingerprint: string; generated_at: string; scope: "single_mission"; full_fleet: false };
  };
};

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function short(value: unknown, max = 160): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= max;
}

/** The browser may only *reduce* source claims. Malformed/partial payloads disappear. */
export function qualifyOrganization(
  binding: ProjectionContext, missionState: SourceState, observation?: OrganizationObservation,
): Context | null {
  if (!observation || missionState !== "CURRENT" || observation.sourceState !== "CURRENT" ||
      !binding.selection || !sameTarget(binding, observation.context) ||
      observation.context.authGeneration !== binding.authGeneration ||
      observation.missionRevision === null || observation.missionRevision !== binding.revisions.mission) return null;

  const value = observation.value;
  if (!record(value) || value.schema !== "mastermind.hermes_organization_context.v1" ||
      value.state !== "SOURCE_LINKED_ADVISORY" || value.reporting_lines_are_authoritative !== false ||
      value.assignments_are_authoritative !== false || value.admitted !== false ||
      value.dispatched !== false || value.reasoning_wake !== false ||
      !record(value.organization) || !record(value.goal_lineage)) return null;
  const organization = value.organization;
  const lineage = value.goal_lineage;
  if (!record(organization.human_root) || organization.human_root.key !== "chairman" ||
      !short(organization.human_root.title) || !Array.isArray(organization.seats) ||
      organization.seats.length < 1 || organization.seats.length > 32 ||
      !record(organization.caller) || !short(organization.caller.charter_key) ||
      !Array.isArray(organization.caller.advisory_reporting_path)) return null;

  const seen = new Set<string>(["chairman"]);
  for (const row of organization.seats) {
    if (!record(row) || !short(row.key, 64) || row.key === "chairman" || seen.has(row.key) ||
        !short(row.title) || !short(row.reports_to, 64) ||
        row.live_enrollment !== "NOT_OBSERVED" || row.authority_grant !== false) return null;
    seen.add(row.key);
  }
  const seats = organization.seats as Seat[];
  const byKey = new Map(seats.map(seat => [seat.key, seat]));
  for (const seat of seats) {
    let at = seat.key;
    const path = new Set<string>();
    while (at !== "chairman") {
      if (path.has(at) || !byKey.has(at)) return null;
      path.add(at);
      at = byKey.get(at)!.reports_to;
    }
  }
  const caller = organization.caller;
  const callerKey = caller.charter_key;
  const reportingPath = caller.advisory_reporting_path;
  if (!short(callerKey, 64) || !Array.isArray(reportingPath) ||
      !byKey.has(callerKey) ||
      reportingPath.length < 2 ||
      reportingPath.length > seats.length + 1 ||
      reportingPath[0] !== "chairman" ||
      reportingPath.at(-1) !== callerKey ||
      reportingPath.some((key: unknown, index: number, path: unknown[]) =>
        typeof key !== "string" || (index > 0 && byKey.get(key)?.reports_to !== path[index - 1]))) return null;

  if (!record(lineage.company_goal) || lineage.company_goal.state !== "NOT_PROJECTED" ||
      !record(lineage.workstream) || !record(lineage.execution_root) ||
      !record(lineage.evidence) || !record(lineage.source) ||
      lineage.workstream.work_ref !== binding.selection.workRef ||
      lineage.execution_root.selected_root_job_id !== binding.selection.rootJobId ||
      !short(lineage.workstream.work_ref, 128) ||
      !short(lineage.execution_root.selected_root_job_id, 128) ||
      ![lineage.workstream.title, lineage.workstream.state, lineage.workstream.next_action,
        lineage.execution_root.job_status, lineage.evidence.acceptance_state]
        .every(item => item === null || short(item)) ||
      lineage.execution_root.role_to_job_assignment !== "NOT_ESTABLISHED" ||
      lineage.evidence.original_parent_consumption !== "NOT_ESTABLISHED" ||
      lineage.evidence.product_acceptance !== "NOT_ESTABLISHED" ||
      !Number.isSafeInteger(lineage.evidence.result_reference_count) ||
      (lineage.evidence.result_reference_count as number) < 0 ||
      !short(lineage.evidence.review_verdict, 128) ||
      lineage.source.scope !== "single_mission" || lineage.source.full_fleet !== false ||
      !short(lineage.source.generated_at, 40) ||
      typeof lineage.source.mission_fingerprint !== "string" ||
      !/^[a-f0-9]{64}$/.test(lineage.source.mission_fingerprint)) return null;

  return { organization, goal_lineage: lineage } as Context;
}

const COPY = {
  "Organization": "组织架构",
  "Open Projects": "打开项目列表",
  "Choose a project, then check its source status or use its existing refresh action.": "选择项目后，查看其来源状态或使用现有刷新操作。",
  "Observed work and reporting": "已观测工作与汇报关系",
  "Configured reporting": "配置的汇报关系",
  "Role charters; session enrollment is not observed.": "职责设置；会话接入情况尚未确认。",
  "Reading organization…": "正在读取组织信息…",
  "Current work is unavailable for this identity and selection. Activity remains unknown.": "当前身份和选择下的工作信息不可用，活动仍未知。",
  "Read-only reporting view": "只读汇报架构",
  "The organization source has not been qualified for this selected mission. This is not evidence of no team or no work.":
    "此任务尚无已核验的组织来源。这不代表团队或工作不存在。",
  "Chairman": "主席",
  "Human direction": "人类决策",
  "Reports to": "汇报给",
  "Enrollment not observed": "尚未确认已接入",
  "Current workstream": "当前工作流",
  "Executive root": "Executive 根任务",
  "Source-qualified mission only": "仅限来源已核验任务",
  "Company goal not projected": "公司目标尚未提供",
  "Role assignment not established": "角色分配尚未证实",
  "Review": "审查",
  "Acceptance": "验收",
  "Approved": "已批准",
  "Rejected": "已拒绝",
  "Pending": "待审查",
  "Accepted": "已验收",
  "Not accepted": "未验收",
  "Not observed": "尚未观测",
  "Indexed result references": "索引结果引用",
  "Original parent consumption not established": "原始父任务消费尚未证实",
  "Product acceptance not established": "产品验收尚未证实",
  "not supplied": "未提供",
  "Source detail": "来源详情",
  "Advisory lines do not grant permissions or prove an active role. A result or green check does not prove acceptance.":
    "参考汇报关系不授予权限，也不证明角色正在运行。结果或绿色检查不等于验收。",
} as const;

export function OrganizationWorkspace({
  binding, missionState, observation, missionProjection, loading = false,
  onOpenProjects, onOpenProject, onInspectWorkerResult, planReader, locale = "en",
}: OrganizationWorkspaceProps) {
  const t = (key: keyof typeof COPY) => locale === "zh-CN" ? COPY[key] : key;
  const context = qualifyOrganization(binding, missionState, observation);
  const mission = qualifyOrganizationMission(binding, missionState, missionProjection);
  if (loading) return <section className="organization-workspace" lang={locale} aria-label={t("Organization")} aria-busy="true">
    <header className="organization-workspace__header"><h2>{t("Organization")}</h2></header>
    <p role="status">{t("Reading organization…")}</p>
    <div className="organization-workspace__skeleton" aria-hidden="true">
      <span /><span /><span /><span />
    </div>
  </section>;
  return <section className="organization-workspace" lang={locale} aria-label={t("Organization")}>
    <header className="organization-workspace__header">
      <h2>{t("Organization")}</h2>
      <span>{t(mission ? "Observed work and reporting" : "Read-only reporting view")}</span>
    </header>
    {mission && <OrganizationMissionView key={JSON.stringify([
      binding.authGeneration, binding.selection, binding.sessionRef, binding.bindingGeneration,
    ])} mission={mission} observedAt={missionProjection!.mission.source.observed_at!}
      onOpenProject={onOpenProject} onInspectWorkerResult={onInspectWorkerResult}
      hasPlanReader={!!planReader} locale={locale} />}
    {missionProjection && !mission && <p className="organization-workspace__notice" role="status">
      {t("Current work is unavailable for this identity and selection. Activity remains unknown.")}
    </p>}
    {!mission && onOpenProjects && <div className="organization-workspace__recovery">
      <p>{t("Choose a project, then check its source status or use its existing refresh action.")}</p>
      <button type="button" className="organization-workspace__action" onClick={onOpenProjects}>{t("Open Projects")}</button>
    </div>}
    {planReader && <AdmittedPlanInspector key={binding.authGeneration} {...planReader}
      selection={binding.selection ? { work_ref: binding.selection.workRef, root_job_id: binding.selection.rootJobId } : null}
      mission={mission} missionSourceState={mission ? "CURRENT" : "UNAVAILABLE"}
      missionObservedAt={mission ? missionProjection!.mission.source.observed_at : null} locale={locale} />}
    {!context ? <p className="organization-workspace__notice" role="status">{t("The organization source has not been qualified for this selected mission. This is not evidence of no team or no work.")}</p> : <>
      <div className="organization-workspace__reporting-heading">
        <h3>{t("Configured reporting")}</h3>
        <p className="organization-workspace__caption">{t("Role charters; session enrollment is not observed.")}</p>
      </div>
      <div className="organization-workspace__grid">
        <section aria-label={t("Chairman")}>
          <div className="organization-workspace__root"><strong>{context.organization.human_root.title}</strong><span>{t("Human direction")}</span></div>
          <ul className="organization-workspace__seats">
            {context.organization.seats.map(seat => <li key={seat.key}>
              <strong>{seat.title}</strong>
              <span>{t("Reports to")}: {seat.reports_to === "chairman"
                ? context.organization.human_root.title
                : context.organization.seats.find(other => other.key === seat.reports_to)!.title}</span>
              <small>{t("Enrollment not observed")}</small>
            </li>)}
          </ul>
        </section>
        <section className="organization-workspace__lineage" aria-label={t("Current workstream")}>
          <h3>{t("Current workstream")}</h3>
          <strong>{context.goal_lineage.workstream.title ?? context.goal_lineage.workstream.work_ref}</strong>
          <p>{context.goal_lineage.workstream.work_ref}</p>
          <p>{t("Company goal not projected")}</p>
          <h3>{t("Executive root")}</h3>
          <p>{context.goal_lineage.execution_root.selected_root_job_id}</p>
          <p>{t("Role assignment not established")}</p>
          <dl>
            <div><dt>{t("Review")}</dt><dd>{t(context.goal_lineage.evidence.review_verdict === "approve" ? "Approved" :
              context.goal_lineage.evidence.review_verdict === "reject" ? "Rejected" :
              ["PENDING", "NOT_YET"].includes(context.goal_lineage.evidence.review_verdict) ? "Pending" : "Not observed")}</dd></div>
            <div><dt>{t("Acceptance")}</dt><dd>{t(context.goal_lineage.evidence.acceptance_state === "ACCEPTED" ? "Accepted" :
              context.goal_lineage.evidence.acceptance_state === "NOT_ACCEPTED" ? "Not accepted" : "Not observed")}</dd></div>
            <div><dt>{t("Indexed result references")}</dt><dd>{context.goal_lineage.evidence.result_reference_count}</dd></div>
          </dl>
          <p>{t("Original parent consumption not established")}</p>
          <p>{t("Product acceptance not established")}</p>
          <small>{t("Source-qualified mission only")}</small>
        </section>
      </div>
      <details className="organization-workspace__source"><summary>{t("Source detail")}</summary>
        <p>{context.goal_lineage.source.generated_at} · {context.goal_lineage.source.scope}</p>
        <p className="organization-workspace__fingerprint">{context.goal_lineage.source.mission_fingerprint}</p>
        <p>{t("Advisory lines do not grant permissions or prove an active role. A result or green check does not prove acceptance.")}</p>
      </details>
    </>}
  </section>;
}
