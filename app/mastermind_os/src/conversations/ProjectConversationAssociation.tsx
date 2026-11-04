import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import {
  decodeProjectAssociation,
  normalizeProjectAssociationSelection,
  type ProjectAssociationDocument,
  type ProjectAssociationRead,
  type ProjectAssociationSelection,
  type ProjectAssociationState,
} from "./project-association";

export type ConversationLocale = "en" | "zh-CN";

const STATIC_ZH: Record<string, string> = {
  "Observational read": "观测读取",
  "Session evidence": "会话记录",
  "Work": "工作",
  "Root job": "根作业",
  "Loading session information…": "正在加载会话信息…",
  "A managed session was observed.": "已观测到托管会话。",
  "A saved session record is available. Its current connection is not confirmed. Nothing resumes automatically.": "有保留的会话记录，但尚未确认当前连接。不会自动恢复。",
  "The project and its work are recorded. No managed session has been recorded yet.": "项目及其工作已记录，尚无托管会话记录。",
  "Session information is unavailable here.": "此处无法获取会话信息。",
  "Observation only: this view cannot send messages or continue sessions, and it does not assert that a session is working.": "仅观测：此视图无法发送消息或继续会话，也不声称会话正在工作。",
  "Owner-reported reason": "所有者报告的原因",
  "The response could not be decoded as an owner association document. This is a local decoding result, not an owner-reported reason.": "响应无法解码为所有者关联文档。这是本地解码结果，并非所有者报告的原因。",
  "The observation read failed locally before an owner response was decoded. This is not an owner-reported reason.": "观测读取在本地失败，未解码出所有者响应。这并非所有者报告的原因。",
  "Session information could not be displayed.": "无法显示会话信息。",
  "Session information could not be loaded.": "无法加载会话信息。",
  "Evidence details": "证据详情",
  "Source publication": "源发布",
  "Runtime creation": "运行时创建",
  "Materialization receipt": "物化凭据",
  "Path": "路径",
  "Operation": "操作",
  "Generation": "代次",
  "Owner receipt recorded at": "所有者凭据记录时间",
  "The receipt time above is recorded by the owner; it is not a locally observed clock.": "上方的凭据时间由所有者记录，不是本地观测时钟。",
  "Refresh observation": "刷新观测",
  "No valid workspace selection is available for this evidence read.": "当前没有可用于此证据读取的有效工作区选择。",
  "No current host generation is available for this evidence read.": "当前没有可用于此证据读取的主机代次。",
  "No association observation port is connected for this selection.": "此选择未连接关联观测端口。",
};

function ui(locale: ConversationLocale, text: string) { return locale === "zh-CN" ? STATIC_ZH[text] ?? text : text; }

const STATE_COPY: Record<ProjectAssociationState, string> = {
  MATERIALIZED_OBSERVATION: "A managed session was observed.",
  RECORDED_MATERIALIZATION: "A saved session record is available. Its current connection is not confirmed. Nothing resumes automatically.",
  PREPARING: "The project and its work are recorded. No managed session has been recorded yet.",
  UNAVAILABLE: "Session information is unavailable here.",
};

type AssociationReadStatus =
  | { readonly kind: "reading" }
  | { readonly kind: "document"; readonly document: ProjectAssociationDocument }
  | { readonly kind: "malformed" }
  | { readonly kind: "read-failed" };

/** Local observational evidence for the Project -> managed Runtime session
 * association of one exact workspace selection. One bounded read per mount or
 * explicit refresh, through the supplied signed owner port only; every
 * display change is local and no send, continue, resume, replay or polling
 * authority is created here. */
export interface ProjectConversationAssociationProps {
  readonly selection: ProjectAssociationSelection | null;
  readonly authGeneration: number;
  readonly hostGeneration: string | number | null;
  readonly readAssociation?: ProjectAssociationRead;
  readonly locale?: ConversationLocale;
}

