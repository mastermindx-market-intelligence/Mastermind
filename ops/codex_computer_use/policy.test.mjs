import assert from "node:assert/strict";
import test from "node:test";
import {POLICY_SCHEMA,compilePolicy,authorizeCall,authorizeElicitation,
  projectedAppsResult,filteredToolsResult} from "./policy.mjs";
const fixture=()=>({schema:POLICY_SCHEMA,apps:[{
  bundle_id:"com.apple.calculator",display_name:"Calculator",
  elicitation:"Allow ChatGPT to use Calculator?",read:true,write:false,preapproved:true
}]});
test("default-deny across other apps and writes",()=>{
  const apps=compilePolicy(fixture());
  for(const [name,args] of [["click",{app:"com.apple.calculator",element_index:1}],
    ["type_text",{app:"com.apple.calculator",text:"123"}],
    ["get_app_state",{app:"com.google.Chrome"}],
    ["press_key",{}],["osascript",{app:"com.apple.calculator"}]]){
    assert.equal(authorizeCall(name,args,apps).ok,false);
  }
  assert.equal(authorizeCall("get_app_state",{app:"com.apple.calculator"},apps).ok,true);
});
test("elicitation strictly binds to app and official exact prompt",()=>{
  const apps=compilePolicy(fixture());
  assert.equal(authorizeElicitation("Allow ChatGPT to use Calculator?",{app:"com.apple.calculator"},apps),true);
  assert.equal(authorizeElicitation("Allow ChatGPT to use Calculator?",null,apps),false);
  assert.equal(authorizeElicitation("Allow ChatGPT to use Calculator?",{app:"com.google.Chrome"},apps),false);
  assert.equal(authorizeElicitation("Allow ChatGPT to use Calendar?",{app:"com.apple.calculator"},apps),false);
});
test("malformed schema and duplicate or spoofed prompt are refused",()=>{
  assert.throws(()=>compilePolicy({schema:"bad",apps:[]}),/REFUSED/);
  let f=fixture();f.apps[0].elicitation="Allow ChatGPT to use Chrome?";
  assert.throws(()=>compilePolicy(f),/REFUSED/);
  f=fixture();f.apps.push({...f.apps[0]});
  assert.throws(()=>compilePolicy(f),/REFUSED/);
});
test("host inventory is filtered and catalog defaults to read-only",()=>{
  const apps=compilePolicy(fixture());
  const content=projectedAppsResult(apps).content[0].text;
  assert.match(content,/Calculator/);assert.doesNotMatch(content,/Chrome/);
  const tools=["list_apps","get_app_state","click","type_text","danger"].map(name=>({name}));
  assert.deepEqual(filteredToolsResult({tools},apps).tools.map(x=>x.name),["list_apps","get_app_state"]);
});
test("explicit write approval is per-app",()=>{
  const f=fixture();f.apps[0].write=true;
  const apps=compilePolicy(f);
  assert.equal(authorizeCall("click",{app:"com.apple.calculator",element_index:1},apps).ok,true);
  assert.equal(authorizeCall("click",{app:"com.google.Chrome",element_index:1},apps).ok,false);
});
