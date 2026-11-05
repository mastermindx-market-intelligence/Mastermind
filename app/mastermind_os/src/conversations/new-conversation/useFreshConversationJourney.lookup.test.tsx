// @vitest-environment jsdom
// Source-only integration: actual binding/controller + captured owner responses;
// the principal/host and atomic store are explicitly inert test seams.
import {IDBFactory} from "fake-indexeddb";
import {createIndexedDbPendingPointerStore} from "../../orchestration/indexeddb-pending-pointer-store";
import {afterEach,expect,it,vi} from "vitest";
import {act,cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {useFreshConversationJourney,type FreshConversationJourneyProps,type FreshConversationInitialRead} from "./useFreshConversationJourney";
import {createFreshConversationBinding} from "./fresh-conversation-command-binding";
import type {OperationPointer,OwnerContext,PendingPointerStore} from "../../orchestration/operation-controller";
import fixture from "./fixtures/fresh-conversation-owner.json";
afterEach(cleanup);
const owner:OwnerContext={principalScope:"unit-executive-principal",generation:"unit-auth-1"};
function setup(pointer:OperationPointer|null=null){
 const store:PendingPointerStore={read:vi.fn(()=>pointer),reserve:vi.fn(()=>({reserved:true as const})),clearIfEqual:vi.fn(()=>true)};
 const transport={preview:vi.fn(async(_request:{work_ref:string;operation_key:string},_signal:AbortSignal)=>fixture.preview),create:vi.fn(async(_request:{work_ref:string;operation_key:string},_signal:AbortSignal)=>fixture.create),
  status:vi.fn(async(_request:{work_ref:string;operation_key:string},_signal:AbortSignal)=>fixture.read),read:vi.fn(async(_request:{work_ref:string;operation_key:string},_signal:AbortSignal)=>fixture.read)};
 const binding=createFreshConversationBinding({owner:()=>owner,canPreviewCreate:()=>true,store,transport});
 const props:FreshConversationJourneyProps={locale:"en",active:true,binding,authGeneration:1,host:{},
  projects:[{workRef:fixture.request.work_ref,title:"Fixture project"}],projectsState:"available",
  isProjectCurrent:()=>true,workRef:fixture.request.work_ref,message:"  Unsaved new draft\n🙂  ",draftOwner:owner,
  onWorkRefChange:vi.fn(),onMessageChange:vi.fn(),onOriginalKeySelected:vi.fn(),onBack:vi.fn(),
  originalLookup:{selection:{work_ref:fixture.request.work_ref,operation_key:fixture.request.operation_key},owner}};
 return {props,store,transport};
}
function Harness(props:FreshConversationJourneyProps){
 const view=useFreshConversationJourney(props);
 return <><button onClick={view.start}>Explicit new-entry gesture</button>{view.panel}</>;
}
it("restores only a lookup outcome after the terminal pointer cleared, then reads only on an explicit Check",async()=>{
 const {props,store,transport}=setup();render(<Harness {...props}/>);
 await screen.findByText("An original conversation request is selected. Check its status to reopen it.");
 expect(transport.read).not.toHaveBeenCalled();expect(transport.preview).not.toHaveBeenCalled();expect(transport.create).not.toHaveBeenCalled();
 expect(store.reserve).not.toHaveBeenCalled();expect(props.onOriginalKeySelected).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:"Explicit new-entry gesture"}));
 expect(screen.queryByRole("button",{name:"Review conversation"})).toBeNull();
 fireEvent.click(screen.getByRole("button",{name:"Check original request"}));
 await waitFor(()=>expect(transport.read).toHaveBeenCalledTimes(1));
 expect(transport.read.mock.calls[0]?.[0]).toEqual(props.originalLookup!.selection);
 expect(transport.status).not.toHaveBeenCalled();expect(store.reserve).not.toHaveBeenCalled();
 expect(props.onOriginalKeySelected).toHaveBeenCalledWith(props.originalLookup!.selection);
 await screen.findByRole("button",{name:"Open initial response"});
 expect(transport.create).not.toHaveBeenCalled();
});
it("gives a genuine pending pointer precedence over conflicting safe URL data",async()=>{
 const pointer:OperationPointer={kind:"conversation_create",targetKey:fixture.request.work_ref,operationKey:fixture.request.operation_key};
 const {props,transport}=setup(pointer);props.originalLookup={selection:{work_ref:"WS:FOREIGN",operation_key:"foreign-url-key"},owner};
 render(<Harness {...props}/>);
 await screen.findByText("An original conversation request needs a status check. Don’t create it again.");
 expect(screen.queryByText("An original conversation request is selected. Check its status to reopen it.")).toBeNull();
 expect(transport.read).not.toHaveBeenCalled();expect(transport.create).not.toHaveBeenCalled();
});
it("does not expose a lookup from another owner, and masks an issued lookup immediately on auth withdrawal",async()=>{
 const {props,transport}=setup();props.originalLookup={...props.originalLookup!,owner:{...owner,generation:"unit-old-auth"}};
 const view=render(<Harness {...props}/>);
 await waitFor(()=>expect(screen.getByRole("button",{name:"Review conversation"})).toBeTruthy());
 expect(screen.queryByText("An original conversation request is selected. Check its status to reopen it.")).toBeNull();
 view.unmount();const fresh=setup();const mounted=render(<Harness {...fresh.props}/>);
 await screen.findByText("An original conversation request is selected. Check its status to reopen it.");
 mounted.rerender(<Harness {...fresh.props} binding={null} draftOwner={null} authGeneration={2}/>);
 expect(screen.queryByText("An original conversation request is selected. Check its status to reopen it.")).toBeNull();
 expect(screen.queryByText(fixture.request.operation_key)).toBeNull();expect(transport.create).not.toHaveBeenCalled();
});

