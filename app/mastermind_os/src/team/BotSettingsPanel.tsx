import { useEffect, useId, useRef, useState } from "react";
import type { MissionHost } from "../host";
import type {
  ModelConfiguration,
  ModelConfigurationRead as ConfigurationRead,
} from "../resources/model-configuration";
import type { TeamBot } from "./team-roster";
import { TeamSurfaceDialog } from "./TeamSurfaceDialog";

/** HC09 — Bot settings: Models tab. Every provider, model, effort level and
 *  fallback tier shown comes from the host's real model-configuration read
 *  (decodeModelConfiguration's fail-closed contract). When that read is not
 *  exposed, unauthorized, or refused, the tab renders the honest unavailable
 *  state with its reason code and shows NO model or provider names — the
 *  Paper samples ("GLM Fabric", "GLM 5.3") are never shipped as values. The
 *  configuration contract is read-only (writes_applied: false), so the
 *  controls preview policy and apply nothing. */
type ModelsState =
  | { kind: "PENDING" }
  | { kind: "UNAVAILABLE"; reason: string }
  | { kind: "AVAILABLE"; read: Extract<ConfigurationRead, { state: "AVAILABLE" }> };

const TAB_KEYS = [
  "overview",
  "models",
  "capabilities",
  "memory",
  "routines",
] as const;
type TabKey = (typeof TAB_KEYS)[number];

const STRINGS = {
  en: {
    title: "Bot settings",
    tabsLabel: "Bot settings sections",
    tab: {
      overview: "Overview",
      models: "Models",
      capabilities: "Capabilities",
      memory: "Memory",
      routines: "Routines",
    } as Record<TabKey, string>,
    placeholderTitle: "Not projected in this build",
    placeholderBody:
      "This section of bot settings is not projected in this build. Nothing about it is shown or inferred.",
    modelDefaultsHeading: "Model defaults",
    modelDefaultsNote: "Used when this bot starts a new session.",
    readOnlyChip: "EFFECT·NONE",
    readOnlyNote:
      "This tab reads the team's model policy. Choices made here preview the policy and apply nothing — the model router owns it.",
    providerLabel: "Provider connection",
    providerTeamDefault: "Team default",
    providerEnabled: "Enabled in policy",
    providerDisabled: "Disabled in policy",
    modelLabel: "Main model",
    modelTeamDefault: "Follow team policy",
    reasoningLabel: "Reasoning level",
    reasoningFromAlias: (effort: string) => effort,
    reasoningFollows: "Follows the selected model's policy",
    fallbackLabel: "Fallback",
    fallbackNote:
      "Used only when the selected provider is unavailable.",
    fallbackChain: (chain: string) => `Configured fallback order: ${chain}`,
    auxiliaryLabel: "Auxiliary tasks",
    auxiliaryValue: "Team default",
    auxiliaryNote: (count: number) =>
      count > 0
        ? `Follows the team policy (${count} configured model aliases).`
        : "Follows the team policy.",
    subagentLabel: "Subagent tasks",
    subagentValue: "Managed placement ›",
    subagentNote:
      "Placement of subagents is managed by the model router; it is not changed from this surface.",
    advanced: "Advanced · context and mixtures",
    unavailableChip: "Model policy not verified",
    unavailableBody:
      "The team's model configuration could not be read on this connection. No provider, model or reasoning level is shown or inferred.",
    reasonLabel: "Model configuration read",
    reasons: {
      READ_NOT_EXPOSED:
        "This host does not expose the model-configuration read.",
      MODEL_CONFIGURATION_UNAUTHORIZED:
        "The read needs a signed-in workspace acquisition.",
      SOURCE_UNAVAILABLE:
        "The model policy source did not release its configuration.",
      SOURCE_CHANGED: "The source changed while being read.",
      RESPONSE_OVER_BUDGET: "The response exceeded the read budget.",
      INVALID_RESPONSE: "The response failed contract validation.",
    } as Record<string, string>,
    scopeLabel: "APPLIES TO",
    scopeBot: "Selected bot",
    scopeConversation: "Current conversation",
    scopeConversationNote: "Use its composer to change the active model.",
    scopeConnection: "Connection",
    scopeConnectionNote: "Credentials are held by this connection.",
    scopeCapabilities: "Capabilities preview",
    manageProviders: "Manage providers →",
    manageCapabilities: "Manage capabilities →",
    manageReason:
      "Provider and capability management is not wired on this connection.",
    closeLabel: "Close bot settings",
  },
  "zh-CN": {
    title: "机器人设置",
    tabsLabel: "机器人设置分区",
    tab: {
      overview: "概览",
      models: "模型",
      capabilities: "能力",
      memory: "记忆",
      routines: "例行事务",
    } as Record<TabKey, string>,
    placeholderTitle: "此构建尚未投影",
    placeholderBody:
      "机器人设置的这一部分尚未在此构建中投影，不显示也不推断任何相关内容。",
    modelDefaultsHeading: "模型默认值",
    modelDefaultsNote: "在此机器人开始新会话时使用。",
    readOnlyChip: "无效果",
    readOnlyNote:
      "此页签读取团队模型策略。这里的选择只是预览策略，不会应用任何更改——模型策略由模型路由器管理。",
    providerLabel: "提供商连接",
    providerTeamDefault: "团队默认",
    providerEnabled: "策略中已启用",
    providerDisabled: "策略中已停用",
    modelLabel: "主模型",
    modelTeamDefault: "遵循团队策略",
    reasoningLabel: "推理强度",
    reasoningFromAlias: (effort: string) => effort,
    reasoningFollows: "遵循所选模型的策略",
    fallbackLabel: "备用路由",
    fallbackNote: "仅当所选提供商不可用时使用。",
    fallbackChain: (chain: string) => `已配置的备用顺序：${chain}`,
    auxiliaryLabel: "辅助任务",
    auxiliaryValue: "团队默认",
    auxiliaryNote: (count: number) =>
      count > 0
        ? `遵循团队策略（已配置 ${count} 个模型别名）。`
        : "遵循团队策略。",
    subagentLabel: "子代理任务",
    subagentValue: "受管部署 ›",
    subagentNote:
      "子代理的部署位置由模型路由器管理，不在此界面更改。",
    advanced: "高级 · 上下文与混合",
    unavailableChip: "模型策略未验证",
    unavailableBody:
      "此连接无法读取团队的模型配置。不显示也不推断任何提供商、模型或推理强度。",
    reasonLabel: "模型配置读取",
    reasons: {
      READ_NOT_EXPOSED: "此主机未提供模型配置读取。",
      MODEL_CONFIGURATION_UNAUTHORIZED: "此读取需要已登录的工作区授权。",
      SOURCE_UNAVAILABLE: "模型策略来源未发布其配置。",
      SOURCE_CHANGED: "读取期间来源发生了变化。",
      RESPONSE_OVER_BUDGET: "响应超出读取预算。",
      INVALID_RESPONSE: "响应未通过契约校验。",
    } as Record<string, string>,
    scopeLabel: "适用范围",
    scopeBot: "所选机器人",
    scopeConversation: "当前对话",
    scopeConversationNote: "使用其输入框更改当前模型。",
    scopeConnection: "连接",
    scopeConnectionNote: "凭据保留在连接中。",
    scopeCapabilities: "能力预览",
    manageProviders: "管理提供商 →",
    manageCapabilities: "管理能力 →",
    manageReason: "提供商与能力管理未在此连接上接通。",
    closeLabel: "关闭机器人设置",
  },
};

