import {
  decodeCurrentProjectAccess,
  validProjectAccessSelection,
  type ProjectAccessSelection,
} from "./project-access-current";
import "./project-access.css";

export interface ProjectAccessPanelProps {
  selection: ProjectAccessSelection | null;
  canRead: boolean;
  sourceGeneration: string;
  source: { data: unknown; generation: string } | null;
  reading?: boolean;
  failed?: boolean;
  onReadCurrent?: () => void;
  locale?: "en" | "zh-CN";
}
const COPY = {
  en: {
    title: "Project permissions",
    note: "Review the permissions supplied for your Workspace membership. Each action still has its own checks.",
    read: "Read current access",
    reading: "Reading…",
    idle: "Current permissions have not been read here.",
    unavailable: "Current permissions are unavailable.",
    member: "You can read this project’s information.",
    legacy:
      "Additional project permissions were not declared in this membership.",
    older:
      "This version of the view supplies no record for latest-data reading or draft-plan publication.",
    supplied: "Supplied",
    absent: "Not supplied here",
    workspace: "Workspace scope",
    instruction: "Instruction",
    details: "Source details",
    project: "Project",
    commit: "Project record commit",
    sha: "Project record digest",
    scope: "Grant scope",
    more: "Other permission records",
    grantVersion: "Membership grant version",
    raw: "Action identifier",
    reason: "Unavailable reason",
  },
  "zh-CN": {
    title: "项目权限",
    note: "查看为您的工作区成员身份提供的权限。每项操作仍须通过其各自的检查。",
    read: "读取当前访问权限",
    reading: "正在读取…",
    idle: "此处尚未读取当前权限。",
    unavailable: "暂时无法获取当前权限。",
    member: "您可以读取此项目的信息。",
    legacy: "此成员身份未声明额外的项目权限。",
    older: "此版本的视图未提供最新数据读取或计划提案草稿发布的权限记录。",
    supplied: "已提供",
    absent: "此处未提供",
    workspace: "工作区范围",
    instruction: "指令",
    details: "来源详情",
    project: "项目",
    commit: "项目记录提交",
    sha: "项目记录摘要",
    scope: "授权范围",
    more: "其他权限记录",
    grantVersion: "成员授权版本",
    raw: "操作标识",
    reason: "不可用原因",
  },
} as const;
const LABELS = {
  en: {
    publish_project_proposal: "Publish a project proposal",
    pause_workstream_admission: "Pause new project work",
    resume_workstream_admission: "Resume new project work",
    ADOPT_PLAN: "Adopt a project plan",
    ACCEPT_DIRECTION: "Accept a project direction",
    add_project_file: "Add a project file",
    set_project_communication_preference:
      "Change project communication preferences",
    pause_instruction_admission: "Pause new work from one instruction",
    publish_project_plan_proposal: "Publish a draft plan proposal",
    read_latest_project_data: "Read the latest project data",
  },
  "zh-CN": {
    publish_project_proposal: "发布项目提案",
    pause_workstream_admission: "暂停项目新工作",
    resume_workstream_admission: "恢复项目新工作",
    ADOPT_PLAN: "采用项目计划",
    ACCEPT_DIRECTION: "接受项目方向",
    add_project_file: "添加项目文件",
    set_project_communication_preference: "更改项目沟通偏好",
    pause_instruction_admission: "暂停来自一条指令的新工作",
    publish_project_plan_proposal: "发布计划提案草稿",
    read_latest_project_data: "读取最新项目数据",
  },
} as const;
export function ProjectAccessPanel({
  selection,
  canRead,
  sourceGeneration,
  source,
  reading = false,
  failed = false,
  onReadCurrent,
  locale = "en",
}: ProjectAccessPanelProps) {
  const t = COPY[locale];
  const valid = selection !== null && validProjectAccessSelection(selection);
  const body =
    canRead && valid && source?.generation === sourceGeneration
      ? decodeCurrentProjectAccess(source.data, selection)
      : null;
  const current = body?.availability === "AVAILABLE" ? body : null;
  const rows = current?.declaration === "SUPPLIED" ? [...current.grants] : [];
  // Knowledge's distinct DATA/proposal facts stay visible; no new authority is
  // inferred from their display. At most eight rows remain at the first level.
  const priority = [
    "read_latest_project_data",
    "add_project_file",
    "set_project_communication_preference",
    "publish_project_plan_proposal",
  ];
  if (body?.schema === "mastermind.workspace_project_access.v2")
    rows.sort(
      (a, b) =>
        (priority.includes(a.action)
          ? priority.indexOf(a.action)
          : priority.length) -
        (priority.includes(b.action)
          ? priority.indexOf(b.action)
          : priority.length),
    );
  const visible = rows.slice(0, 8),
    more = rows.slice(8);
  const renderRows = (items: typeof rows) => (
    <dl className="project-access__grants">
      {items.map((row) => (
        <div key={row.action}>
          <dt>{LABELS[locale][row.action]}</dt>
          <dd>
            {row.supply === "SUPPLIED" ? t.supplied : t.absent}
            {row.scope === "WORKSPACE" && (
              <span className="project-access__scope">{t.workspace}</span>
            )}
            {row.instruction_ref && (
              <span className="project-access__scope">
                {t.instruction}: {row.instruction_ref}
              </span>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
  return (
    <section className="project-access" lang={locale} aria-label={t.title}>
      <header>
        <div>
          <h3>{t.title}</h3>
          <p>{t.note}</p>
        </div>
        {onReadCurrent && (
          <button
            type="button"
            disabled={!canRead || !valid || reading}
            onClick={onReadCurrent}
          >
            {reading ? t.reading : t.read}
          </button>
        )}
      </header>
      <p role="status">
        {current ? t.member : !canRead || source || failed ? t.unavailable : t.idle}
      </p>
      {current?.declaration === "NOT_DECLARED" && <p>{t.legacy}</p>}
      {current?.schema === "mastermind.workspace_project_access.v1" &&
        current.declaration === "SUPPLIED" && <p>{t.older}</p>}
      {visible.length > 0 && renderRows(visible)}
      {more.length > 0 && (
        <details>
          <summary>
            {t.more} ({more.length})
          </summary>
          {renderRows(more)}
        </details>
      )}
      {body && (
        <details>
          <summary>{t.details}</summary>
          <dl className="project-access__source">
            <dt>{t.project}</dt>
            <dd>{body.selection.work_ref}</dd>
            {current && (
              <>
                {current.schema ===
                  "mastermind.workspace_project_access.v2" && (
                  <>
                    <dt>{t.grantVersion}</dt>
                    <dd>{current.grant_schema}</dd>
                  </>
                )}
                <dt>{t.commit}</dt>
                <dd>{current.source.commit}</dd>
                <dt>{t.sha}</dt>
                <dd>{current.source.content_sha256}</dd>
              </>
            )}
            {body.availability === "UNAVAILABLE" && (
              <>
                <dt>{t.reason}</dt>
                <dd>{body.reason_codes.join(", ")}</dd>
              </>
            )}
          </dl>
          {current?.declaration === "SUPPLIED" && (
            <ul>
              {current.grants.map((row) => (
                <li key={row.action}>
                  {t.raw}: {row.action} · {t.scope}: {row.scope}
                </li>
              ))}
            </ul>
          )}
        </details>
      )}
    </section>
  );
}
