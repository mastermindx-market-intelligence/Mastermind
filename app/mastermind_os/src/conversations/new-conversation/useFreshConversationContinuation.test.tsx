// @vitest-environment jsdom
// Actual A4E6 raw frames, incumbent port/controller, named inert owner/store.
import {useState,useLayoutEffect} from "react";
import type {MissionHost} from "../../host";
import {freshConversationTarget} from "../../orchestration/fresh-conversation-target";
import {useFreshConversationTurnDraftState} from "./useFreshConversationTurnDraftState";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {act,cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import type {OperationPointer,OwnerContext,PendingPointerStore} from "../../orchestration/operation-controller";
import {createFreshConversationAttendedBinding,type FreshConversationOriginalRead} from "./fresh-conversation-attended-binding";
import {useFreshConversationContinuation,type FreshConversationContinuationProps} from "./useFreshConversationContinuation";
import {decodeFreshConversationWindow} from "../fresh-conversation-reference";
import {decodeFreshConversationTurnResult,type FreshConversationTurnRequest} from "./fresh-conversation-turn";
import fixture from "./fixtures/fresh-conversation-recovery-owner.json";

const realCrypto=globalThis.crypto;
beforeEach(()=>{let draw=0;vi.stubGlobal("crypto",{getRandomValues:(a:Uint8Array)=>{const start=++draw===1?21:41;for(let i=0;i<a.length;i++)a[i]=start+i;return a;}});});
afterEach(()=>{cleanup();vi.unstubAllGlobals();Object.defineProperty(globalThis,"crypto",{value:realCrypto,configurable:true});});
function setup(){
  let owner:OwnerContext|null={principalScope:"fixture-principal",generation:"auth-1"};
  let pointer:OperationPointer|null=null;
  let current=true;
  const window=decodeFreshConversationWindow(fixture.initial_read,fixture.initial_read.reference);
  const read:FreshConversationOriginalRead={selection:{work_ref:window.reference.work_ref,reference:window.reference},
    locator:window.locator,result:window.initial_result!,current:()=>current};
  const store:PendingPointerStore={read:vi.fn(async()=>pointer),reserve:vi.fn(async(_scope,next)=>{
    if(pointer)return{reserved:false as const,pointer};pointer=next;return{reserved:true as const};
  }),clearIfEqual:vi.fn(async(_scope,held)=>{if(pointer&&JSON.stringify(pointer)===JSON.stringify(held)){pointer=null;return true;}return false;})};
  const transport={consume:vi.fn(async(_request:FreshConversationTurnRequest,_signal:AbortSignal):Promise<unknown>=>fixture.lost_consume),consumeStatus:vi.fn(async(_request:FreshConversationTurnRequest,_signal:AbortSignal):Promise<unknown>=>fixture.consume_status),
    turnPreview:vi.fn(async(_request:FreshConversationTurnRequest,_signal:AbortSignal):Promise<unknown>=>fixture.turn_preview),turn:vi.fn(async(_request:FreshConversationTurnRequest,_signal:AbortSignal):Promise<unknown>=>fixture.turn),
    turnStatus:vi.fn(async(_request:FreshConversationTurnRequest,_signal:AbortSignal):Promise<unknown>=>fixture.status),turnRead:vi.fn(async(_request:FreshConversationTurnRequest,_signal:AbortSignal):Promise<unknown>=>fixture.turn_read)};
  const binding=createFreshConversationAttendedBinding({owner:()=>owner,canModify:()=>true,store,transport,
    readInitial:async()=>current?read:null});
  const consumption=decodeFreshConversationTurnResult(fixture.consume_status,"consume_status",fixture.consume_request);
  if(!consumption?.ok)throw Error("Actual consume_status fixture refused");
  const props:FreshConversationContinuationProps={locale:"en",active:true,binding,host:{},authGeneration:1,
    selection:read.selection,read,message:fixture.turn_request.message,draftOwner:owner,onMessageChange:vi.fn()};
  return{props,store,transport,binding,read,consumption:consumption.data.initial_consumption,setOwner:(next:OwnerContext|null)=>{owner=next;},
    setCurrent:(next:boolean)=>{current=next;},setPointer:(next:OperationPointer|null)=>{pointer=next;},peek:()=>pointer};
}
function Harness({config}:{config:FreshConversationContinuationProps}){
  const [message,setMessage]=useState(config.message);
  const view=useFreshConversationContinuation({...config,message,onMessageChange:setMessage});
  return <>{view.panel}<output>{view.hasUnresolvedOriginal?"Held original":"No held original"}</output></>;
}
async function readyKeep(){await waitFor(()=>expect((screen.getByRole("button",{name:"Keep first response"}) as HTMLButtonElement).disabled).toBe(false));}
async function keepAndRecover(h:ReturnType<typeof setup>){
  await readyKeep();fireEvent.click(screen.getByRole("button",{name:"Keep first response"}));
  await screen.findByText("The original request needs a status check. Don’t send it again.");
  expect(h.peek()?.kind).toBe("conversation_consume");
  fireEvent.click(screen.getByRole("button",{name:"Check original request"}));
  await screen.findByText("First response kept");
  await waitFor(()=>expect(h.peek()).toBeNull());
}
it("never transports or mints on mount, and preserves a foreign original",async()=>{
  const h=setup();const foreign:OperationPointer={kind:"conversation_create",operationKey:fixture.request.operation_key,targetKey:fixture.request.work_ref};
  h.setPointer(foreign);render(<Harness config={h.props}/>);
  await screen.findByText("Another request needs its existing status controls before continuing.");
  expect(h.peek()).toBe(foreign);expect(h.store.clearIfEqual).not.toHaveBeenCalled();
  for(const fn of Object.values(h.transport))expect(fn).not.toHaveBeenCalled();
});
it("uses genuine lost Keep→readonly original status→pure review→one exact turn→reply",async()=>{
  const h=setup();render(<Harness config={h.props}/>);await keepAndRecover(h);
  expect(h.transport.consume).toHaveBeenCalledTimes(1);expect(h.transport.consume.mock.calls[0]?.[0]).toEqual(fixture.consume_request);
  expect(h.transport.consumeStatus).toHaveBeenCalledTimes(2);
  const message=screen.getByRole("textbox",{name:"Your next message"}) as HTMLTextAreaElement;
  expect(message.value).toBe(fixture.turn_request.message);
  fireEvent.click(screen.getByRole("button",{name:"Review message"}));
  await screen.findByRole("heading",{name:"Review message"});
  expect(h.transport.turn).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"Send message"}));
  await screen.findByText("Follow-up response recorded");
  expect(h.transport.turn).toHaveBeenCalledTimes(1);expect(h.transport.turn.mock.calls[0]?.[0]).toEqual(fixture.turn_request);
  expect(h.transport.turnRead).toHaveBeenCalledTimes(1);expect(h.peek()).toBeNull();
  expect(screen.queryByRole("button",{name:"Send message"})).toBeNull();
  expect(screen.getByText(fixture.turn_read.data.result.envelope.summary)).toBeTruthy();
});
it("same-store successor checks lost Keep without consuming again",async()=>{
  const h=setup();const first=render(<Harness config={h.props}/>);await readyKeep();
  fireEvent.click(screen.getByRole("button",{name:"Keep first response"}));
  await screen.findByText("The original request needs a status check. Don’t send it again.");
  const original=h.peek();first.unmount();
  const successor=createFreshConversationAttendedBinding({owner:()=>h.props.draftOwner,canModify:()=>false,
    store:h.store,transport:h.transport,readInitial:async()=>h.read});
  render(<Harness config={{...h.props,binding:successor}}/>);
  await screen.findByText("Check the original request before continuing. Don’t send it again.");
  expect(h.peek()).toEqual(original);fireEvent.click(screen.getByRole("button",{name:"Check original request"}));
  await screen.findByText("First response kept");expect(h.transport.consume).toHaveBeenCalledTimes(1);expect(h.peek()).toBeNull();
});
it("pre-reservation double clicks cannot duplicate Keep",async()=>{
  const h=setup();render(<Harness config={h.props}/>);await readyKeep();
  const button=screen.getByRole("button",{name:"Keep first response"});fireEvent.click(button);fireEvent.click(button);
  await screen.findByText("The original request needs a status check. Don’t send it again.");
  expect(h.transport.consume).toHaveBeenCalledTimes(1);expect(h.store.reserve).toHaveBeenCalledTimes(1);
});
it("Edit preserves exact text and one already-minted turn request across locale change",async()=>{
  const h=setup();const mounted=render(<Harness config={h.props}/>);await keepAndRecover(h);
  fireEvent.click(screen.getByRole("button",{name:"Review message"}));await screen.findByRole("heading",{name:"Review message"});
  expect(screen.queryByRole("textbox",{name:"Your next message"})).toBeNull();
  expect(screen.getAllByText(fixture.turn_request.message,{exact:true})).toHaveLength(1);
  fireEvent.click(screen.getByRole("button",{name:"Edit message"}));
  expect(document.activeElement).toBe(screen.getByRole("textbox",{name:"Your next message"}));
  mounted.rerender(<Harness config={{...h.props,locale:"zh-CN"}}/>);
  expect((screen.getByRole("textbox",{name:"下一条消息"}) as HTMLTextAreaElement).value).toBe(fixture.turn_request.message);
  fireEvent.click(screen.getByRole("button",{name:"预览消息"}));await screen.findByRole("heading",{name:"预览消息"});
  expect(h.transport.turnPreview.mock.calls[0]?.[0]).toEqual(h.transport.turnPreview.mock.calls[1]?.[0]);
  expect(h.transport.turn).not.toHaveBeenCalled();expect(h.transport.consume).toHaveBeenCalledTimes(1);
});
it("a no-render owner loss during preview cannot expose Send or submit",async()=>{
  const h=setup();render(<Harness config={h.props}/>);await keepAndRecover(h);
  let resolve!:(value:typeof fixture.turn_preview)=>void;
  h.transport.turnPreview.mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
  fireEvent.click(screen.getByRole("button",{name:"Review message"}));await waitFor(()=>expect(h.transport.turnPreview).toHaveBeenCalledTimes(1));
  h.setOwner(null);resolve(fixture.turn_preview);
  await waitFor(()=>expect(screen.queryByRole("button",{name:"Send message"})).toBeNull());
  expect(h.transport.turn).not.toHaveBeenCalled();
});
it("a source-supplied kept receipt needs pure review, never another Keep or automatic Send",async()=>{
  const h=setup();render(<Harness config={{...h.props,initialConsumption:h.consumption}}/>);
  await waitFor(()=>expect((screen.getByRole("button",{name:"Review message"}) as HTMLButtonElement).disabled).toBe(false));
  expect(screen.getByText("First response kept")).toBeTruthy();expect(screen.queryByRole("button",{name:"Keep first response"})).toBeNull();
  expect(screen.queryByRole("button",{name:"Send message"})).toBeNull();
  for(const fn of Object.values(h.transport))expect(fn).not.toHaveBeenCalled();
});
it("a status check before Keep releases authoritative absence without submitting an operation",async()=>{
  const h=setup(),settled=vi.fn();h.props.onOriginalSettled=settled;
  h.transport.consumeStatus.mockImplementation(async()=>({...fixture.consume_status,data:{...fixture.consume_status.data,state:"ABSENT",effect:"NONE",initial_consumption:null}}));
  render(<Harness config={h.props}/>);await readyKeep();
  fireEvent.click(screen.getByRole("button",{name:"Check original request"}));
  await waitFor(()=>expect(h.transport.consumeStatus).toHaveBeenCalledTimes(1));await readyKeep();
  expect(screen.getByText("No held original")).toBeTruthy();expect(h.binding.controller.getState().status).toBe("idle");
  expect(h.peek()).toBeNull();expect(h.store.reserve).not.toHaveBeenCalled();expect(h.store.clearIfEqual).not.toHaveBeenCalled();
  expect(h.transport.consume).not.toHaveBeenCalled();expect(h.transport.turn).not.toHaveBeenCalled();expect(settled).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"Keep first response"}));
  await screen.findByText("The original request needs a status check. Don’t send it again.");
  expect(h.transport.consume).toHaveBeenCalledTimes(1);expect(h.peek()?.kind).toBe("conversation_consume");
});
it("an absent status check preserves a foreign request that arrives during the read",async()=>{
  const h=setup();let finish!:(value:unknown)=>void;
  h.transport.consumeStatus.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  render(<Harness config={h.props}/>);await readyKeep();
  fireEvent.click(screen.getByRole("button",{name:"Check original request"}));
  await waitFor(()=>expect(h.transport.consumeStatus).toHaveBeenCalledTimes(1));
  const foreign:OperationPointer={kind:"conversation_create",operationKey:fixture.request.operation_key,targetKey:fixture.request.work_ref};
  h.setPointer(foreign);await act(async()=>finish({...fixture.consume_status,data:{...fixture.consume_status.data,state:"ABSENT",effect:"NONE",initial_consumption:null}}));
  await screen.findByText("Another request needs its existing status controls before continuing.");
  expect(screen.getByText("Held original")).toBeTruthy();expect(screen.queryByRole("button",{name:"Keep first response"})).toBeNull();
  expect(h.peek()).toBe(foreign);expect(h.store.reserve).not.toHaveBeenCalled();expect(h.store.clearIfEqual).not.toHaveBeenCalled();
  expect(h.transport.consume).not.toHaveBeenCalled();expect(h.transport.turn).not.toHaveBeenCalled();
});
it("an absent original after attempted Keep stays held with no consume replay",async()=>{
  const h=setup();
  // Named synthetic negative only; this is not an owner success fixture.
  h.transport.consumeStatus.mockImplementation(async()=>({...fixture.consume_status,data:{...fixture.consume_status.data,state:"ABSENT",effect:"NONE",initial_consumption:null}}) as never);
  render(<Harness config={h.props}/>);await readyKeep();fireEvent.click(screen.getByRole("button",{name:"Keep first response"}));
  await screen.findByText("The original request needs a status check. Don’t send it again.");const original=h.peek();
  fireEvent.click(screen.getByRole("button",{name:"Check original request"}));
  await waitFor(()=>expect(h.transport.consumeStatus).toHaveBeenCalledTimes(1));
  expect(h.peek()).toEqual(original);expect(h.transport.consume).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("button",{name:"Keep first response"})).toBeNull();expect(screen.queryByRole("button",{name:"Send message"})).toBeNull();
});
it("lost turn and duplicate Send clicks keep one original and recover with status/read only",async()=>{
  const h=setup();
  // Named synthetic transport loss; all recovered success frames are actual A4.
  h.transport.turn.mockImplementationOnce(async()=>{throw Error("unit lost turn response");});
  render(<Harness config={h.props}/>);await keepAndRecover(h);
  fireEvent.click(screen.getByRole("button",{name:"Review message"}));await screen.findByRole("heading",{name:"Review message"});
  const send=screen.getByRole("button",{name:"Send message"});fireEvent.click(send);fireEvent.click(send);
  await screen.findByText("The original request needs a status check. Don’t send it again.");
  const original=h.peek();expect(original?.kind).toBe("conversation_turn");expect(h.transport.turn).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button",{name:"Check original request"}));await screen.findByText("Follow-up response recorded");
  expect(h.transport.turn).toHaveBeenCalledTimes(1);expect(h.transport.turnStatus).toHaveBeenCalledTimes(1);expect(h.transport.turnRead).toHaveBeenCalledTimes(1);expect(h.peek()).toBeNull();
});
it("explicitly rediscovers a foreign original cleared by its genuine owner without a source request",async()=>{
  const h=setup();h.setPointer({kind:"conversation_create",operationKey:fixture.request.operation_key,targetKey:fixture.request.work_ref});
  render(<Harness config={h.props}/>);await screen.findByText("Another request needs its existing status controls before continuing.");
  h.setPointer(null);fireEvent.click(screen.getByRole("button",{name:"Check for pending requests"}));await readyKeep();
  for(const fn of Object.values(h.transport))expect(fn).not.toHaveBeenCalled();
  expect(h.store.reserve).not.toHaveBeenCalled();expect(h.peek()).toBeNull();
});
it("a binding method replaced without a render cannot start a new preview",async()=>{
  const h=setup();render(<Harness config={{...h.props,initialConsumption:h.consumption}}/>);
  await waitFor(()=>expect((screen.getByRole("button",{name:"Review message"}) as HTMLButtonElement).disabled).toBe(false));
  const replacement=vi.fn(h.binding.previewTurn);h.binding.previewTurn=replacement;
  fireEvent.click(screen.getByRole("button",{name:"Review message"}));
  await Promise.resolve();expect(replacement).not.toHaveBeenCalled();expect(h.transport.turnPreview).not.toHaveBeenCalled();
});
it("withdraws the prepared private view when the same issued witness is revoked",async()=>{
  const h=setup();const mounted=render(<Harness config={h.props}/>);
  await keepAndRecover(h);
  fireEvent.click(screen.getByRole("button",{name:"Review message"}));await screen.findByRole("heading",{name:"Review message"});
  h.setCurrent(false);mounted.rerender(<Harness config={h.props}/>);
  expect(screen.queryByRole("heading",{name:"Review message"})).toBeNull();expect(screen.queryByRole("button",{name:"Send message"})).toBeNull();
  expect(screen.queryByText("First response kept")).toBeNull();expect(h.transport.turn).not.toHaveBeenCalled();
});
it("shows the actual supplied receipt in closed source details without claiming a turn frame",async()=>{
  const h=setup();render(<Harness config={{...h.props,initialConsumption:h.consumption}}/>);
  await screen.findByText("First response kept");
  const receipt=screen.getByText(`event ${h.consumption!.event_id} · ${h.consumption!.event_sha256}`);
  expect((receipt.closest("details") as HTMLDetailsElement).open).toBe(false);
});
it("accepted turn with unavailable reply stays on original Check, without another Review/Send or unsent claim",async()=>{
  const h=setup();h.transport.turnRead.mockImplementationOnce(async()=>{throw Error('unit unavailable original reply');});
  render(<Harness config={h.props}/>);await keepAndRecover(h);
  fireEvent.click(screen.getByRole("button",{name:"Review message"}));await screen.findByRole("heading",{name:"Review message"});
  fireEvent.click(screen.getByRole("button",{name:"Send message"}));
  await screen.findByText("Check the original request to read its response. Don’t send another message here.");
  expect(screen.queryByRole("button",{name:"Review message"})).toBeNull();expect(screen.queryByRole("button",{name:"Send message"})).toBeNull();
  expect(screen.queryByText("Continuing is unavailable here right now. Your message remains a draft.")).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"Check original request"}));await screen.findByText("Follow-up response recorded");
  expect(h.transport.turn).toHaveBeenCalledTimes(1);expect(h.transport.turnRead).toHaveBeenCalledTimes(2);
});
it("a temporary before-edit hold preserves the actual Keep receipt and unsent text",async()=>{
  const h=setup();const mounted=render(<Harness config={h.props}/>);await keepAndRecover(h);
  mounted.rerender(<Harness config={{...h.props,readOnly:true}}/>);
  expect(screen.getByText("First response kept")).toBeTruthy();expect((screen.getByRole("textbox",{name:"Your next message"}) as HTMLTextAreaElement).disabled).toBe(true);
  expect(screen.queryByRole("button",{name:"Review message"})).toBeNull();
  mounted.rerender(<Harness config={h.props}/>);
  expect(screen.getByText("First response kept")).toBeTruthy();expect((screen.getByRole("textbox",{name:"Your next message"}) as HTMLTextAreaElement).value).toBe(fixture.turn_request.message);
  expect(h.transport.consume).toHaveBeenCalledTimes(1);
});

