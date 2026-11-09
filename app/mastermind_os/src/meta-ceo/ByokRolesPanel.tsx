import { useEffect, useId, useRef, useState } from "react";
import { ByokConnectionDrawer, type ByokConnectionRow } from "./ByokConnectionDrawer";
import "./byok-roles-panel.css";

/** Presentation identity only; it does not select a runtime role or credential. */
export type ByokRoleId = "meta-ceo" | "secretary";

/**
 * Runtime role identity as reported by the parent owner. It selects nothing
 * here: the panel only displays what the parent owner already validated.
 */
export type ByokObservationRoleId = "mmmeta" | "mmsecretary";

/**
 * What the parent owner could observe about one role's installed
 * configuration. ABSENT means the configuration is not installed, never that a
 * credential is missing. CONFIGURATION_OBSERVED means consistent metadata
 * only: never a connection, health, credential or served model. UNAVAILABLE
 * means the configuration cannot be read right now.
 */
export type ByokObservationRoleState = "ABSENT" | "CONFIGURATION_OBSERVED" | "UNAVAILABLE";

/**
 * What the parent owner could observe about the source of the observation.
 * SOURCE_UNBOUND means the source is not connected and the installation is
 * unknown. UNAVAILABLE means the source cannot be read right now. OBSERVED
 * means the source was read and the per-role states carry the detail.
 */
export type ByokObservationState = "LOADING" | "SOURCE_UNBOUND" | "UNAVAILABLE" | "OBSERVED";

export interface ByokObservedRole {
  readonly role: ByokObservationRoleId;
  readonly state: ByokObservationRoleState;
  /** Bounded display strings only. Never a key, path, raw reason or exception. */
  readonly requestedProvider?: string;
  readonly requestedModel?: string;
}

export interface ByokObservation {
  readonly state: ByokObservationState;
  readonly roles?: readonly ByokObservedRole[];
}

export interface ByokRolesPanelProps {
  locale?: "en" | "zh-CN";
  /** Supplied by an actual setup owner. The panel never enrolls or connects a role. */
  onReviewConnection?: (role: ByokRoleId) => void;
  /**
   * Read-only view of an observation owned by the parent. The props confer no
   * authority, provenance, enrollment or connection of their own.
   */
  observation?: ByokObservation;
}

const COPY = {
  "Your operating team": "你的执行团队",
  "Role setup and connection status": "角色设置与连接状态",
  "Two roles, one accountable workflow.": "两个角色，同一套负责流程。",
  "Meta-CEO": "Meta-CEO",
  "Secretary": "秘书",
  "Sets direction and coordinates delivery.": "确定方向并协调交付。",
  "Tracks progress and brings returns back to you.": "跟踪进展，并将返回结果带给你。",
  "Model candidate": "候选模型",
  "Qualified Flash route": "合格的 Flash 路由",
  "Enrollment": "接入登记",
  "Unverified": "尚未验证",
  "Service and model connection": "服务与模型连接",
  "Not verified": "未经验证",
  "Last turn": "最近一次交互",
  "Not proven": "尚未确认",
  "Usage": "用量",
  "Unavailable": "不可用",
  "Setup requirements": "设置要求",
  "Enroll the provider credential through the authorized role setup.": "通过已授权的角色设置登记提供商凭据。",
  "Verify the installed role and its model connection.": "验证已安装的角色及其模型连接。",
  "Confirm a useful return reaches the original conversation.": "确认有效结果返回原始对话。",
  "Review connection": "查看连接",
  "Source status": "来源状态",
  "Configuration status": "配置状态",
  "Requested provider": "请求的提供方",
  "Requested model": "请求的模型",
  "Not observed": "未观察到",
  "Reading source": "正在读取来源",
  "Source not connected": "来源未连接",
  "Source unavailable": "来源不可用",
  "Source read": "已读取来源",
  "Configuration not installed": "未安装配置",
  "Configuration observed": "已观察到配置",
  "Configuration unavailable": "配置不可用",
  "The role observation is still loading. No configuration has been read yet.": "角色观察仍在加载中。尚未读取任何配置。",
  "The role source is not connected, so no configuration has been read.": "角色来源未连接，因此未读取任何配置。",
  "The role source cannot be read right now, so no configuration has been read.": "当前无法读取角色来源，因此未读取任何配置。",
  "The role source was read. Each configuration state reflects only the metadata the source reported. Enrollment, service and model connection, last useful turn and usage remain unverified.": "角色来源已读取。各配置状态仅反映来源所报告的元数据。接入登记、服务与模型连接、最近一次有效交互和用量仍未验证。",
  "No external setup owner is connected in this session, so this review stays read-only.": "当前会话未连接外部设置负责人，因此此审阅保持只读。",
  "Keep API keys in secure role setup. This view never accepts or displays credentials.": "请在安全的角色设置中管理 API 密钥。此视图不接收或显示凭据。",
  "A candidate label is a planning choice. The requested provider and model are what the source reported; they are not the served model.": "候选标签是规划选择。请求的提供方与模型是来源所报告的内容，并非实际服务的模型。",
  "This review is read-only. It does not enroll a role, connect a provider or change any setting.": "此审阅为只读。它不会登记角色、连接提供方或更改任何设置。",
} as const;
type Copy = keyof typeof COPY;

