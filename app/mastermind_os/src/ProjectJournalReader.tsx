import { useLayoutEffect, useMemo, useRef, useState } from "react";
import "./workJourney.css";
import "./project-journal.css";
import {
  decodeProjectJournal,
  ProjectJournalDecodeError,
  validJournalWorkRef,
  type JournalEntry,
  type JournalReasonCode,
  type ProjectJournalDocument,
} from "./project-journal";

export type JournalRead = (request: { workRef: string; signal: AbortSignal }) => Promise<unknown>;

export interface ProjectJournalReaderProps {
  selection: { workRef: string; rootJobId?: string | null };
  locale: "en" | "zh-CN";
  generation: string | number;
  authGeneration: string | number;
  read?: JournalRead;
  canRead?: () => boolean;
}

type JournalCopy = (en: string, zh: string) => string;
type BlockedWhy = "selection" | "not-permitted" | "revoked" | "no-transport";
type Phase =
  | { tag: "idle" }
  | { tag: "loading" }
  | { tag: "blocked"; why: BlockedWhy }
  | { tag: "error"; failed: "decode" | "transport" }
  | { tag: "ready"; doc: ProjectJournalDocument; selectedId: string | null };

/** Explicit, user-triggered reader for the bounded AgentOS project-journal sample.
 * No autorun: nothing is fetched until the user presses the read button. Any
 * change of selection, generation, auth generation, read or canRead identity
 * aborts a pending read and conceals the previous response before the next
 * paint; after a revocation, re-granting within the same generation never
 * redisplays it. Reading records is data observation only — never acceptance or
 * release — and the parent host owns all transport and authentication. The
 * runtime root id is parent UI identity only; records are keyed by the
 * workstream ref. */
