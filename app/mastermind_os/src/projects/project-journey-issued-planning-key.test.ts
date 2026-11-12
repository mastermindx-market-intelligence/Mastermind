import {expect,it} from "vitest";
import {makePlanningIntent,planningOperationKey} from "../planning/project-planning-command-port";
import {projectJourneyUrl,readProjectJourneyLocation} from "./project-journey-location";
const owner={principalScope:"f".repeat(64),generation:"actual-port-fixture"};
const input={stage:"clarify",work_ref:"WS:PROJ-1",
 project_source:{repository:"macro",commit:"a".repeat(40),path:"agentos/workstreams/WS-PROJ-1.md",content_sha256:"b".repeat(64),request_sha256:"c".repeat(64)},
 publication:{request_id:"mmos-project-create-"+"d".repeat(40),principal_scope:owner.principalScope,event_id:7,receipt_sha256:"e".repeat(64)},
 grounding:{mastermind_sha:"a".repeat(40),macro_sha:"a".repeat(40)},private_request:"Original planning request"};
it("retains the genuine command port's issued original planning key through the actual URL adapter",()=>{
 const intent=makePlanningIntent(owner,input);expect(intent).not.toBeNull();
 const key=planningOperationKey(owner,input);expect((intent!.payload as Record<string,unknown>).operation_key).toBe(key);
 const selected={createRequestId:input.publication.request_id,workRef:input.work_ref,planningOperationKey:key,jobId:null};
 expect(key).toMatch(/^mmos-project-planning-[0-9a-f]{40}$/);
 const url=projectJourneyUrl("https://mcp.mastermind-x.com/os/",selected);
 expect(readProjectJourneyLocation(url)).toEqual({valid:true,open:true,selection:selected});
});
it("refuses old synthetic bare hashes and foreign-prefix lookalikes instead of inventing a producer identity",()=>{
 for(const planningOperationKey of ["a".repeat(64),"mmos-project-planning-"+"a".repeat(64),"mmos-launch-"+"a".repeat(40)]){
  const selected={createRequestId:input.publication.request_id,workRef:input.work_ref,planningOperationKey,jobId:null};
  expect(()=>projectJourneyUrl("https://mcp.mastermind-x.com/os/",selected)).toThrow("PROJECT_JOURNEY_SELECTION_INVALID");
 }
});
