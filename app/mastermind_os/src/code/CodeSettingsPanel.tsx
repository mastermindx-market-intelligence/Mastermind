import { useEffect, useId, useState } from "react";
import "./code-settings.css";

/** HC11 — Code settings · Provider, environment and capabilities (15QF-0).
 *  Structure and copy follow the authored Paper extraction: location bar,
 *  settings nav (248) with four groups, Providers content. Only Providers
 *  carries real content; every other tab renders an honest "Not configured in
 *  this build" placeholder. Providers/environments arrive as typed props —
 *  null means no configuration source is projected and is said so. Paper
 *  samples ("DeepSeek Harness", "Ubuntu 2"…) are never shipped: they appear
 *  only as test fixtures. There is no provider write path in this build —
 *  "＋ Add provider" reports that honestly instead of faking success. */

export type ProviderCapabilityState =
  | "available"
  | "discovered"
  | "not-provided"
  | "unknown";

export interface ProviderCapability {
  label: string;
  state: ProviderCapabilityState;
  /** Optional producer note rendered under the row (e.g. a linked-tasks
   *  qualifier). Null/absent renders nothing — never an invented note. */
  note: string | null;
}

/** One coding-agent provider connection as projected by the configuration
 *  source. Null fields render unknown-with-reason, never sampled values. */
export interface ProviderConnection {
  id: string;
  name: string;
  /** Null = readiness not observed by the source. */
  ready: boolean | null;
  executable: string | null;
  args: string | null;
  defaultModel: string | null;
  connectionAuth: "held" | "missing" | "unknown";
  capabilities: ProviderCapability[];
}

export interface EnvironmentSummary {
  id: string;
  label: string;
}

/** Settings nav groups — fixed structure; labels come from STRINGS. */
const NAV_GROUPS = [
  {
    group: "interface",
    items: ["general", "appearance", "chat", "keyboard"],
  },
  {
    group: "agents",
    items: [
      "providers",
      "threads",
      "browser",
      "devices",
      "scheduled",
    ],
  },
  {
    group: "code",
    items: ["projects", "diffs", "sourceControl", "worktrees"],
  },
  {
    group: "connections",
    items: ["environments", "sharing"],
  },
] as const;

type TabKey = (typeof NAV_GROUPS)[number]["items"][number];

