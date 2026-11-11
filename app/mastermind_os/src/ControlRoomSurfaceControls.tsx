/** Existing #1515 surface presentation. App retains authentication, source
 * generations, the original action promise/result and the single action slot.
 * This component owns only explicit form drafts and disclosure preferences.
 */
import { useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  controlRoomActionIsUncertain,
  decodeControlRoomActionPayload,
  type ControlRoomActionResult,
  type ControlRoomOperation,
} from "./control-room";
import type {
  ControlRoomBindingSummary,
  ControlRoomDiscovery,
  ControlRoomNavigation,
  ControlRoomProvider,
  ControlRoomRole,
} from "./control-room-navigation";

export type ControlRoomDiscoveryPresentation =
  | Readonly<{ state: "IDLE" | "PENDING" | "UNAVAILABLE" }>
  | Readonly<{ state: "AVAILABLE"; document: ControlRoomDiscovery }>;

export type ControlRoomActionPresentation =
  | Readonly<{ state: "IDLE" }>
  | Readonly<{ state: "PENDING"; operation: ControlRoomOperation }>
  | Readonly<{ state: "RESULT"; result: ControlRoomActionResult }>
  | Readonly<{
      state: "FAILURE";
      operation: ControlRoomOperation;
      disposition: "NOT_DISPATCHED" | "EFFECT_UNKNOWN";
    }>
  | Readonly<{ state: "WITHHELD"; held: boolean }>;

export type ControlRoomSurfaceLocale = "en" | "zh-CN";

export type ControlRoomSurfaceControlsProps = Readonly<{
  navigation: ControlRoomNavigation | null;
  discovery: ControlRoomDiscoveryPresentation;
  action: ControlRoomActionPresentation;
  /** Current App custody. READ presentation does not release this hold. */
  held: boolean;
  /** Current authenticated presentation eligibility, not an action grant. */
  canAct: boolean;
  locale?: ControlRoomSurfaceLocale;
  onDiscover?: () => void;
  onOpenSurface?: (payload: Readonly<Record<string, unknown>>) => void;
  onBindSurface?: (payload: Readonly<Record<string, unknown>>) => void;
  onUnbindSurface?: (payload: Readonly<Record<string, unknown>>) => void;
  onRefreshBuilds?: () => void;
}>;

const INITIAL_ROWS = 8;
const PROVIDER_LABELS: Readonly<Record<ControlRoomProvider, string>> = {
  chatgpt: "ChatGPT",
  claude_code: "Claude Code",
  claude_desktop: "Claude desktop",
  cursor_agent: "Cursor agent",
  codex: "Codex",
};
const ROLE_LABELS: Readonly<Record<ControlRoomRole, string>> = {
  chairman: "Chairman", ceo: "CEO", coo: "COO", worker: "Worker",
};
const OPERATION_LABELS: Readonly<Record<ControlRoomOperation, string>> = {
  open: "Open surface", bind: "Bind surface", unbind: "Unbind surface",
  "refresh-builds": "Refresh builds",
};
const PROVIDER_LABELS_ZH: Readonly<Record<ControlRoomProvider, string>> = {
  chatgpt: "ChatGPT", claude_code: "Claude Code", claude_desktop: "Claude 桌面端",
  cursor_agent: "Cursor 智能体", codex: "Codex",
};
const ROLE_LABELS_ZH: Readonly<Record<ControlRoomRole, string>> = {
  chairman: "主席", ceo: "CEO", coo: "COO", worker: "工作智能体",
};
const OPERATION_LABELS_ZH: Readonly<Record<ControlRoomOperation, string>> = {
  open: "打开界面", bind: "绑定界面", unbind: "解除绑定", "refresh-builds": "刷新构建",
};
const copy = (locale: ControlRoomSurfaceLocale) => (english: string, chinese: string) =>
  locale === "zh-CN" ? chinese : english;

function isUncertain(action: ControlRoomActionPresentation): boolean {
  return action.state === "RESULT"
    ? controlRoomActionIsUncertain(action.result)
    : action.state === "FAILURE" && action.disposition === "EFFECT_UNKNOWN";
}

