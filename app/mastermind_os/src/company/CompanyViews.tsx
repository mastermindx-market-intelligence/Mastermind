import { SourceLink } from "./SourceLink";
import { TaskOutputs } from "./TaskOutputs";
import { useState } from "react";
import { RuntimeIntegrationView } from "./RuntimeIntegrationView";
import { CompanyConnectionsView } from "./CompanyConnectionsView";
import type {
  CompanyCollection,
  CompanyRecord,
  CompanySelection,
  CompanySnapshot,
} from "./contract";

type Props = {
  snapshot: CompanySnapshot;
  selection: CompanySelection;
  locale: "en" | "zh-CN";
  onSelect(selection: CompanySelection): void;
  onOpenProject?(workRef: string): void;
};
const value = (row: CompanyRecord, key: string, fallback = "—") =>
  row[key] === undefined ? fallback : String(row[key]);
const title = (row: CompanyRecord) =>
  value(
    row,
    "title",
    value(row, "name", value(row, "identifier", String(row.id))),
  );
function State({ row }: { row: CompanyRecord }) {
  const state = value(row, "status", "unknown");
  return (
    <span className="company-state" data-state={state}>
      {state.replaceAll("_", " ")}
    </span>
  );
}
function Empty({
  collection,
  zh,
}: {
  collection?: CompanyCollection;
  zh: boolean;
}) {
  return (
    <div className="company-empty" role="status">
      <strong>
        {collection?.state === "UNAVAILABLE"
          ? zh
            ? "此来源暂不可用"
            : "This source is unavailable"
          : zh
            ? "此视图暂无项目"
            : "Nothing in this source view yet"}
      </strong>
      <p>
        {collection?.state === "UNAVAILABLE"
          ? zh
            ? "其他公司视图仍可使用。未用示例数据填充此处。"
            : "Other company views remain available. No sample data has been substituted."
          : zh
            ? "保留当前范围；刷新将读取同一来源。"
            : "Keep this scope; refresh reads the same source."}
      </p>
      {collection?.code && <code>{collection.code}</code>}
    </div>
  );
}
function CollectionFoot({
  collection,
  zh,
  more,
}: {
  collection: CompanyCollection;
  zh: boolean;
  more?: () => void;
}) {
  return (
    <footer className="company-list-foot">
      <span>
        {zh ? "已载入的来源窗口" : "Loaded source window"} ·{" "}
        {collection.items.length}
        {collection.restrictedCount
          ? ` · ${collection.restrictedCount} ${zh ? "项不可访问" : "restricted"}`
          : ""}
      </span>
      {more && (
        <button type="button" onClick={more}>
          {zh ? "下一页" : "Next page"} →
        </button>
      )}
      {collection.hasMore && !more && (
        <span>
          {zh ? "还有更多来源记录" : "More records exist at the source"}
        </span>
      )}
    </footer>
  );
}
export function CompanyViews({
  snapshot,
  selection,
  locale,
  onSelect,
  onOpenProject,
}: Props) {
  const zh = locale === "zh-CN",
    t = (en: string, cn: string) => (zh ? cn : en);
  const [board, setBoard] = useState(false);
  const collection = snapshot.collections[selection.view];
  const items = collection?.items ?? [];
  const openTask = (row: CompanyRecord) =>
    onSelect({ view: "task", itemId: String(row.id) });
  const projectBinding = (id: string) =>
    snapshot.projectBindings.find((binding) => binding.projectId === id);
  const openProject = (row: CompanyRecord) =>
    onSelect({ view: "work", projectId: String(row.id) });
  const more =
    collection?.nextOffset !== null && collection?.nextOffset !== undefined
      ? () => onSelect({ ...selection, offset: collection.nextOffset! })
      : collection?.nextCursor
        ? () => onSelect({ ...selection, cursor: collection.nextCursor! })
        : undefined;
  const workRow = (row: CompanyRecord) => (
    <button
      type="button"
      className="company-work-card"
      key={row.id}
      onClick={() => openTask(row)}
    >
      <span className="company-kicker">
        {value(row, "identifier", String(row.id).slice(0, 8))}
      </span>
      <strong>{title(row)}</strong>
      <span className="company-row-meta">
        <State row={row} />
        <span>{value(row, "priority", "")}</span>
      </span>
    </button>
  );

  if (selection.view === "overview") {
    const labels = {
      people: t("Teammates", "团队成员"),
      projects: t("Projects", "项目"),
      work: t("Work", "工作"),
      routines: t("Routines", "例行工作"),
    };
    return (
      <>
        <div className="company-summary-grid">
          {Object.entries(labels).map(([key, label]) => {
            const source = snapshot.collections[key];
            return (
              <button
                type="button"
                className="company-summary-card"
                key={key}
                onClick={() =>
                  onSelect({ view: key as CompanySelection["view"] })
                }
              >
                <span>{label}</span>
                <strong>
                  {source?.state === "CURRENT"
                    ? `${source.items.length}${source.hasMore ? "+" : ""}`
                    : "—"}
                </strong>
                <small>
                  {source?.state === "CURRENT"
                    ? t("Visible in this source window", "当前来源窗口内可见")
                    : t("Source unavailable", "来源暂不可用")}
                </small>
              </button>
            );
          })}
        </div>
        <div className="company-two-column">
          <section className="company-section">
            <div className="company-section-heading">
              <h2>{t("Current work", "当前工作")}</h2>
              <button type="button" onClick={() => onSelect({ view: "work" })}>
                {t("All work", "全部工作")} →
              </button>
            </div>
            {snapshot.collections.work?.state === "CURRENT" &&
            snapshot.collections.work.items.length ? (
              <div className="company-work-grid">
                {snapshot.collections.work.items.slice(0, 6).map(workRow)}
              </div>
            ) : (
              <Empty collection={snapshot.collections.work} zh={zh} />
            )}
          </section>
          <section className="company-section">
            <h2>{t("The company and its runtime", "公司管理与执行运行时")}</h2>
            <p>
              {t(
                "Paperclip organizes the work. Existing Hermes profiles keep their sessions, memory and tools.",
                "Paperclip 组织工作；现有 Hermes 配置保留会话、记忆与工具。",
              )}
            </p>
            <dl className="company-facts">
              <dt>{t("Work management", "工作管理")}</dt>
              <dd>{snapshot.ownership.work}</dd>
              <dt>{t("Wake scheduling", "唤醒调度")}</dt>
              <dd>{snapshot.ownership.wake}</dd>
              <dt>{t("Bot runtime", "机器人运行时")}</dt>
              <dd>Hermes</dd>
              <dt>{t("Admission", "执行准入")}</dt>
              <dd>Executive</dd>
              <dt>{t("Model and account routing", "模型与账户路由")}</dt>
              <dd>Capacity Fabric</dd>
            </dl>
            <p className="company-muted">
              {t(
                "These are configured ownership references—not proof that a bot is running. Navigation does not start a worker.",
                "这是已配置的归属引用，不表示机器人正在运行。浏览页面不会启动工作进程。",
              )}
            </p>
          </section>
        </div>
        <CompanyConnectionsView snapshot={snapshot} locale={locale} onSelect={onSelect} onOpenProject={onOpenProject} />
      </>
    );
  }
  if (selection.view === "runtime")
    return <RuntimeIntegrationView snapshot={snapshot} locale={locale} />;
  if (selection.view === "task" && snapshot.item) {
    const task = snapshot.item,
      comments = snapshot.collections.comments,
      binding = projectBinding(value(task, "projectId", ""));
    return (
      <div className="company-two-column">
        <section className="company-section">
          <div className="company-section-heading">
            <div>
              <span className="company-kicker">
                {value(task, "identifier", String(task.id))}
              </span>
              <h2>{title(task)}</h2>
            </div>
            <State row={task} />
          </div>
          <p className="company-preserve">
            {value(
              task,
              "description",
              t("No source description supplied.", "来源未提供描述。"),
            )}
          </p>
          <TaskOutputs
            products={snapshot.collections.products}
            executions={snapshot.collections.executions}
            locale={locale}
          />
          <h3>{t("Task discussion", "任务讨论")}</h3>
          {comments?.state === "CURRENT" && comments.items.length ? (
            <div className="company-timeline">
              {comments.items.map((comment) => (
                <article key={comment.id}>
                  <div className="company-row-meta">
                    <strong>
                      {value(
                        comment,
                        "authorAgentId",
                        value(
                          comment,
                          "authorUserId",
                          t("Source author", "来源作者"),
                        ),
                      )}
                    </strong>
                    <time>{value(comment, "createdAt", "")}</time>
                  </div>
                  <p className="company-preserve">
                    {value(comment, "body", "")}
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <Empty collection={comments} zh={zh} />
          )}
          <p className="company-muted">
            {t(
              "Comments are read from the original task. Sending or waking an agent stays with its qualified owner.",
              "讨论来自原始任务；发送消息与唤醒机器人仍由已接入的负责人处理。",
            )}
          </p>
        </section>
        <section className="company-section">
          <h2>{t("Original context", "原始上下文")}</h2>
          <dl className="company-facts">
            <dt>{t("Task", "任务")}</dt>
            <dd>
              <code>{task.id}</code>
            </dd>
            <dt>{t("Project", "项目")}</dt>
            <dd>{value(task, "projectId")}</dd>
            <dt>{t("Parent", "父任务")}</dt>
            <dd>{value(task, "parentId")}</dd>
            <dt>{t("Assigned teammate", "受派成员")}</dt>
            <dd>{value(task, "assigneeAgentId", t("Unassigned", "未分派"))}</dd>
            <dt>{t("Source version", "来源版本")}</dt>
            <dd>{value(task, "statusVersion")}</dd>
          </dl>
          {task.projectId && (
            <button
              type="button"
              onClick={() =>
                onSelect({ view: "work", projectId: String(task.projectId) })
              }
            >
              {t("Project work", "项目工作")} →
            </button>
          )}
          {binding && onOpenProject && (
            <button
              type="button"
              onClick={() => onOpenProject(binding.workRef)}
            >
              {t("Open original OS project", "打开原 OS 项目")} →
            </button>
          )}
          <div className="company-inset">
            <strong>
              {t(
                "Work status is not a release receipt.",
                "工作状态不等于发布回执。",
              )}
            </strong>
            <p>
              {t(
                "A completed task does not establish that a PR was merged, an app deployed, or the original outcome accepted.",
                "任务完成不能证明 PR 已合并、应用已部署或原始目标已验收。",
              )}
            </p>
          </div>
        </section>
      </div>
    );
  }
  if (selection.view === "routine" && snapshot.item)
    return (
      <>
        <section className="company-section">
          <div className="company-section-heading">
            <h2>{title(snapshot.item)}</h2>
            <State row={snapshot.item} />
          </div>
          <p className="company-preserve">
            {value(snapshot.item, "description", "")}
          </p>
          <p>
            {t(
              "Definition and history come from the existing Paperclip routine. No schedule is activated by opening this page.",
              "定义与历史来自现有 Paperclip 例行工作；打开此页不会启用调度。",
            )}
          </p>
        </section>
        <div className="company-two-column">
          {(["runs", "revisions"] as const).map((kind) => {
            const source = snapshot.collections[kind];
            return (
              <section className="company-section" key={kind}>
                <h2>
                  {kind === "runs"
                    ? t("Run history", "执行历史")
                    : t("Definition revisions", "定义版本")}
                </h2>
                {source?.state === "CURRENT" && source.items.length ? (
                  <div className="company-timeline">
                    {source.items.map((row) => (
                      <article key={row.id}>
                        <div className="company-row-meta">
                          <strong>
                            {kind === "runs"
                              ? value(row, "status")
                              : `${t("Version", "版本")} ${value(row, "revisionNumber")}`}
                          </strong>
                          <time>
                            {value(
                              row,
                              "createdAt",
                              value(row, "startedAt", ""),
                            )}
                          </time>
                        </div>
                        <p>
                          {value(
                            row,
                            "changeSummary",
                            value(row, "issueId", String(row.id)),
                          )}
                        </p>
                      </article>
                    ))}
                  </div>
                ) : (
                  <Empty collection={source} zh={zh} />
                )}
              </section>
            );
          })}
        </div>
      </>
    );
  if (!collection || collection.state === "UNAVAILABLE" || !items.length)
    return <Empty collection={collection} zh={zh} />;
  if (selection.view === "people")
    return (
      <>
        <div className="company-people-grid">
          {items.map((agent) => {
            const runtime = snapshot.runtimeBindings.find(
              (binding) => binding.agentId === agent.id,
            );
            const manager = items.find(
              (person) => person.id === agent.reportsTo,
            );
            return (
              <article className="company-section" key={agent.id}>
                <div className="company-section-heading">
                  <div className="company-avatar" aria-hidden="true">
                    {title(agent).slice(0, 1)}
                  </div>
                  <State row={agent} />
                </div>
                <h2>{title(agent)}</h2>
                <p>{value(agent, "title", value(agent, "role", ""))}</p>
                <dl className="company-facts">
                  <dt>{t("Reports to", "汇报对象")}</dt>
                  <dd>
                    {manager
                      ? title(manager)
                      : agent.reportsTo
                        ? t("Manager outside this loaded view", "汇报对象不在当前已载入视图中")
                        : t("No manager recorded", "未记录汇报对象")}
                  </dd>
                  <dt>{t("Paperclip adapter", "Paperclip 适配器")}</dt>
                  <dd>{value(agent, "adapterType")}</dd>
                  <dt>{t("Retained Hermes profile", "保留的 Hermes 配置")}</dt>
                  <dd>{runtime?.profileRef ?? t("Not bound", "尚未绑定")}</dd>
                </dl>
                <button
                  type="button"
                  onClick={() =>
                    onSelect({ view: "runtime", itemId: String(agent.id) })
                  }
                >
                  {t("Runtime integration", "运行时接入")} →
                </button>
                <details>
                  <summary>
                    {t("Identity and runtime binding", "身份与运行时绑定")}
                  </summary>
                  <code>{agent.id}</code>
                  {runtime ? (
                    <>
                      <p>
                        {t("Gateway reference", "网关引用")}:{" "}
                        {runtime.gatewayRef}
                      </p>
                      <p>
                        {t("Supervisor session", "主管会话")}:{" "}
                        {runtime.supervisorSessionRef ?? "—"}
                      </p>
                      <p className="company-muted">
                        {t(
                          "Configured reference; live attachment has not been established by this screen.",
                          "配置引用；此屏幕不证明实时连接已建立。",
                        )}
                      </p>
                    </>
                  ) : (
                    <p>
                      {t(
                        "Adopt the existing profile; do not create another bot to fill this slot.",
                        "接入现有配置，不要为此创建另一个机器人。",
                      )}
                    </p>
                  )}
                </details>
              </article>
            );
          })}
        </div>
        <CollectionFoot collection={collection} zh={zh} more={more} />
      </>
    );
  if (selection.view === "work")
    return (
      <>
        <div className="company-work-toolbar">
          <div role="group" aria-label={t("Work layout", "工作布局")}>
            <button
              type="button"
              aria-pressed={!board}
              onClick={() => setBoard(false)}
            >
              {t("List", "列表")}
            </button>
            <button
              type="button"
              aria-pressed={board}
              onClick={() => setBoard(true)}
            >
              {t("Board", "看板")}
            </button>
          </div>
          <label>
            {t("Status", "状态")}{" "}
            <select
              value={selection.status ?? ""}
              onChange={(event) =>
                onSelect({
                  view: "work",
                  ...(selection.projectId
                    ? { projectId: selection.projectId }
                    : {}),
                  ...(event.target.value ? { status: event.target.value } : {}),
                })
              }
            >
              <option value="">{t("All", "全部")}</option>
              {[
                "backlog",
                "todo",
                "in_progress",
                "in_review",
                "done",
                "blocked",
                "cancelled",
              ].map((status) => (
                <option key={status} value={status}>
                  {status.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
        </div>
        {board ? (
          <div className="company-board">
            {[
              "backlog",
              "todo",
              "in_progress",
              "in_review",
              "blocked",
              "done",
              "cancelled",
            ]
              .filter((status) => items.some((row) => row.status === status))
              .map((status) => (
                <section key={status}>
                  <h3>{status.replaceAll("_", " ")}</h3>
                  {items.filter((row) => row.status === status).map(workRow)}
                </section>
              ))}
          </div>
        ) : (
          <div className="company-work-grid">{items.map(workRow)}</div>
        )}
        <CollectionFoot collection={collection} zh={zh} more={more} />
      </>
    );
  if (selection.view === "projects")
    return (
      <>
        <div className="company-people-grid">
          {items.map((project) => {
            const binding = projectBinding(String(project.id));
            return (
              <article className="company-section" key={project.id}>
                <State row={project} />
                <h2>{title(project)}</h2>
                <p>{value(project, "description", "")}</p>
                <div className="company-inline-actions">
                  <button type="button" onClick={() => openProject(project)}>
                    {t("Open work", "查看工作")} →
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      onSelect({
                        view: "artifacts",
                        projectId: String(project.id),
                      })
                    }
                  >
                    {t("Artifacts", "成果")}
                  </button>
                  {binding && onOpenProject && (
                    <button
                      type="button"
                      onClick={() => onOpenProject(binding.workRef)}
                    >
                      {t("Original OS project", "原 OS 项目")} ↗
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
        <CollectionFoot collection={collection} zh={zh} more={more} />
      </>
    );
  if (selection.view === "routines")
    return (
      <>
        <div className="company-people-grid">
          {items.map((routine) => (
            <article className="company-section" key={routine.id}>
              <State row={routine} />
              <h2>{title(routine)}</h2>
              <p>{value(routine, "description", "")}</p>
              <button
                type="button"
                onClick={() =>
                  onSelect({ view: "routine", itemId: String(routine.id) })
                }
              >
                {t("Definition and history", "定义与历史")} →
              </button>
            </article>
          ))}
        </div>
        <CollectionFoot collection={collection} zh={zh} more={more} />
      </>
    );
  if (selection.view === "artifacts")
    return (
      <>
        <div className="company-people-grid">
          {items.map((artifact) => (
            <article className="company-section" key={artifact.id}>
              <span className="company-kicker">
                {value(
                  artifact,
                  "mediaKind",
                  value(artifact, "sourceKind", "Artifact"),
                )}
              </span>
              <h2>{title(artifact)}</h2>
              <p className="company-muted">
                {value(artifact, "updatedAt", value(artifact, "createdAt", ""))}
              </p>
              <div className="company-inline-actions">
                <SourceLink
                  row={artifact}
                  label={t("Open source", "打开来源")}
                />
                {artifact.issueId && (
                  <button
                    type="button"
                    onClick={() =>
                      onSelect({
                        view: "task",
                        itemId: String(artifact.issueId),
                      })
                    }
                  >
                    {t("Original task", "原任务")} →
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
        <CollectionFoot collection={collection} zh={zh} more={more} />
      </>
    );
  if (selection.view === "activity")
    return (
      <section className="company-section">
        <div className="company-timeline">
          {items.map((event) => (
            <article key={event.id}>
              <div className="company-row-meta">
                <strong>{value(event, "action")}</strong>
                <time>{value(event, "createdAt", "")}</time>
              </div>
              <p>
                {value(event, "actorType", "")} · {value(event, "actorId", "")}{" "}
                → {value(event, "entityType", "")} ·{" "}
                {value(event, "entityId", "")}
              </p>
            </article>
          ))}
        </div>
        <CollectionFoot collection={collection} zh={zh} />
      </section>
    );
  return (
    <>
      <div className="company-people-grid">
        {items.map((goal) => (
          <article className="company-section" key={goal.id}>
            <State row={goal} />
            <h2>{title(goal)}</h2>
            <p>{value(goal, "description", "")}</p>
            <dl className="company-facts">
              <dt>{t("Level", "层级")}</dt>
              <dd>{value(goal, "level")}</dd>
              <dt>{t("Parent goal", "上级目标")}</dt>
              <dd>{value(goal, "parentId")}</dd>
            </dl>
          </article>
        ))}
      </div>
      <CollectionFoot collection={collection} zh={zh} more={more} />
    </>
  );
}
