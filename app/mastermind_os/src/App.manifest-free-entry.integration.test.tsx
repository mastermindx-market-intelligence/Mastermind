// @vitest-environment jsdom
// Actual App -> native client -> composeMissionHost(null) -> shared owner/ports/IDB.
// Only native invoke/listen responses are inert; no installed service or provider.
import {act,cleanup,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {IDBFactory} from "fake-indexeddb";
import {App} from "./App";
import {createNativeClient,type AuthState} from "./host";
import {composeMissionHost} from "./compose-mission-host";
import {controlRoomFixture} from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import plan from "./fixtures/project-plan-canonical-owner.json";
import work from "./fixtures/work-service-available.json";
import historyFixture from "./fixtures/project-execution-history-owner.json";
import freshFixture from "./fixtures/native-fresh-app-owner.json";
import {intentIdForOperationKey} from "./orchestration/operation-key";

vi.mock("@tauri-apps/api/core",()=>({invoke:vi.fn().mockResolvedValue({
  version:"0.1.0",source_revision:"a".repeat(40),build_identity:"inert-fixture",
  transport:"UNCONFIGURED",state:"BUILT_NOT_PROVEN"})}));
const workRef=historyFixture.completed_read.reference.work_ref;
const scope=historyFixture.completed_read.reference.principal_scope_sha256;
const goal=historyFixture.completed_read.goal;
const signed:AuthState={status:"signed_in",reason:null,acquisition:true,content:true};
const disposals:Array<()=>void>=[];
beforeEach(async()=>{
  history.replaceState(null,"","/os/");localStorage.clear();
  delete window.MastermindMissionHost;delete (window as any).__TAURI_INTERNALS__;
  vi.stubEnv("VITE_MM_LAUNCH_CONFIG","");
  const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>("node:crypto");
  vi.stubGlobal("crypto",webcrypto);
});
afterEach(()=>{
  cleanup();disposals.splice(0).forEach(dispose=>dispose());vi.useRealTimers();
  vi.restoreAllMocks();vi.unstubAllGlobals();vi.unstubAllEnvs();
  delete window.MastermindMissionHost;
});
const executionResult=(operation:string,data:unknown)=>({
  schema:"mastermind.project_execution_private_result.v1",operation,ok:true,data,error:null,
});
type Options={completed?:boolean;loseReply?:boolean;signedOut?:boolean;omitExecutive?:boolean;
  holdPreview?:boolean;legacyManifest?:boolean;holdOperationDiscovery?:boolean;nativeFresh?:boolean};
async function setup(options:Options={},database=new IDBFactory()){
  const workRef=options.nativeFresh?freshFixture.request.work_ref:historyFixture.completed_read.reference.work_ref;
  const scope=options.nativeFresh?freshFixture.executive_context.principal_scope:historyFixture.completed_read.reference.principal_scope_sha256;
  if(options.nativeFresh){vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date(freshFixture.clock.verified_at_seconds*1000));}
  const room=controlRoomFixture(),responsibility=structuredClone(room.autonomy.responsibilities[0]);
  room.work=[room.work[0]];room.autonomy.responsibilities=[];
  const publishRoots=(roots:string[])=>{
    const retained=structuredClone(responsibility);
    Object.assign(retained,{responsibility_ref:workRef,root_job_id:roots.length===1?roots[0]:null,
      root_job_candidates:roots,root_job_ambiguous:roots.length!==1,
      runtime_root_state:roots.length===1?"RESOLVED":"CONFLICT"});
    retained.dispatch.responsibility_ref=workRef;retained.dispatch.root_job_id=retained.root_job_id;
    retained.dispatch.evidence.responsibility_ref=workRef;
    retained.dispatch.evidence.root_job_id=retained.root_job_id;
    room.work[0].executive.jobs[0].job_id=roots[0];room.autonomy.responsibilities=[retained];
  };
  if(options.completed)publishRoots([historyFixture.completed_read.reference.root_job_id,"JOB-900"]);
  const row=room.work[0];row.work_ref=workRef;row.agent_os.workstream=workRef.slice(3);
  row.agent_os.title="Manifest-free project";
  for(const binding of row.bindings)binding.work_ref=workRef;
  row.executive.jobs[0].workstream=workRef;
  const sourcePlan=structuredClone(plan);sourcePlan.selection.work_ref=workRef;
  sourcePlan.source.path="agentos/workstreams/WS-"+workRef.slice(3)+".md";
  sourcePlan.plan.objective=goal;
  const events=new Map<string,Set<(event:{payload:unknown})=>void>>();
  let finishPreview:(()=>void)|undefined;
  const invoke=vi.fn(async(command:string,args?:Record<string,unknown>):Promise<unknown>=>{
    if(command==="auth_status")return options.signedOut
      ?{status:"signed_out",reason:"USER_SIGNED_OUT",acquisition:false,content:false}:signed;
    if(command==="executive_auth_status")return {generation:1,available:!options.signedOut};
    if(command==="executive_context"&&options.nativeFresh)return structuredClone(freshFixture.executive_context);
    if(command==="executive_context")return {
      schema:"mastermind.os.executive.owner_context.v1",principal_scope:scope,
      verified_expiry:4102444800,profile:{name:"web_ceo_v3",server_version:"1.5.0"},
    };
    if(command==="read_programs")return options.nativeFresh?structuredClone(freshFixture.programs.result):{...structuredClone(programs),control_room:structuredClone(room)};
    if(command==="read_mission_v3"&&options.nativeFresh)return structuredClone(freshFixture.mission.result);
    if(command==="read_work")return structuredClone(work);
    if(command==="read_project_plan")return structuredClone(sourcePlan);
    if(command==="executive_project_history_context"&&options.nativeFresh){
      expect(args).toEqual({workRef});return structuredClone(freshFixture.history_context);
    }
    if(command==="executive_project_history_context")return {
      schema:"mastermind.os.executive.session_result.v1",operation:"history_context",ok:true,
      effect:"NONE",operation_key:null,error:null,data:{
        schema:"mastermind.os.executive.project_history_context.v1",principal_scope:scope,
        verified_expiry:4102444800,selection:{work_ref:workRef},
        capabilities:{references_read:true,reply_read:true},
      },
    };
    if(command==="executive_project_conversations_read"){
      if(options.nativeFresh){
        const operation=args!.operation,request=args!.arguments as any;
        if(operation==='fresh_references'){expect(request).toEqual({work_ref:workRef});return structuredClone(freshFixture.catalogue);}
        if(operation==='fresh_read'){
          if(request.content){const part=freshFixture.fragments.find(p=>p.request.content.offset_bytes===request.content.offset_bytes);
            expect(part).toBeTruthy();expect(request).toEqual(part!.request);return structuredClone(part!.response);}
          expect(request).toEqual(freshFixture.window.reference);return structuredClone(freshFixture.window);
        }
      }
      if(args!.operation==="execution_references")return structuredClone(historyFixture.catalogue);
      if(args!.operation==="execution_read")return structuredClone(historyFixture.completed_read);
    }
    if(command==="executive_fresh_conversation"){
      expect(options.nativeFresh).toBe(true);expect(args!.contract).toBe('native-v2');
      const operation=String(args!.operation),request=args!.arguments as Record<string,unknown>;
      expect(request).toEqual(operation==='preview'?freshFixture.request:operation==='create'?freshFixture.create_request:
        operation==='consume_status'?freshFixture.consume_request:{work_ref:workRef,operation_key:freshFixture.request.operation_key});
      if(operation==='consume_status')return structuredClone(freshFixture.consume_status_before);
      if(operation==='preview'||operation==='create'||operation==='read'||operation==='status')
        return structuredClone(freshFixture[operation]);
    }
    if(command==="executive_project_execution"){
      const operation=String(args!.operation),request=args!.arguments as Record<string,unknown>;
      if(operation==="preview"){
        const response=executionResult(operation,{
        schema:"mastermind.project_execution_preview.v1",work_ref:workRef,
        context_sha256:"c".repeat(64),execution_binding_sha256:"d".repeat(64),
        execution_profile_bindings:{research_only:"d".repeat(64)},execution_state:"WORK_CAPABLE",
        continuation_mode:"DURABLE",coordinator:{provider:"codex",model:"inert-source-model",effort:"high"},
        execution_scope:{repository:"mastermindx-market-intelligence/Mastermind",commit:"e".repeat(40)},
        previous_run:request.previous_run??null,
        binding:{workstream:workRef,priority:0,attemptLimit:1,
          projects:[{ref:"executive-infrastructure",label:"Project team"}],
          profiles:[{ref:"research_only",label:"Research team"}]},
        });
        if(options.holdPreview)return new Promise(resolve=>{finishPreview=()=>resolve(response);});
        return response;
      }
      publishRoots(["JOB-002"]);
      if(operation==="submit"&&options.loseReply)throw Error("INERT_LOST_ORIGINAL_RESPONSE");
      return executionResult(operation,{operation_key:request.operation_key,work_ref:workRef,state:"ACCEPTED",
        receipt:{schema:"mastermind.ceo_intent_receipt.v2",
          intent_id:intentIdForOperationKey(String(request.operation_key)),fingerprint:"f".repeat(64),
          job_id:"JOB-002",status:"QUEUED",accepted:true,dispatched:false,duplicate:operation==="status",
          authority:{requested:["READ","RESEARCH"],policy_sha256:"a".repeat(64),authority_level:"A0"},
          grounding:{},created_at_ms:0}});
    }
    throw Error("INERT_SOURCE_NOT_SUPPLIED:"+command);
  });
  const client=await createNativeClient(invoke as never,async(name,listener)=>{
    const listeners=events.get(name)??new Set();listeners.add(listener);events.set(name,listeners);
    return()=>{listeners.delete(listener);};
  });
  const {executive:_executive,...withoutExecutive}=client;
  const legacy=options.legacyManifest?{workstream:workRef,priority:0,attemptLimit:1,
    projects:[{ref:"executive-infrastructure",label:"Fixture legacy project"}],
    profiles:[{ref:"research_only",label:"Fixture legacy research"}]}:null;
  const composition=composeMissionHost(options.omitExecutive?withoutExecutive:client,legacy,database,"native");
  disposals.push(composition.dispose);await composition.ready;await composition.sessionReady;
  let finishOperationDiscovery:(()=>void)|undefined;
  if(options.holdOperationDiscovery){
    const store=composition.host.commandBinding!.store;
    const read=store.read.bind(store);
    const pending=new Promise<void>(resolve=>{finishOperationDiscovery=resolve;});
    // Delay delivery of the actual IndexedDB result, keeping the same store
    // and its source read. A visible project goal does not settle this owner.
    vi.spyOn(store,"read").mockImplementation(async(principalScope,signal)=>{
      const value=await read(principalScope,signal);await pending;return value;
    });
    disposals.push(()=>finishOperationDiscovery?.());
  }
  window.MastermindMissionHost=composition.host;
  const view=render(<App/>);
  const executionCalls=(operation:string)=>invoke.mock.calls.filter(([command,args])=>
    command==="executive_project_execution"&&args?.operation===operation);
  const freshCalls=(operation:string)=>invoke.mock.calls.filter(([command,args])=>
    command==="executive_fresh_conversation"&&args?.operation===operation);
  return {composition,client,invoke,events,view,executionCalls,freshCalls,database,
    releasePreview:()=>finishPreview?.(),
    releaseOperationDiscovery:()=>finishOperationDiscovery?.(),
    withdrawExecutive:()=>events.get("mastermind-executive-auth-state")?.forEach(listener=>
      listener({payload:{generation:2,available:false}}))};
}
async function openProject(){
  fireEvent.click(screen.getByRole("button",{name:"Projects"}));
  fireEvent.click(await screen.findByRole("button",{name:"Open project Manifest-free project"}));
  await screen.findByText(goal);
}