it("supplies one stable actual initial-read witness, never authority, and retires it on reread or unmount",async()=>{
 const {props,transport}=setup();const issued:FreshConversationInitialRead[]=[];
 props.renderContinuation=read=>{issued.push(read);return <p>Inert independently supplied controls</p>;};
 const view=render(<Harness {...props}/>);
 await screen.findByText("An original conversation request is selected. Check its status to reopen it.");
 fireEvent.click(screen.getByRole("button",{name:"Check original request"}));
 await screen.findByRole("button",{name:"Open initial response"});expect(issued).toHaveLength(0);
 fireEvent.click(screen.getByRole("button",{name:"Open initial response"}));
 await screen.findByText("Inert independently supplied controls");
 expect(screen.getByText("Inert independently supplied controls").closest(".mm-new-conversation-outcome-panel")).toBeNull();
 const first=issued[0]!;
 expect(first.current()).toBe(true);expect(first.selection).toEqual(props.originalLookup!.selection);
 expect(first.result).toEqual(fixture.read.data.result);expect(first.locator).toEqual(fixture.read.data.locator);
 view.rerender(<Harness {...props} locale="zh-CN"/>);expect(issued.at(-1)).toBe(first);
 expect(first.current()).toBe(true);fireEvent.click(screen.getByRole("button",{name:"查看原请求状态"}));
 expect(first.current()).toBe(false);
 await waitFor(()=>expect(transport.read).toHaveBeenCalledTimes(3));
 await waitFor(()=>expect(issued.at(-1)).not.toBe(first));const second=issued.at(-1)!;
 expect(second.current()).toBe(true);view.unmount();expect(second.current()).toBe(false);
 expect(transport.create).not.toHaveBeenCalled();expect(transport.preview).not.toHaveBeenCalled();
});


it("rediscovers a cleared foreign original on explicit entry using the actual durable store, preserving exact text",async()=>{
 const {props,transport}=setup();const currentOwner={principalScope:"a".repeat(64),generation:"unit-auth-1"};
 const store=createIndexedDbPendingPointerStore(new IDBFactory());
 const foreign:OperationPointer={kind:"launch",operationKey:"mmos-launch-"+"1".repeat(40),targetKey:fixture.request.work_ref};
 await store.reserve(currentOwner.principalScope,foreign);
 props.binding=createFreshConversationBinding({owner:()=>currentOwner,canPreviewCreate:()=>true,store,transport});
 props.draftOwner=currentOwner;props.originalLookup=null;
 render(<Harness {...props}/>);
 await screen.findByText("Another request needs its existing status controls before a new conversation can be created.");
 expect(await store.clearIfEqual(currentOwner.principalScope,foreign)).toBe(true);
 fireEvent.click(screen.getByRole("button",{name:"Explicit new-entry gesture"}));
 await waitFor(()=>expect((screen.getByRole("button",{name:"Review conversation"}) as HTMLButtonElement).disabled).toBe(false));
 expect((screen.getByRole("textbox",{name:"First message"}) as HTMLTextAreaElement).value).toBe(props.message);
 expect(await store.read(currentOwner.principalScope)).toBeNull();
 expect(transport.preview).not.toHaveBeenCalled();expect(transport.create).not.toHaveBeenCalled();
 expect(transport.status).not.toHaveBeenCalled();expect(transport.read).not.toHaveBeenCalled();
 expect(props.onOriginalKeySelected).not.toHaveBeenCalled();expect(props.onMessageChange).not.toHaveBeenCalled();
});

