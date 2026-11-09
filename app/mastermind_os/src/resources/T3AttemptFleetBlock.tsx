import { useEffect, useId, useRef, useState } from "react";
import type { MissionHost } from "../host";
import { validT3AttemptId, type DuplicateKind, type InvariantVerdict, type T3Attempt, type T3AttemptFleetRead } from "./t3-attempt-fleet-contract";
import "./t3-attempt-fleet.css";

type ReadState = T3AttemptFleetRead | { state: "PENDING" };

/** One attempt's launch-fleet observation. A read-only view; it never launches,
 *  interrupts, sends to or reads a T3 thread. Unknown stays unknown with its
 *  reason — never healthy, never zero. */
export function T3AttemptFleetBlock({ host, locale = "en", attemptId }: {
  host?: MissionHost; locale?: "en" | "zh-CN"; attemptId?: string | null;
}) {
  const zh = locale === "zh-CN", t = (en: string, cn: string) => zh ? cn : en;
  const id = useId();
  const reader = host?.readT3AttemptFleet, epoch = host?.invalidationGeneration?.();
  // Plain render-time auth read (incumbent panel pattern): the epoch key remounts
  // this block when auth changes, and the effect below drops any owned read.
  const auth = host?.auth?.getState();
  const permitted = !!host && !!reader && Number.isSafeInteger(epoch) && auth?.status === "signed_in" && auth.acquisition;
  const selectable = validT3AttemptId(attemptId);
  const [owned, setOwned] = useState<{ host: MissionHost; reader: typeof reader; epoch: number; attemptId: string; read: ReadState } | null>(null);
  const abort = useRef<AbortController | null>(null), current = useRef({ host, reader });
  current.current = { host, reader };
  const visible = permitted && owned?.host === host && owned.reader === reader && owned.epoch === epoch && owned.attemptId === attemptId ? owned.read : null;
  // No in-block auth subscription: the parent keys this block by the host epoch,
  // and a bound host bumps that epoch on every auth change (remount ⇒ fresh
  // permitted). Subscribing here would also crowd out single-listener hosts.
  useEffect(() => {
    abort.current?.abort(); setOwned(null);
    return () => { abort.current?.abort(); };
  }, [host, reader, attemptId]);
  const refresh = async () => {
    if (!host || !reader || !permitted || epoch === undefined || !selectable) return;
    abort.current?.abort(); const controller = new AbortController(); abort.current = controller;
    const origin = { host, reader, epoch, attemptId };
    const valid = () => !controller.signal.aborted && current.current.host === host && current.current.reader === reader
      && host.invalidationGeneration?.() === epoch && host.auth?.getState().status === "signed_in" && host.auth?.getState().acquisition;
    setOwned({ ...origin, read: { state: "PENDING" } });
    try {
      const read = await reader.call(host, { attemptId, signal: controller.signal });
      if (valid()) setOwned({ ...origin, read });
    } catch { if (valid()) setOwned({ ...origin, read: { state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" } }); }
  };
  const when = (value: string | null) => value ? new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : t("Not observed", "未观测");
  const document = visible?.state === "AVAILABLE" ? visible.document : null;
  return <section className="t3-attempt-fleet" aria-labelledby={id} lang={locale} aria-busy={visible?.state === "PENDING"} data-testid="t3-attempt-fleet">
    <header className="t3-attempt-fleet-heading"><div>
      <p className="eyebrow">{t("T3 ATTEMPT FLEET", "T3 尝试舰群")}</p>
      <h3 id={id} tabIndex={-1}>{t("Attempt invariants", "尝试不变量")}</h3>
      {selectable ? <p className="muted"><code>{attemptId}</code></p>
        : attemptId ? <p className="muted">{t("This run id is not a readable attempt id.", "此运行编号不是可读取的尝试编号。")}</p> : null}
    </div>
      <button type="button" onClick={() => void refresh()} disabled={!permitted || !selectable || visible?.state === "PENDING"}>{visible?.state === "PENDING" ? t("Reading…", "读取中…") : t("Read attempt", "读取尝试")}</button>
    </header>
    {!document ? <div className="t3-attempt-fleet-empty" role="status" data-testid="t3-attempt-fleet-state">
      <p>{!selectable ? attemptId
          ? t("This run id is not a readable attempt id; nothing was fetched.", "此运行编号不是可读取的尝试编号，未进行任何读取。")
          : t("Select a run above to observe its attempt.", "在上方选择一个运行以观测其尝试。")
        : !permitted ? auth?.status === "signed_in" && auth.acquisition
          ? t("The T3 attempt reader is not connected to this workspace.", "此工作区尚未连接 T3 尝试读取器。")
          : t("Sign in with Workspace access to read attempt observations.", "登录具有 Workspace 权限的账号后查看尝试观测。")
        : visible?.state === "PENDING" ? t("Reading the recorded attempt observation.", "正在读取已记录的尝试观测。")
        : visible?.state === "UNAVAILABLE" ? t("No qualified attempt observation is connected. Every invariant stays unknown.", "尚未连接合格的尝试观测，所有不变量保持未知。")
        : t("One read-only observation per attempt: thread, harness and duplicate launchers.", "每次尝试一条只读观测：线程、执行器与重复启动器。")}</p>
    </div> : document.kind === "refusal" ? <div className="t3-attempt-fleet-empty" role="status" data-testid="t3-attempt-fleet-refusal">
      <p>{t("The attempt evidence was refused; nothing is shown.", "尝试证据被拒绝显示，不展示任何内容。")}</p>
      <p><code>{document.refusal}</code></p>
      <p className="muted">{t("A typed refusal carries no partial projection. Retry after the recorded state changes.", "类型化拒绝不携带任何部分投影，待记录状态变化后重试。")}</p>
    </div> : <AttemptObservation attempt={document.attempt} notes={document.notes} evaluatedAt={document.evaluated_at_utc} when={when} t={t} locale={locale} id={id} />}
  </section>;
}

function Chip({ verdict, label, reason, t }: { verdict: InvariantVerdict; label: string; reason: string | null; t: (en: string, cn: string) => string; }) {
  return <span className={`t3-attempt-fleet-chip t3-verdict-${verdict.toLowerCase()}`}>
    <b>{label}</b> {verdict === "PROVEN" ? t("PROVEN", "已证实") : verdict === "VIOLATED" ? t("VIOLATED", "已违反") : t("UNKNOWN", "未知")}
    {verdict === "UNKNOWN" && reason ? <small> · {reason}</small> : null}
  </span>;
}

function AttemptObservation({ attempt, notes, evaluatedAt, when, t, locale, id }: {
  attempt: T3Attempt; notes: string[]; evaluatedAt: string; when: (value: string | null) => string;
  t: (en: string, cn: string) => string; locale: string; id: string;
}) {
  const thread = attempt.t3_thread, harness = attempt.harness_process, duplicate = attempt.duplicate_launcher;
  const threadReason = thread.unknown_reason ?? attempt.thread_count_reason;
  const harnessReason = harness.unknown_reason ?? attempt.harness_count_reason;
  const kindLabel = (kind: DuplicateKind) => ({
    dsh_direct: t("direct DSH process", "DSH 直启进程"), codex_cli: t("Codex CLI process", "Codex CLI 进程"),
    second_t3_thread: t("second T3 thread", "第二个 T3 线程"), other: t("other launcher", "其他启动器"),
  }[kind]);
  const fresh = (state: string) => ({ fresh: t("fresh", "新鲜"), stale: t("stale", "过期"), absent: t("absent", "缺失"), unknown: t("unknown", "未知") } as Record<string, string>)[state] ?? state;
  return <>
    <div className="t3-attempt-fleet-chips" data-testid="t3-attempt-fleet-chips">
      <Chip verdict={attempt.invariant.exactly_one_thread} label={t("Exactly one thread", "唯一线程")} reason={threadReason} t={t} />
      <Chip verdict={attempt.invariant.exactly_one_harness} label={t("Exactly one harness", "唯一执行器")} reason={harnessReason} t={t} />
    </div>
    <dl className="t3-attempt-fleet-facts">
      <div><dt>{t("T3 thread", "T3 线程")}</dt><dd>{thread.thread_id
        ? <>{t("Observed", "已观测")} <code>{thread.thread_id}</code>{thread.state ? <small>{t("state", "状态")} {thread.state}</small> : null}</>
        : <span className="t3-unknown">{t("Unknown", "未知")} · {thread.unknown_reason}</span>}</dd></div>
      <div><dt>{t("Harness process", "执行器进程")}</dt><dd>{harness.pid !== null
        ? <>{t("pid", "进程号")} <code>{harness.pid}</code>{harness.provider ? <small>{harness.provider}{harness.model ? ` · ${harness.model}` : ""}</small> : null}{harness.start_time ? <small>{t("started", "启动于")} {when(harness.start_time)}</small> : null}</>
        : <span className="t3-unknown">{t("Unknown", "未知")} · {harness.unknown_reason}{harness.provider ? "" : ""}</span>}</dd></div>
      <div><dt>{t("Duplicate launchers", "重复启动器")}</dt><dd>{duplicate.observed === true
        ? <span className="t3-verdict-violated">{t("Observed", "已观测")} · {duplicate.kinds.map(kindLabel).join(" · ")}</span>
        : duplicate.observed === false ? t("None observed", "未观测到")
        : <span className="t3-unknown">{t("Unknown", "未知")} · {duplicate.unknown_reason}</span>}</dd></div>
      <div><dt>{t("Threads under this key", "此键下线程数")}</dt><dd>{attempt.thread_count_for_key !== null
        ? String(attempt.thread_count_for_key)
        : <span className="t3-unknown">{t("Unknown", "未知")} · {attempt.thread_count_reason}</span>}</dd></div>
    </dl>
    <details className="t3-attempt-fleet-method"><summary>{t("Freshness & evidence", "新鲜度与证据")}</summary>
      <p>{t("Evaluated", "评估于")} <time dateTime={evaluatedAt}>{when(evaluatedAt)}</time> · {t("adapter state", "适配器状态")} {fresh(attempt.freshness.adapter_state)} · {t("census", "进程普查")} {fresh(attempt.freshness.census)} · {t("thread read", "线程读取")} {fresh(attempt.freshness.thread_read)}</p>
      {notes.length > 0 && <p className="muted" aria-live="polite">{notes.join(" · ")}</p>}
      {attempt.evidence_refs.length > 0 && <ul aria-label={t("Evidence references", "证据引用")}>{attempt.evidence_refs.map(ref => <li key={ref}><code>{ref}</code></li>)}</ul>}
      <p className="muted">{t("This view reads the durable adapter state and one bounded process census. A remote or exited harness is unknown, not a violation; it never launches, interrupts or sends to a thread.", "此视图读取持久适配器状态与一次有界进程普查。远程或已退出的执行器属于未知而非违规；本视图不会启动、中断或向线程发送消息。")}</p>
      <p className="muted">{t("Idempotency", "幂等标识")} <code>{attempt.idempotency.key ?? t("Not recorded", "未记录")}</code> · <code>{attempt.idempotency.namespace ?? t("Not recorded", "未记录")}</code></p>
    </details>
  </>;
}
