import { useId } from "react";
import "./byok-roles-panel.css";

/** Presentation identity only; it does not select a runtime role or credential. */
export type ByokRoleId = "meta-ceo" | "secretary";

export interface ByokRolesPanelProps {
  locale?: "en" | "zh-CN";
  /** Supplied by an actual setup owner. The panel never enrolls or connects a role. */
  onReviewConnection?: (role: ByokRoleId) => void;
}

const COPY = {
  "Your operating team": "你的执行团队",
  "Role setup and connection status": "角色设置与连接状态",
  "Two roles, one accountable workflow.": "两个角色，同一套负责流程。",
  "Meta-CEO": "Meta-CEO",
  "Secretary": "秘书",
  "Sets direction and coordinates delivery.": "确定方向并协调交付。",
  "Tracks progress and brings returns back to you.": "跟踪进展，并将返回结果带给你。",
  "Needs setup": "需要设置",
  "Model candidate": "候选模型",
  "Qualified Flash route": "合格的 Flash 路由",
  "Enrollment": "接入登记",
  "Unverified": "尚未验证",
  "Last turn": "最近一次交互",
  "Not proven": "尚未确认",
  "Usage": "用量",
  "Unavailable": "不可用",
  "Setup requirements": "设置要求",
  "Enroll the provider credential through the authorized role setup.": "通过已授权的角色设置登记提供商凭据。",
  "Verify the installed role and its model connection.": "验证已安装的角色及其模型连接。",
  "Confirm a useful return reaches the original conversation.": "确认有效结果返回原始对话。",
  "Review connection": "查看连接",
  "Connection controls are not available in this session.": "当前会话尚无可用的连接控制。",
  "Connection verification has not been supplied. Candidate models are shown for setup planning.": "尚未提供连接验证结果。候选模型仅用于设置规划。",
  "Keep API keys in secure role setup. This view never accepts or displays credentials.": "请在安全的角色设置中管理 API 密钥。此视图不接收或显示凭据。",
} as const;
type Copy = keyof typeof COPY;

const ROLES: ReadonlyArray<{
  id: ByokRoleId;
  name: Copy;
  purpose: Copy;
  candidate: "GLM 5.3" | "Qualified Flash route";
}> = [
  { id: "meta-ceo", name: "Meta-CEO", purpose: "Sets direction and coordinates delivery.", candidate: "GLM 5.3" },
  { id: "secretary", name: "Secretary", purpose: "Tracks progress and brings returns back to you.", candidate: "Qualified Flash route" },
];

/**
 * Honest setup state until an authorized role-observation contract is available.
 * No mission, model preference, browser session, or configured key implies readiness.
 * No network, credential storage, enrollment, retry, or dispatch is owned here.
 */
export function ByokRolesPanel({ locale = "en", onReviewConnection }: ByokRolesPanelProps) {
  const headingId = useId();
  const noteId = useId();
  const t = (text: Copy): string => locale === "zh-CN" ? COPY[text] : text;
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
          <span className="byok-role-state">{t("Needs setup")}</span>
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
        <details className="byok-role-setup">
          <summary>{t("Setup requirements")}</summary>
          <ol>
            <li>{t("Enroll the provider credential through the authorized role setup.")}</li>
            <li>{t("Verify the installed role and its model connection.")}</li>
            <li>{t("Confirm a useful return reaches the original conversation.")}</li>
          </ol>
          {onReviewConnection
            ? <button type="button" onClick={() => onReviewConnection(role.id)}
                aria-label={t("Review connection") + " · " + t(role.name)}>
                {t("Review connection")}
              </button>
            : <p className="byok-roles-muted">{t("Connection controls are not available in this session.")}</p>}
        </details>
      </article>)}
    </div>
    <div className="byok-roles-note" id={noteId}>
      <p>{t("Connection verification has not been supplied. Candidate models are shown for setup planning.")}</p>
      <p>{t("Keep API keys in secure role setup. This view never accepts or displays credentials.")}</p>
    </div>
  </section>;
}