export function BotSettingsPanel({
  locale = "en",
  bot,
  host,
  onClose,
}: {
  locale?: "en" | "zh-CN";
  /** The selected roster bot — its name and role are real roster data. */
  bot: TeamBot;
  /** Host carrying the model-configuration read; absent → honest unavailable. */
  host?: MissionHost;
  onClose: () => void;
}) {
  const t = STRINGS[locale];
  const [tab, setTab] = useState<TabKey>("models");
  const [models, setModels] = useState<ModelsState>({
    kind: "UNAVAILABLE",
    reason: "READ_NOT_EXPOSED",
  });
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const started = useRef(false);

  // One bounded read per open, in the TeamRoute shape: no polling, no retry.
  // The reader enforces its own auth and fails closed to typed reasons.
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const reader = host?.readModelConfiguration;
    if (!host || !reader) {
      setModels({ kind: "UNAVAILABLE", reason: "READ_NOT_EXPOSED" });
      return;
    }
    const auth = host.auth?.getState();
    if (host.auth && auth?.status !== "signed_in") {
      // The typed host read refuses with this exact code unauthorized.
      setModels({
        kind: "UNAVAILABLE",
        reason: "MODEL_CONFIGURATION_UNAUTHORIZED",
      });
      return;
    }
    const controller = new AbortController();
    setModels({ kind: "PENDING" });
    void (async () => {
      try {
        const read = await reader.call(host, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setModels(
          read.state === "AVAILABLE"
            ? { kind: "AVAILABLE", read }
            : { kind: "UNAVAILABLE", reason: read.reason },
        );
      } catch (error) {
        if (controller.signal.aborted) return;
        const message =
          error instanceof Error
            ? error.message
            : typeof error === "string"
              ? error
              : "";
        setModels({
          kind: "UNAVAILABLE",
          reason:
            message === "MODEL_CONFIGURATION_UNAUTHORIZED"
              ? message
              : "SOURCE_UNAVAILABLE",
        });
      }
    })();
    return () => controller.abort();
  }, [host]);

  const configuration =
    models.kind === "AVAILABLE" ? models.read.configuration : null;
  const providerNames = configuration
    ? Object.keys(configuration.providers)
    : [];
  const modelEntries = configuration
    ? Object.entries(configuration.models).filter(
        ([, row]) =>
          !provider || row.provider_alias === provider,
      )
    : [];
  const selectedModel =
    configuration && model
      ? (configuration.models[model] ?? null)
      : null;
  const reasonPhrase =
    models.kind === "UNAVAILABLE" ? t.reasons[models.reason] : null;

  const onTablistKeyDown = (event: React.KeyboardEvent) => {
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    event.preventDefault();
    const index = TAB_KEYS.indexOf(tab);
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const next = TAB_KEYS[(index + direction + TAB_KEYS.length) % TAB_KEYS.length];
    setTab(next);
    tabRefs.current[TAB_KEYS.indexOf(next)]?.focus();
  };

  return (
    <TeamSurfaceDialog
      title={t.title}
      closeLabel={t.closeLabel}
      onClose={onClose}
      wide
    >
      <div
        role="tablist"
        aria-label={t.tabsLabel}
        className="mm-settings-tabs"
        onKeyDown={onTablistKeyDown}
      >
        {TAB_KEYS.map((key, index) => (
          <button
            key={key}
            type="button"
            role="tab"
            ref={(node) => {
              tabRefs.current[index] = node;
            }}
            id={`mm-bot-settings-tab-${key}`}
            aria-selected={tab === key}
            aria-controls={`mm-bot-settings-panel-${key}`}
            tabIndex={tab === key ? 0 : -1}
            className="mm-settings-tab"
            onClick={() => setTab(key)}
          >
            {t.tab[key]}
          </button>
        ))}
      </div>
      {tab === "models" ? (
        <div className="mm-surface-body">
          <div className="mm-surface-main" role="tabpanel" id="mm-bot-settings-panel-models" aria-labelledby="mm-bot-settings-tab-models">
            <header className="mm-settings-head">
              <div>
                <h3>{t.modelDefaultsHeading}</h3>
                <p className="muted">{t.modelDefaultsNote}</p>
              </div>
              <span className="mm-chip mm-chip-effect-none">
                {t.readOnlyChip}
              </span>
            </header>
            <p className="mm-card-action-reason">{t.readOnlyNote}</p>
            {models.kind === "PENDING" ? (
              <p className="muted" role="status" aria-busy="true">
                {t.reasonLabel}…
              </p>
            ) : null}
            {models.kind === "UNAVAILABLE" ? (
              <div className="mm-models-unavailable" role="status">
                <div className="mm-not-wired-chips">
                  <span className="mm-chip mm-chip-state" data-state="unknown">
                    {t.unavailableChip}
                  </span>
                </div>
                <p className="mm-not-wired-body">{t.unavailableBody}</p>
                <p className="mm-field-hint">
                  {t.reasonLabel}: <code>{models.reason}</code>
                  {reasonPhrase ? ` — ${reasonPhrase}` : null}
                </p>
              </div>
            ) : null}
            {configuration ? (
              <>
                <div className="mm-field">
                  <label htmlFor="mm-bot-settings-provider">
                    {t.providerLabel}
                  </label>
                  <select
                    id="mm-bot-settings-provider"
                    value={provider}
                    onChange={(event) => {
                      setProvider(event.target.value);
                      setModel("");
                    }}
                  >
                    <option value="">{t.providerTeamDefault}</option>
                    {providerNames.map((name) => (
                      <option key={name} value={name}>
                        {name} ·{" "}
                        {configuration.providers[name].enabled
                          ? t.providerEnabled
                          : t.providerDisabled}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="mm-field">
                  <label htmlFor="mm-bot-settings-model">{t.modelLabel}</label>
                  <select
                    id="mm-bot-settings-model"
                    value={model}
                    onChange={(event) => setModel(event.target.value)}
                  >
                    <option value="">{t.modelTeamDefault}</option>
                    {modelEntries.map(([alias, row]) => (
                      <option key={alias} value={alias}>
                        {alias} · {row.model}
                      </option>
                    ))}
                  </select>
                </div>
                <dl className="mm-settings-facts">
                  <div>
                    <dt>{t.reasoningLabel}</dt>
                    <dd>
                      {selectedModel
                        ? t.reasoningFromAlias(selectedModel.effort)
                        : t.reasoningFollows}
                    </dd>
                  </div>
                  <div>
                    <dt>{t.fallbackLabel}</dt>
                    <dd>
                      {t.modelTeamDefault}
                      <small>{t.fallbackNote}</small>
                      {Object.keys(configuration.routes).length > 0 ? (
                        <small>
                          {t.fallbackChain(
                            Object.entries(configuration.routes)
                              .map(
                                ([kind, route]) =>
                                  `${kind}: ${route.routine
                                    .flatMap((tier) => tier.model_aliases)
                                    .join(" → ")}`,
                              )
                              .join(" · "),
                          )}
                        </small>
                      ) : null}
                    </dd>
                  </div>
                  <div>
                    <dt>{t.auxiliaryLabel}</dt>
                    <dd>
                      {t.auxiliaryValue}
                      <small>
                        {t.auxiliaryNote(
                          Object.keys(configuration.models).length,
                        )}
                      </small>
                    </dd>
                  </div>
                  <div>
                    <dt>{t.subagentLabel}</dt>
                    <dd>
                      {t.subagentValue}
                      <small>{t.subagentNote}</small>
                    </dd>
                  </div>
                </dl>
              </>
            ) : null}
            <details className="mm-surface-details">
              <summary>{t.advanced} ›</summary>
              <p className="muted">{t.placeholderBody}</p>
            </details>
          </div>
          <ScopePanel
            t={t}
            bot={bot}
            configuration={configuration}
            provider={
              provider ||
              (configuration && providerNames.length > 0
                ? providerNames[0]
                : "")
            }
          />
        </div>
      ) : (
        <div
          className="mm-surface-body mm-surface-body-single"
          role="tabpanel"
          id={`mm-bot-settings-panel-${tab}`}
          aria-labelledby={`mm-bot-settings-tab-${tab}`}
        >
          <div className="mm-surface-main">
            <div className="mm-models-unavailable">
              <p className="mm-not-wired-body">{t.placeholderTitle}</p>
              <p className="mm-field-hint">{t.placeholderBody}</p>
            </div>
          </div>
        </div>
      )}
    </TeamSurfaceDialog>
  );
}

/** Scope side panel (HC09 "APPLIES TO"). The selected bot row is real roster
 *  data; the conversation and connection rows stay honest about what this
 *  build projects. */
function ScopePanel({
  t,
  bot,
  configuration,
  provider,
}: {
  t: typeof STRINGS.en;
  bot: TeamBot;
  configuration: ModelConfiguration | null;
  provider: string;
}) {
  const reasonId = useId();
  const providerRow = configuration && provider
    ? `${provider} · ${
        configuration.providers[provider]?.enabled
          ? t.providerEnabled
          : t.providerDisabled
      }`
    : t.modelTeamDefault;
  return (
    <aside className="mm-surface-side">
      <p className="mm-eyebrow">{t.scopeLabel}</p>
      <dl className="mm-settings-facts">
        <div>
          <dt>{t.scopeBot}</dt>
          <dd>{bot.displayName}</dd>
        </div>
        <div>
          <dt>{t.scopeConversation}</dt>
          <dd>
            {t.placeholderTitle}
            <small>{t.scopeConversationNote}</small>
          </dd>
        </div>
        <div>
          <dt>{t.scopeConnection}</dt>
          <dd>
            {providerRow}
            <small>{t.scopeConnectionNote}</small>
          </dd>
        </div>
        <div>
          <dt>{t.scopeCapabilities}</dt>
          <dd>
            <button
              type="button"
              className="mm-card-action"
              disabled
              aria-describedby={reasonId}
            >
              {t.manageCapabilities}
            </button>
            <button
              type="button"
              className="mm-card-action"
              disabled
              aria-describedby={reasonId}
            >
              {t.manageProviders}
            </button>
            <small id={reasonId}>{t.manageReason}</small>
          </dd>
        </div>
      </dl>
    </aside>
  );
}