it("the real ephemeral owner settles recorded sent text, preserves displayed original, and permits another original after Back",async()=>{
  const h=setup();const owner=h.props.draftOwner!;
  const host={invalidationGeneration:()=>1,auth:{getState:()=>({status:"signed_in" as const,reason:null,acquisition:true,content:true}),subscribe:()=>()=>{},signIn:async()=>{},signOut:async()=>{}},freshConversation:{request:async()=>{throw Error("inert host: no direct transport");}}};
  window.MastermindMissionHost=host as MissionHost;h.props.host=host;
  const ownerProps={host,authRevision:1,currentAuthRevision:()=>1,getExecutiveOwner:()=>owner};
  let draftApi:ReturnType<typeof useFreshConversationTurnDraftState>;
  function Coupled(){
    const draft=useFreshConversationTurnDraftState(ownerProps);draftApi=draft;
    const [shown,setShown]=useState(true);
    useLayoutEffect(()=>{draft.selectOriginal(h.read.selection);},[]);
    return <>{shown?<><OwnedPanel draft={draft}/><button onClick={()=>setShown(false)}>Back from attended view</button></>:<p>Back at the list</p>}<output>{draft.hasUnsentDraft()?"Unsent text remains":"No unsent text"}</output></>;
  }
  function OwnedPanel({draft}:{draft:ReturnType<typeof useFreshConversationTurnDraftState>}){
    const v=useFreshConversationContinuation({...h.props,message:draft.message,draftOwner:draft.draftOwner,onMessageChange:draft.onMessageChange,draftSubmission:draft});return v.panel;
  }
  const mounted=render(<Coupled/>);await keepAndRecover(h);
  fireEvent.change(screen.getByRole('textbox',{name:'Your next message'}),{target:{value:fixture.turn_request.message}});
  await screen.findByText('Unsent text remains');fireEvent.click(screen.getByRole('button',{name:'Review message'}));await screen.findByRole('heading',{name:'Review message'});
  fireEvent.click(screen.getByRole('button',{name:'Send message'}));await screen.findByText('Follow-up response recorded');await screen.findByText('No unsent text');
  expect(screen.getByText(fixture.turn_request.message)).toBeTruthy();expect(draftApi!.message).toBe('');
  fireEvent.click(screen.getByRole('button',{name:'Back from attended view'}));await screen.findByText('Back at the list');
  let changed=false;act(()=>{changed=draftApi!.selectOriginal({work_ref:'WS:OTHER',operation_key:'mmos-conversation-create-'+'f'.repeat(40)});});
  expect(changed).toBe(true);expect(h.transport.turn).toHaveBeenCalledTimes(1);mounted.unmount();delete window.MastermindMissionHost;
});
it("native before-edit readonly remains focusable, rejects changes, and does not block Keep",async()=>{
 const h=setup(),focus=vi.fn();const mounted=render(<Harness config={{...h.props,messageReadOnly:true,onMessageFocus:focus}}/>);
 await keepAndRecover(h);const input=screen.getByRole('textbox',{name:'Your next message'}) as HTMLTextAreaElement;
 expect(input.disabled).toBe(false);expect(input.readOnly).toBe(true);fireEvent.focus(input);expect(focus).toHaveBeenCalledTimes(1);
 fireEvent.change(input,{target:{value:'Must not enter while checking'}});expect(input.value).toBe(fixture.turn_request.message);
 expect((screen.getByRole('button',{name:'Review message'}) as HTMLButtonElement).disabled).toBe(true);
 mounted.rerender(<Harness config={h.props}/>);expect((screen.getByRole('textbox',{name:'Your next message'}) as HTMLTextAreaElement).readOnly).toBe(false);
 expect(h.transport.consume).toHaveBeenCalledTimes(1);
});

