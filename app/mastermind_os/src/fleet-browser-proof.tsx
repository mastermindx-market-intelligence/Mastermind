/**
 * Test-only compiled browser entry. The production index never imports this file.
 * All account, machine and authorization states below are synthetic fixtures.
 * Uses the existing App and host adapter; no collector, server credential or action.
 */
import {createRoot} from "react-dom/client";
import {App} from "./App";
import {bindMissionHost, createNativeClient} from "./host";
import {decodeFleetHealth} from "./fleet";
import {fleetFixture} from "./fleet.test-fixture";
import {controlRoomFixture} from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import paired from "./fixtures/window-mission-association-producer.json";
import work from "./fixtures/work-service-available.json";
import "./styles.css";

async function mount() {
  const signed = {status:"signed_in", reason:null, acquisition:true, content:true};
  let notify: (event:{payload:unknown}) => void = () => {};
  const room = controlRoomFixture();
  const invoke = async (command:string) => {
    if (command === "auth_status") return signed;
    return structuredClone(command === "read_programs" ? {...programs, control_room:room} :
      command === "read_mission_v3" ? paired.mission :
      command === "read_work" ? work : paired.window);
  };
  const client = await createNativeClient(invoke as never, async (_event, listener) => {notify=listener; return () => {};});
  const host = bindMissionHost(client);
  host.readFleet = async ({window}) => {
    const document = fleetFixture();
    const now = Math.floor(Date.now()/1000);
    document.generated_at=now; document.window=window; document.availability="PARTIAL";
    const current = document.hosts[0];
    current.observed_at=now;
    current.history.forEach((point,index) => {point.timestamp=now-(1-index)*60;});
    const stale = structuredClone(current);
    Object.assign(stale, {id:"m1",label:"M1 Studio",platform:"macos",state:"STALE",observed_at:now-3600,history:[]});
    Object.assign(stale.metrics,{cpu_busy_pct:null,cpu_temp_c:null,memory_total_bytes:null,memory_used_pct:null,
      fabric_active_lanes:null,process_lane_candidates:null,nvme_temp_c:null});
    stale.coverage=["CPU_UTILIZATION_UNAVAILABLE","CPU_TEMP_UNAVAILABLE","MEMORY_TOTAL_UNAVAILABLE",
      "MAC_MEMORY_FREE_INACTIVE_ESTIMATE","SNAPSHOT_NOT_CURRENT"];
    document.hosts.push(stale);
    const decoded=decodeFleetHealth(document);
    if (!decoded) throw Error("SYNTHETIC_FLEET_FIXTURE_INVALID");
    return decoded;
  };
  window.MastermindMissionHost=host;
  document.getElementById("fixture-sign-out")!.onclick=() => {
    notify({payload:{...signed,status:"signed_out",acquisition:false,content:false}});
  };
  createRoot(document.getElementById("root")!).render(<App/>);
}
void mount();
