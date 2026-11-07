import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { decodeSavedConversationPage, type SavedConversationPage, type SavedConversationReference } from "../discovery/saved-conversations";
import { SourceMarkdown } from "./SourceMarkdown";
import type { createProjectConversationHistoryOwner } from "./project-conversation-history-owner";
import "./conversations-list.css";

type Handle = ReturnType<typeof createProjectConversationHistoryOwner>;
export interface ProjectConversationHistoryProps {
  workRef: string;
  sourceGeneration: string;
  history?: Handle;
  canRead: () => boolean;
  locale?: "en" | "zh-CN";
  theme?: "dark" | "light";
}
type Snapshot = { owner: Handle; workRef: string; generation: string; principal: string;
  epoch: string; page: SavedConversationPage; cursor?: string };

/** Explicit one-project original-reply history. Mounting never acquires a
 * context/reference/body; Open never continues or consumes its original turn. */
export function ProjectConversationHistory(props: ProjectConversationHistoryProps) {
  const live = useRef(props); live.current = props;
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [answer, setAnswer] = useState<{ reference: SavedConversationReference; text: string } | null>(null);
  const [phase, setPhase] = useState<"idle" | "reading" | "unavailable" | "ready">("idle");
  const [, changed] = useState(0);
  const request = useRef<AbortController | null>(null);
  const zh = props.locale === "zh-CN", t = (en: string, cn: string) => zh ? cn : en;
  useLayoutEffect(() => {
    request.current?.abort(); setSnapshot(null); setAnswer(null); setPhase("idle");
  }, [props.history, props.workRef, props.sourceGeneration]);
  useEffect(() => props.history?.subscribe(() => changed(value => value + 1)), [props.history]);
  useEffect(() => () => request.current?.abort(), []);
  const readable = (p: ProjectConversationHistoryProps) => {
    try { return !!p.history && p.canRead(); } catch { return false; }
  };
  const current = (s: Snapshot | null) => {
    try {
      const p = live.current, context = p.history?.owner.context();
      return !!s && readable(p) && p.history === s.owner && p.workRef === s.workRef &&
        p.sourceGeneration === s.generation && context?.principalScope === s.principal && context?.generation === s.epoch;
    } catch { return false; }
  };
  const visible = current(snapshot) ? snapshot : null;
  async function read(cursor?: string) {
    const p = live.current, owner = p.history;
    if (!owner || !readable(p)) return;
    const previous = snapshot;
    if (cursor !== undefined && (!current(previous) || previous?.page.nextCursor !== cursor)) return;
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setPhase("reading"); setAnswer(null); setSnapshot(null);
    try {
      if (cursor === undefined) await owner.refresh(); // explicit gesture only
      const context = owner.owner.context();
      if (!context || controller.signal.aborted || live.current.history !== owner ||
          live.current.workRef !== p.workRef || live.current.sourceGeneration !== p.sourceGeneration || !readable(live.current)) throw new Error();
      const raw = await owner.owner.readReferences({ workRef: p.workRef, pageSize: 4, ...(cursor ? { cursor } : {}), signal: controller.signal });
      const page = decodeSavedConversationPage(raw, p.workRef, cursor === undefined ? undefined : previous!.page.highWater);
      const next: Snapshot = { owner, workRef: p.workRef, generation: p.sourceGeneration,
        principal: context.principalScope, epoch: context.generation, ...(cursor ? { cursor } : {}), page: page! };
      if (!page || controller.signal.aborted || !current(next)) throw new Error();
      setSnapshot(next); setPhase("ready");
    } catch { if (!controller.signal.aborted) { setSnapshot(null); setAnswer(null); setPhase("unavailable"); } }
  }
  async function open(reference: SavedConversationReference) {
    const s = snapshot;
    if (!s || !current(s) || !s.page.references.includes(reference)) return;
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setAnswer(null); setPhase("reading");
    try {
      const result = await s.owner.owner.readAnswer({ kind: "message", operationKey: reference.operation_key, targetKey: reference.target_ref }, controller.signal);
      if (controller.signal.aborted || !current(s) || result.receipt.disposition !== "accepted" ||
          !result.answer || result.answer.readRef !== reference.read_ref || result.answer.parentConsumed !== false) throw new Error();
      setAnswer({ reference, text: result.answer.text }); setPhase("ready");
    } catch { if (!controller.signal.aborted) { setAnswer(null); setPhase("unavailable"); } }
  }
  return <section className="conversations-list project-conversation-history" data-theme={props.theme ?? "dark"} lang={props.locale ?? "en"} aria-label={t("Saved replies in this project", "此项目中已保存的回复")}>
    <h2>{t("Saved replies", "已保存的回复")}</h2>
    <p>{t("Read one page of this project's original reply references. Other projects are not searched.", "读取此项目的一页原始回复引用，不搜索其他项目。")}</p>
    <button type="button" disabled={!readable(props) || phase === "reading"} onClick={() => { void read(); }}>{t("Read saved replies", "读取已保存的回复")}</button>
    {phase === "reading" ? <p role="status">{t("Reading…", "正在读取…")}</p> : null}
    {phase === "unavailable" || (snapshot && !visible) ? <p role="status">{t("These replies are unavailable here. Read again to check the current source.", "此处无法查看这些回复。请重新读取，检查当前来源。")}</p> : null}
    {visible && answer ? <>
      <button type="button" onClick={() => { request.current?.abort(); setAnswer(null); setPhase("ready"); }}>{t("Back to saved replies", "返回已保存的回复")}</button>
      <p>{t("Request time", "请求时间")}: <time dateTime={answer.reference.requested_at}>{answer.reference.requested_at}</time></p>
      <SourceMarkdown source={answer.text} locale={props.locale}/>
    </> : visible ? <>
      <p>{t(`Showing ${visible.page.references.length} reply references from this page. This is not a list of every conversation.`, `本页显示 ${visible.page.references.length} 条回复引用，并非所有对话的列表。`)}</p>
      {!visible.page.references.length ? <p>{t("No saved reply references were returned for this page.", "此页未返回已保存的回复引用。")}</p> : null}
      {visible.page.references.map(reference => <article className="conversations-list__row" key={reference.read_ref}>
        <div><h3>{t("Saved reply", "已保存的回复")}</h3><p>{t("Request time", "请求时间")}: <time dateTime={reference.requested_at}>{reference.requested_at}</time></p></div>
        <button type="button" aria-label={t(`Open saved reply requested ${reference.requested_at}`, `打开请求时间为 ${reference.requested_at} 的已保存回复`)} onClick={() => { void open(reference); }}>{t("Open", "打开")}</button>
      </article>)}
      {visible.page.nextCursor ? <><p>{t("More references are available. This page is partial.", "还有其他引用可用，此页仅为部分内容。")}</p>
        <button type="button" disabled={phase === "reading"} onClick={() => { void read(visible.page.nextCursor!); }}>{t("Read next page", "读取下一页")}</button></> : null}
    </> : null}
    {visible ? <details className="conversations-list__sources"><summary>{t("Reply source details", "回复来源详情")}</summary>
      <p>{visible.workRef}</p><p>{t("Reference watermark", "引用水位")}: {visible.page.highWater}</p>
      {visible.page.references.map(reference => <dl key={reference.read_ref}><dt>{reference.read_ref}</dt><dd>{reference.request_revision}</dd></dl>)}
    </details> : null}
  </section>;
}