function ActionPresentation({ action, locale }: { action: ControlRoomActionPresentation; locale: ControlRoomSurfaceLocale }) {
  const t = copy(locale);
  if (action.state === "IDLE") return null;
  if (action.state === "WITHHELD") {
    return (
      <div role="status" aria-live="polite">
        <p><strong>{t("Earlier action details withheld", "先前操作详情已隐藏")}</strong></p>
        <p>{t("Those details are unavailable in this workspace context.", "当前工作区上下文无法显示这些详情。")}</p>
        {action.held && (
          <p>{t("Further surface actions are paused. State and Discovery reads remain available.", "界面操作已暂停。仍可读取当前状态和发现结果。")}</p>
        )}
      </div>
    );
  }
  const operation = action.state === "RESULT" ? action.result.operation : action.operation;
  if (action.state === "PENDING") {
    return (
      <div role="status" aria-live="polite">
        <p><strong>{t("Awaiting action result", "正在等待操作结果")}</strong></p>
        <p>{t("Requested action:", "已请求的操作：")} {(locale === "zh-CN" ? OPERATION_LABELS_ZH : OPERATION_LABELS)[operation]}</p>
        <p>{t("Surface actions are paused. State and Discovery reads remain available.", "界面操作已暂停。仍可读取当前状态和发现结果。")}</p>
      </div>
    );
  }
  const uncertain = isUncertain(action);
  const disposition = action.state === "RESULT" ? action.result.disposition : action.disposition;
  const heading = uncertain
    ? t("Action outcome unknown", "操作结果未知")
    : disposition === "NOT_DISPATCHED"
      ? t("Action not dispatched", "操作尚未发出")
      : action.state === "RESULT" && action.result.outcome.ok === true
        ? t("Owner reported success", "负责方已返回成功结果")
        : t("Success was not reported", "未报告成功");
  return (
    <div>
      <div role="status" aria-live="polite">
        <p><strong>{heading}</strong></p>
        <p>{t("Requested action:", "已请求的操作：")} {(locale === "zh-CN" ? OPERATION_LABELS_ZH : OPERATION_LABELS)[operation]}</p>
        {uncertain ? (
          <>
            <p>{t("The action may have run. Further surface actions remain paused.", "操作可能已执行。后续界面操作仍处于暂停状态。")}</p>
            <p>{t("Reconcile the original action before another surface action.", "执行下一次界面操作前，需要核对原操作的结果。")}</p>
            <p>{t("No retry is sent automatically. State and Discovery reads remain available.", "不会自动重试。仍可读取当前状态和发现结果。")}</p>
          </>
        ) : disposition === "NOT_DISPATCHED" ? (
          <p>{t("This action was not dispatched. Review its receipt before choosing another action.", "此操作尚未发出。选择下一步操作前，请查看回执。")}</p>
        ) : action.state === "RESULT" && action.result.outcome.ok === true ? (
          <>
            <p>{t("The owner returned a successful result.", "负责方返回了成功结果。")}</p>
            {operation === "open" && action.result.outcome.verified !== true
              ? <p>{t("Verification that the surface is open was not confirmed.", "尚未确认界面已通过打开状态验证。")}</p>
              : null}
          </>
        ) : (
          <p>{t("The owner returned. This does not confirm that no change occurred.", "负责方已返回结果。这不能证明未发生任何变更。")}</p>
        )}
      </div>
      <details className="ccr-access">
        <summary>{t("Action receipt", "操作回执")}</summary>
        <div className="ccr-access-content">
          <p><code>{JSON.stringify(action.state === "RESULT" ? action.result : { operation, disposition })}</code></p>
        </div>
      </details>
    </div>
  );
}

type TextFieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  required?: boolean;
  description?: string;
  type?: "text" | "url";
};
function TextField({ id, label, value, onChange, disabled, required, description, type = "text" }: TextFieldProps) {
  return (
    <div className="form-field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id} type={type} value={value} required={required} disabled={disabled}
        autoComplete="off" spellCheck={false}
        aria-describedby={description ? `${id}-hint` : undefined}
        onChange={event => onChange(event.currentTarget.value)}
      />
      {description && <small id={`${id}-hint`}>{description}</small>}
    </div>
  );
}