const STRINGS = {
  en: {
    locationRoot: "Code settings",
    close: "Close settings",
    navLabel: "Settings sections",
    groups: {
      interface: "INTERFACE",
      agents: "AGENTS",
      code: "CODE",
      connections: "CONNECTIONS",
    } as Record<(typeof NAV_GROUPS)[number]["group"], string>,
    nav: {
      general: "General",
      appearance: "Appearance",
      chat: "Chat",
      keyboard: "Keyboard shortcuts",
      providers: "Providers",
      threads: "Threads",
      browser: "Browser",
      devices: "Devices",
      scheduled: "Scheduled tasks",
      projects: "Projects",
      diffs: "Diffs & pull requests",
      sourceControl: "Source control",
      worktrees: "Worktrees",
      environments: "Environments",
      sharing: "Sharing & access",
    } as Record<TabKey, string>,
    providersHeading: "Providers",
    providersIntro: "Configure coding agents for this environment.",
    addProvider: "＋ Add provider",
    addProviderNotWired:
      "Adding a provider is not wired in this build. No provider write path exists — nothing was added or saved.",
    showingFor: "Showing configuration for",
    envSelectLabel: "Showing configuration for",
    envUnknownOption: "Unknown environment",
    envsUnavailable:
      "No environment list is projected in this build — the active environment cannot be confirmed here.",
    envStickyNote: "Existing threads stay on their original environment.",
    envNotProjected: (label: string) =>
      `Provider configuration for ${label} is not projected in this build. Only the active environment's configuration is loaded here.`,
    providersUnavailableTitle:
      "No provider configuration source is projected in this build",
    providersUnavailableBody:
      "This surface shows providers only from a verified configuration source. None is connected here, so nothing is shown or inferred.",
    providersUnavailableNote:
      "Design samples are never shown as real provider configuration.",
    providersEmpty: "No providers are configured for this environment.",
    executableLabel: "Executable",
    argsLabel: "Arguments",
    defaultModelLabel: "Default model",
    connectionAuthLabel: "Connection auth",
    authHeld: "Held by the connection",
    authMissing: "Not configured",
    authUnknown: "Unknown",
    fieldUnknown: "Unknown — not provided by the connection",
    readyChip: "Ready",
    notReadyChip: "Not ready",
    readyUnknownChip: "Unknown",
    credentialsNote: "Credentials stay on the execution environment.",
    capabilitiesHeading: "Capabilities from this connection",
    capAvailable: "Available",
    capDiscovered: "Discovered from agent",
    capNotProvided: "Not provided by ACP",
    capUnknown: "Unknown",
    linkedTasksNote:
      "Linked tasks stay with their conversation thread; they are not part of this connection's capabilities.",
    moreProviders: "More providers →",
    moreProvidersReason: "The provider catalog is not wired in this build.",
    closeUnavailableReason: "No close path is wired for this surface.",
    placeholderBody: (label: string) =>
      `${label} is not configured in this build. This build ships the Providers surface only; no configuration source is wired for this section.`,
  },
  "zh-CN": {
    locationRoot: "代码设置",
    close: "关闭设置",
    navLabel: "设置分区",
    groups: {
      interface: "界面",
      agents: "智能体",
      code: "代码",
      connections: "连接",
    } as Record<(typeof NAV_GROUPS)[number]["group"], string>,
    nav: {
      general: "常规",
      appearance: "外观",
      chat: "聊天",
      keyboard: "键盘快捷键",
      providers: "提供商",
      threads: "线程",
      browser: "浏览器",
      devices: "设备",
      scheduled: "计划任务",
      projects: "项目",
      diffs: "差异与拉取请求",
      sourceControl: "源代码管理",
      worktrees: "工作树",
      environments: "环境",
      sharing: "共享与访问",
    } as Record<TabKey, string>,
    providersHeading: "提供商",
    providersIntro: "为此环境配置编码智能体。",
    addProvider: "＋ 添加提供商",
    addProviderNotWired:
      "此版本未接入添加提供商的路径。不存在提供商写入路径——未添加、未保存任何内容。",
    showingFor: "显示以下环境的配置",
    envSelectLabel: "显示以下环境的配置",
    envUnknownOption: "未知环境",
    envsUnavailable: "此版本未投影环境列表——无法在此确认当前环境。",
    envStickyNote: "现有线程保留在其原始环境中。",
    envNotProjected: (label: string) =>
      `尚未投影 ${label} 的提供商配置。此处仅加载当前活动环境的配置。`,
    providersUnavailableTitle: "此版本未投影提供商配置来源",
    providersUnavailableBody:
      "此界面仅在经过验证的配置来源提供数据时才显示提供商。当前未连接任何来源，因此不显示也不推断任何内容。",
    providersUnavailableNote: "绝不将设计示例显示为真实的提供商配置。",
    providersEmpty: "此环境未配置任何提供商。",
    executableLabel: "可执行文件",
    argsLabel: "参数",
    defaultModelLabel: "默认模型",
    connectionAuthLabel: "连接身份验证",
    authHeld: "由连接持有",
    authMissing: "未配置",
    authUnknown: "未知",
    fieldUnknown: "未知——该连接未提供",
    readyChip: "就绪",
    notReadyChip: "未就绪",
    readyUnknownChip: "未知",
    credentialsNote: "凭据保存在执行环境中。",
    capabilitiesHeading: "此连接的能力",
    capAvailable: "可用",
    capDiscovered: "由智能体发现",
    capNotProvided: "ACP 未提供",
    capUnknown: "未知",
    linkedTasksNote: "关联任务保留在其所属的会话线程中，不属于此连接的能力。",
    moreProviders: "更多提供商 →",
    moreProvidersReason: "此版本未接入提供商目录。",
    closeUnavailableReason: "此界面未接入关闭路径。",
    placeholderBody: (label: string) =>
      `${label} 在此版本中未配置。此版本仅提供“提供商”界面；该分区没有接入配置来源。`,
  },
};

function capabilityLabel(
  state: ProviderCapabilityState,
  t: typeof STRINGS.en,
): string {
  if (state === "available") return t.capAvailable;
  if (state === "discovered") return t.capDiscovered;
  if (state === "not-provided") return t.capNotProvided;
  return t.capUnknown;
}

