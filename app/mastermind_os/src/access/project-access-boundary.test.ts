// @vitest-environment node
import {it,expect} from "vitest";
import fixture from "./fixtures/current-grants.json";
import {decodeProjectAccess,validProjectAccessSelection} from "./project-access";
it.each(["selection","commit","digest","instruction"])("consumes the entire %s value including rejecting a trailing newline",field=>{
 const body=structuredClone(fixture);
 if(field==="selection"){
  body.selection.work_ref+="\n";
  expect(validProjectAccessSelection(body.selection)).toBe(false);
  expect(decodeProjectAccess(body,body.selection)).toBeNull();return;
 }
 if(field==="commit")body.source.commit+="\n";
 else if(field==="digest")body.source.content_sha256+="\n";
 else body.grants[7].instruction_ref+="\n";
 expect(decodeProjectAccess(body,fixture.selection)).toBeNull();
});
it("does not invoke inherited array serialization getters",()=>{
 const body=structuredClone(fixture);let calls=0;
 const proto=Object.create(Array.prototype);Object.defineProperty(proto,"toJSON",{get(){calls++;return ()=>[];}});
 Object.setPrototypeOf(body.grants,proto);
 expect(decodeProjectAccess(body,fixture.selection)).toBeNull();expect(calls).toBe(0);
});
it("rejects nonenumerable array fields and contains unknown-object exceptions",()=>{
 const body=structuredClone(fixture);Object.defineProperty(body.grants,"0",{value:body.grants[0],enumerable:false});
 expect(decodeProjectAccess(body,fixture.selection)).toBeNull();
 const unknown=new Proxy({work_ref:"WS:ONE"},{getPrototypeOf(){throw Error("untrusted object");}});
 expect(validProjectAccessSelection(unknown)).toBe(false);expect(decodeProjectAccess(unknown,fixture.selection)).toBeNull();
});