it("starts current-project work through actual manifest-free composition and the original preview/submit owner",async()=>{
  const f=await setup();await openProject();
  const start=screen.getByRole("button",{name:"Start work"});
  await waitFor(()=>expect(start).toHaveProperty("disabled",false));
  fireEvent.click(start);
  expect((await screen.findByLabelText("Goal") as HTMLTextAreaElement).value).toBe(goal);
  fireEvent.change(screen.getByLabelText("Goal"),{target:{value:"Implement this exact project request."}});
  fireEvent.change(screen.getByLabelText("Handoff (optional)"),{target:{value:"Preserve the accepted handoff conditions."}});
  const launch=screen.getByRole("button",{name:"Launch"});
  fireEvent.click(launch);fireEvent.click(launch);
  await waitFor(()=>expect(f.executionCalls("submit")).toHaveLength(1));
  expect(f.executionCalls("preview")).toHaveLength(1);
  expect(f.executionCalls("submit")[0][1]!.arguments).toMatchObject({
    work_ref:workRef,objective:"Implement this exact project request.",
    handoff_text:"Preserve the accepted handoff conditions.",execution_profile:"research_only",
    execution_binding_sha256:"d".repeat(64),continuation_mode:"DURABLE",
  });
  const binding=f.composition.host.commandBinding!;
  expect(binding.getView()).toEqual({projects:[],profiles:[],session:null});
  expect(binding.makeLaunchIntent({goal:"Invented legacy launch",projectRef:"executive-infrastructure",profileRef:"research_only"})).toBeNull();
  await waitFor(async()=>expect(await binding.store.read(scope)).toBeNull());
  expect(f.invoke.mock.calls.filter(([name])=>name==="executive_submit")).toHaveLength(0);
});


