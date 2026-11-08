import {describe,expect,it,vi} from "vitest";
import {createCompanyFrameBridge} from "./company-frame-bridge";
import {
  COMPANY_SCHEMA,DONOR_SHA,deepSeekAppConfig,decodeCompanyView,decodeChildMessage,
  type CompanyView,
} from "../../../../../integrations/deepseek_harness/company_plugin/src/protocol";

const view:CompanyView={generation:1,state:"CURRENT",locale:"en",theme:"dark",
  selectedProject:"WS:CHAT",projects:[{workRef:"WS:CHAT",title:"Chat integration"}]};
const origin="https://chat.mastermind-x.com";
function owner() {
  const target={postMessage:vi.fn()},open=vi.fn(()=>true),state=vi.fn();
  const bridge=createCompanyFrameBridge({target,origin,view,onOpenProject:open,onState:state});
  bridge.connect();
  const challenge=()=>target.postMessage.mock.calls.findLast(([m])=>m.type==="connect")![0].nonce;
  const send=(data:unknown,overrides={})=>bridge.receive({source:target,origin,data,...overrides});
  const ready=()=>send({schema:COMPANY_SCHEMA,type:"ready",nonce:challenge(),donor:DONOR_SHA});
  return {target,open,state,bridge,challenge,send,ready};
}
describe("full DeepSeek app boundary",()=>{
 it("accepts only an owned separate HTTPS deployment origin without URL secrets",()=>{
  expect(deepSeekAppConfig(origin+"/","https://mcp.mastermind-x.com")).toEqual({url:origin+"/",origin});
  for(const url of ["https://mcp.mastermind-x.com/","http://chat.mastermind-x.com/","https://chat.mastermind-x.com.evil.test/",
    "https://x@chat.mastermind-x.com/","https://chat.mastermind-x.com/?token=x","https://chat.mastermind-x.com/#x",
    "https://chat.mastermind-x.com/os/","javascript:alert(1)"])
   expect(deepSeekAppConfig(url,"https://mcp.mastermind-x.com")).toBeNull();
 });
 it("does not transfer data until exact frame, origin, challenge and donor agree",()=>{
  const e=owner(),ready={schema:COMPANY_SCHEMA,type:"ready",nonce:e.challenge(),donor:DONOR_SHA};
  e.send(ready,{origin:"https://evil.example"});e.send(ready,{source:{}});
  e.send({...ready,donor:"wrong"});e.send({...ready,nonce:crypto.randomUUID()});
  expect(e.target.postMessage.mock.calls.filter(([m])=>m.type==="context")).toHaveLength(0);
  e.ready();
  expect(e.target.postMessage).toHaveBeenLastCalledWith({schema:COMPANY_SCHEMA,type:"context",nonce:e.challenge(),view},origin);
  e.send({schema:COMPANY_SCHEMA,type:"ack",nonce:e.challenge(),generation:1});
  expect(e.state).toHaveBeenLastCalledWith("connected");
 });
 it("rotates on document reload and rejects old ready, ack and navigation",()=>{
  const e=owner();e.ready();const nonce=e.challenge();e.bridge.connect();
  expect(e.challenge()).not.toBe(nonce);
  e.send({schema:COMPANY_SCHEMA,type:"ready",nonce,donor:DONOR_SHA});
  e.send({schema:COMPANY_SCHEMA,type:"ack",nonce,generation:1});
  e.send({schema:COMPANY_SCHEMA,type:"open_project",nonce,generation:1,workRef:"WS:CHAT"});
  expect(e.open).not.toHaveBeenCalled();expect(e.state).toHaveBeenLastCalledWith("loading");
  e.ready();e.send({schema:COMPANY_SCHEMA,type:"open_project",nonce:e.challenge(),generation:1,workRef:"WS:CHAT"});
  expect(e.open).toHaveBeenCalledExactlyOnceWith("WS:CHAT");
 });
 it("uses current owner navigation and refuses stale, unlisted and revoked project views",()=>{
  const e=owner();e.ready();
  const command={schema:COMPANY_SCHEMA,type:"open_project",nonce:e.challenge(),generation:1,workRef:"WS:CHAT"};
  e.send({...command,workRef:"WS:OTHER"});expect(e.open).not.toHaveBeenCalled();
  e.open.mockReturnValue(false);e.send(command);
  expect(e.target.postMessage).toHaveBeenLastCalledWith({...command,type:"navigation_result",ok:false},origin);
  e.bridge.update({...view,generation:2,state:"UNAVAILABLE",projects:[],selectedProject:null});
  e.send(command);e.send({...command,generation:2});expect(e.open).toHaveBeenCalledTimes(1);
  expect(e.bridge.update(view)).toBe(false);
 });
 it("clears the original frame on logout and ignores every late message",()=>{
  const e=owner();e.ready();e.bridge.dispose();
  expect(e.target.postMessage.mock.calls.at(-1)![0].view).toMatchObject({state:"SIGNED_OUT",projects:[],selectedProject:null});
  const count=e.target.postMessage.mock.calls.length;
  e.send({schema:COMPANY_SCHEMA,type:"open_project",nonce:e.challenge(),generation:1,workRef:"WS:CHAT"});
  e.bridge.connect();e.bridge.dispose();
  expect(e.open).not.toHaveBeenCalled();expect(e.target.postMessage).toHaveBeenCalledTimes(count);
 });
 it("rejects authority-bearing extras, accessors and malformed projections",()=>{
  expect(decodeChildMessage({schema:COMPANY_SCHEMA,type:"hello",token:"secret"})).toBeNull();
  const getter=vi.fn(()=>COMPANY_SCHEMA);
  expect(decodeChildMessage({get schema(){return getter()},type:"hello"})).toBeNull();
  expect(getter).not.toHaveBeenCalled();
  expect(decodeCompanyView({...view,projects:[...view.projects,...view.projects]})).toBeNull();
  expect(decodeCompanyView({...view,state:"SIGNED_OUT"})).toBeNull();
  expect(decodeCompanyView({...view,selectedProject:"WS:OTHER"})).toBeNull();
  expect(decodeCompanyView({...view,token:"forbidden"})).toBeNull();
 });
});
