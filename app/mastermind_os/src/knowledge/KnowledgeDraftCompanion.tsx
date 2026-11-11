import { useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { observedMissionAssociation } from "../workspace-contract";
import { normalizeResultSelection, type ResultSelection } from "../result";
import { sameTarget, type OfficeProjection, type ProjectionContext } from "../meta-ceo/projection";
import type { DraftInsertion, DraftSource } from "../conversations/drafts";

// Translate presentation only; the draft text, source excerpts, provenance
// labels and insertion identity stay verbatim.
const STATIC_ZH: Record<string, string> = {
  "Original draft": "原草稿",
  "Your unsent notes": "你的未发送笔记",
  "An eligible scoped draft is unavailable. Reading does not create one.": "没有符合条件的对应草稿。读取不会创建草稿。",
  "No unsent text yet.": "还没有未发送的文字。",
  "Exact source excerpt": "原文摘录",
  "Source label for the draft": "草稿中的来源标注",
  "Add excerpt to draft": "将摘录添加到草稿",
  "Adds the excerpt and its source label to the original draft. Nothing is sent.": "将摘录和来源标注添加到原草稿。不会发送任何内容。",
  "Added to draft · Not sent": "已添加到草稿 · 未发送",
  "The original draft changed or is unavailable. Return to review it before adding.": "原草稿已更改或不可用。请返回检查后再添加。",
  "Undo source insertion": "撤销来源插入",
  "Source insertion removed. Your original draft is preserved.": "已移除插入的来源，原草稿已保留。",
  "The draft has changed. Automatic removal is unavailable.": "草稿已更改，无法自动移除。",
  "The draft changed. Edit the draft to preserve your newer text.": "草稿已更改。请编辑草稿以保留较新的文字。",
  "Edit draft": "编辑草稿",
  "Return to this source and reopen it to review the current draft before adding.": "请返回此来源并重新打开，检查当前草稿后再添加。"
};

/** The explicit port over the existing scoped draft owner. The companion never
 * holds draft state, creates a draft, invents a recipient or sends anything. */
export interface KnowledgeDraftPort {
  projection: OfficeProjection;
  text: string;
  revision: number;
  insertion: DraftInsertion | null;
  append: (source: DraftSource, expectedRevision: number) => boolean;
  undo: (identity: string, expectedRevision: number) => boolean;
  edit?: () => void;
}

export interface KnowledgeDraftCompanionProps {
  source: DraftSource | null;
  selection: ResultSelection;
  context: ProjectionContext;
  /** Destination witness captured before the exact source read, retained only
   * when the same owner association remained qualified after that read. */
  readBinding?: string | null;
  port?: KnowledgeDraftPort;
  locale?: "en" | "zh-CN";
}

type Association = NonNullable<ReturnType<typeof observedMissionAssociation>>;
type Qualification =
  | { kind: "unavailable" }
  | { kind: "qualified"; association: Association; port: KnowledgeDraftPort };

/** Presentation witness for the existing draft destination, never a grant or
 * recipient. A completed same-Mission source may belong to another child than
 * the currently observed live plan conversation. The source itself is admitted
 * exclusively by the fixed retained-result index and exact-result decoder. */
export function knowledgeDraftBinding(context: ProjectionContext,
  port: KnowledgeDraftPort | undefined): string | null {
  if (!port || port.projection.context.authGeneration !== context.authGeneration ||
      !context.selection || !sameTarget(context, port.projection.context) ||
      port.projection.mission.source.state !== "CURRENT" ||
      port.projection.conversation.source.state !== "CURRENT") return null;
  const { projection } = port;
  const association = observedMissionAssociation(projection.conversation.value,
    projection.mission.value, projection.context.selection);
  const window = projection.conversation.value;
  if (!association || !window || !window.selection_ref || !window.view.epoch) return null;
  return JSON.stringify([context.authGeneration, context.selection.workRef,
    context.selection.rootJobId, context.sessionRef, context.bindingGeneration,
    window.selection_ref, window.view.epoch, association.job_id, association.attempt_id]);
}

function qualify(selection: ResultSelection, context: ProjectionContext,
  port: KnowledgeDraftPort | undefined, readBinding: string | null | undefined): Qualification {
  const exact = normalizeResultSelection(selection);
  if (!exact || !port) return { kind: "unavailable" };
  const projection = port.projection;
  const portContext = projection.context;
  if (portContext.authGeneration !== context.authGeneration || !sameTarget(context, portContext) ||
      !context.selection || exact.workRef !== context.selection.workRef ||
      exact.rootJobId !== context.selection.rootJobId)
    return { kind: "unavailable" };
  if (!readBinding || knowledgeDraftBinding(context, port) !== readBinding) return { kind: "unavailable" };
  const association = observedMissionAssociation(projection.conversation.value, projection.mission.value, portContext.selection);
  if (!association) return { kind: "unavailable" };
  return { kind: "qualified", association, port };
}

// IME/composition Enter must never trigger a local draft action.
function blockCompositionEnter(event: KeyboardEvent): void {
  if (event.key === "Enter" && (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229))
    event.preventDefault();
}

interface CompanionBodyProps { port: KnowledgeDraftPort; source: DraftSource; locale: "en" | "zh-CN";
  context: ProjectionContext; readBinding: string }

// Keyed by the parent on the exact source identity plus the auth/context/
// selection association epoch, so the captured revision baseline is always
// re-established when scope, source or association change and no stale notice
// or baseline survives them.
function CompanionBody({ port, source, locale, context, readBinding }: CompanionBodyProps) {
  const t = (text: string) => locale === "zh-CN" ? STATIC_ZH[text] ?? text : text;
  const originalDraftRevision = useRef(port.revision);
  const [notice, setNotice] = useState("");
  const [invalidated, setInvalidated] = useState(false);
  const actionStatus = useRef<HTMLParagraphElement>(null);
  useLayoutEffect(() => { if (notice) actionStatus.current?.focus(); }, [notice]);
  const unchanged = port.revision === originalDraftRevision.current;
  const added = port.insertion?.source.identity === source.identity ? port.insertion : null;
  const canAdd = unchanged && !added;
  const current = () => knowledgeDraftBinding(context, port) === readBinding;
  if (invalidated || !current()) return <p role="status" className="knowledge-muted">
    {t("An eligible scoped draft is unavailable. Reading does not create one.")}</p>;
  return <>
    <p className="knowledge-muted">{port.text || t("No unsent text yet.")}</p>
    <h3>{t("Exact source excerpt")}</h3>
    <blockquote>{source.excerpt}</blockquote>
    <details><summary>{t("Source label for the draft")}</summary><p>{source.label}</p></details>
    <button type="button" disabled={!canAdd} onKeyDown={blockCompositionEnter} onClick={() => {
      if (!current()) { setInvalidated(true); return; }
      if (!canAdd) return;
      setNotice(port.append(source, originalDraftRevision.current)
        ? "Added to draft · Not sent"
        : "The original draft changed or is unavailable. Return to review it before adding.");
    }}>{t("Add excerpt to draft")}</button>
    <p className="knowledge-muted">{t("Adds the excerpt and its source label to the original draft. Nothing is sent.")}</p>
    {added && port.revision === added.revision ? <button type="button" onKeyDown={blockCompositionEnter} onClick={() => {
      if (!current()) { setInvalidated(true); return; }
      setNotice(port.undo(added.source.identity, port.revision)
        ? "Source insertion removed. Your original draft is preserved."
        : "The draft changed. Edit the draft to preserve your newer text.");
    }}>{t("Undo source insertion")}</button>
      : (added || !unchanged) && <>
        <p className="knowledge-muted">{t("The draft has changed. Automatic removal is unavailable.")}</p>
        {port.edit && <button type="button" onKeyDown={blockCompositionEnter} onClick={port.edit}>{t("Edit draft")}</button>}
      </>}
    {!added && !unchanged && <p className="knowledge-muted">{t("Return to this source and reopen it to review the current draft before adding.")}</p>}
    {(notice || added) && <p ref={actionStatus} tabIndex={-1} role="status">{t(notice || "Added to draft · Not sent")}</p>}
  </>;
}

/** Paper KD01 knowledge companion: shows the scoped unsent draft next to one
 * exact source excerpt and lets the existing draft owner append or undo that
 * single insertion. No send path, no storage, no recipient and no draft is
 * created here; an unqualified source or port renders unavailable instead. */
export function KnowledgeDraftCompanion({ source, selection, context, port, readBinding, locale = "en" }: KnowledgeDraftCompanionProps) {
  const t = (text: string) => locale === "zh-CN" ? STATIC_ZH[text] ?? text : text;
  const qualification = qualify(selection, context, port, readBinding);
  return <section className="knowledge-draft-companion" role="region" aria-label={t("Original draft")}>
    <p className="knowledge-eyebrow">{t("Original draft")}</p>
    <h2>{t("Your unsent notes")}</h2>
    {qualification.kind !== "qualified" || !source ? <p role="status" className="knowledge-muted">
      {t("An eligible scoped draft is unavailable. Reading does not create one.")}
    </p>
      : <CompanionBody key={[context.authGeneration, qualification.port.projection.context.authGeneration,
        JSON.stringify(context.selection), qualification.association.job_id, qualification.association.attempt_id,
        source.identity, readBinding].join("|")} port={qualification.port} source={source} locale={locale}
        context={context} readBinding={readBinding!} />}
  </section>;
}