it("continues the actual completed-result witness through manifest-free App composition despite multiple historical roots",async()=>{
  const f=await setup({completed:true});await openProject();
  const read=screen.getByRole("button",{name:"Read project runs"});
  await waitFor(()=>expect(read).toHaveProperty("disabled",false));fireEvent.click(read);
  fireEvent.click(await screen.findByRole("button",{name:"Open run"}));
  fireEvent.click(await screen.findByRole("button",{name:"Reply to project team"}));
  const message=await screen.findByLabelText("Follow-up message") as HTMLTextAreaElement;
  expect(message.value).toBe("");
  expect(f.executionCalls("preview")[0][1]!.arguments).toMatchObject({
    work_ref:workRef,previous_run:historyFixture.completed_read.parent_witness,
  });
  fireEvent.change(message,{target:{value:"Extend the retained result with this new request."}});
  fireEvent.click(screen.getByRole("button",{name:"Launch"}));
  await waitFor(()=>expect(f.executionCalls("submit")).toHaveLength(1));
  expect(f.executionCalls("submit")[0][1]!.arguments).toMatchObject({
    objective:"Extend the retained result with this new request.",
    previous_run:historyFixture.completed_read.parent_witness,
  });
  const reads=f.invoke.mock.calls.filter(([name,args])=>
    name==="executive_project_conversations_read"&&args?.operation==="execution_read");
  expect(reads).toHaveLength(1);
  expect(reads[0][1]!.arguments).toEqual(historyFixture.completed_read.reference);
  expect(f.invoke.mock.calls.filter(([name])=>name==="executive_submit")).toHaveLength(0);
});

