import {expect,it} from "vitest";
import fixture from "./fixtures/fresh-conversation-attended-owner.json";
import {decodeFreshConversationTurnResult} from "./fresh-conversation-turn";

// Actual same-run D4B signed fixture, including its named inert authority,
// provider and Runtime seams. No rewritten receipt or production claim.
const selector={work_ref:fixture.turn_request.work_ref,
 reference:fixture.turn_request.reference,turn_key:fixture.turn_request.turn_key};
it.each([
 ["consume",fixture.consume,fixture.consume_request],
 ["turn",fixture.turn,fixture.turn_request],
 ["turn_read",fixture.turn_read,selector],
 ["turn_status",fixture.status,selector],
] as const)("accepts the actual D4B signed %s frame verbatim",(operation,raw,request)=>{
 const decoded=decodeFreshConversationTurnResult(raw,operation,request);
 expect(decoded?.ok).toBe(true);
 if(decoded?.ok){
  expect(decoded.data).toEqual(raw.data);
  expect(decoded.data).not.toBe(raw.data);
  expect(decoded.data.parent_consumed).toBe(false);
  expect(decoded.data.initial_consumption?.initial_digest).toBe(fixture.initial_read.initial_result.digest);
 }
});