type BindDraft = {
  workRef: string;
  role: ControlRoomRole | "";
  provider: ControlRoomProvider | "";
  seatRef: string;
  envManager: "" | "gologin" | "multilogin";
  folderId: string;
  profileId: string;
  url: string;
  projectDir: string;
  sessionId: string;
  chatId: string;
  workspaceDir: string;
  cwd: string;
};
const EMPTY_LOCATOR = {
  envManager: "" as const, folderId: "", profileId: "", url: "",
  projectDir: "", sessionId: "", chatId: "", workspaceDir: "", cwd: "",
};
function BindSurfaceForm({ disabled, onBind, locale }: {
  disabled: boolean;
  onBind: NonNullable<ControlRoomSurfaceControlsProps["onBindSurface"]>;
  locale: ControlRoomSurfaceLocale;
}) {
  const t = copy(locale);
  const id = useId();
  const [draft, setDraft] = useState<BindDraft>({
    workRef: "", role: "", provider: "", seatRef: "", ...EMPTY_LOCATOR,
  });
  const [error, setError] = useState<string | null>(null);
  function update<K extends keyof BindDraft>(key: K, value: BindDraft[K]) {
    setDraft(current => ({ ...current, [key]: value }));
    setError(null);
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled || !event.currentTarget.reportValidity()) return;
    if (!draft.workRef.trim() || !draft.role || !draft.provider ||
        (draft.provider === "chatgpt" && (!draft.seatRef.trim() || !draft.envManager))) {
      setError(t("Complete the work reference, role, provider and required seat details.", "请填写工作引用、角色、提供方及必需的席位信息。"));
      return;
    }
    // These are explicit form fields, not locators inferred from Discovery.
    // The incumbent codec owns wire validation; the server owns locator law.
    let locator: Record<string, unknown>;
    switch (draft.provider) {
      case "chatgpt":
        locator = {
          env_manager: draft.envManager, profile_id: draft.profileId, url: draft.url,
          ...(draft.envManager === "multilogin" ? { folder_id: draft.folderId } : {}),
        };
        break;
      case "claude_code":
        locator = { project_dir: draft.projectDir, session_id: draft.sessionId };
        break;
      case "claude_desktop":
        locator = { url: draft.url };
        break;
      case "cursor_agent":
        locator = { chat_id: draft.chatId, ...(draft.workspaceDir ? { workspace_dir: draft.workspaceDir } : {}) };
        break;
      case "codex":
        locator = { session_id: draft.sessionId, ...(draft.cwd ? { cwd: draft.cwd } : {}) };
        break;
      default:
        setError(t("Choose an available provider before submitting.", "提交前请选择可用的提供方。"));
        return;
    }
    let payload: Readonly<Record<string, unknown>>;
    try {
      payload = decodeControlRoomActionPayload({
        work_ref: draft.workRef, role: draft.role, provider: draft.provider, locator,
        ...(draft.seatRef ? { seat_ref: draft.seatRef } : {}),
      }, "bind");
    } catch {
      setError(t("These binding details could not be accepted. Review the fields before submitting.", "无法接受这些绑定信息。请检查各项内容后再提交。"));
      return;
    }
    setError(null);
    // Never catch a callback failure as a local no-dispatch result. App owns
    // the actual boundary, promise and outcome before invoking the host.
    onBind(payload);
  }
  const field = (key: "workRef" | "seatRef" | "folderId" | "profileId" | "url" | "projectDir" | "sessionId" | "chatId" | "workspaceDir" | "cwd",
                 label: string, required = true, description?: string, type: "text" | "url" = "text") => (
    <TextField key={key} id={`${id}-${key}`} label={label} value={draft[key]}
      onChange={value => update(key, value)} disabled={disabled}
      required={required} description={description} type={type} />
  );
  return (
    <details className="ccr-access">
      <summary>{t("Bind a surface", "绑定界面")}</summary>
      <div className="ccr-access-content">
        <p>{t("Enter the exact work reference and surface address to bind.", "输入要绑定的准确工作引用和界面地址。")}</p>
        <form aria-label={t("Bind a workspace surface", "绑定工作区界面")} onSubmit={submit}>
          {field("workRef", t("Work reference", "工作引用"), true, t("Use an exact WS:, JOB: or PR: reference.", "请使用准确的 WS:、JOB: 或 PR: 引用。"))}
          <div className="form-field">
            <label htmlFor={`${id}-role`}>{t("Role", "角色")}</label>
            <select id={`${id}-role`} value={draft.role} required disabled={disabled}
              onChange={event => update("role", event.currentTarget.value as BindDraft["role"])}>
              <option value="">{t("Choose a role", "选择角色")}</option>
              {(Object.keys(ROLE_LABELS) as ControlRoomRole[]).map(role => <option key={role} value={role}>{(locale === "zh-CN" ? ROLE_LABELS_ZH : ROLE_LABELS)[role]}</option>)}
            </select>
          </div>
          <div className="form-field">
            <label htmlFor={`${id}-provider`}>{t("Provider", "提供方")}</label>
            <select id={`${id}-provider`} value={draft.provider} required disabled={disabled}
              onChange={event => {
                const provider = event.currentTarget.value as BindDraft["provider"];
                setDraft(current => ({ ...current, ...EMPTY_LOCATOR, provider }));
                setError(null);
              }}>
              <option value="">{t("Choose a provider", "选择提供方")}</option>
              {(Object.keys(PROVIDER_LABELS) as ControlRoomProvider[]).map(provider => <option key={provider} value={provider}>{(locale === "zh-CN" ? PROVIDER_LABELS_ZH : PROVIDER_LABELS)[provider]}</option>)}
            </select>
          </div>
          {field("seatRef", draft.provider === "chatgpt" ? t("Seat reference (required for ChatGPT)", "席位引用（ChatGPT 必填）") : t("Seat reference (optional)", "席位引用（可选）"), draft.provider === "chatgpt")}
          {draft.provider === "chatgpt" && (
            <>
              <div className="form-field">
                <label htmlFor={`${id}-manager`}>{t("Environment manager", "环境管理器")}</label>
                <select id={`${id}-manager`} value={draft.envManager} required disabled={disabled}
                  onChange={event => {
                    const envManager = event.currentTarget.value as BindDraft["envManager"];
                    setDraft(current => ({ ...current, envManager, folderId: "", profileId: "" }));
                    setError(null);
                  }}>
                  <option value="">{t("Choose an environment manager", "选择环境管理器")}</option>
                  <option value="gologin">GoLogin</option>
                  <option value="multilogin">Multilogin</option>
                </select>
              </div>
              {draft.envManager === "multilogin" && field("folderId", t("Multilogin folder ID", "Multilogin 文件夹 ID"), true, t("The exact folder UUID.", "准确的文件夹 UUID。"))}
              {draft.envManager && field("profileId", t(`${draft.envManager === "gologin" ? "GoLogin" : "Multilogin"} profile ID`, `${draft.envManager === "gologin" ? "GoLogin" : "Multilogin"} 配置 ID`), true,
                draft.envManager === "gologin" ? t("The 24-character lowercase hexadecimal profile ID.", "24 位小写十六进制配置 ID。") : t("The exact profile UUID.", "准确的配置 UUID。"))}
              {field("url", t("ChatGPT conversation URL", "ChatGPT 对话 URL"), true, t("An exact conversation URL, including a Project conversation when applicable.", "准确的对话 URL；也可使用项目内对话的完整 URL。"), "url")}
              <p>{t("ChatGPT bindings can be saved here. Opening ChatGPT is currently unsupported.", "这里可以保存 ChatGPT 绑定，暂不支持打开 ChatGPT 界面。")}</p>
            </>
          )}
          {draft.provider === "claude_code" && <>
            {field("projectDir", t("Claude Code project directory", "Claude Code 项目目录"), true, t("The exact absolute project path.", "准确的项目绝对路径。"))}
            {field("sessionId", t("Claude Code session ID", "Claude Code 会话 ID"), true, t("The exact session UUID.", "准确的会话 UUID。"))}
          </>}
          {draft.provider === "claude_desktop" && field("url", t("Claude desktop URL", "Claude 桌面端 URL"), true, t("Use the exact claude:// address or an https://claude.ai URL.", "使用准确的 claude:// 地址或 https://claude.ai URL。"), "url")}
          {draft.provider === "cursor_agent" && <>
            {field("chatId", t("Cursor chat ID", "Cursor 对话 ID"))}
            {field("workspaceDir", t("Cursor workspace directory (optional)", "Cursor 工作区目录（可选）"), false, t("An absolute path, when supplied.", "如填写，请使用绝对路径。"))}
          </>}
          {draft.provider === "codex" && <>
            {field("sessionId", t("Codex session ID", "Codex 会话 ID"))}
            {field("cwd", t("Codex working directory (optional)", "Codex 工作目录（可选）"), false, t("An absolute path, when supplied.", "如填写，请使用绝对路径。"))}
          </>}
          {error && <p className="field-error" role="alert">{error}</p>}
          <div className="form-actions">
            <button type="submit" disabled={disabled}>{t("Bind", "绑定")}</button>
          </div>
        </form>
      </div>
    </details>
  );
}