async function editFreshMessage(selectedWork=workRef){
  fireEvent.click(within(document.querySelector("#workspace-navigation") as HTMLElement)
    .getByRole("button",{name:"New conversation"}));
  const project=await screen.findByRole("combobox",{name:"Project"});
  await waitFor(()=>expect(project).toHaveProperty("disabled",false));
  fireEvent.change(project,{target:{value:selectedWork}});
  vi.spyOn(crypto,'getRandomValues').mockImplementation(value=>{for(let i=0;i<20;i++)(value as Uint8Array)[i]=0xaa;return value;});
  fireEvent.change(screen.getByRole("textbox",{name:"First message"}),
    {target:{value:freshFixture.request.message}});
}

it("global New conversation uses the shared manifest-free owner and exact original fresh preview/create",async()=>{
  const f=await setup({nativeFresh:true});await editFreshMessage(freshFixture.request.work_ref);
  const workRef=freshFixture.request.work_ref;
  const review=screen.getByRole("button",{name:"Review conversation"});
  await waitFor(()=>expect(review).toHaveProperty("disabled",false));fireEvent.click(review);
  const create=await screen.findByRole("button",{name:"Create conversation"});
  expect(f.freshCalls("preview")).toHaveLength(1);expect(f.freshCalls("create")).toHaveLength(0);
  const preview=f.freshCalls("preview")[0][1]!.arguments as Record<string,unknown>;
  expect(preview).toEqual({work_ref:workRef,message:freshFixture.request.message,
    operation_key:expect.stringMatching(/^mmos-native-create-[0-9a-f]{40}$/)});
  await waitFor(()=>expect(create).toHaveProperty("disabled",false));
  fireEvent.click(create);fireEvent.click(create);
  const open=await screen.findByRole("button",{name:"Open initial response"});
  expect(f.freshCalls("read")).toHaveLength(1);
  expect(f.freshCalls("read")[0][1]!.arguments).toEqual({
    work_ref:workRef,operation_key:preview.operation_key,
  });
  fireEvent.click(open);
  const record=await screen.findByRole('region',{name:'Recorded conversation'});
  const recorded=within(record).getByRole('button',{name:'Read recorded conversation'});
  await waitFor(()=>expect(recorded).toHaveProperty('disabled',false));
  fireEvent.click(recorded);
  const reply=await within(record).findByRole('button',{name:'Read reply'});
  await waitFor(()=>expect(reply).toHaveProperty('disabled',false));
  fireEvent.click(reply);
  // Markdown omits its final paragraph newline; the content owner still checks
  // the exact source digest and every original fragment at the transport seam.
  expect(freshFixture.answer.endsWith('\n')).toBe(true);
  await waitFor(()=>{
    expect(record.querySelector('.source-markdown')?.textContent).toBe(freshFixture.answer.slice(0,-1));
  },{container:record,timeout:5_000});
  expect(f.invoke.mock.calls.filter(([name,args])=>name==='executive_project_conversations_read'&&
    args?.operation==='fresh_read'&&(args.arguments as any)?.content)).toHaveLength(freshFixture.fragments.length);
  expect(f.freshCalls("create")).toHaveLength(1);
  expect(f.freshCalls("create")[0][1]!.arguments).toEqual({
    ...preview,preview_digest:freshFixture.preview.data.preview.digest,
  });
  expect(f.executionCalls("submit")).toHaveLength(0);
  expect(f.invoke.mock.calls.filter(([name])=>name==="executive_submit")).toHaveLength(0);
});