it("notifies local-hint refresh only after accepted original receipt/read, never unknown or unmount",async()=>{
 const h=setup(),settled=vi.fn();h.props.onOriginalSettled=settled;
 const mounted=render(<Harness config={h.props}/>);await readyKeep();
 fireEvent.click(screen.getByRole("button",{name:"Keep first response"}));await screen.findByText("The original request needs a status check. Don’t send it again.");expect(settled).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:"Check original request"}));await screen.findByText("First response kept");expect(settled).toHaveBeenCalledTimes(1);
 mounted.unmount();expect(settled).toHaveBeenCalledTimes(1);expect(h.transport.consume).toHaveBeenCalledTimes(1);
});

it("sends three distinct follow-ups and keeps each confirmed reply while resetting only its sent draft",async()=>{
 const h=setup();h.props.initialConsumption=h.consumption;
 let draw=0;vi.stubGlobal("crypto",{getRandomValues:(a:Uint8Array)=>{const seed=++draw*17;for(let i=0;i<a.length;i++)a[i]=(seed+i)%256;return a;}});
 const withKey=(frame:unknown,request:FreshConversationTurnRequest)=>{
  if(!("turn_key"in request))throw Error("turn key required");
  const value=structuredClone(frame) as {data:{turn_key:string}};value.data.turn_key=request.turn_key;return value;
 };
 h.transport.turnPreview.mockImplementation(async request=>withKey(fixture.turn_preview,request));
 h.transport.turn.mockImplementation(async request=>withKey(fixture.turn,request));
 h.transport.turnRead.mockImplementation(async request=>withKey(fixture.turn_read,request));
 render(<Harness config={h.props}/>);
 for(let index=1;index<=3;index++){
  const input=await screen.findByRole("textbox",{name:"Your next message"});
  await waitFor(()=>expect((input as HTMLTextAreaElement).disabled).toBe(false));
  fireEvent.change(input,{target:{value:"Sequential message "+index}});
  fireEvent.click(screen.getByRole("button",{name:"Review message"}));
  const send=await screen.findByRole("button",{name:"Send message"});fireEvent.click(send);
  await waitFor(()=>expect(h.transport.turnRead).toHaveBeenCalledTimes(index));
  await waitFor(()=>expect((screen.getByRole("textbox",{name:"Your next message"}) as HTMLTextAreaElement).value).toBe(""));
  expect(screen.getByText("Sequential message "+index)).toBeTruthy();
  expect(h.peek()).toBeNull();
 }
 expect(h.transport.consume).not.toHaveBeenCalled();
 expect(h.transport.turn).toHaveBeenCalledTimes(3);
 expect(new Set(h.transport.turn.mock.calls.map(([request])=>"turn_key"in request?request.turn_key:null)).size).toBe(3);
 for(let index=1;index<=3;index++)expect(screen.getByText("Sequential message "+index)).toBeTruthy();
 expect(screen.getAllByText(fixture.turn_read.data.result.envelope.summary)).toHaveLength(3);
});

