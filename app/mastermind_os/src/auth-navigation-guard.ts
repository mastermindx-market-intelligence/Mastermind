/** In-memory UI-only guard for potentially destructive automatic Auth0 navigation.
 *
 * Probes never contain, persist, transmit, or reveal draft content or credentials.
 * They never change authentication or revocation authority.
 */
const holds = new Set<() => boolean>();
export function registerUnsavedNavigationHold(probe: () => boolean): () => void {
  holds.add(probe);
  return () => { holds.delete(probe); };
}
/** A prior explicit or cross-tab logout is a security boundary, not expiry. */
export function explicitLogoutRecorded(): boolean {
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith("mastermind-os-auth-logout-v1:") &&
          localStorage.getItem(key) === "1") return true;
    }
    return false;
  } catch {
    // Unable to prove this was merely passive expiry: discard old drafts.
    return true;
  }
}

export function canNavigateForAutomaticSignIn(): boolean {
  for (const probe of holds) {
    try { if (probe()) return false; }
    catch { return false; }
  }
  return true;
}