it.each(["absent Executive","signed out"] as const)(
  "keeps manifest-free entries effect-free when %s",async(boundary)=>{
    const f=await setup(boundary==="absent Executive"?{omitExecutive:true}:{signedOut:true});
    if(boundary==="absent Executive"){
      await openProject();fireEvent.click(screen.getByRole("button",{name:"Start work"}));
      expect(f.composition.host.commandBinding).toBeUndefined();
      const fresh=within(document.querySelector("#workspace-navigation") as HTMLElement)
        .getByRole("button",{name:"New conversation"});
      fireEvent.click(fresh);
    }else{
      expect(f.composition.host.commandBinding?.port.context()).toBeNull();
      expect(document.querySelector("#workspace-navigation")).toBeNull();
      expect(screen.queryByRole("button",{name:"New conversation"})).toBeNull();
    }
    await act(async()=>{});
    expect(f.invoke.mock.calls.filter(([name])=>name==="executive_context")).toHaveLength(0);
    expect(f.executionCalls("preview")).toHaveLength(0);
    expect(f.executionCalls("submit")).toHaveLength(0);
    expect(f.freshCalls("preview")).toHaveLength(0);
    expect(f.freshCalls("create")).toHaveLength(0);
    expect(f.invoke.mock.calls.filter(([name])=>name==="executive_submit")).toHaveLength(0);
  });

