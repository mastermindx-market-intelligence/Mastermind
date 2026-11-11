import {describe,it,expect} from 'vitest';
import actual from './fixtures/project-discovery-current-data.json';
import {decodeMissionv3} from './mission';
const selection={workRef:actual.mission.program.work_ref,rootJobId:actual.mission.mission.root_job_id!};
describe('actual new DATA Mission clock binding',()=>{
  it('accepts the unchanged producer clock',()=>expect(decodeMissionv3(actual.mission,selection)).not.toBeNull());
  it.each([actual.programs.control_room.generated_at,'2020-01-01T00:00:00Z'])('withholds one-field mixed source clock %s',clock=>{
    const raw=structuredClone(actual.mission);raw.source.control_room_generated_at=clock;
    expect(decodeMissionv3(raw,selection)).toBeNull();
  });
});
