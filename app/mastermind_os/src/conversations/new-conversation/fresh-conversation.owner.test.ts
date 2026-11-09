import {expect,it} from "vitest";
import fixture from "./fixtures/fresh-conversation-owner.json";
import {decodeFreshConversationResult,decodeFreshConversationInitialResult,validateFreshConversationRequest} from "./fresh-conversation";
import {canonicalJson,sha256Hex} from "../../orchestration/operation-key";
it.each(["preview","create","read"] as const)("accepts the actual final161 signed %s envelope without rewriting it",operation=>{
 const raw=fixture[operation];const decoded=decodeFreshConversationResult(raw,operation,fixture.request);
 expect(decoded?.ok).toBe(true);expect(decoded?.data).toEqual(raw.data);
});
it("preserves the genuine request and exact original client key",()=>{
 expect(validateFreshConversationRequest(fixture.request,"preview")).toEqual(fixture.request);
 expect(validateFreshConversationRequest(fixture.create_request,"create")).toEqual(fixture.create_request);
});
it("rejects wrong/missing envelope schema, operation and extra data rather than a normalized surrogate",()=>{
 for(const raw of [{...fixture.read,schema:"foreign"},{...fixture.read,operation:"status"},
  {ok:true,data:fixture.read.data},{...fixture.read,error:{code:"no",message:"no"}}])
  expect(decodeFreshConversationResult(raw,"read",fixture.request)).toBeNull();
});
it("does not execute accessors or lose an own __proto__ key in a sealed JSON envelope",()=>{
 let accessed=false;const input={...fixture.read};Object.defineProperty(input,"data",{enumerable:true,get(){accessed=true;return fixture.read.data;}});
 expect(decodeFreshConversationResult(input,"read",fixture.request)).toBeNull();expect(accessed).toBe(false);
 const envelope=JSON.parse('{"__proto__":{"literal":"original"},"summary":"Exact source"}');
 const raw={...fixture.read,data:{...fixture.read.data,result:{digest:sha256Hex(canonicalJson(envelope)),envelope}}};
 const decoded=decodeFreshConversationResult(raw,"read",fixture.request);
 expect(decoded?.ok).toBe(true);if(decoded?.ok){const body=decoded.data.result?.envelope as Record<string,unknown>;
  expect(Object.hasOwn(body,"__proto__")).toBe(true);expect(Object.getPrototypeOf(body)).toBe(Object.prototype);
  expect(canonicalJson(body)).toBe(canonicalJson(envelope));}
});

it("validates a genuine initial result with its own locator and no old create DTO",()=>{
 const result=fixture.read.data.result,locator=fixture.read.data.locator;
 expect(decodeFreshConversationInitialResult(result,locator)).toEqual(result);
 expect(decodeFreshConversationInitialResult(result,{...locator,job_id:"JOB-foreign"})).toBeNull();
 expect(decodeFreshConversationInitialResult(result,{...locator,attempt_id:"ATT-foreign"})).toBeNull();
 for(const delta of [{extra:true},{role:"assistant"},{status:"RUNNING"},{validations:["not-empty"]},{next_actions:[7]},{summary:7}]){
  const envelope={...result!.envelope,...delta};
  expect(decodeFreshConversationInitialResult({envelope,digest:sha256Hex(canonicalJson(envelope))},locator)).toBeNull();
 }
});
