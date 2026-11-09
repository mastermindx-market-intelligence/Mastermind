import { useEffect, useId, useRef } from "react";
import "./byok-roles-panel.css";

/** One bounded, already-translated fact row rendered inside the review. */
export interface ByokConnectionRow {
  readonly label: string;
  readonly value: string;
}

export interface ByokConnectionDrawerProps {
  locale: "en" | "zh-CN";
  /** Display name of the reviewed role. The owner translates it before it arrives. */
  roleName: string;
  /** Source and configuration rows. The owner translates and bounds them first. */
  sourceRows: readonly ByokConnectionRow[];
  /** Enrollment, last-return and usage rows. The owner translates them first. */
  proofRows: readonly ByokConnectionRow[];
  /** Read-only boundary statements. The owner translates them first. */
  notes: readonly string[];
  /** The next authorized setup steps. The owner translates them first. */
  steps: readonly string[];
  onClose: () => void;
}

const DRAWER_COPY = {
  "Connection review": "连接审阅",
  "Close": "关闭",
  "Source and configuration": "来源与配置",
  "Proof status": "证明状态",
  "Next authorized steps": "后续已授权步骤",
} as const;
type DrawerCopy = keyof typeof DRAWER_COPY;

const FOCUSABLE = 'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled),'
  + ' textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';

/**
 * Read-only review surface for one role's connection evidence.
 *
 * It shows what the parent owner already validated and nothing else: no
 * fetch, poll, storage, service mutation, key input, credential field or
 * fake connect action lives here. Escape and the Close control both dismiss
 * it, focus stays inside it while it is open, and the owner restores focus to
 * the trigger that opened it.
 */
export function ByokConnectionDrawer({
  locale = "en",
  roleName,
  sourceRows,
  proofRows,
  notes,
  steps,
  onClose,
}: ByokConnectionDrawerProps) {
  const titleId = useId();
  const bodyId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  const t = (text: DrawerCopy): string => locale === "zh-CN" ? DRAWER_COPY[text] : text;

  useEffect(() => { closeRef.current = onClose; });

  useEffect(() => {
    const node = dialogRef.current;
    if (!node) return;
    node.focus();
    const handle = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); closeRef.current(); return; }
      if (event.key !== "Tab") return;
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE));
      const first = items[0];
      const last = items[items.length - 1];
      if (!first || !last) { event.preventDefault(); node.focus(); return; }
      const active = document.activeElement;
      const inside = active ? node.contains(active) : false;
      if (event.shiftKey) {
        if (!inside || active === first || active === node) { event.preventDefault(); last.focus(); }
        return;
      }
      if (!inside || active === last || active === node) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", handle);
    return () => { document.removeEventListener("keydown", handle); };
  }, []);

  return <div className="byok-drawer-backdrop"
    onMouseDown={event => { if (event.target === event.currentTarget) closeRef.current(); }}>
    <div className="byok-drawer" role="dialog" aria-modal="true" aria-labelledby={titleId}
      aria-describedby={bodyId} tabIndex={-1} ref={dialogRef}>
      <header className="byok-drawer-header">
        <div>
          <p className="byok-drawer-eyebrow">{t("Connection review")}</p>
          <h3 id={titleId}>{roleName}</h3>
        </div>
        <button type="button" className="byok-drawer-close" onClick={() => closeRef.current()}>
          {t("Close")}
        </button>
      </header>
      <div className="byok-drawer-body" id={bodyId}>
        <section className="byok-drawer-section">
          <h4>{t("Source and configuration")}</h4>
          <dl className="byok-drawer-rows">
            {sourceRows.map(row => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}
          </dl>
        </section>
        <section className="byok-drawer-section">
          <h4>{t("Proof status")}</h4>
          <dl className="byok-drawer-rows">
            {proofRows.map(row => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}
          </dl>
        </section>
        {notes.length > 0 && <div className="byok-drawer-notes">
          {notes.map(note => <p key={note}>{note}</p>)}
        </div>}
        <section className="byok-drawer-section">
          <h4>{t("Next authorized steps")}</h4>
          <ol className="byok-drawer-steps">{steps.map(step => <li key={step}>{step}</li>)}</ol>
        </section>
      </div>
    </div>
  </div>;
}
