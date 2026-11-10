/** TEST-ONLY entry. Real App/handlers; synthetic read-only owner and auth.
 * No production import, provider, credential, send, or business mutation. */
import { createRoot } from "react-dom/client";
import { App } from "../App";
import type { AuthState } from "../host";
import { DisplayPreferences, DisplayPreferencesRoot } from "../preferences/DisplayPreferences";
import { controlRoomFixture, missionFixture } from "../test-fixtures";
import { decodeProgramsObservation } from "../programs-observation";
import programs from "../fixtures/programs-available-workspace-service.json";
import { installAppControl } from "./install";
import "../styles.css";

if (!['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)) throw new Error("SOURCE_FIXTURE_REQUIRES_LOCALHOST");
let generation = 1;
let auth: AuthState = { status: "signed_in", reason: null, acquisition: true, content: false };
const listeners = new Set<(state: AuthState) => void>();
window.MastermindMissionHost = {
  invalidationGeneration: () => generation,
  readPrograms: async () => controlRoomFixture(),
  readProgramsObservation: async () => decodeProgramsObservation({ ...structuredClone(programs), control_room: controlRoomFixture() }),
  readMission: async selection => missionFixture(selection.workRef, selection.rootJobId),
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
