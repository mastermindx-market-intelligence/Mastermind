/** TEST-ONLY entry. Real App/handlers; synthetic read-only owner and auth.
 * No production import, provider, credential, send, or business mutation. */
import { createRoot } from "react-dom/client";
import { App } from "../App";
import type { AuthState } from "../host";
import { DisplayPreferences, DisplayPreferencesRoot } from "../preferences/DisplayPreferences";
import { controlRoomFixture, missionFixture } from "../test-fixtures";
import { decodeProgramsObservation } from "../programs-observation";
import programs from "../fixtures/programs-available-workspace-service.json";
import capacityFixture from "../resources/fixtures/capacity-fabric-owner-read.json";
import { decodeCapacityFabric } from "../resources/capacity-fabric";
import { installAppControl } from "./install";
import "../styles.css";

if (!['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)) throw new Error("SOURCE_FIXTURE_REQUIRES_LOCALHOST");
let generation = 1;
let auth: AuthState = { status: "signed_in", reason: null, acquisition: true, content: false };
const listeners = new Set<(state: AuthState) => void>();
// Rebase the explicitly synthetic observation clock for this isolated source
// fixture. The source values remain the actual Python/H2 projection fixture;
// no production reader imports this entry or receives these observations.
function readCapacityFixture() {
  const delta = Date.now() - (Date.parse(capacityFixture.observed_at) + 10_000);
  const shift = (value: string | null) => value === null ? null : new Date(Date.parse(value) + delta).toISOString();
  return decodeCapacityFabric({ ...structuredClone(capacityFixture),
    observed_at: shift(capacityFixture.observed_at), expires_at: shift(capacityFixture.expires_at),
    resources: capacityFixture.resources.map(row => ({ ...row, cooldown_until: shift(row.cooldown_until),
      single_window_observed_at: shift(row.single_window_observed_at),
      windows: row.windows.map(w => ({ ...w, observed_at: shift(w.observed_at), reset_at: shift(w.reset_at) })) })),
    consumers: capacityFixture.consumers.map(row => ({ ...row, observed_at: shift(row.observed_at) })),
  });
}
window.MastermindMissionHost = {
  invalidationGeneration: () => generation,
  readPrograms: async () => controlRoomFixture(),
  readProgramsObservation: async () => decodeProgramsObservation({ ...structuredClone(programs), control_room: controlRoomFixture() }),
  readMission: async selection => missionFixture(selection.workRef, selection.rootJobId),
  readCapacityFabric: async () => readCapacityFixture(),
  auth: {
    getState: () => auth,
    subscribe: listener => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    signIn: async () => { throw new Error("SOURCE_FIXTURE_CANNOT_AUTHENTICATE"); },
    signOut: async () => { generation++; auth = { status: "signed_out", reason: null, acquisition: false, content: false }; listeners.forEach(listener => listener(auth)); },
  },
};
const root = document.getElementById("root")!;
const control = installAppControl(root);
createRoot(root).render(<DisplayPreferencesRoot>{({ theme, locale, control }) =>
  <App theme={theme} locale={locale} preferencesControl={<DisplayPreferences control={control} />} />
}</DisplayPreferencesRoot>);
window.addEventListener("pagehide", () => control.dispose(), { once: true });
