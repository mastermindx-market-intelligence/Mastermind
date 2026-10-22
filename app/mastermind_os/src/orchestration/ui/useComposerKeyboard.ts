import { useEffect, useRef, type KeyboardEvent } from "react";
import { observeComposition } from "../../vendor/deepseek/keyboard-composition";

/**
 * Presentation-only keyboard adapter. DeepSeek's composition guard protects
 * Safari's late IME-closing Enter as well as the standard isComposing signal.
 * This adapter never creates an operation or calls a transport: every gesture
 * goes through the existing form submission and its exactly-once controller.
 */
export function useComposerKeyboard(canSubmit: boolean) {
  const composition = useRef<ReturnType<typeof observeComposition> | null>(null);
  useEffect(() => {
    if (typeof document === "undefined") return;
    const guard = observeComposition(document);
    composition.current = guard;
    return () => {
      guard.dispose();
      if (composition.current === guard) composition.current = null;
    };
  }, []);

  return (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter") return;
    // Do not consume IME confirmation, held keys, line breaks, or application
    // shortcuts. In particular AltGraph and Ctrl+Meta are not send gestures.
    if (composition.current?.guards(event.nativeEvent) || event.nativeEvent.isComposing ||
        event.nativeEvent.keyCode === 229 || event.repeat || event.shiftKey ||
        event.altKey || event.getModifierState("AltGraph") || (event.ctrlKey && event.metaKey)) return;
    // Preserve Mastermind's established newline-by-default composer contract.
    if (!event.ctrlKey && !event.metaKey) return;
    if (!canSubmit) return;
    const form = event.currentTarget.form;
    if (!form) return;
    event.preventDefault();
    form.requestSubmit();
  };
}