function DiscoveryGroup<T>({ title, rows, children, locale }: {
  title: string;
  rows: readonly T[];
  children: (row: T) => ReactNode;
  locale: ControlRoomSurfaceLocale;
}) {
  const t = copy(locale);
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? rows : rows.slice(0, INITIAL_ROWS);
  return (
    <details className="ccr-access">
      <summary><span>{title}</span><span className="ccr-access-status">{t(`${rows.length} observed`, `已观察到 ${rows.length} 项`)}</span></summary>
      <div className="ccr-access-content">
        {rows.length ? (
          <ul className="items" aria-label={title}>
            {visible.map((row, index) => <li key={index}><div>{children(row)}</div></li>)}
          </ul>
        ) : <p>{t("No candidates in this observation.", "本次观察中没有候选项。")}</p>}
        {rows.length > INITIAL_ROWS && (
          <div className="form-actions">
            <button type="button" aria-expanded={expanded}
              aria-label={expanded ? t(`Show first ${INITIAL_ROWS} ${title.toLowerCase()}`, `${title}：显示前 ${INITIAL_ROWS} 项`) : t(`See all ${rows.length} ${title.toLowerCase()}`, `${title}：查看全部 ${rows.length} 项`)}
              onClick={() => setExpanded(value => !value)}>
              {expanded ? t(`Show first ${INITIAL_ROWS}`, `显示前 ${INITIAL_ROWS} 项`) : t(`See all ${rows.length}`, `查看全部 ${rows.length} 项`)}
            </button>
          </div>
        )}
      </div>
    </details>
  );
}

