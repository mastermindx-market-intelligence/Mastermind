import realControlRoom from "./fixtures/control-room-b5-c20a3cf8.json";
import realMission from "./fixtures/mission-workspace-c20a3cf8.json";
import bothUnavailableMission from "./fixtures/mission-workspace-bf9540a3-both-unavailable.json";
import controlRoomUnavailableMission from "./fixtures/mission-workspace-bf9540a3-control-room-unavailable.json";
import fabricUnavailableMission from "./fixtures/mission-workspace-bf9540a3-fabric-unavailable.json";
import nullRoleMission from "./fixtures/mission-workspace-bf9540a3-null-role.json";
import retainedPartialMission from "./fixtures/mission-workspace-bf9540a3-retained-partial.json";
import rootConflictMission from "./fixtures/mission-workspace-bf9540a3-root-conflict.json";

// Test-only frozen fixtures. Both originate at reducer commit
// c20a3cf8e6541d894404d6c0f44d0999edd8e142. The Control Room fixture was
// emitted by tests/test_chairman_control_room_server.py::_b5_navigation_fixture
// through the real cache composition path. The mission fixture continues that
// chain through the real Fabric Job View composer and compose_mission_workspace.
export const realControlRoomFixture = () => structuredClone(realControlRoom);
export const realMissionFixture = () => structuredClone(realMission);

// Additional actual reducer outputs originate at bf9540a3047370b244d9915ed510409368a09209.
// Together with the byte-identical normal B5 output above, they cover all seven
// receipt cases: each missing-owner combination, duplicate-root conflict, a
// persisted nullable Runtime role, and a malformed attempt retained as an
// explicitly degraded known subset. Production imports none of these fixtures.
export const fabricUnavailableMissionFixture = () =>
  structuredClone(fabricUnavailableMission);
export const controlRoomUnavailableMissionFixture = () =>
  structuredClone(controlRoomUnavailableMission);
export const bothUnavailableMissionFixture = () =>
  structuredClone(bothUnavailableMission);
export const rootConflictMissionFixture = () =>
  structuredClone(rootConflictMission);
export const nullRoleMissionFixture = () => structuredClone(nullRoleMission);
export const retainedPartialMissionFixture = () =>
  structuredClone(retainedPartialMission);

export function missionFixture(workRef = "WS:ALPHA", root = "JOB-ROOT") {
  const document: any = realMissionFixture();
  document.program.work_ref = workRef;
  const name = workRef.slice(3);
  document.program.title = `${name.charAt(0)}${name.slice(1).toLowerCase()} program`;
  document.mission.root_job_id = root;
  document.mission.root_job_candidates = [root];
  document.children.items[0].parent_job_id = root;
  document.children.items[0].job_id = `${root}-CHILD`;
  const evidence = {
    owner: "EXECUTIVE_OS",
    ref: `job:${root}`,
    field: "status",
    source_revision: "sha256:abc",
    source_time: "2026-09-20T10:00:00Z",
    observed_at: "2026-09-20T10:01:00Z",
    freshness_state: "CURRENT",
  };
  document.program.evidence = [
    {
      ...evidence,
      owner: "AGENT_OS",
      ref: `workstream:${workRef}`,
      field: "next_action",
    },
  ];
  document.mission.evidence = [evidence];
  document.principal.evidence = [
    {
      ...evidence,
      owner: "AUTONOMY_PROJECTION",
      ref: `responsibility:${workRef}`,
      field: "current_worker",
    },
  ];
  document.execution.evidence = [evidence];
  document.review.evidence = [evidence];
  document.transport.evidence = [evidence];
  document.posture.evidence = [evidence];
  document.execution.artifacts = ["artifact:result/report.json"];
  document.execution.next_actions = ["Wait for the bounded return."];
  return document;
}

export function controlRoomFixture() {
  const document: any = realControlRoomFixture();
  const make = (ref: string, root: string, title: string) => {
    const work = structuredClone(document.work[0]);
    work.work_ref = ref;
    work.agent_os.workstream = ref.slice(3);
    work.agent_os.title = title;
    work.agent_os.next_action = `Open ${title}`;
    work.executive.jobs[0].workstream = ref;
    work.executive.jobs[0].job_id = root;
    for (const binding of work.bindings) binding.work_ref = ref;

    const responsibility = structuredClone(
      document.autonomy.responsibilities[0],
    );
    responsibility.responsibility_ref = ref;
    responsibility.root_job_id = root;
    responsibility.root_job_candidates = [root];
    responsibility.title = title;
    responsibility.dispatch.responsibility_ref = ref;
    responsibility.dispatch.root_job_id = root;
    responsibility.dispatch.evidence.responsibility_ref = ref;
    responsibility.dispatch.evidence.root_job_id = root;
    return { work, responsibility };
  };
  const alpha = make("WS:ALPHA", "JOB-A", "Alpha program");
  const beta = make("WS:BETA", "JOB-B", "Beta program");
  document.work = [alpha.work, beta.work];
  document.autonomy.responsibilities = [
    alpha.responsibility,
    beta.responsibility,
  ];
  return document;
}