it("withdraws the original Executive owner while a manifest-free project preview waits without reserving or submitting",async()=>{
  const f=await setup({holdPreview:true,holdOperationDiscovery:true});await openProject();
  const start=screen.getByRole("button",{name:"Start work"});
  const binding=f.composition.host.commandBinding!;
  const reserve=vi.spyOn(binding.store,"reserve");
  expect(screen.getByText("Checking previous work…")).toBeTruthy();
  expect(start).toHaveProperty("disabled",true);
  fireEvent.click(start);
  expect(f.executionCalls("preview")).toHaveLength(0);
  expect(reserve).not.toHaveBeenCalled();
  await act(async()=>{f.releaseOperationDiscovery();});
  await waitFor(()=>expect(start).toHaveProperty("disabled",false));
  fireEvent.click(start);
  await waitFor(()=>expect(f.executionCalls("preview")).toHaveLength(1));
  await act(async()=>{f.withdrawExecutive();f.releasePreview();});
  expect(binding.port.context()).toBeNull();
  expect(screen.queryByLabelText("Goal")).toBeNull();
  expect(f.executionCalls("preview")).toHaveLength(1);
  expect(f.executionCalls("submit")).toHaveLength(0);
  expect(reserve).not.toHaveBeenCalled();
  expect(await binding.store.read(scope)).toBeNull();
  expect(f.invoke.mock.calls.filter(([name])=>name==="executive_submit")).toHaveLength(0);
});

it("reopens the original project pointer after its legacy manifest disappears and checks status without another creation",async()=>{
  const database=new IDBFactory();
  const first=await setup({legacyManifest:true,loseReply:true},database);await openProject();
  const start=screen.getByRole("button",{name:"Start work"});
  await waitFor(()=>expect(start).toHaveProperty("disabled",false));
  fireEvent.click(start);
  await screen.findByLabelText("Handoff (optional)");
  await waitFor(()=>expect(screen.getByRole("button",{name:"Launch"})).toHaveProperty("disabled",false));
  fireEvent.click(screen.getByRole("button",{name:"Launch"}));
  await waitFor(()=>expect(first.executionCalls("submit")).toHaveLength(1));
  await screen.findByRole("button",{name:"Check status"});
  const original=await first.composition.host.commandBinding!.store.read(scope);
  expect(original).toEqual({kind:"launch",targetKey:workRef,
    operationKey:expect.stringMatching(/^mmos-project-execute-[0-9a-f]{40}$/)});
  first.view.unmount();first.composition.dispose();
  history.replaceState(null,"","/os/");
  const reopened=await setup({},database);
  await screen.findByRole("button",{name:"Check status"});
  expect(reopened.composition.host.commandBinding!.getView().projects).toEqual([]);
  fireEvent.click(within(document.querySelector("#workspace-navigation") as HTMLElement)
    .getByRole("button",{name:"New conversation"}));
  await screen.findByText("Another request needs its existing status controls before a new conversation can be created.");
  expect(screen.queryByRole("button",{name:"Review conversation"})).toBeNull();
  expect(screen.queryByRole("button",{name:"Create conversation"})).toBeNull();
  expect(await reopened.composition.host.commandBinding!.store.read(scope)).toEqual(original);
  fireEvent.click(screen.getByRole("button",{name:"Check status"}));
  await waitFor(async()=>expect(await reopened.composition.host.commandBinding!.store.read(scope)).toBeNull());
  expect(first.executionCalls("submit")).toHaveLength(1);
  expect(reopened.executionCalls("preview")).toHaveLength(0);
  expect(reopened.executionCalls("submit")).toHaveLength(0);
  expect(reopened.executionCalls("status")).toHaveLength(1);
  expect(reopened.executionCalls("status")[0][1]!.arguments).toEqual({
    work_ref:workRef,operation_key:original!.operationKey,
  });
  expect(reopened.freshCalls("preview")).toHaveLength(0);
  expect(reopened.freshCalls("create")).toHaveLength(0);
  expect(reopened.invoke.mock.calls.filter(([name])=>name==="executive_submit")).toHaveLength(0);
});