function DiscoveryPresentation({ discovery, locale }: { discovery: ControlRoomDiscoveryPresentation; locale: ControlRoomSurfaceLocale }) {
  const t = copy(locale);
  if (discovery.state !== "AVAILABLE") {
    return <p role="status">{discovery.state === "IDLE" ? t("Discovery has not been read.", "尚未读取发现结果。") : discovery.state === "PENDING" ? t("Reading surface discovery…", "正在读取界面发现结果……") : t("Surface discovery is unavailable.", "界面发现结果暂不可用。")}</p>;
  }
  const document = discovery.document;
  return (
    <div className="ccr-programmes">
      <p>{t("These observed candidates have not been bound or verified by this view.", "此视图尚未绑定或验证这些已观察到的候选项。")}</p>
      <DiscoveryGroup title={t("Multilogin environments", "Multilogin 环境")} rows={document.chatgpt_environments.multilogin} locale={locale}>
        {row => <>
          <p>{t("Profile", "配置")} <code>{row.profile_id}</code></p>
          <p>{t("Workspace", "工作区")} <code>{row.workspace_id}</code> · {t("Folder", "文件夹")} <code>{row.folder_id}</code></p>
          <p>{row.running ? t("Manager reports running in this observation.", "本次观察中，管理器报告其正在运行。") : t("Manager reports not running in this observation.", "本次观察中，管理器报告其未运行。")}</p>
        </>}
      </DiscoveryGroup>
      <DiscoveryGroup title={t("GoLogin environments", "GoLogin 环境")} rows={document.chatgpt_environments.gologin} locale={locale}>
        {row => <>
          <p>{t("Profile", "配置")} <code>{row.profile_id}</code></p>
          <p>{row.running ? t("Manager reports running in this observation.", "本次观察中，管理器报告其正在运行。") : t("Manager reports not running in this observation.", "本次观察中，管理器报告其未运行。")}</p>
        </>}
      </DiscoveryGroup>
      <DiscoveryGroup title={t("Claude Code sessions", "Claude Code 会话")} rows={document.claude_code_sessions} locale={locale}>
        {row => <>
          <p>{t("Session", "会话")} <code>{row.session_id}</code></p>
          <p>{t("Project", "项目")} <code>{row.project_dir}</code></p>
          <p>{t("Observed modification value", "观察到的修改时间值")} <code>{String(row.mtime)}</code></p>
        </>}
      </DiscoveryGroup>
      <DiscoveryGroup title={t("Codex sessions", "Codex 会话")} rows={document.codex_sessions} locale={locale}>
        {row => <>
          <p>{t("Session", "会话")} <code>{row.session_id}</code></p>
          <p>{t("Observed date", "观察到的日期")} <code>{row.date}</code></p>
        </>}
      </DiscoveryGroup>
      <details className="ccr-access">
        <summary>{t("Cursor discovery", "Cursor 发现")}</summary>
        <div className="ccr-access-content">
          <p>{t("Cursor discovery is not supported.", "暂不支持 Cursor 发现。")}</p>
          <p>{document.cursor.note}</p>
        </div>
      </details>
    </div>
  );
}