const ROLES: ReadonlyArray<{
  id: ByokRoleId;
  observationRole: ByokObservationRoleId;
  name: Copy;
  purpose: Copy;
  candidate: "GLM 5.3" | "Qualified Flash route";
}> = [
  {
    id: "meta-ceo",
    observationRole: "mmmeta",
    name: "Meta-CEO",
    purpose: "Sets direction and coordinates delivery.",
    candidate: "GLM 5.3",
  },
  {
    id: "secretary",
    observationRole: "mmsecretary",
    name: "Secretary",
    purpose: "Tracks progress and brings returns back to you.",
    candidate: "Qualified Flash route",
  },
];

const SETUP_STEPS: readonly Copy[] = [
  "Enroll the provider credential through the authorized role setup.",
  "Verify the installed role and its model connection.",
  "Confirm a useful return reaches the original conversation.",
];

const MAX_DISPLAY = 120;

/**
 * Bounds an observed display string before it is rendered. The result is
 * plain text: it is never treated as markup and never becomes a link.
 */
function boundedDisplay(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const cleaned = value.replace(/[\x00-\x1f\x7f]/g, " ").replace(/\s+/g, " ").trim();
  if (!cleaned) return undefined;
  return cleaned.length > MAX_DISPLAY ? `${cleaned.slice(0, MAX_DISPLAY - 1)}…` : cleaned;
}

function sourceStatusLabel(state: ByokObservationState): Copy {
  switch (state) {
    case "LOADING": return "Reading source";
    case "SOURCE_UNBOUND": return "Source not connected";
    case "UNAVAILABLE": return "Source unavailable";
    case "OBSERVED": return "Source read";
  }
}

function observedRole(observation: ByokObservation, role: ByokRoleId): ByokObservedRole | undefined {
  const id = ROLES.find(item => item.id === role)?.observationRole;
  if (!id) return undefined;
  return observation.roles?.find(item => item.role === id);
}

function configurationStatusLabel(observation: ByokObservation, role: ByokRoleId): Copy {
  if (observation.state !== "OBSERVED") return "Not observed";
  const entry = observedRole(observation, role);
  if (!entry) return "Not observed";
  switch (entry.state) {
    case "ABSENT": return "Configuration not installed";
    case "CONFIGURATION_OBSERVED": return "Configuration observed";
    case "UNAVAILABLE": return "Configuration unavailable";
  }
}

/** The most specific honest statement the observation supports for one card. */
function cardStateLabel(observation: ByokObservation, role: ByokRoleId): Copy {
  if (observation.state === "OBSERVED") return configurationStatusLabel(observation, role);
  return sourceStatusLabel(observation.state);
}

function observationNote(observation: ByokObservation): Copy {
  switch (observation.state) {
    case "LOADING":
      return "The role observation is still loading. No configuration has been read yet.";
    case "SOURCE_UNBOUND":
      return "The role source is not connected, so no configuration has been read.";
    case "UNAVAILABLE":
      return "The role source cannot be read right now, so no configuration has been read.";
    case "OBSERVED":
      return "The role source was read. Each configuration state reflects only the metadata the source reported. Enrollment, service and model connection, last useful turn and usage remain unverified.";
  }
}

/**
 * The requested provider and model exist only where the owner observed
 * consistent configuration metadata. They stay separate from the planning
 * candidate label, and they are never a served model or a connection claim.
 */
function observedRequest(observation: ByokObservation, role: ByokRoleId):
{ provider?: string; model?: string } {
  if (observation.state !== "OBSERVED") return {};
  const entry = observedRole(observation, role);
  if (!entry || entry.state !== "CONFIGURATION_OBSERVED") return {};
  return {
    provider: boundedDisplay(entry.requestedProvider),
    model: boundedDisplay(entry.requestedModel),
  };
}

/**
 * The panel shows the observation its owner supplies and nothing more. No
 * mission, model preference, browser session, or configured key implies
 * readiness. No network, credential storage, enrollment, retry, or dispatch is
 * owned here, and an observed configuration never becomes an enrollment, a
 * connection or a served-model claim.
 */
