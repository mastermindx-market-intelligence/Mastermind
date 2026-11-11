import type { CompanySnapshot } from "./contract";

const requirementCopy: Record<string, readonly [string, string]> = {
  EXCLUSIVE_CONFIGURATION_WRITER: [
    "Reconcile the current configuration writer before changing this agent.",
    "更改此成员前，先核对当前配置写入者。",
  ],
  ORIGINAL_RUNS_AND_EFFECTS_RECONCILED: [
    "Retain and reconcile existing runs and outstanding source effects.",
    "保留并核对现有执行及尚未确认的来源变更。",
  ],
  QUALIFIED_EXISTING_HTTP_SSE_GATEWAY: [
    "Bind the existing Hermes HTTP/SSE service; the private native bridge is a different protocol.",
    "绑定现有 Hermes HTTP/SSE 服务；私有原生桥接使用不同协议。",
  ],
  EXISTING_SECRET_BINDING: [
    "Resolve the existing gateway credential through its current secret owner.",
    "通过现有凭据管理者解析网关凭据。",
  ],
  EXECUTIVE_AND_CAPACITY_CONSUMER_BINDINGS: [
    "Connect actual Executive admission and Capacity placement before unattended work.",
    "在无人值守执行前，接入真实的 Executive 准入与 Capacity 分配。",
  ],
  EXISTING_HERMES_PROFILE_REFERENCE: [
    "Select the already-enrolled Hermes profile, not a replacement bot.",
    "选择已接入的 Hermes 配置，不创建替代机器人。",
  ],
  ORIGINAL_SUPERVISOR_RETURN_REFERENCE: [
    "Retain the original supervisor conversation and result-return destination.",
    "保留原主管对话与成果返回位置。",
  ],
  DONOR_RUNTIME_MISMATCH: [
    "The current source adapter is not a qualified Hermes adapter.",
    "当前来源适配器不是已确认的 Hermes 适配器。",
  ],
  WORK_OWNER_CUTOVER: [
    "Move work authority from the legacy board to Paperclip once; avoid dual writes.",
    "将工作管理权一次性从旧看板迁移到 Paperclip，避免双重写入。",
  ],
  WAKE_OWNER_CUTOVER: [
    "Transfer wake scheduling only after the old trigger owner is fenced.",
    "旧触发器停止接管新工作后，再转移唤醒调度权。",
  ],
};