it("gives an actual replacement conversation pointer precedence during explicit foreign-state refresh",async()=>{
 const {props,transport}=setup();const currentOwner={principalScope:"b".repeat(64),generation:"unit-auth-1"};
 const store=createIndexedDbPendingPointerStore(new IDBFactory());
 const foreign:OperationPointer={kind:"launch",operationKey:"mmos-launch-"+"2".repeat(40),targetKey:fixture.request.work_ref};
 const original:OperationPointer={kind:"conversation_create",operationKey:fixture.request.operation_key,targetKey:fixture.request.work_ref};
 await store.reserve(currentOwner.principalScope,foreign);
 props.binding=createFreshConversationBinding({owner:()=>currentOwner,canPreviewCreate:()=>true,store,transport});props.draftOwner=currentOwner;props.originalLookup=null;
 render(<Harness {...props}/>);await screen.findByText("Another request needs its existing status controls before a new conversation can be created.");
 await store.clearIfEqual(currentOwner.principalScope,foreign);await store.reserve(currentOwner.principalScope,original);
 fireEvent.click(screen.getByRole("button",{name:"Explicit new-entry gesture"}));
 await screen.findByText("An original conversation request needs a status check. Don’t create it again.");
 expect(await store.read(currentOwner.principalScope)).toEqual(original);
 expect(screen.queryByRole("button",{name:"Review conversation"})).toBeNull();
 expect(transport.create).not.toHaveBeenCalled();expect(transport.status).not.toHaveBeenCalled();expect(transport.read).not.toHaveBeenCalled();
});

it("does not apply late explicit rediscovery after the actual Executive owner is withdrawn",async()=>{
 const {props,transport}=setup();let currentOwner:OwnerContext|null={principalScope:"c".repeat(64),generation:"unit-auth-1"};
 const durable=createIndexedDbPendingPointerStore(new IDBFactory());const scope=currentOwner.principalScope;
 const foreign:OperationPointer={kind:"launch",operationKey:"mmos-launch-"+"3".repeat(40),targetKey:fixture.request.work_ref};
 await durable.reserve(scope,foreign);let reads=0,finish:((pointer:OperationPointer|null)=>void)|undefined;
 const store:PendingPointerStore={...durable,read:who=>++reads===1?durable.read(who):new Promise(resolve=>{finish=resolve;})};
 props.binding=createFreshConversationBinding({owner:()=>currentOwner,canPreviewCreate:()=>true,store,transport});props.draftOwner=currentOwner;props.originalLookup=null;
 const view=render(<Harness {...props}/>);await screen.findByText("Another request needs its existing status controls before a new conversation can be created.");
 await durable.clearIfEqual(scope,foreign);fireEvent.click(screen.getByRole("button",{name:"Explicit new-entry gesture"}));
 await waitFor(()=>expect(reads).toBe(2));currentOwner=null;
 view.rerender(<Harness {...props} binding={null} draftOwner={null} message="" authGeneration={2}/>);
 await act(async()=>{finish?.(null);});
 expect((screen.getByRole("button",{name:"Review conversation"}) as HTMLButtonElement).disabled).toBe(true);
 expect(transport.preview).not.toHaveBeenCalled();expect(transport.create).not.toHaveBeenCalled();expect(transport.status).not.toHaveBeenCalled();expect(transport.read).not.toHaveBeenCalled();
 expect(props.onOriginalKeySelected).not.toHaveBeenCalled();expect(await durable.read(scope)).toBeNull();
});
