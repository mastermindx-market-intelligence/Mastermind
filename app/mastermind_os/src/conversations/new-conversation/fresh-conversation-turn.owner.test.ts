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

import recovery from "./fixtures/fresh-conversation-recovery-owner.json";
import {decodeFreshConversationTurnPreviewResult} from "./fresh-conversation-turn";

const recoverySelector={work_ref:recovery.turn_request.work_ref,reference:recovery.turn_request.reference,turn_key:recovery.turn_request.turn_key};
it.each([
 ["consume_status",recovery.consume_status,recovery.consume_request],
 ["turn",recovery.turn,recovery.turn_request],
 ["turn_read",recovery.turn_read,recoverySelector],
 ["turn_status",recovery.status,recoverySelector],
 ["turn",recovery.duplicate,recovery.turn_request],
] as const)("accepts actual same-run A4E6 %s data without rewriting the original",(operation,raw,request)=>{
 const decoded=decodeFreshConversationTurnResult(raw,operation,request);expect(decoded?.ok).toBe(true);
 if(decoded?.ok){expect(decoded.data).toEqual(raw.data);expect(decoded.data.parent_consumed).toBe(false);}
});
it("reads the actual A4E6 TURN_READY body separately from a command receipt",()=>{
 const {preview_digest,...request}=recovery.turn_request;
 const decoded=decodeFreshConversationTurnPreviewResult(recovery.turn_preview,request);
 expect(decoded?.ok).toBe(true);if(decoded?.ok){expect(decoded.data).toEqual(recovery.turn_preview.data);expect(decoded.data.preview_digest).toBe(preview_digest);}
 expect(decodeFreshConversationTurnResult(recovery.turn_preview,"turn_preview",request)).toBeNull();
});
it("preserves the actual lost-Keep error instead of relabelling it as consumption",()=>{
 const decoded=decodeFreshConversationTurnResult(recovery.lost_consume,"consume",recovery.consume_request);
 expect(decoded?.ok).toBe(false);if(decoded&&!decoded.ok)expect(decoded.error.code).toBe("effect_unknown");
});
