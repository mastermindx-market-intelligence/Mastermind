import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { bindMissionHost, createNativeClient, type AuthState } from "./host";
import { controlRoomFixture } from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import paired from "./fixtures/window-mission-association-producer.json";
import work from "./fixtures/work-service-available.json";
import "./styles.css";

/** Isolated, loopback-only application qualification. No credential, provider,
 * backend, command binding or actual authentication exists in this fixture.
 * Real App/host/decoder/draft owners consume exact synthetic fixed reads.
 */
async function mount() {
  const root = document.getElementById("root")!;
  if (!["127.0.0.1", "localhost", "[::1]"].includes(location.hostname)) {
    root.textContent = "SOURCE FIXTURE REFUSED: a dedicated loopback origin is required.";
    return;
  }
  const params = new URLSearchParams({ work_ref: paired.selection.work_ref, root_job_id: paired.selection.root_job_id });
  history.replaceState(null, "", `${location.pathname}?${params}`);
  const room = controlRoomFixture();
  room.work = [room.work[0]];
  room.autonomy.responsibilities = [room.autonomy.responsibilities[0]];
  room.work[0].work_ref = paired.selection.work_ref;
  Object.assign(room.autonomy.responsibilities[0], {
    responsibility_ref: paired.selection.work_ref, root_job_id: paired.selection.root_job_id,
    root_job_candidates: [paired.selection.root_job_id], root_job_ambiguous: false, runtime_root_state: "RESOLVED",
  });
  const mission = structuredClone(paired.mission);
  mission.program.title = "Harness integration review";
  const windowSource = structuredClone(paired.window);
  const text = "## Source integration is ready for review\n\nA published change is not yet a running session. Review the exact result before continuing the original project.\n\n| Capability | Evidence |\n| --- | --- |\n| Source reading | Exact original text |\n| Session execution | Not established by this fixture |\n\n**Next:** qualify the original send and return path.";
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text))))
    .map(value => value.toString(16).padStart(2, "0")).join("");
  windowSource.view.items[0].text = text;
  windowSource.view.items[0].display_sha256 = digest;
  const signed: AuthState = { status: "signed_in", reason: null, acquisition: true, content: true };
  let auth = signed;
  const listeners = new Map<string, Set<(event: { payload: unknown }) => void>>();
  const counts: Record<string, number> = {};
  const telemetry = document.createElement("output"); telemetry.id = "fixture-read-counts";
  Object.assign(telemetry.style, { display: "block", overflowWrap: "anywhere", minWidth: "0" });
  const renderCounts = () => { telemetry.textContent = `Synthetic read calls only: ${JSON.stringify(counts)}`; };
  const invoke = async <T,>(command: string): Promise<T> => {
    counts[command] = (counts[command] ?? 0) + 1; renderCounts();
    let result: unknown;
    switch (command) {
      case "auth_status": result = auth; break;
      case "executive_auth_status": result = { generation: 0, available: false }; break;
      case "read_programs": result = { ...structuredClone(programs), control_room: room }; break;
      case "read_mission_v3": result = mission; break;
      case "read_work": result = work; break;
      case "read_current_window": result = windowSource; break;
      case "sign_out":
        auth = { status: "signed_out", reason: null, acquisition: false, content: false };
        for (const listener of listeners.get("mastermind-auth-state") ?? []) listener({ payload: auth });
        result = auth; break;
      default: throw new Error("SOURCE_FIXTURE_COMMAND_UNAVAILABLE");
    }
    return structuredClone(result) as T;
  };
  const client = await createNativeClient(invoke, async (name, listener) => {
    const entries = listeners.get(name) ?? new Set(); entries.add(listener); listeners.set(name, entries);
    return () => { entries.delete(listener); };
  });
  window.MastermindMissionHost = bindMissionHost(client);
  const controls = document.getElementById("fixture-controls")!;
  const withdraw = document.createElement("button"); withdraw.type = "button";
  withdraw.textContent = "Fixture: withdraw authenticated projection";
  withdraw.addEventListener("click", () => { void client.signOut(); });
  controls.append(withdraw, telemetry); renderCounts();
  createRoot(root).render(<StrictMode><App /></StrictMode>);
}
void mount();
