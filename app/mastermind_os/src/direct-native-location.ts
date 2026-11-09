import { locationSelectionInput } from "./mission";
import { sessionTargetKind } from "./orchestration/executive-session-command-port";
/** Display-route hints only; canonical backend access never trusts them. */
export function directLocationInput(search = window.location.search) {
  const raw = search.startsWith("?") ? search.slice(1) : search;
  const refused = { hasIdentity: true, selection: null, direct: false };
  try {
    let parts = raw.split("&");
    // App retains this closed session choice in the same URL. Peel only
    // that owned field; the Mission owner still validates the exact pair.
    const kinds = parts.filter((part) => {
      const at = part.indexOf("=");
      return at > 0 && decodeURIComponent(part.slice(0, at)) === "session_target_kind";
    });
    if (kinds.length) {
      if (kinds.length !== 1) return refused;
      const kind = decodeURIComponent(kinds[0].slice(kinds[0].indexOf("=") + 1));
      if (sessionTargetKind({ targetKind: kind }) === null) return refused;
      parts = parts.filter((part) => part !== kinds[0]);
    }
    const original = locationSelectionInput(parts.join("&"));
    const hints = parts.filter((part) => part.startsWith("direct_native_job="));
    if (!hints.length) return { ...original, direct: false };
    if (hints.length !== 1 || parts.length !== 3) return refused;
    const hint = decodeURIComponent(hints[0].slice("direct_native_job=".length));
    const selected = locationSelectionInput(
      parts.filter((part) => part !== hints[0]).join("&"),
    );
    if (!selected.selection || hint !== selected.selection.rootJobId) return refused;
    return { ...selected, direct: true };
  } catch {
    return refused;
  }
}
