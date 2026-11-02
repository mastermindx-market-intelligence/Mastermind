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
export function canNavigateForAutomaticSignIn(): boolean {
  for (const probe of holds) {
    try { if (probe()) return false; }
    catch { return false; }
  }
  return true;
}