export function ControlRoomSurfaceControls({
  navigation, discovery, action, held, canAct, locale = "en",
  onDiscover, onOpenSurface, onBindSurface, onUnbindSurface, onRefreshBuilds,
}: ControlRoomSurfaceControlsProps) {
  const t = copy(locale);
  const providers = locale === "zh-CN" ? PROVIDER_LABELS_ZH : PROVIDER_LABELS;
  const roles = locale === "zh-CN" ? ROLE_LABELS_ZH : ROLE_LABELS;
  const id = useId();
  const [showAllBindings, setShowAllBindings] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const [unbindDraft, setUnbindDraft] = useState<string | null>(null);
  // This ref consumes only the unsubmitted local choice synchronously. It
  // does not retain an operation/result or replace App's action custody.
  const unbindDraftRef = useRef<string | null>(null);
  const current = canAct && navigation?.state === "AVAILABLE" ? navigation : null;
  const retained = held || (action.state === "WITHHELD" && action.held) || isUncertain(action);
  const disabled = !canAct || retained || action.state === "PENDING";
  const presentedAction: ControlRoomActionPresentation = !canAct && action.state !== "IDLE"
    ? { state: "WITHHELD", held: retained }
    : action.state === "IDLE" && retained ? { state: "WITHHELD", held: true } : action;
  const visibleBindings = current ? (showAllBindings ? current.bindings : current.bindings.slice(0, INITIAL_ROWS)) : [];

  function open(row: ControlRoomBindingSummary, desktop = false) {
    if (disabled || !onOpenSurface || row.provider === "chatgpt" || (desktop && row.provider !== "claude_code")) return;
    let payload: Readonly<Record<string, unknown>>;
    try {
      payload = decodeControlRoomActionPayload({ binding_id: row.binding_id, ...(desktop ? { target_surface: "desktop" } : {}) }, "open");
    } catch {
      setInputError(t("The surface address could not be accepted. Refresh the source before choosing a target.", "无法接受此界面地址。请选择刷新来源后再确定目标。"));
      return;
    }
    setInputError(null);
    onOpenSurface(payload);
  }
  function chooseUnbind(row: ControlRoomBindingSummary) {
    if (disabled || !onUnbindSurface) return;
    unbindDraftRef.current = row.binding_id;
    setUnbindDraft(row.binding_id);
    setInputError(null);
  }
  function keepBinding() {
    unbindDraftRef.current = null;
    setUnbindDraft(null);
  }
  function confirmUnbind() {
    const binding_id = unbindDraftRef.current;
    if (disabled || !onUnbindSurface || binding_id === null) return;
    let payload: Readonly<Record<string, unknown>>;
    try {
      payload = decodeControlRoomActionPayload({ binding_id }, "unbind");
    } catch {
      setInputError(t("The binding address could not be accepted. Refresh the source before choosing a target.", "无法接受此绑定地址。请刷新来源后再确定目标。"));
      return;
    }
    setInputError(null);
    // Consume before invoking App, including repeated activation before a
    // React commit. Dismissing a draft never clears an App pending/unknown.
    keepBinding();
    onUnbindSurface(payload);
  }
  const unbindConfirmation = canAct && onUnbindSurface && unbindDraft !== null ? (
    <div className="ccr-programmes" role="group" aria-label={t("Confirm binding removal", "确认移除绑定")}>
      <p><strong>{t("Unbind this surface?", "解除此界面的绑定？")}</strong></p>
      <p>{t("Confirm removal of this exact binding:", "请确认移除这一准确绑定：")} <code>{unbindDraft}</code></p>
      <div className="form-actions">
        <button type="button" disabled={disabled} onClick={confirmUnbind}>{t("Confirm Unbind", "确认解除绑定")}</button>
        <button type="button" onClick={keepBinding}>{t("Keep binding", "保留绑定")}</button>
      </div>
    </div>
  ) : null;

  return (
    <section aria-labelledby={`${id}-title`} className="ccr-programmes">
      <div className="ccr-list-heading">
        <h3 id={`${id}-title`}>{t("Workspace surfaces", "工作区界面")}</h3>
        {current && <span>{t(`${current.bindings.length} bindings observed`, `已观察到 ${current.bindings.length} 项绑定`)}</span>}
      </div>
      <ActionPresentation action={presentedAction} locale={locale} />
      {!canAct && <p>{t("Sign in to read and use the available workspace surface controls.", "登录后可读取并使用工作区中可用的界面控件。")}</p>}
      <div className="form-actions">
        {onDiscover && <button type="button" disabled={!canAct || discovery.state === "PENDING"} onClick={onDiscover}>
          {discovery.state === "PENDING" ? t("Reading Discovery…", "正在读取发现结果……") : t("Discover surfaces", "发现界面")}
        </button>}
        {onRefreshBuilds && <button type="button" disabled={disabled} onClick={() => { if (!disabled) onRefreshBuilds(); }}>{t("Refresh builds", "刷新构建")}</button>}
      </div>
      {onRefreshBuilds && <p className="ccr-observation">{t("Refresh builds updates the source. Overview Refresh reads the current Control Room state.", "“刷新构建”更新来源；概览中的“刷新”读取控制室当前状态。")}</p>}
      {inputError && canAct && <p className="field-error" role="alert">{inputError}</p>}
      <details className="ccr-access" open>
        <summary>{t("Surface bindings", "界面绑定")}</summary>
        <div className="ccr-access-content">
          {unbindDraft !== null && !visibleBindings.some(row => row.binding_id === unbindDraft) && unbindConfirmation}
          {current ? <>
            {current.conflicts.length > 0 && <p>{t("Some work roles have conflicting bindings. Select the exact binding you intend.", "部分工作角色存在绑定冲突。请明确选择你要使用的准确绑定。")}</p>}
            {!current.bindings.length && <p>{t("No surface bindings in this observation.", "本次观察中没有界面绑定。")}</p>}
            <ul className="items" aria-label={t("Observed surface bindings", "已观察到的界面绑定")}>
              {visibleBindings.map(row => {
                const conflicting = current.conflicts.some(conflict => conflict.binding_ids.includes(row.binding_id));
                return (
                  <li key={row.binding_id}>
                    <div>
                      <p><strong>{providers[row.provider]}</strong> · {roles[row.role]}{row.seat_ref !== null && <> · {t("Seat", "席位")} <code>{row.seat_ref}</code></>}</p>
                      <p>{t("Work", "工作")} <code>{row.work_ref}</code></p>
                      <p>{t("Binding", "绑定")} <code>{row.binding_id}</code></p>
                      {conflicting && <p>{t("Conflicting binding for this work role.", "此工作角色存在绑定冲突。")}</p>}
                      {current.unboundBindingIds.includes(row.binding_id) && <p>{t("This work reference is outside the current programme observation.", "此工作引用不在当前项目观察范围内。")}</p>}
                      {row.provider === "chatgpt" && onOpenSurface && <p>{t("Opening a ChatGPT surface is not supported here.", "这里暂不支持打开 ChatGPT 界面。")}</p>}
                      <div className="form-actions">
                        {onOpenSurface && row.provider !== "chatgpt" && <button type="button" disabled={disabled} aria-label={t(`Open ${providers[row.provider]} binding ${row.binding_id}`, `打开 ${providers[row.provider]} 绑定 ${row.binding_id}`)} onClick={() => open(row)}>{t("Open", "打开")}</button>}
                        {onOpenSurface && row.provider === "claude_code" && <button type="button" disabled={disabled} aria-label={t(`Open Claude Code binding ${row.binding_id} in Claude desktop`, `在 Claude 桌面端打开 Claude Code 绑定 ${row.binding_id}`)} onClick={() => open(row, true)}>{t("Open in Claude desktop", "在 Claude 桌面端打开")}</button>}
                        {onUnbindSurface && <button type="button" disabled={disabled} aria-label={t(`Unbind ${providers[row.provider]} binding ${row.binding_id}`, `解除 ${providers[row.provider]} 绑定 ${row.binding_id}`)} onClick={() => chooseUnbind(row)}>{t("Unbind", "解除绑定")}</button>}
                      </div>
                      {unbindDraft === row.binding_id && unbindConfirmation}
                      <details className="ccr-access">
                        <summary>{t("Binding details", "绑定详情")}</summary>
                        <div className="ccr-access-content">
                          <dl>
                            <dt>{t("Observed", "观察时间")}</dt><dd>{row.observed_at}</dd>
                            <dt>{t("Last verified", "最后验证时间")}</dt><dd>{row.last_verified_at ?? t("Not reported", "未报告")}</dd>
                          </dl>
                        </div>
                      </details>
                    </div>
                  </li>
                );
              })}
            </ul>
            {current.bindings.length > INITIAL_ROWS && <div className="form-actions">
              <button type="button" aria-expanded={showAllBindings} onClick={() => setShowAllBindings(value => !value)}>{showAllBindings ? t(`Show first ${INITIAL_ROWS} bindings`, `显示前 ${INITIAL_ROWS} 项绑定`) : t(`See all ${current.bindings.length} bindings`, `查看全部 ${current.bindings.length} 项绑定`)}</button>
            </div>}
          </> : <p>{t("Surface binding observations are unavailable.", "界面绑定观察暂不可用。")}</p>}
        </div>
      </details>
      {canAct && onBindSurface && <BindSurfaceForm disabled={disabled} onBind={onBindSurface} locale={locale} />}
      <section aria-label={t("Surface discovery", "界面发现")} className="ccr-programmes">
        <div className="ccr-list-heading"><h3>{t("Surface discovery", "界面发现")}</h3></div>
        <DiscoveryPresentation discovery={canAct ? discovery : { state: "UNAVAILABLE" }} locale={locale} />
      </section>
    </section>
  );
}
