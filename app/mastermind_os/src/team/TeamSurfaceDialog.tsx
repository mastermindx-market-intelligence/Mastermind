import { useEffect, useId, useRef, type ReactNode } from "react";

/** Focusable elements inside the dialog, for the Tab trap. jsdom cannot
 *  compute visibility, so disabled/hidden filtering relies on the selector —
 *  the same lightweight approach the roster's roving focus uses. */
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Shared modal shell for the Team conversation surfaces (HC02/HC03/HC09).
 *  Owns the keyboard contract: Escape closes, Tab stays trapped inside, and
 *  focus returns to the trigger that opened the surface when it closes. The
 *  backdrop never closes a form surface — data loss is not a shortcut. */
export function TeamSurfaceDialog({
  title,
  closeLabel,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  /** Accessible label for the ✕ button (locale copy from the caller). */
  closeLabel: string;
  onClose: () => void;
  children: ReactNode;
  /** Extra-wide variant for the full workspace surfaces. */
  wide?: boolean;
}) {
  const headingId = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  // onClose is re-created by the parent each render (inline state setters in
  // form-heavy surfaces); keep the effect mount-stable via a ref so focus
  // capture/restore happens exactly once per open.
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    dialogRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const root = dialogRef.current;
      if (!root) return;
      const items = Array.from(
        root.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((node) => node.offsetParent !== null || node === root);
      // jsdom reports offsetParent null for everything; fall back to the raw
      // list when the visibility filter is uninformative.
      const focusables =
        items.length > 0
          ? items
          : Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (focusables.length === 0) {
        event.preventDefault();
        root.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      const inside = active instanceof Node && root.contains(active);
      if (!event.shiftKey && (!inside || active === last || active === root)) {
        event.preventDefault();
        first.focus();
      } else if (
        event.shiftKey &&
        (!inside || active === first || active === root)
      ) {
        event.preventDefault();
        last.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      // Focus returns to the trigger that opened the surface.
      if (previous && previous.isConnected) previous.focus();
    };
  }, []);

  return (
    <div className="mm-surface-overlay">
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        tabIndex={-1}
        className={`mm-surface-dialog${wide ? " mm-surface-wide" : ""}`}
      >
        <header className="mm-surface-head">
          <h2 id={headingId}>{title}</h2>
          <button
            type="button"
            className="mm-surface-close"
            aria-label={closeLabel}
            onClick={() => closeRef.current()}
          >
            ✕
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}