it.each([false,true])("recovers an accepted original after remount without inventing acceptance or resending (later pending turn: %s)",async(later)=>{
 const h=setup(),settled=vi.fn();h.props.onOriginalSettled=settled;
 h.transport.turnRead.mockRejectedValueOnce(Error("fixture lost original read after accepted Send"));
 const owner=h.props.draftOwner!;
 const host={invalidationGeneration:()=>1,auth:{getState:()=>({status:"signed_in" as const,reason:null,acquisition:true,content:true}),subscribe:()=>()=>{},signIn:async()=>{},signOut:async()=>{}},freshConversation:{request:async()=>{throw Error("fixture has no direct transport");}}};
 window.MastermindMissionHost=host as MissionHost;h.props.host=host;
 const ownerProps={host,authRevision:1,currentAuthRevision:()=>1,getExecutiveOwner:()=>owner};
 let draftApi:ReturnType<typeof useFreshConversationTurnDraftState>;
 function Coupled(){
  const draft=useFreshConversationTurnDraftState(ownerProps);draftApi=draft;
  const [shown,setShown]=useState(true);
  useLayoutEffect(()=>{draft.selectOriginal(h.read.selection);},[]);
  return <>{shown?<Owned draft={draft}/>:<p>Retained App draft</p>}
   <button onClick={()=>setShown(value=>!value)}>{shown?"Leave original":"Reopen original"}</button></>;
 }
 function Owned({draft}:{draft:ReturnType<typeof useFreshConversationTurnDraftState>}){
  return useFreshConversationContinuation({...h.props,message:draft.message,draftOwner:draft.draftOwner,
   onMessageChange:draft.onMessageChange,draftSubmission:draft}).panel;
 }
 const mounted=render(<Coupled/>);await keepAndRecover(h);settled.mockClear();
 const input=await screen.findByRole("textbox",{name:"Your next message"});
 await waitFor(()=>expect((input as HTMLTextAreaElement).disabled).toBe(false));
 fireEvent.change(input,{target:{value:fixture.turn_request.message}});
 fireEvent.click(screen.getByRole("button",{name:"Review message"}));
 fireEvent.click(await screen.findByRole("button",{name:"Send message"}));
 await screen.findByText("Check the original request to read its response. Don’t send another message here.");
 expect(h.peek()).toBeNull();expect(h.binding.controller.getState().status).toBe("accepted");
 const originalKey=draftApi!.submittedTurnKey;expect(originalKey).toBeTruthy();
 fireEvent.click(screen.getByRole("button",{name:"Leave original"}));
 expect(h.binding.controller.getState().status).toBe("idle");
 if(later){
  // A separate actual-owner hint is a named synthetic negative. It may settle
  // first, but must never outrank this App draft after that hint is cleared.
  h.setPointer({kind:"conversation_turn",operationKey:"mmos-conversation-turn-"+"f".repeat(40),targetKey:freshConversationTarget(h.read.selection)!});
  const keyed=(frame:unknown,request:FreshConversationTurnRequest)=>{
   if(!("turn_key"in request))throw Error("turn key required");
   const value=structuredClone(frame) as {data:{turn_key:string}};value.data.turn_key=request.turn_key;return value;
  };
  h.transport.turnStatus.mockImplementation(async request=>keyed(fixture.status,request));
  h.transport.turnRead.mockImplementation(async request=>keyed(fixture.turn_read,request));
 }
 fireEvent.click(screen.getByRole("button",{name:"Reopen original"}));
 const check=await screen.findByRole("button",{name:"Check original request"});
 await waitFor(()=>expect((check as HTMLButtonElement).disabled).toBe(false));
 expect(screen.queryByRole("button",{name:"Review message"})).toBeNull();fireEvent.click(check);
 if(later){
  await waitFor(()=>expect(settled).toHaveBeenCalledTimes(1));
  expect(draftApi!.submittedTurnKey).toBe(originalKey);expect(h.peek()).toBeNull();
  expect(screen.queryByRole("button",{name:"Review message"})).toBeNull();
  await waitFor(()=>expect((check as HTMLButtonElement).disabled).toBe(false));fireEvent.click(check);
 }
 await screen.findByText("Follow-up response recorded");
 await waitFor(()=>expect(settled).toHaveBeenCalledTimes(later?2:1));
 expect(draftApi!.message).toBe("");expect(draftApi!.submittedTurnKey).toBeNull();
 expect((screen.getByRole("textbox",{name:"Your next message"}) as HTMLTextAreaElement).disabled).toBe(false);
 expect(screen.getByText(fixture.turn_request.message)).toBeTruthy();
 expect(h.binding.controller.getState().status).toBe(later?"accepted":"idle");
 expect(h.transport.turn).toHaveBeenCalledTimes(1);expect(h.transport.turnRead).toHaveBeenCalledTimes(later?3:2);
 expect(h.transport.turnStatus).toHaveBeenCalledTimes(later?1:0);expect(h.peek()).toBeNull();
 const finalRead=h.transport.turnRead.mock.calls.at(-1)![0];
 expect("turn_key"in finalRead?finalRead.turn_key:null).toBe(originalKey);
 mounted.unmount();delete window.MastermindMissionHost;
});