export function CodeSettingsPanel({
  locale = "en",
  onClose,
  providers,
  environments,
  activeEnvironmentId,
  onMoreProviders,
}: {
  locale?: "en" | "zh-CN";
  /** Absent → the × renders disabled with a visible reason. */
  onClose?: () => void;
  /** Null = no provider configuration source is projected. */
  providers: ProviderConnection[] | null;
  /** Null = no environment list is projected. */
  environments: EnvironmentSummary[] | null;
  /** The environment whose configuration `providers` describes, if known. */
  activeEnvironmentId: string | null;
  /** Absent → "More providers" renders disabled with a visible reason. */
  onMoreProviders?: () => void;
}) {
  const t = STRINGS[locale];
  const headingId = useId();
  const moreReasonId = useId();
  const closeReasonId = useId();

  const [tab, setTab] = useState<TabKey>("providers");
  const [addProviderAsked, setAddProviderAsked] = useState(false);
  const [selectedEnvId, setSelectedEnvId] = useState(activeEnvironmentId);
  useEffect(() => {
    setSelectedEnvId(activeEnvironmentId);
  }, [activeEnvironmentId]);

  // Escape closes the settings surface (onClose). Document-level so it works
  // regardless of focus; removed on unmount.
  useEffect(() => {
    if (!onClose) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const tabLabel = t.nav[tab];
  const selectedEnvKnown =
    selectedEnvId !== null &&
    environments !== null &&
    environments.some((env) => env.id === selectedEnvId);
  const selectValue = selectedEnvKnown ? selectedEnvId : "";
  const otherEnvSelected =
    selectedEnvId !== null && selectedEnvId !== activeEnvironmentId;
  const otherEnv =
    otherEnvSelected && environments !== null
      ? (environments.find((env) => env.id === selectedEnvId) ?? null)
      : null;

  return (
    <section className="mm-cs" aria-labelledby={headingId}>
      {/* Location bar. */}
      <div className="mm-cs-location">
        <p>{`${t.locationRoot} / ${tabLabel}`}</p>
        <button
          type="button"
          className="mm-cs-close"
          onClick={onClose}
          disabled={!onClose}
          aria-label={t.close}
          aria-describedby={onClose ? undefined : closeReasonId}
        >
          ×
        </button>
      </div>
      {!onClose ? (
        <p className="mm-cs-reason" id={closeReasonId}>
          {t.closeUnavailableReason}
        </p>
      ) : null}

      <div className="mm-cs-body">
        {/* Settings nav (248) — four groups, Providers is the real surface. */}
        <nav className="mm-cs-nav" aria-label={t.navLabel}>
          {NAV_GROUPS.map((group) => (
            <div key={group.group} className="mm-cs-nav-group">
              <p>{t.groups[group.group]}</p>
              {group.items.map((item) => (
                <button
                  key={item}
                  type="button"
                  className="mm-cs-nav-item"
                  aria-current={tab === item ? "page" : undefined}
                  onClick={() => {
                    setTab(item);
                    setAddProviderAsked(false);
                  }}
                >
                  {t.nav[item]}
                </button>
              ))}
            </div>
          ))}
        </nav>

        {/* Content column. */}
        <div className="mm-cs-content">
          {tab !== "providers" ? (
            <div className="card mm-cs-placeholder">
              <h1 id={headingId} className="mm-cs-heading">
                {tabLabel}
              </h1>
              <p>{t.placeholderBody(tabLabel)}</p>
            </div>
          ) : (
            <>
              <div className="mm-cs-head">
                <div>
                  <h1 id={headingId} className="mm-cs-heading">
                    {t.providersHeading}
                  </h1>
                  <p className="muted">{t.providersIntro}</p>
                </div>
                <button
                  type="button"
                  className="mm-cs-add"
                  onClick={() => setAddProviderAsked(true)}
                >
                  {t.addProvider}
                </button>
              </div>
              {addProviderAsked ? (
                <p className="mm-cs-status" role="status">
                  {t.addProviderNotWired}
                </p>
              ) : null}

              <div className="mm-cs-env">
                {environments === null ? (
                  <>
                    <p className="mm-cs-env-label">{t.showingFor}</p>
                    <p className="mm-cs-reason">{t.envsUnavailable}</p>
                  </>
                ) : (
                  <>
                    <label
                      className="mm-cs-env-label"
                      htmlFor="mm-cs-environment"
                    >
                      {t.envSelectLabel}
                    </label>
                    <select
                      id="mm-cs-environment"
                      className="mm-cs-select"
                      value={selectValue}
                      onChange={(event) =>
                        setSelectedEnvId(event.target.value || null)
                      }
                    >
                      {selectValue === "" ? (
                        <option value="">{t.envUnknownOption}</option>
                      ) : null}
                      {environments.map((env) => (
                        <option key={env.id} value={env.id}>
                          {env.label}
                        </option>
                      ))}
                    </select>
                  </>
                )}
                <p className="mm-cs-env-note">{t.envStickyNote}</p>
              </div>

              {otherEnvSelected ? (
                <div className="card mm-cs-placeholder">
                  <p>
                    {otherEnv
                      ? t.envNotProjected(otherEnv.label)
                      : t.envNotProjected(selectedEnvId ?? "")}
                  </p>
                </div>
              ) : providers === null ? (
                <div className="card mm-cs-unavailable">
                  <p className="mm-eyebrow">{t.providersUnavailableTitle}</p>
                  <p>{t.providersUnavailableBody}</p>
                  <p className="muted">{t.providersUnavailableNote}</p>
                </div>
              ) : providers.length === 0 ? (
                <div className="card mm-cs-placeholder">
                  <p>{t.providersEmpty}</p>
                </div>
              ) : (
                <>
                  {providers.map((provider) => (
                    <article
                      key={provider.id}
                      className="card mm-cs-provider"
                    >
                      <header className="mm-cs-provider-head">
                        <h2>{provider.name}</h2>
                        <span
                          className="mm-chip mm-cs-ready"
                          data-ready={
                            provider.ready === null
                              ? "unknown"
                              : provider.ready
                                ? "ready"
                                : "not-ready"
                          }
                        >
                          {provider.ready === null
                            ? t.readyUnknownChip
                            : provider.ready
                              ? t.readyChip
                              : t.notReadyChip}
                        </span>
                      </header>
                      <dl className="mm-cs-facts">
                        <div>
                          <dt>{t.executableLabel}</dt>
                          <dd>
                            {provider.executable ?? (
                              <span className="mm-cs-unknown">
                                {t.fieldUnknown}
                              </span>
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt>{t.argsLabel}</dt>
                          <dd>
                            {provider.args ?? (
                              <span className="mm-cs-unknown">
                                {t.fieldUnknown}
                              </span>
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt>{t.defaultModelLabel}</dt>
                          <dd>
                            {provider.defaultModel ?? (
                              <span className="mm-cs-unknown">
                                {t.fieldUnknown}
                              </span>
                            )}
                          </dd>
                        </div>
                        <div>
                          <dt>{t.connectionAuthLabel}</dt>
                          <dd
                            className="mm-cs-auth"
                            data-auth={provider.connectionAuth}
                          >
                            {provider.connectionAuth === "held"
                              ? t.authHeld
                              : provider.connectionAuth === "missing"
                                ? t.authMissing
                                : t.authUnknown}
                          </dd>
                        </div>
                      </dl>
                      <p className="mm-cs-credentials">{t.credentialsNote}</p>
                      <div className="mm-cs-capabilities">
                        <h3>{t.capabilitiesHeading}</h3>
                        <dl>
                          {provider.capabilities.map((capability) => (
                            <div key={capability.label}>
                              <dt>{capability.label}</dt>
                              <dd
                                className="mm-cs-capability"
                                data-state={capability.state}
                              >
                                {capabilityLabel(capability.state, t)}
                                {capability.note ? (
                                  <small> {capability.note}</small>
                                ) : null}
                              </dd>
                            </div>
                          ))}
                        </dl>
                        <p className="mm-cs-env-note">{t.linkedTasksNote}</p>
                      </div>
                    </article>
                  ))}
                  {onMoreProviders ? (
                    <button
                      type="button"
                      className="mm-cs-more"
                      onClick={onMoreProviders}
                    >
                      {t.moreProviders}
                    </button>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="mm-cs-more"
                        disabled
                        aria-describedby={moreReasonId}
                      >
                        {t.moreProviders}
                      </button>
                      <p className="mm-cs-reason" id={moreReasonId}>
                        {t.moreProvidersReason}
                      </p>
                    </>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