export function ProjectJournalReader({
  selection, locale, generation, authGeneration, read, canRead,
}: ProjectJournalReaderProps) {
  const t: JournalCopy = (en, zh) => (locale === "zh-CN" ? zh : en);
  const workRef = selection.workRef;
  const rootJobId = selection.rootJobId;
  const epochKey = `${typeof generation === "string" ? `s:${generation}` : `n:${generation}`}\u0000${
    typeof authGeneration === "string" ? `s:${authGeneration}` : `n:${authGeneration}`}`;

  const identity = useMemo(
    () => ({ workRef, rootJobId, generation, authGeneration, read, canRead }),
    [workRef, rootJobId, generation, authGeneration, read, canRead],
  );
  const [applied, setApplied] = useState(identity);
  const [phase, setPhase] = useState<Phase>({ tag: "idle" });
  const pending = useRef<{ controller: AbortController } | null>(null);
  const taken = useRef(0);
  const readEpoch = useRef<string | null>(null);
  const revokedFor = useRef<string | null>(null);
  if (applied !== identity) {
    // A selection/generation/auth/read/canRead identity change (A-B-A safe):
    // conceal any prior response synchronously, before this render paints.
    setApplied(identity);
    setPhase({ tag: "idle" });
  }
  const authorizationAllowed = () => { try { return canRead?.() === true; } catch { return false; } };
  const permitted = authorizationAllowed();
  useLayoutEffect(() => {
    return () => {
      const current = pending.current;
      if (current !== null) {
        current.controller.abort();
        pending.current = null;
      }
    };
  }, [applied]);
  useLayoutEffect(() => {
    if (permitted) return;
    pending.current?.controller.abort();
    pending.current = null;
    taken.current++;
    // canRead denies under the current identity. When a read was already served
    // for this generation, poison the epoch so a same-generation re-grant can
    // never redisplay it; only a new generation may read again.
    if (readEpoch.current === epochKey) revokedFor.current = epochKey;
    setPhase({ tag: "blocked", why: revokedFor.current === epochKey ? "revoked" : "not-permitted" });
  }, [applied, permitted]);

  const revoked = revokedFor.current !== null && revokedFor.current === epochKey;
  const deny = (): BlockedWhy | null => {
    if (revoked) return "revoked";
    if (!authorizationAllowed()) {
      if (readEpoch.current === epochKey) {
        revokedFor.current = epochKey;
        return "revoked";
      }
      return "not-permitted";
    }
    return null;
  };
  const settle = (
    controller: AbortController,
    ticket: number,
    askedRef: string,
    result: { ok: true; value: unknown } | { ok: false; cause: unknown },
  ): void => {
    if (controller.signal.aborted) return;
    const current = pending.current;
    if (current === null || current.controller !== controller || ticket !== taken.current) return;
    if (!authorizationAllowed()) {
      pending.current = null;
      revokedFor.current = epochKey;
      setPhase({ tag: "blocked", why: "revoked" });
      return;
    }
    pending.current = null;
    if (!result.ok) {
      setPhase({ tag: "error", failed: result.cause instanceof ProjectJournalDecodeError ? "decode" : "transport" });
      return;
    }
    try {
      const doc = decodeProjectJournal(result.value, askedRef);
      setPhase({ tag: "ready", doc, selectedId: null });
    } catch (error) {
      setPhase({ tag: "error", failed: error instanceof ProjectJournalDecodeError ? "decode" : "transport" });
    }
  };
  const startRead = (): void => {
    if (phase.tag === "loading") return;
    if (!validJournalWorkRef(workRef)) {
      setPhase({ tag: "blocked", why: "selection" });
      return;
    }
    const denial = deny();
    if (denial !== null) {
      setPhase({ tag: "blocked", why: denial });
      return;
    }
    if (read === undefined) {
      setPhase({ tag: "blocked", why: "no-transport" });
      return;
    }
    const earlier = pending.current;
    if (earlier !== null) {
      earlier.controller.abort();
      pending.current = null;
    }
    const controller = new AbortController();
    const ticket = ++taken.current;
    pending.current = { controller };
    readEpoch.current = epochKey;
    setPhase({ tag: "loading" });
    try {
      void read({ workRef, signal: controller.signal }).then(
        value => settle(controller, ticket, workRef, { ok: true, value }),
        cause => settle(controller, ticket, workRef, { ok: false, cause }),
      );
    } catch (cause) { settle(controller, ticket, workRef, { ok: false, cause }); }
  };
  const selectEntry = (id: string | null): void => {
    setPhase(current =>
      current.tag === "ready" ? { ...current, selectedId: current.selectedId === id ? null : id } : current);
  };

  const busy = phase.tag === "loading";
  const doc = permitted && !revoked && phase.tag === "ready" ? phase.doc : null;
  const blockedMessage: string | null = phase.tag === "blocked"
    ? {
        selection: t("This project has no qualified workstream reference, so its journal cannot be requested.",
          "该选择不是有效的 WS:UPPER-KEBAB 工作流 ref，因此无法请求日志。"),
        "not-permitted": t(
          "Reading the project journal is not permitted for this selection right now. Nothing was fetched, and this does not mean the project has no records.",
          "当前不允许读取此选择的项目日志。未获取任何内容，这并不意味着项目没有记录。"),
        revoked: t(
          "Journal access was revoked after a read. The previous view was cleared and does not redisplay when access returns in the same source observation.",
          "读取后日志访问权限已撤销，旧视图已清除；相同来源观察中恢复权限也不会重新显示。"),
        "no-transport": t(
          "The journal reader is unavailable in this workspace. Other workspace sections remain available.",
          "父宿主未提供读取传输，因此此面板无法读取记录，也不会自行获取任何内容。"),
      }[phase.why]
    : null;

  return (
    <section className="mm-work-journey mm-project-journal" aria-busy={busy || undefined}>
      <h2 className="section-title">{t("Project journal", "项目日志")}</h2>
      <p className="muted">{t("Workstream", "工作流")}: <code>{workRef}</code></p>
      <div className="segmented">
        <button type="button" onClick={() => startRead()} disabled={busy}>
          {t("Read project journal", "读取项目日志")}
        </button>
        {doc !== null && (
          <button type="button" onClick={() => startRead()} disabled={busy}>
            {t("Refresh", "刷新")}
          </button>
        )}
      </div>
      {phase.tag === "idle" && (
        <p className="muted">
          {t("The journal has not been read yet. Choose “Read project journal” to see recorded updates.",
            "尚未读取日志。选择“读取项目日志”以查看已记录的更新。")}
        </p>
      )}
      {blockedMessage !== null && <p className="muted" role="status">{blockedMessage}</p>}
      {busy && <p className="muted" role="status">{t("Reading the project journal…", "正在读取项目日志…")}</p>}
      {phase.tag === "error" && (
        <div role="status">
          <p className="muted">
            {phase.failed === "decode"
              ? t("Journal information could not be verified. Its records are hidden.",
                "无法验证日志信息，因此已隐藏记录。")
              : t("Reading failed: the journal source could not be reached.", "读取失败：无法访问日志来源。")}
          </p>
          <p className="muted">{t("Only this panel is affected; the rest of the workspace keeps working.",
            "仅此面板受影响；工作区其余部分继续正常工作。")}</p>
          <p className="muted">{t("Choose “Read project journal” to retry.", "选择“读取项目日志”重试。")}</p>
        </div>
      )}
      {doc !== null && doc.availability === "UNAVAILABLE" && <JournalUnavailable reason={doc.reason_codes[0]} t={t} />}
      {doc !== null && doc.availability === "AVAILABLE" && (
        <JournalAvailable
          doc={doc}
          t={t}
          selectedId={phase.tag === "ready" ? phase.selectedId : null}
          onSelect={selectEntry}
        />
      )}
    </section>
  );
}

