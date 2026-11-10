import { useEffect, useMemo, useRef, useState } from "react";
import { createIndexedDbPendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import type { OperationPointer } from "../orchestration/operation-controller";
import type { CompanyTransport } from "./transport";
import {
  validateBacklogRequest,
  type BacklogRequest,
  type CompanyRead,
  type CompanyReceipt,
  type CompanySelection,
  type CompanySnapshot,
} from "./contract";
import { companyPendingPointer, readCompanyPending } from "./pending";
import { CompanyViews } from "./CompanyViews";
import "./company.css";

type Destination =
  "Projects" | "Conversations" | "Meta-CEO" | "Fleet & Capacity";
interface Props {
  transport?: CompanyTransport;
  authGeneration: number;
  canRead: boolean;
  locale: "en" | "zh-CN";
  onNavigate(destination: Destination): void;
  onOpenProject?(workRef: string): boolean;
}
const tabs = [
  ["overview", "Overview", "概览"],
  ["people", "People", "成员"],
  ["work", "Work", "工作"],
  ["projects", "Projects", "项目"],
  ["goals", "Goals", "目标"],
  ["routines", "Routines", "例行工作"],
  ["artifacts", "Artifacts", "成果"],
  ["activity", "Activity", "活动"],
] as const;

export function CompanyWorkspace({
  transport,
  authGeneration,
  canRead,
  locale,
  onNavigate,
  onOpenProject,
}: Props) {
  const zh = locale === "zh-CN",
    t = (en: string, cn: string) => (zh ? cn : en);
  const [selection, setSelection] = useState<CompanySelection>({
    view: "overview",
  });
  const [returnSelection, setReturnSelection] = useState<CompanySelection>({
    view: "work",
  });
  const [read, setRead] = useState<CompanyRead | null>(null);
  const [loading, setLoading] = useState(false),
    [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0),
    [compose, setCompose] = useState(false);
  const [title, setTitle] = useState(""),
    [description, setDescription] = useState("");
  const [pending, setPending] = useState<OperationPointer | null>(null),
    [pendingReady, setPendingReady] = useState(false);
  const [busy, setBusy] = useState(false),
    [notice, setNotice] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<CompanyReceipt | null>(null);
  const owner = useRef({ transport, authGeneration, alive: true });
  owner.current.transport = transport;
  owner.current.authGeneration = authGeneration;
  const action = useRef<AbortController | null>(null);
  const store = useMemo(
    () =>
      createIndexedDbPendingPointerStore(
        typeof indexedDB === "undefined" ? undefined : indexedDB,
      ),
    [],
  );
  const snapshot: CompanySnapshot | null =
    read && read.state !== "UNAVAILABLE" ? read : null;

  useEffect(() => {
    owner.current.alive = true;
    return () => {
      owner.current.alive = false;
      action.current?.abort();
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setRead(null);
    setError(null);
    setLoading(false);
    setReceipt(null);
    if (!canRead || !transport) return () => controller.abort();
    setLoading(true);
    transport
      .read(selection, controller.signal)
      .then(
        (value) => {
          if (!controller.signal.aborted) setRead(value);
        },
        () => {
          if (!controller.signal.aborted) setError("COMPANY_READ_UNAVAILABLE");
        },
      )
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [transport, authGeneration, canRead, selection, refresh]);
  useEffect(() => {
    const controller = new AbortController();
    setPending(null);
    setPendingReady(false);
    if (!snapshot) return () => controller.abort();
    store.read(snapshot.scopeKey, controller.signal).then(
      (pointer) => {
        if (!controller.signal.aborted) {
          setPending(pointer);
          setPendingReady(true);
        }
      },
      () => {
        if (!controller.signal.aborted)
          setNotice("PENDING_POINTER_STORE_UNAVAILABLE");
      },
    );
    return () => controller.abort();
  }, [store, snapshot?.scopeKey, snapshot?.bindingRevision, authGeneration]);

  function select(next: CompanySelection) {
    if (
      ["task", "routine", "runtime"].includes(next.view) &&
      !["task", "routine", "runtime"].includes(selection.view)
    )
      setReturnSelection(selection);
    setSelection(next);
    setReceipt(null);
  }
  async function captureBacklog() {
    if (
      !snapshot ||
      !transport?.createBacklog ||
      busy ||
      !pendingReady ||
      pending ||
      !snapshot.capabilities.includes("create_backlog") ||
      !title.trim()
    )
      return;
    const current = snapshot,
      currentOwner = transport,
      generation = authGeneration;
    const controller = new AbortController();
    action.current = controller;
    const stillCurrent = () =>
      owner.current.alive &&
      owner.current.transport === currentOwner &&
      owner.current.authGeneration === generation &&
      !controller.signal.aborted;
    setBusy(true);
    setNotice(null);
    const requestId = crypto.randomUUID();
    const pointer = companyPendingPointer(
      String(current.company.id),
      current.scopeKey,
      requestId,
    );
    const request: BacklogRequest = {
      operation: "create_backlog",
      requestId,
      bindingRevision: current.bindingRevision,
      title: title.trim(),
      description,
      ...(selection.projectId ? { projectId: selection.projectId } : {}),
    };
    try {
      validateBacklogRequest(request);
    } catch {
      setNotice("COMPANY_COMMAND_INVALID");
      setBusy(false);
      return;
    }
    try {
      const reservation = await store.reserve(
        current.scopeKey,
        pointer,
        controller.signal,
      );
      if (!stillCurrent()) return;
      if (!reservation.reserved) {
        setPending(reservation.pointer);
        setNotice("ORIGINAL_SOURCE_REQUEST_RETAINED");
        return;
      }
      setPending(pointer);
      const result = await currentOwner.createBacklog!(
        request,
        { scopeKey: current.scopeKey, companyId: String(current.company.id) },
        controller.signal,
      );
      if (!stillCurrent()) return;
      if (result.state === "SAVED" || result.state === "NOT_APPLIED") {
        await store.clearIfEqual(current.scopeKey, pointer, controller.signal);
        if (!stillCurrent()) return;
        setPending(await store.read(current.scopeKey, controller.signal));
        if (!stillCurrent()) return;
        if (result.state === "SAVED" && result.item) {
          setTitle("");
          setDescription("");
          setCompose(false);
          setNotice("BACKLOG_SAVED_NO_RUN_REQUESTED");
          select({ view: "task", itemId: String(result.item.id) });
        } else setNotice(result.code ?? "SOURCE_REQUEST_NOT_APPLIED");
      } else setNotice(result.code ?? "SOURCE_OUTCOME_UNCONFIRMED");
    } catch {
      // A reservation or dispatch may have succeeded. Read-only reconciliation
      // follows; never generate another request ID to route around uncertainty.
      if (stillCurrent()) {
        setNotice("SOURCE_OUTCOME_UNCONFIRMED");
        setPendingReady(false);
        try {
          const retained = await store.read(
            current.scopeKey,
            controller.signal,
          );
          if (stillCurrent()) {
            setPending(retained);
            setPendingReady(true);
          }
        } catch {
          /* retain the fence */
        }
      }
    } finally {
      if (stillCurrent()) setBusy(false);
    }
  }
  async function checkOriginal() {
    if (!snapshot || !pending || !transport || busy) return;
    const original = readCompanyPending(pending, snapshot.scopeKey);
    if (!original || original.company_id !== snapshot.company.id) {
      setNotice("ORIGINAL_OPERATION_OWNER_REQUIRED");
      return;
    }
    const current = snapshot,
      pointer = pending,
      currentOwner = transport,
      generation = authGeneration;
    const controller = new AbortController();
    action.current = controller;
    const stillCurrent = () =>
      owner.current.alive &&
      owner.current.transport === currentOwner &&
      owner.current.authGeneration === generation &&
      !controller.signal.aborted;
    setBusy(true);
    try {
      const observed = await currentOwner.read(
        { view: "receipt", requestId: original.request_id },
        controller.signal,
      );
      if (!stillCurrent() || observed.state === "UNAVAILABLE") return;
      if (
        observed.scopeKey !== current.scopeKey ||
        observed.company.id !== current.company.id
      )
        throw new Error("SOURCE_SCOPE_CHANGED");
      setReceipt(observed.receipt ?? null);
      if (observed.receipt?.state === "SAVED") {
        await store.clearIfEqual(current.scopeKey, pointer, controller.signal);
        if (!stillCurrent()) return;
        setPending(await store.read(current.scopeKey, controller.signal));
        if (!stillCurrent()) return;
        setNotice("ORIGINAL_SOURCE_RECEIPT_CONFIRMED");
      } else setNotice("ORIGINAL_SOURCE_RECEIPT_REQUIRED");
    } catch {
      if (stillCurrent()) setNotice("SOURCE_OUTCOME_UNCONFIRMED");
    } finally {
      if (stillCurrent()) setBusy(false);
    }
  }

  return (
    <section
      className="company-workspace"
      aria-label={t("Always-on company", "持续运作的公司")}
    >
      <header className="company-header">
        <div>
          <span className="company-kicker">
            {t("TEAM / COMPANY", "团队 / 公司")}
          </span>
          <h1>
            {snapshot
              ? String(snapshot.company.name ?? "Mastermind")
              : t("Your company at work", "你的公司正在协作")}
          </h1>
          <p>
            {t(
              "One team, shared work, retained context.",
              "同一团队，共享工作，保留上下文。",
            )}
          </p>
        </div>
        <div className="company-inline-actions">
          <button type="button" onClick={() => onNavigate("Conversations")}>
            {t("Conversations", "对话")} ↗
          </button>
          <button
            type="button"
            onClick={() => setRefresh((value) => value + 1)}
            disabled={loading || !canRead || !transport}
          >
            {loading ? t("Reading…", "读取中…") : t("Refresh", "刷新")}
          </button>
        </div>
      </header>
      <nav className="company-tabs" aria-label={t("Company views", "公司视图")}>
        {tabs.map(([view, en, cn]) => (
          <button
            type="button"
            key={view}
            aria-current={selection.view === view ? "page" : undefined}
            onClick={() => select({ view })}
          >
            {zh ? cn : en}
          </button>
        ))}
      </nav>
      {!canRead ? (
        <div className="company-empty">
          <h2>{t("Sign in to your company workspace", "登录公司工作区")}</h2>
          <p>
            {t(
              "The existing Workspace account determines what you can see and manage.",
              "现有工作区账户决定你可以查看和管理的内容。",
            )}
          </p>
        </div>
      ) : !transport ? (
        <div className="company-empty">
          <h2>{t("Company host is not attached", "公司接口尚未接入")}</h2>
          <p>
            {t(
              "This app requires the new company methods on its existing Workspace host. The Hermes runtime is unchanged.",
              "应用需要现有工作区提供公司接口。Hermes 运行时保持不变。",
            )}
          </p>
        </div>
      ) : null}
      {loading && (
        <p role="status">
          {t(
            "Reading the existing Paperclip company…",
            "正在读取现有 Paperclip 公司…",
          )}
        </p>
      )}
      {error && (
        <div className="company-empty" role="alert">
          <h2>{t("Company data could not be read", "无法读取公司数据")}</h2>
          <p>
            {t(
              "Access, connection or source response changed. No fallback company has been created.",
              "访问权限、连接或来源响应已变化。没有创建替代公司。",
            )}
          </p>
          <code>{error}</code>
        </div>
      )}
      {read?.state === "UNAVAILABLE" && (
        <div className="company-empty" role="status">
          <h2>
            {t(
              "Paperclip connection is not available",
              "Paperclip 连接暂不可用",
            )}
          </h2>
          <p>
            {t(
              "Bind the existing company and the current principal in the installed Workspace configuration. Do not provision another team.",
              "在现有工作区配置中绑定现有公司与当前身份，不要另行创建团队。",
            )}
          </p>
          <code>{read.code}</code>
        </div>
      )}
      {notice && (
        <div className="company-command-notice" role="status">
          <p>
            {notice === "BACKLOG_SAVED_NO_RUN_REQUESTED"
              ? t(
                  "Saved to the company backlog. No agent run was requested.",
                  "已保存至公司待办，没有请求机器人执行。",
                )
              : notice === "ORIGINAL_SOURCE_RECEIPT_CONFIRMED"
                ? t(
                    "The original source receipt is confirmed.",
                    "原始来源回执已确认。",
                  )
                : notice === "PENDING_POINTER_STORE_UNAVAILABLE"
                  ? t(
                      "Recovery storage is unavailable. Saving is disabled so an interrupted request cannot be lost.",
                      "恢复存储不可用。为避免丢失中断的请求，保存功能已停用。",
                    )
                  : notice === "OS_PROJECT_REFERENCE_UNAVAILABLE"
                    ? t(
                        "The original OS project is not in the current permitted catalogue. Your Paperclip work remains open.",
                        "原 OS 项目不在当前可访问目录中，Paperclip 工作保持打开。",
                      )
                    : notice === "COMPANY_COMMAND_INVALID"
                      ? t(
                          "Shorten the draft before saving. No request was sent.",
                          "请先缩短草稿再保存，尚未发送请求。",
                        )
                      : t(
                          "Keep the original request. Check its source receipt before saving again.",
                          "请保留原请求，核对来源回执后再保存。",
                        )}
          </p>
          <details>
            <summary>{t("Details", "详情")}</summary>
            <code>{notice}</code>
          </details>
        </div>
      )}
      {snapshot && (
        <>
          {snapshot.state === "PARTIAL" && (
            <p role="status">
              {t(
                "Some source views are unavailable; available views remain usable.",
                "部分来源视图不可用；其余视图仍可使用。",
              )}
            </p>
          )}
          <div className="company-context-bar">
            <div>
              {["task", "routine", "runtime"].includes(selection.view) && (
                <button type="button" onClick={() => select(returnSelection)}>
                  ← {t("Back to original view", "返回原视图")}
                </button>
              )}
              {selection.projectId && (
                <span>
                  {t("Project scope", "项目范围")}:{" "}
                  <code>{selection.projectId}</code>
                </span>
              )}
              {(selection.offset || selection.cursor || selection.status) && (
                <button
                  type="button"
                  onClick={() =>
                    select({
                      view: selection.view,
                      ...(selection.projectId
                        ? { projectId: selection.projectId }
                        : {}),
                    })
                  }
                >
                  {t("Clear filters / First page", "清除筛选 / 首页")}
                </button>
              )}
            </div>
            {snapshot.capabilities.includes("create_backlog") &&
              transport?.createBacklog && (
                <button
                  type="button"
                  onClick={() => setCompose((value) => !value)}
                  disabled={busy || Boolean(pending) || !pendingReady}
                >
                  {t("Capture work", "记录工作")}
                </button>
              )}
          </div>
          {pending && (
            <section
              className="company-inset"
              aria-label={t("Retained source request", "保留的来源请求")}
            >
              <h2>
                {t(
                  "Check the original request before another save.",
                  "再次保存前，先核对原始请求。",
                )}
              </h2>
              <p>
                {t(
                  "A saved pointer is retained in the existing recovery store. A missing response does not mean nothing happened.",
                  "原请求引用已保留在现有恢复存储中。没有收到响应并不意味着未产生变更。",
                )}
              </p>
              <button
                type="button"
                onClick={() => void checkOriginal()}
                disabled={busy}
              >
                {t("Check original source receipt", "检查原始来源回执")}
              </button>
              {receipt?.candidates.map((candidate) => (
                <p key={candidate.id}>
                  <button
                    type="button"
                    onClick={() =>
                      select({ view: "task", itemId: String(candidate.id) })
                    }
                  >
                    {t("Inspect possible original task", "查看可能的原始任务")}:{" "}
                    {String(candidate.title ?? candidate.id)}
                  </button>
                </p>
              ))}
            </section>
          )}
          {compose && snapshot.capabilities.includes("create_backlog") && (
            <form
              className="company-section company-compose"
              onSubmit={(event) => {
                event.preventDefault();
                void captureBacklog();
              }}
            >
              <h2>
                {t("Save work to the company backlog", "保存到公司工作待办")}
              </h2>
              <label>
                {t("Title", "标题")}
                <input
                  value={title}
                  maxLength={300}
                  required
                  onChange={(event) => setTitle(event.target.value)}
                  disabled={busy}
                />
              </label>
              <label>
                {t("Context and intended result", "上下文与期望结果")}
                <textarea
                  value={description}
                  maxLength={16000}
                  rows={5}
                  onChange={(event) => setDescription(event.target.value)}
                  disabled={busy}
                />
              </label>
              <p className="company-muted">
                {t(
                  "Creates an unassigned backlog item. This action does not request an agent run or change a schedule.",
                  "创建未分派的待办任务。此操作不请求机器人执行，也不更改调度。",
                )}
              </p>
              <div className="company-inline-actions">
                <button
                  type="submit"
                  disabled={
                    busy || !pendingReady || Boolean(pending) || !title.trim()
                  }
                >
                  {busy
                    ? t("Saving…", "保存中…")
                    : t("Save backlog item", "保存待办")}
                </button>
                <button
                  type="button"
                  onClick={() => setCompose(false)}
                  disabled={busy}
                >
                  {t("Close editor", "关闭编辑器")}
                </button>
              </div>
            </form>
          )}
          <CompanyViews
            snapshot={snapshot}
            selection={selection}
            locale={locale}
            onSelect={select}
            onOpenProject={
              onOpenProject
                ? (workRef) => {
                    if (!onOpenProject(workRef))
                      setNotice("OS_PROJECT_REFERENCE_UNAVAILABLE");
                  }
                : undefined
            }
          />
          <details className="company-source-details">
            <summary>
              {t(
                "Sources, ownership and runtime integration",
                "来源、归属与运行时集成",
              )}
            </summary>
            <dl className="company-facts">
              <dt>Paperclip company</dt>
              <dd>
                <code>{snapshot.company.id}</code>
              </dd>
              <dt>{t("Observed at", "读取时间")}</dt>
              <dd>{snapshot.observedAt}</dd>
              <dt>{t("Source revision", "来源版本")}</dt>
              <dd>
                <code>
                  {snapshot.sourceRevision ?? t("Not supplied", "未提供")}
                </code>
              </dd>
              <dt>{t("Work owner", "工作负责人")}</dt>
              <dd>{snapshot.ownership.work}</dd>
              <dt>{t("Wake owner", "唤醒负责人")}</dt>
              <dd>{snapshot.ownership.wake}</dd>
            </dl>
            <p>
              {t(
                "Hermes remains the bot runtime. Executive and Capacity retain admission and routing. These views do not install, unpause, restart or clone agents.",
                "Hermes 仍是机器人运行时。Executive 与 Capacity 保留准入和路由职责。浏览这些视图不会安装、解除暂停、重启或克隆机器人。",
              )}
            </p>
            <div className="company-inline-actions">
              <button type="button" onClick={() => onNavigate("Meta-CEO")}>
                {t("Retained supervisor workspace", "保留的主管工作区")} ↗
              </button>
              <button
                type="button"
                onClick={() => onNavigate("Fleet & Capacity")}
              >
                {t("Capacity and resources", "容量与资源")} ↗
              </button>
              <button type="button" onClick={() => onNavigate("Projects")}>
                {t("Existing OS projects", "现有 OS 项目")} ↗
              </button>
            </div>
          </details>
        </>
      )}
    </section>
  );
}