it("bounds local complete replies while preserving the latest eight original turns",async()=>{
 const h=setup();h.props.initialConsumption=h.consumption;
 let draw=0;vi.stubGlobal("crypto",{getRandomValues:(a:Uint8Array)=>{const seed=++draw*17;for(let i=0;i<a.length;i++)a[i]=(seed+i)%256;return a;}});
 const withKey=(frame:unknown,request:FreshConversationTurnRequest)=>{
  if(!("turn_key"in request))throw Error("turn key required");
  const value=structuredClone(frame) as {data:{turn_key:string}};value.data.turn_key=request.turn_key;return value;
 };
 h.transport.turnPreview.mockImplementation(async request=>withKey(fixture.turn_preview,request));
 h.transport.turn.mockImplementation(async request=>withKey(fixture.turn,request));
 h.transport.turnRead.mockImplementation(async request=>withKey(fixture.turn_read,request));
 render(<Harness config={h.props}/>);
 for(let index=1;index<=9;index++){
  const input=await screen.findByRole("textbox",{name:"Your next message"});
  await waitFor(()=>expect((input as HTMLTextAreaElement).disabled).toBe(false));
  fireEvent.change(input,{target:{value:"Bounded message "+index}});
  fireEvent.click(screen.getByRole("button",{name:"Review message"}));
  fireEvent.click(await screen.findByRole("button",{name:"Send message"}));
  await waitFor(()=>expect(h.transport.turnRead).toHaveBeenCalledTimes(index));
  await waitFor(()=>expect((screen.getByRole("textbox",{name:"Your next message"}) as HTMLTextAreaElement).value).toBe(""));
 }
 expect(screen.queryByText("Bounded message 1")).toBeNull();
 for(let index=2;index<=9;index++)expect(screen.getByText("Bounded message "+index)).toBeTruthy();
 expect(screen.getAllByText(fixture.turn_read.data.result.envelope.summary)).toHaveLength(8);
 expect(screen.getByText("Earlier replies remain available in project conversation history.")).toBeTruthy();
 expect(h.transport.turn).toHaveBeenCalledTimes(9);expect(h.peek()).toBeNull();
});

