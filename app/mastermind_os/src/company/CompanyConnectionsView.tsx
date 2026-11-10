import type { CompanyRecord, CompanySelection, CompanySnapshot } from "./contract";
import type { CompanyConnection, ConnectionRef } from "./connections";

const collectionFor: Record<string, string> = { agent: "people", project: "projects", goal: "goals", issue: "work" };
const labels: Record<string, [string, string]> = {
  reports_to: ["reports to", "汇报给"], project_goal: ["supports", "支持目标"],
  project_lead: ["is led by", "负责人是"], goal_parent: ["supports", "支持目标"],
  goal_owner: ["is owned by", "负责人是"], issue_parent: ["is part of", "属于"],
  issue_project: ["belongs to", "所属项目"], issue_goal: ["supports", "支持目标"],
  issue_assignee: ["is assigned to", "分配给"], runs_as: ["has a retained profile", "保留运行配置"],
  tracks_work: ["links to project context", "关联项目上下文"],
};
const rowTitle = (row: CompanyRecord) => String(row.title ?? row.name ?? row.identifier ?? "");

export function CompanyConnectionsView({ snapshot, locale, onSelect, onOpenProject }: {
  snapshot: CompanySnapshot; locale: "en" | "zh-CN";
  onSelect(selection: CompanySelection): void; onOpenProject?(workRef: string): void;
}) {
  const graph = snapshot.connections, zh = locale === "zh-CN";
  const t = (en: string, cn: string) => zh ? cn : en;
  if (!graph) return null;
  const visible = (reference: ConnectionRef) => reference.owner === "paperclip"
    ? snapshot.collections[collectionFor[reference.kind] ?? ""]?.items.find(row => String(row.id).toLowerCase() === reference.id)
    : undefined;
  const renderRef = (reference: ConnectionRef) => {
    const row = visible(reference);
    if (!row) return <span>{reference.owner === "hermes" ? t("Hermes profile", "Hermes 运行配置")
      : reference.owner === "agentos" ? t("Linked project context", "关联项目上下文")
      : t("Outside this loaded view", "不在当前已载入视图中")}</span>;
    const selection: CompanySelection = reference.kind === "agent" ? { view: "runtime", itemId: reference.id }
      : reference.kind === "project" ? { view: "work", projectId: reference.id }
      : reference.kind === "issue" ? { view: "task", itemId: reference.id } : { view: "goals" };
    return <button type="button" onClick={() => onSelect(selection)}>{rowTitle(row) || t("Open source record", "打开来源记录")}</button>;
  };
  const row = (edge: CompanyConnection, index: number) => <li key={`${edge.relation}:${edge.from.id}:${index}`}>
    {renderRef(edge.from)} {labels[edge.relation]?.[zh ? 1 : 0]} {renderRef(edge.to)}
    {edge.relation === "tracks_work" && onOpenProject && <button type="button" onClick={() => onOpenProject(edge.to.id)}>
      {t("Open project", "打开项目")}</button>}
  </li>;
  return <section className="company-section" aria-label={t("Team connections", "团队关系")}>
    <div className="company-section-heading">
      <h2>{t("Team connections", "团队关系")}</h2>
      <button type="button" onClick={() => onSelect({ view: "people" })}>{t("Find a teammate", "查找团队成员")} →</button>
    </div>
    <p>{t("See who owns the work and how projects connect.", "查看工作负责人以及项目之间的关系。")}</p>
    {graph.state === "WITHHELD" ? <p role="status">{t("These relationships need checking. Source records remain available.", "这些关系需要核对。来源记录仍可查看。")}</p>
      : graph.relationships.length ? <ul>{graph.relationships.slice(0, 6).map(row)}</ul>
      : <p>{t("No relationships are included in this loaded view.", "当前已载入视图未包含关系。")}</p>}
    <details>
      <summary>{t("All loaded connections and available help", "全部已载入关系与协作途径")}</summary>
      {graph.relationships.length > 6 && <ul>{graph.relationships.slice(6).map(row)}</ul>}
      <p>{t("Direct consultation, delegation and resume are not connected to this view yet.", "此视图暂未连接直接咨询、任务委派和恢复执行。")}</p>
      <p>{t("Reporting lines and task parentage do not establish execution dependencies or accepted results.", "汇报关系与任务层级不代表执行依赖或结果已被验收。")}</p>
      <p>{t("Configured profiles identify retained runtimes; current availability is checked separately.", "已配置的运行配置标识保留的运行时；当前可用性需要另行核验。")}</p>
      {graph.findings.map((finding, index) => <p key={index}><code>{finding.code}</code> · <code>{finding.relation}</code></p>)}
      <button type="button" onClick={() => onSelect({ view: "projects" })}>{t("View project work", "查看项目工作")}</button>
    </details>
    <p className="company-muted">{graph.outsideWindowCount || graph.state === "PARTIAL"
      ? t("This view is partial; some sources or related records are not loaded.", "此视图不完整；部分来源或关联记录尚未载入。")
      : t("These sources are read separately; refresh before acting on changed work.", "各来源分别读取；处理已变化的工作前请刷新。")}</p>
  </section>;
}