export function ProjectConversationAssociation(props: ProjectConversationAssociationProps) {
  const normalized = normalizeProjectAssociationSelection(props.selection);
  const host = props.hostGeneration;
  const hostGeneration = typeof host === "string" && host.length > 0 || typeof host === "number" && Number.isFinite(host) ? host : null;
  const method = useRef({ value: props.readAssociation, epoch: 0 });
  if (method.current.value !== props.readAssociation) {
    method.current = { value: props.readAssociation, epoch: method.current.epoch + 1 };
  }
  const epoch = JSON.stringify([props.authGeneration, hostGeneration, normalized, method.current.epoch]);
  // A keyed private body removes old evidence during render, before effects
  // or paint. Effect dependency changes alone do not supply that boundary.
  return <ProjectAssociationBody key={epoch} {...props} selection={normalized} hostGeneration={hostGeneration} />;
}

function ProjectAssociationBody(props: ProjectConversationAssociationProps) {
  const { selection, authGeneration, hostGeneration, readAssociation, locale = "en" } = props;
  const headingId = useId();
  const normalized = useMemo(() => normalizeProjectAssociationSelection(selection), [selection]);
  const selectionKey = normalized === null ? "" : `${normalized.workRef}\n${normalized.rootJobId}`;
  const hostKey = hostGeneration === null ? null : String(hostGeneration);
  const portReady = typeof readAssociation === "function";
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState<AssociationReadStatus>({ kind: "reading" });
  const ticketRef = useRef(0);
  const busy = status.kind === "reading";

  // The private read body is keyed by auth generation, actual host
  // generation, the exact selection and the actual port identity: any
  // replacement aborts the previous read and clears the view before a new
  // result can paint. The monotonic ticket rejects late completions, so
  // StrictMode cleanup cannot leave a busy or stale view behind.
  useEffect(() => {
    if (selectionKey === "" || hostKey === null || typeof readAssociation !== "function") return;
    const separator = selectionKey.indexOf("\n");
    const target = normalizeProjectAssociationSelection({
      workRef: selectionKey.slice(0, separator),
      rootJobId: selectionKey.slice(separator + 1),
    });
    if (!target) return;
    const port = readAssociation;
    const ticket = ++ticketRef.current;
    const controller = new AbortController();
    setStatus({ kind: "reading" });
    const request = Object.freeze({
      workRef: target.workRef,
      rootJobId: target.rootJobId,
      signal: controller.signal,
    });
    let returned: Promise<unknown>;
    try { returned = Promise.resolve(port(request)); }
    catch (error) { returned = Promise.reject(error); }
    returned.then(
      raw => {
        if (ticketRef.current !== ticket || controller.signal.aborted) return;
        const document = decodeProjectAssociation(raw, target);
        if (ticketRef.current !== ticket || controller.signal.aborted) return;
        setStatus(document === null ? { kind: "malformed" } : { kind: "document", document });
      },
      () => {
        if (ticketRef.current !== ticket || controller.signal.aborted) return;
        setStatus({ kind: "read-failed" });
      },
    );
    return () => {
      ticketRef.current += 1;
      controller.abort();
    };
  }, [selectionKey, hostKey, authGeneration, readAssociation, attempt]);


  const refresh = useCallback(() => {
    if (selectionKey === "" || hostKey === null || !portReady) return;
    setAttempt(value => value + 1);
  }, [selectionKey, hostKey, portReady]);

  const missing = normalized === null || hostKey === null || !portReady;
  const diagnostic = missing ? normalized === null
    ? "No valid workspace selection is available for this evidence read."
    : hostKey === null ? "No current host generation is available for this evidence read."
    : "No association observation port is connected for this selection."
    : status.kind === "malformed"
      ? "The response could not be decoded as an owner association document. This is a local decoding result, not an owner-reported reason."
      : status.kind === "read-failed"
        ? "The observation read failed locally before an owner response was decoded. This is not an owner-reported reason."
        : null;
  const document = !missing && status.kind === "document" ? status.document : null;
  return (
    <section className="conversation-companion" lang={locale} aria-labelledby={headingId} aria-busy={!missing && busy}>
      <h2 id={headingId}>{ui(locale, "Session evidence")}</h2>
      <div className="card conversation-state" role="status" aria-live="polite">
        {missing ? <p>{ui(locale, "Session information is unavailable here.")}</p> : <>
          {status.kind === "reading" && <p>{ui(locale, "Loading session information…")}</p>}
          {status.kind === "malformed" && <p>{ui(locale, "Session information could not be displayed.")}</p>}
          {status.kind === "read-failed" && <p>{ui(locale, "Session information could not be loaded.")}</p>}
          {document && <p>{ui(locale, STATE_COPY[document.state])}</p>}
        </>}
      </div>
      <details className="conversation-association">
        <summary>{ui(locale, "Evidence details")}</summary>
        {normalized && <dl><dt>{ui(locale, "Work")}</dt><dd className="visible-text">{normalized.workRef}</dd>
          <dt>{ui(locale, "Root job")}</dt><dd className="visible-text">{normalized.rootJobId}</dd></dl>}
        {diagnostic && <p className="muted">{ui(locale, diagnostic)}</p>}
        {document && <>
          <p className="conversation-history"><span className="visible-text">{document.availability}</span> · <span className="visible-text">{document.state}</span></p>
          {document.reason && <p className="muted">{ui(locale, "Owner-reported reason")} · <span className="visible-text">{document.reason}</span></p>}
          <p className="muted">{ui(locale, "Observation only: this view cannot send messages or continue sessions, and it does not assert that a session is working.")}</p>
        </>}
          {document?.project_source != null && <dl aria-label={ui(locale, "Source publication")}>
            <dt>{ui(locale, "Source publication")}</dt>
            <dd><span className="visible-text">{document.project_source.repository}</span> · <span className="visible-text">{document.project_source.commit}</span></dd>
            <dt>{ui(locale, "Path")}</dt><dd className="visible-text">{document.project_source.path}</dd>
            <dt>content_sha256</dt><dd className="visible-text">{document.project_source.content_sha256}</dd>
            <dt>request_sha256</dt><dd className="visible-text">{document.project_source.request_sha256}</dd>
          </dl>}
          {document?.runtime_creation != null && <dl aria-label={ui(locale, "Runtime creation")}>
            <dt>{ui(locale, "Runtime creation")}</dt>
            <dt>intent_id</dt><dd className="visible-text">{document.runtime_creation.intent_id}</dd>
            <dt>fingerprint</dt><dd className="visible-text">{document.runtime_creation.fingerprint}</dd>
            <dt>creation_event_sha256</dt><dd className="visible-text">{document.runtime_creation.creation_event_sha256}</dd>
          </dl>}
          {document?.materialization != null && <dl aria-label={ui(locale, "Materialization receipt")}>
            <dt>{ui(locale, "Materialization receipt")}</dt>
            <dt>receipt_sha256</dt><dd className="visible-text">{document.materialization.receipt_sha256}</dd>
            <dt>{ui(locale, "Operation")}</dt><dd className="visible-text">{document.materialization.operation_kind}</dd>
            <dt>{ui(locale, "Generation")}</dt><dd className="visible-text">{document.materialization.generation_number}</dd>
            <dt>epoch_sha256</dt><dd className="visible-text">{document.materialization.epoch_sha256}</dd>
            <dt>process_generation_sha256</dt><dd className="visible-text">{document.materialization.process_generation_sha256}</dd>
            <dt>provider_session_sha256</dt><dd className="visible-text">{document.materialization.provider_session_sha256}</dd>
            <dt>{ui(locale, "Owner receipt recorded at")}</dt><dd className="visible-text">{document.materialization.recorded_at}</dd>
          </dl>}
          {document?.materialization != null && <p className="muted">{ui(locale, "The receipt time above is recorded by the owner; it is not a locally observed clock.")}</p>}
        </details>
      {!missing && <div className="conversation-context">
        <button type="button" className="button" onClick={refresh} disabled={busy || !portReady}>
          {ui(locale, "Refresh observation")}
        </button>
      </div>}
    </section>
  );
}