it("does not release an exact recovered result over a newer foreign pending operation",async()=>{
 const h=setup();let finish!:(value:unknown)=>void;
 h.transport.turnRead.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 render(<Harness config={h.props}/>);await keepAndRecover(h);
 fireEvent.click(screen.getByRole("button",{name:"Review message"}));
 fireEvent.click(await screen.findByRole("button",{name:"Send message"}));
 await waitFor(()=>expect(h.transport.turnRead).toHaveBeenCalledTimes(1));
 const foreign:OperationPointer={kind:"conversation_create",operationKey:fixture.request.operation_key,targetKey:fixture.request.work_ref};
 h.setPointer(foreign);await act(async()=>finish(fixture.turn_read));
 await screen.findByText("Another request needs its existing status controls before continuing.");
 expect(h.peek()).toBe(foreign);expect(screen.queryByRole("button",{name:"Review message"})).toBeNull();
 expect(screen.getByText("Held original")).toBeTruthy();expect(h.transport.turn).toHaveBeenCalledTimes(1);
});

it("keeps an unknown controller held when an exact read finds the store unexpectedly empty",async()=>{
 const h=setup();h.transport.turn.mockRejectedValueOnce(Error("fixture transport loss"));
 render(<Harness config={h.props}/>);await keepAndRecover(h);
 fireEvent.click(screen.getByRole("button",{name:"Review message"}));
 fireEvent.click(await screen.findByRole("button",{name:"Send message"}));
 await screen.findByText("The original request needs a status check. Don’t send it again.");
 expect(h.binding.controller.getState().status).toBe("unknown");
 // Explicit negative fixture: no owner receipt accompanied this missing hint.
 h.setPointer(null);fireEvent.click(screen.getByRole("button",{name:"Check original request"}));
 await waitFor(()=>expect(h.transport.turnRead).toHaveBeenCalledTimes(1));
 expect(h.binding.controller.getState().status).toBe("unknown");
 expect(screen.queryByRole("button",{name:"Review message"})).toBeNull();
 expect(screen.getByText("Held original")).toBeTruthy();expect(h.transport.turn).toHaveBeenCalledTimes(1);
});