export function RuntimeIntegrationView({
  snapshot,
  locale,
}: {
  snapshot: CompanySnapshot;
  locale: "en" | "zh-CN";
}) {
  const agent = snapshot.item,
    migration = snapshot.migration;
  if (!agent || !migration) return null;
  const zh = locale === "zh-CN";
  const t = (en: string, cn: string) => (zh ? cn : en);
  return (
    <>
      <section className="company-section">
        <div className="company-section-heading">
          <div>
            <span className="company-kicker">
              {t(
                "EXISTING TEAMMATE / RUNTIME INTEGRATION",
                "现有成员 / 运行时集成",
              )}
            </span>
            <h2>{String(agent.name ?? agent.title ?? agent.id)}</h2>
          </div>
          <span className="company-state">
            {t("Prepared · Not applied", "已准备 · 未应用")}
          </span>
        </div>
        <p>
          {t(
            "Move company coordination into Paperclip without replacing the bot that knows your work.",
            "将公司协作管理移入 Paperclip，同时保留熟悉你工作上下文的机器人。",
          )}
        </p>
        <dl className="company-facts">
          <dt>{t("Existing agent", "现有成员")}</dt>
          <dd>
            <code>{agent.id}</code>
          </dd>
          <dt>{t("Current source adapter", "当前来源适配器")}</dt>
          <dd>{String(agent.adapterType ?? "—")}</dd>
          <dt>{t("Current source status", "当前来源状态")}</dt>
          <dd>{String(agent.status ?? "—")}</dd>
          <dt>{t("Intended adapter", "目标适配器")}</dt>
          <dd>
            <code>{migration.targetAdapter}</code>
          </dd>
          <dt>{t("Retained Hermes profile", "保留的 Hermes 配置")}</dt>
          <dd>{migration.profileRef ?? t("Not bound", "尚未绑定")}</dd>
          <dt>{t("Existing gateway reference", "现有网关引用")}</dt>
          <dd>{migration.gatewayRef ?? t("Not bound", "尚未绑定")}</dd>
        </dl>
      </section>
      <div className="company-two-column">
        <section className="company-section">
          <h2>{t("Replace the management layer", "替换管理层")}</h2>
          <p>
            {t(
              "Paperclip owns the company directory, goals, project coordination, work board, routine definitions and attention views. Work and wake authority are transferred separately.",
              "Paperclip 管理公司目录、目标、项目协作、工作看板、例行工作定义与待处理事项。工作管理与唤醒调度分别迁移。",
            )}
          </p>
          <dl className="company-facts">
            <dt>{t("Configured work owner", "已配置的工作管理者")}</dt>
            <dd>{snapshot.ownership.work}</dd>
            <dt>{t("Configured wake owner", "已配置的唤醒管理者")}</dt>
            <dd>{snapshot.ownership.wake}</dd>
            <dt>{t("Execution admission", "执行准入")}</dt>
            <dd>Executive</dd>
            <dt>{t("Model and account placement", "模型与账户分配")}</dt>
            <dd>Capacity Fabric</dd>
          </dl>
          <div className="company-inset">
            <strong>
              {t(
                "One active owner for each capability.",
                "每项能力只有一个主动管理者。",
              )}
            </strong>
            <p>
              {t(
                "An owner label is not proof of a completed cutover. Retire the corresponding legacy trigger before enabling its Paperclip successor; do not run both.",
                "管理者标签不代表切换已经完成。启用 Paperclip 对应功能前，应停止旧触发器接管新工作，不让两者同时运行。",
              )}
            </p>
          </div>
        </section>
        <section className="company-section">
          <h2>{t("Retain the Hermes bot", "保留 Hermes 机器人")}</h2>
          <p>
            {t(
              "Keep the enrolled profile, memory, skills, tool permissions, provider configuration and native conversation history. Paperclip coordinates the work; Hermes still executes it.",
              "保留已接入的配置、记忆、技能、工具权限、模型配置与原生对话历史。Paperclip 协调工作，Hermes 继续执行。",
            )}
          </p>
          <dl className="company-facts">
            <dt>{t("Supervisor conversation", "主管对话")}</dt>
            <dd>
              {migration.supervisorSessionRef ??
                t("Original reference required", "需要原始引用")}
            </dd>
            <dt>{t("Project execution sessions", "项目执行会话")}</dt>
            <dd>
              {t("One retained context per issue", "每个任务保留独立上下文")}
            </dd>
            <dt>{t("Work session strategy", "工作会话策略")}</dt>
            <dd>
              <code>{migration.workSessionStrategy}</code>
            </dd>
          </dl>
          <p className="company-muted">
            {t(
              "A persistent teammate is not one endless transcript for every project. Direct steering keeps the supervisor session; issue execution keeps its own context and original return link.",
              "持续存在的成员不等于所有项目共享一条无限对话。直接指挥保留主管会话；任务执行保留各自上下文及原始返回链接。",
            )}
          </p>
        </section>
      </div>
      <section className="company-section">
        <h2>{t("Integration requirements", "接入要求")}</h2>
        <div className="company-timeline">
          {migration.requirements.map((requirement) => {
            const copy = requirementCopy[requirement];
            return (
              <article key={requirement}>
                <p>{copy ? copy[zh ? 1 : 0] : requirement}</p>
              </article>
            );
          })}
        </div>
        <details>
          <summary>
            {t(
              "Why this screen does not apply a runtime switch",
              "为何此屏幕不直接切换运行时",
            )}
          </summary>
          <p>
            {t(
              "The pinned upstream general agent update has no expected-revision check. A snapshot digest is not an atomic write fence. Applying a switch requires the existing configuration owner and original effects to be reconciled first.",
              "已固定版本的上游成员更新接口没有预期版本校验。快照摘要不是原子写入保护。应用切换前，需要先核对现有配置管理者与原始执行结果。",
            )}
          </p>
          <p>
            {t(
              "No bot has been cloned, unpaused or restarted. No credential has been copied, no schedule enabled and no model execution requested by preparing this view.",
              "准备此视图不会克隆、解除暂停或重启机器人，不会复制凭据、启用调度或请求模型执行。",
            )}
          </p>
        </details>
      </section>
    </>
  );
}