function JournalUnavailable({ reason, t }: { reason: JournalReasonCode; t: JournalCopy }) {
  const descriptions: Record<JournalReasonCode, string> = {
    SOURCE_UNAVAILABLE: t("The AgentOS source could not be reached for this selection.", "无法为该选择访问 AgentOS 来源。"),
    SOURCE_CHANGED: t("The AgentOS source changed while the journal was read.", "读取日志时 AgentOS 来源发生了变化。"),
    RECORD_NOT_FOUND: t("The selected workstream record was not found at this source revision.", "AgentOS 来源未发布该工作流 ref 的日志。"),
    RECORD_INVALID: t("The journal record at the AgentOS source was invalid, so its content is withheld.", "AgentOS 来源处的日志记录无效，因此其内容被扣留。"),
    CONTENT_OVER_BUDGET: t("The journal record exceeded the source content budget, so its content is withheld.", "日志记录超出来源内容预算，因此其内容被扣留。"),
  };
  return (
    <div className="empty">
      <p>
        {t("Journal information is unavailable", "日志信息不可用")}
      </p>
      <details><summary>{t("Source details", "来源详情")}</summary><code>{reason}</code></details>
      <p className="muted">{descriptions[reason]}</p>
      <p className="muted">
        {t("Unavailable does not mean there are no project records.",
          "信息不可用并不代表项目没有记录。")}
      </p>
    </div>
  );
}

function journalTimeLabel(entry: JournalEntry, t: JournalCopy): string {
  const when = entry.recorded_at === null ? "" : ` ${entry.recorded_at}`;
  if (entry.time_basis === "DECLARED_DECISION_DATE") return `${t("Decision date", "决策日期")}:${when}`;
  if (entry.time_basis === "DECLARED_VERIFICATION_DATE") return `${t("Verification date", "验证日期")}:${when}`;
  if (entry.time_basis === "GIT_RECORD_COMMIT_TIME") return `${t("Git record commit time", "Git 记录提交时间")}:${when}`;
  return t("Time unavailable", "时间不可用");
}