export function ByokRolesPanel({ locale = "en", onReviewConnection, observation }: ByokRolesPanelProps) {
  const headingId = useId();
  const noteId = useId();
  const [reviewRole, setReviewRole] = useState<ByokRoleId | null>(null);
  const reviewTriggerRef = useRef<HTMLButtonElement | null>(null);
  const t = (text: Copy): string => locale === "zh-CN" ? COPY[text] : text;
  const view: ByokObservation = observation ?? { state: "SOURCE_UNBOUND" };

  // Focus returns to the control that opened the review once it is dismissed.
  useEffect(() => {
    if (reviewRole !== null) return;
    reviewTriggerRef.current?.focus();
  }, [reviewRole]);

  const openReview = (role: ByokRoleId, trigger: HTMLButtonElement) => {
    reviewTriggerRef.current = trigger;
    setReviewRole(role);
    onReviewConnection?.(role);
  };

  const reviewed = ROLES.find(role => role.id === reviewRole) ?? null;
  const request = reviewed ? observedRequest(view, reviewed.id) : {};
  const sourceRows: readonly ByokConnectionRow[] = reviewed ? [
    { label: t("Source status"), value: t(sourceStatusLabel(view.state)) },
    { label: t("Configuration status"), value: t(configurationStatusLabel(view, reviewed.id)) },
    {
      label: t("Model candidate"),
      value: reviewed.candidate === "GLM 5.3" ? reviewed.candidate : t(reviewed.candidate),
    },
    { label: t("Requested provider"), value: request.provider ?? t("Not observed") },
    { label: t("Requested model"), value: request.model ?? t("Not observed") },
  ] : [];
  const proofRows: readonly ByokConnectionRow[] = [
    { label: t("Enrollment"), value: t("Unverified") },
    { label: t("Service and model connection"), value: t("Not verified") },
    { label: t("Last turn"), value: t("Not proven") },
    { label: t("Usage"), value: t("Unavailable") },
  ];
  const notes: readonly string[] = [
    t("A candidate label is a planning choice. The requested provider and model are what the source reported; they are not the served model."),
    t("This review is read-only. It does not enroll a role, connect a provider or change any setting."),
  ];

  return <section className="byok-roles-panel" aria-labelledby={headingId} aria-describedby={noteId}>
    <header className="byok-roles-heading">
      <div>
        <p className="byok-roles-eyebrow">{t("Role setup and connection status")}</p>
        <h2 id={headingId}>{t("Your operating team")}</h2>
      </div>
      <p className="byok-roles-muted">{t("Two roles, one accountable workflow.")}</p>
    </header>
    <div className="byok-role-grid">
      {ROLES.map(role => <article className="byok-role-card" key={role.id}
        aria-labelledby={headingId + "-" + role.id}>
        <div className="byok-role-title">
          <h3 id={headingId + "-" + role.id}>{t(role.name)}</h3>
          <span className="byok-role-state">{t(cardStateLabel(view, role.id))}</span>
        </div>
        <p className="byok-role-purpose">{t(role.purpose)}</p>
        <div className="byok-role-model">
          <span>{t("Model candidate")}</span>
          <strong>{role.candidate === "GLM 5.3" ? role.candidate : t(role.candidate)}</strong>
        </div>
        <dl className="byok-role-facts">
          <div><dt>{t("Enrollment")}</dt><dd>{t("Unverified")}</dd></div>
          <div><dt>{t("Last turn")}</dt><dd>{t("Not proven")}</dd></div>
          <div><dt>{t("Usage")}</dt><dd>{t("Unavailable")}</dd></div>
        </dl>
        <button type="button" className="byok-role-review"
          aria-haspopup="dialog" aria-expanded={reviewRole === role.id}
          aria-label={t("Review connection") + " · " + t(role.name)}
          onClick={event => openReview(role.id, event.currentTarget)}>
          {t("Review connection")}
        </button>
        <details className="byok-role-setup">
          <summary>{t("Setup requirements")}</summary>
          <ol>{SETUP_STEPS.map(step => <li key={step}>{t(step)}</li>)}</ol>
        </details>
      </article>)}
    </div>
    <div className="byok-roles-note" id={noteId}>
      <p>{t(observationNote(view))}</p>
      <p>{t("Keep API keys in secure role setup. This view never accepts or displays credentials.")}</p>
      {!onReviewConnection && <p>{t("No external setup owner is connected in this session, so this review stays read-only.")}</p>}
    </div>
    {reviewed && <ByokConnectionDrawer locale={locale} roleName={t(reviewed.name)}
      sourceRows={sourceRows} proofRows={proofRows} notes={notes}
      steps={SETUP_STEPS.map(step => t(step))} onClose={() => setReviewRole(null)} />}
  </section>;
}
