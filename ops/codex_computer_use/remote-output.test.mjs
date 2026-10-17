import assert from "node:assert/strict";
import test from "node:test";
import {createComputerUseFacet} from "./remote-facet.mjs";

const ctx={session:"source-only-test"};
const grant=(write=false)=>({
  allowed:true,canRead:true,canWrite:write,
  principalRef:"test-owner",bindingRef:"test-host",operationRef:"test-action",
});
test("sanitize remote screenshots, accessibility text and metadata",async()=>{
  const facet=createComputerUseFacet({
    authorize:async()=>grant(),
    dispatch:async()=>({
      content:[
        {type:"text",text:"Calculator",secret:"unwanted"},
        {type:"image",mimeType:"image/png",data:"aGVsbG8=",uri:"https://unexpected.example"}
      ],
      diagnostic:"untrusted backend detail",isError:false,
    }),
  });
  const result=await facet.callTool({name:"cuse_get_app_state",
    arguments:{app:"com.apple.calculator"}},ctx);
  assert.deepEqual(result,{
    content:[{type:"text",text:"Calculator"},
      {type:"image",data:"aGVsbG8=",mimeType:"image/png"}],isError:false,
  });
});
test("reject resource links, huge text, unexpected image MIME",async()=>{
  let result={content:[{type:"resource_link",uri:"file:///private"}]};
  const facet=createComputerUseFacet({
    authorize:async()=>grant(),
    dispatch:async()=>result,
  });
  const request={name:"cuse_get_app_state",arguments:{app:"com.apple.calculator"}};
  await assert.rejects(()=>facet.callTool(request,ctx),/unexpected or oversize/);
  result={content:[{type:"text",text:"x".repeat(200001)}]};
  await assert.rejects(()=>facet.callTool(request,ctx),/unexpected or oversize/);
  result={content:[{type:"image",mimeType:"text/html",data:"dGVzdA=="}]};
  await assert.rejects(()=>facet.callTool(request,ctx),/unexpected or oversize/);
});
test("ambiguous write with unsafe result reports effect unknown without retry",async()=>{
  let calls=0,records=0;
  const facet=createComputerUseFacet({
    authorize:async()=>grant(true),
    dispatch:async()=>{calls++;return {content:[{type:"resource_link",uri:"file:///private"}]};},
    recordUncertainEffect:async()=>{records++;},
  });
  await assert.rejects(()=>facet.callTool({
    name:"cuse_press_key",arguments:{app:"com.apple.calculator",key:"Return"}
  },ctx),/EFFECT_UNKNOWN/);
  assert.equal(calls,1);
  assert.equal(records,1);
});