function JournalAvailable({ doc, t, selectedId, onSelect }: {
  doc: ProjectJournalDocument; t: JournalCopy; selectedId: string | null; onSelect: (id: string | null) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const journal = doc.journal, source = doc.source;
  if (!journal || !source) return null;
  const entries = journal.entries;
  const selected = entries.find(entry => entry.id === selectedId) ?? null;
  const names = { DECISION: t("Decision", "决策"), DISCOVERY: t("Discovery", "发现"), HANDOFF: t("Handoff", "交接") };
  return <div className="mm-work-journey">
    <div>
      <h3>{t("Recorded updates", "已记录的更新")}</h3>
      <p>{t("Records in this view", "此视图中的记录")}: <strong>{entries.length}</strong>. {t("Other history may not be included.", "可能未包含其他历史记录。")}</p>
    </div>
    <div className="mm-work-journey__columns">
      <div className="mm-work-journey__main">
        {entries.length === 0 && <p className="empty">{t("No records were supplied in this sample; the project may have other history.", "本次样本未提供记录；项目可能还有其他历史。")}</p>}
        <ul className="mm-work-journey__list">
          {(expanded ? entries : entries.slice(0, 8)).map(entry => <li key={entry.id}>
            <button type="button" className="mm-work-journey__row" aria-expanded={selectedId === entry.id} onClick={() => onSelect(entry.id)}>
              <span className="badge">{names[entry.kind]}</span>
              <span className="mm-work-journey__rowmain mm-project-journal__record-title">{entry.title}</span>
              <span className="muted">{journalTimeLabel(entry, t)}</span>
              {entry.actor !== null && <span className="muted"> · {t("actor", "记录人")}: {entry.actor}</span>}
            </button>
          </li>)}
        </ul>
        {entries.length > 8 && <button type="button" onClick={() => setExpanded(!expanded)}>{expanded ? t("Show fewer", "收起") : t(`See all ${entries.length}`, `查看全部 ${entries.length} 条`)}</button>}
      </div>
      <aside className="mm-work-journey__side">
        {selected ? <JournalEntryDetail entry={selected} workRef={doc.selection.work_ref} t={t} onClose={() => onSelect(null)} /> :
          <section className="card mm-work-journey__card"><h3>{t("Update details", "更新详情")}</h3><p className="muted">{t("Choose an update to read its details.", "选择一条更新以查看详情。")}</p></section>}
      </aside>
    </div>
    <details className="mm-work-journey__details">
      <summary>{t("Source and sample coverage", "来源与样本覆盖")}</summary>
      <p className="muted">{t("Source", "来源")}: <code>{source.repository}</code> @ <code>{source.commit}</code></p>
      <dl><dt>{t("Scanned", "已扫描")}</dt><dd>{journal.coverage.scanned}</dd><dt>{t("Matched", "已匹配")}</dt><dd>{journal.coverage.matched}</dd><dt>{t("Omitted", "已省略")}</dt><dd>{journal.coverage.omitted}</dd><dt>{t("Invalid", "无效")}</dt><dd>{journal.coverage.invalid}</dd></dl>
      <p>{t("Coverage is a bounded source-record sample; dates retain their own labelled meanings.", "覆盖范围仅为有界来源记录样本；各日期保留其已标注的含义。")}</p>
      <p className="muted">{t("Recorded source snapshots; current applicability is not established here.", "已记录的来源快照；此处不确立其当前适用性。")}</p>
      <p className="muted">{t("Reading these records is data observation only and never implies execution, review, acceptance or release.", "读取这些记录仅是数据观察，绝不意味着执行、评审、验收或发布。")}</p>
    </details>
  </div>;
}

function JournalEntryDetail({ entry, workRef, t, onClose }: {
  entry: JournalEntry; workRef: string; t: JournalCopy; onClose: () => void;
}) {
  const notRecorded = t("Not recorded in the source record.", "来源记录中未记载。");
  return <section className="card mm-work-journey__card">
    <h3>{t("Source record detail", "来源记录详情")}</h3>
    <p>{entry.title}</p>
    <p className="muted">{journalTimeLabel(entry, t)}</p>
    <dl>
      <dt>{t("Why", "原因")}</dt><dd>{entry.why ?? notRecorded}</dd>
      <dt>{t("Recorded next action", "记录的后续行动")}</dt><dd>{entry.next_action ?? notRecorded}</dd>
      <dt>{t("Recorded by", "记录人")}</dt><dd>{entry.actor ?? notRecorded}</dd>
    </dl>
    <details className="mm-work-journey__tuple">
      <summary>{t("Source details", "来源详情")}</summary>
      <dl>
        <dt>{t("Source owner", "来源归属")}</dt><dd>AgentOS</dd>
        <dt>{t("Kind", "类型")}</dt><dd>{entry.kind}</dd>
        <dt>{t("Workstream ref", "工作流引用")}</dt><dd><code>{workRef}</code></dd>
        <dt>{t("Record", "记录")}</dt><dd><code>{entry.source.path}</code></dd>
        <dt>{t("Content digest", "内容摘要")}</dt><dd><code>{entry.source.content_sha256}</code></dd>
        <dt>{t("Source commit", "来源修订")}</dt><dd><code>{entry.source.commit}</code></dd>
      </dl>
    </details>
    <button type="button" onClick={onClose}>{t("Close detail", "关闭详情")}</button>
  </section>;
}
