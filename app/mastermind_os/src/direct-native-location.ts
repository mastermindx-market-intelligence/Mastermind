import { locationSelectionInput } from "./mission";
/** A display-route hint only; canonical backend access never trusts it. */
export function directLocationInput(search = window.location.search) {
  const original = locationSelectionInput(search),
    raw = search.startsWith("?") ? search.slice(1) : search;
  const parts = raw.split("&"),
    hints = parts.filter((p) => p.startsWith("direct_native_job="));
  if (!hints.length) return { ...original, direct: false };
  if (hints.length !== 1 || parts.length !== 3)
    return { hasIdentity: true, selection: null, direct: false };
  try {
    const hint = decodeURIComponent(
      hints[0].slice("direct_native_job=".length),
    );
    const selected = locationSelectionInput(
      parts.filter((p) => p !== hints[0]).join("&"),
    );
    if (!selected.selection || hint !== selected.selection.rootJobId)
      return { hasIdentity: true, selection: null, direct: false };
    return { ...selected, direct: true };
  } catch {
    return { hasIdentity: true, selection: null, direct: false };
  }
}
