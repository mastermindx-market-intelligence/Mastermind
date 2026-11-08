// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {App} from "./App";
import {bindMissionHost,createNativeClient,type AuthState} from "./host";
import {canNavigateForAutomaticSignIn} from "./auth-navigation-guard";
import {controlRoomFixture,missionFixture} from "./test-fixtures";
import programs from "./fixtures/programs-available-workspace-service.json";
import plan from "./fixtures/project-plan-canonical-owner.json";
import work from "./fixtures/work-service-available.json";
import {attachProjectExecution} from "./planning/project-execution-command-port";
import type {ProjectExecutionOperation} from "./planning/project-execution-transport";
import {intentIdForOperationKey} from "./orchestration/operation-key";
import type {OrchestratorCommandBinding} from "./orchestration/host-command-bindings";
import type {OperationPointer,PendingPointerStore} from "./orchestration/operation-controller";

vi.mock("@tauri-apps/api/core",()=>({isTauri:()=>false,invoke:vi.fn().mockResolvedValue({
  version:"0.1.0",source_revision:"a".repeat(40),build_identity:"fixture",transport:"UNCONFIGURED",state:"BUILT_NOT_PROVEN"})}));
const signed:AuthState={status:"signed_in",reason:null,acquisition:true,content:true};
const preview={schema:"mastermind.project_execution_preview.v1",work_ref:"WS:ONE",
  context_sha256:"c".repeat(64),execution_binding_sha256:"d".repeat(64),execution_state:"WORK_CAPABLE",
  execution_profile_bindings:{research_only:"d".repeat(64),bounded_code_change:"e".repeat(64)},
  continuation_mode:"DURABLE",coordinator:{provider:"codex",model:"installed-model",effort:"high"},
  execution_scope:{repository:"mastermindx-market-intelligence/Mastermind",commit:"e".repeat(40)},
  binding:{workstream:"WS:ONE",priority:0,attemptLimit:1,
    projects:[{ref:"executive-infrastructure",label:"Project team"}],
    profiles:[{ref:"research_only",label:"Research team"},{ref:"bounded_code_change",label:"Build in declared paths"}]}};
function envelope(operation:ProjectExecutionOperation,data:unknown){
  return {schema:"mastermind.project_execution_private_result.v1",operation,ok:true,data,error:null};
}
beforeEach(async()=>{
  history.replaceState(null,"","/os/");delete window.MastermindMissionHost;delete (window as any).__TAURI_INTERNALS__;
  vi.stubEnv("VITE_MM_LAUNCH_CONFIG","");
  const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>("node:crypto");vi.stubGlobal("crypto",webcrypto);
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();vi.unstubAllEnvs();delete window.MastermindMissionHost;});

async function setup(options:{holdPreview?:boolean;loseReply?:boolean}={}){
  const room=controlRoomFixture();room.work=[room.work[0]];room.work[0].work_ref="WS:ONE";room.autonomy.responsibilities=[];
  const invoke=vi.fn(async(command:string)=>{
    if(command==="auth_status")return signed;
    if(command==="read_programs")return {...structuredClone(programs),control_room:room};
    if(command==="read_work")return structuredClone(work);
    if(command==="read_project_plan")return structuredClone(plan);
    throw Error("Unexpected fixture read");
  });
  let notify!:(event:{payload:unknown})=>void;
  const client=await createNativeClient(invoke as never,async(_name,listener)=>{notify=listener;return()=>{};});
  let principalScope="a".repeat(64),ownerGeneration=1;
  const host=bindMissionHost(client);
  const saved=new Map<string,OperationPointer>();
  const store:PendingPointerStore={
    read:scope=>saved.get(scope)??null,
    reserve:(scope,pointer)=>saved.has(scope)?{reserved:false,pointer:saved.get(scope)!}:(saved.set(scope,pointer),{reserved:true}),
    clearIfEqual:(scope,pointer)=>saved.get(scope)?.operationKey===pointer.operationKey?saved.delete(scope):false,
  };
  const legacy=vi.fn(()=>{throw Error("Dynamic project must not use a static launch");});
  const base:OrchestratorCommandBinding={store,port:{context:()=>client.getState().status==="signed_in"?{principalScope,generation:String(ownerGeneration)}:null,
    prepare:legacy,submit:legacy,readOperation:legacy},
    getView:()=>({projects:[],profiles:[],session:null}),subscribe:()=>()=>{},
    makeLaunchIntent:()=>null,makeMessageIntent:()=>null,makeStopIntent:()=>null};
  let finishPreview!:(value:unknown)=>void, generation=0;
  const request=vi.fn(async(operation:ProjectExecutionOperation,args:Readonly<Record<string,unknown>>):Promise<unknown>=>{
    if(operation==="preview")return options.holdPreview ? new Promise(resolve=>{finishPreview=resolve;}) : envelope(operation,preview);
    // Admission publishes the exact root through the existing Programs owner.
    // Keeping this catalogue rootless after success would correctly refuse a Mission read.
    const responsibility=controlRoomFixture().autonomy.responsibilities[0];
    responsibility.responsibility_ref="WS:ONE";responsibility.root_job_id="JOB-NEW";
    responsibility.root_job_candidates=["JOB-NEW"];
    responsibility.dispatch.responsibility_ref="WS:ONE";responsibility.dispatch.root_job_id="JOB-NEW";
    responsibility.dispatch.evidence.responsibility_ref="WS:ONE";responsibility.dispatch.evidence.root_job_id="JOB-NEW";
    room.autonomy.responsibilities=[responsibility];
    room.work[0].executive.jobs[0].workstream="WS:ONE";room.work[0].executive.jobs[0].job_id="JOB-NEW";
    if(operation==="submit" && options.loseReply)throw Error("Lost original response");
    return envelope(operation,{operation_key:args.operation_key,work_ref:args.work_ref,state:"ACCEPTED",
      receipt:{schema:"mastermind.ceo_intent_receipt.v2",intent_id:intentIdForOperationKey(String(args.operation_key)),
        fingerprint:"f".repeat(64),job_id:"JOB-NEW",status:"QUEUED",accepted:true,dispatched:false,duplicate:operation==="status",
        authority:{requested:["READ","RESEARCH"],policy_sha256:"a".repeat(64),authority_level:"A0"},grounding:{},created_at_ms:0}});
  });
  const readMission=vi.fn(async({workRef,rootJobId}:{workRef:string;rootJobId:string})=>missionFixture(workRef,rootJobId));
  window.MastermindMissionHost={...host,readMissionV3:undefined,readMission,commandBinding:attachProjectExecution(base,{request}),
    invalidationGeneration:()=>generation+client.invalidationGeneration()};
  const view=render(<App/>);
  fireEvent.click(screen.getByRole("button",{name:"Projects"}));
  fireEvent.click(await screen.findByRole("button",{name:"Open project Alpha program"}));
  await screen.findByText("Deliver the real owner content.");
  return {view,request,saved,readMission,legacy,bump:()=>{generation++;},
    publishAuth:(state:AuthState,scope=principalScope)=>{principalScope=scope;ownerGeneration++;notify({payload:state});},
    rebind:()=>{window.MastermindMissionHost!.commandBinding=attachProjectExecution(base,{request});},
    finishPreview:()=>finishPreview(envelope("preview",preview))};
}

it("starts a rootless project through live preview, handoff and one existing launch owner",async()=>{
  const f=await setup();
  fireEvent.click(screen.getByRole("button",{name:"Start work"}));
  const goal=await screen.findByLabelText("Goal");
  expect((goal as HTMLTextAreaElement).value).toBe("Deliver the real owner content.");
  fireEvent.change(screen.getByLabelText("Handoff (optional)"),{target:{value:"Keep the prior acceptance conditions."}});
  expect(screen.getByText(/team continues in the background/)).toBeTruthy();
  expect(screen.getByText("mastermindx-market-intelligence/Mastermind")).toBeTruthy();
  expect(screen.getByText("e".repeat(40))).toBeTruthy();
  const launch=screen.getByRole("button",{name:"Launch"});
  fireEvent.click(launch);fireEvent.click(launch);
  await waitFor(()=>expect(f.request.mock.calls.filter(c=>c[0]==="submit")).toHaveLength(1));
  expect(f.request.mock.calls.find(c=>c[0]==="submit")![1]).toMatchObject({
    work_ref:"WS:ONE",handoff_text:"Keep the prior acceptance conditions.",continuation_mode:"DURABLE"});
  await waitFor(()=>expect(f.readMission).toHaveBeenCalledWith(expect.objectContaining({workRef:"WS:ONE",rootJobId:"JOB-NEW"})));
  expect(f.saved.size).toBe(0);expect(f.legacy).not.toHaveBeenCalled();
});

it("keeps the original operation after a lost launch response and checks status without another team",async()=>{
  const f=await setup({loseReply:true});
  fireEvent.click(screen.getByRole("button",{name:"Start work"}));await screen.findByLabelText("Goal");
  fireEvent.click(screen.getByRole("button",{name:"Launch"}));
  const check=await screen.findByRole("button",{name:"Check status"});
  expect(f.saved.size).toBe(1);
  fireEvent.click(check);
  await waitFor(()=>expect(f.request.mock.calls.filter(c=>c[0]==="status")).toHaveLength(1));
  await waitFor(()=>expect(f.saved.size).toBe(0));
  expect(f.request.mock.calls.filter(c=>c[0]==="submit")).toHaveLength(1);
});

it("discards a preview when its current project acquisition changes",async()=>{
  const f=await setup({holdPreview:true});
  fireEvent.click(screen.getByRole("button",{name:"Start work"}));
  await waitFor(()=>expect(f.request).toHaveBeenCalledTimes(1));
  f.bump();await act(async()=>f.finishPreview());
  expect(screen.queryByRole("button",{name:"Launch"})).toBeNull();
  expect(f.saved.size).toBe(0);
  expect(f.request.mock.calls.some(c=>c[0]==="submit")).toBe(false);
});

const draftDetails={criteria:"First proof\nSecond proof",handoff:"Retain these acceptance conditions.",paths:"app/source.ts\nREADME.md",tests:"tests/test_source.py"};
async function editCodeDraft(){
  fireEvent.click(screen.getByRole("button",{name:"Start work"}));
  await screen.findByLabelText("Goal");
  fireEvent.change(screen.getByLabelText("Goal"),{target:{value:"My edited project goal."}});
  fireEvent.change(screen.getByLabelText("Handoff (optional)"),{target:{value:draftDetails.handoff}});
  fireEvent.change(screen.getByLabelText(/Acceptance criteria/),{target:{value:draftDetails.criteria}});
  fireEvent.change(screen.getByLabelText("Profile"),{target:{value:"bounded_code_change"}});
  fireEvent.change(screen.getByLabelText("Paths to change"),{target:{value:draftDetails.paths}});
  fireEvent.change(screen.getByLabelText("Pytest targets (optional)"),{target:{value:draftDetails.tests}});
  fireEvent.click(screen.getByRole("checkbox",{name:"Check the diff for whitespace errors"}));
}
function expectDraftDetails(){
  expect((screen.getByLabelText(/Acceptance criteria/) as HTMLTextAreaElement).value).toBe(draftDetails.criteria);
  expect((screen.getByLabelText("Handoff (optional)") as HTMLTextAreaElement).value).toBe(draftDetails.handoff);
  expect((screen.getByLabelText("Paths to change") as HTMLTextAreaElement).value).toBe(draftDetails.paths);
  expect((screen.getByLabelText("Pytest targets (optional)") as HTMLTextAreaElement).value).toBe(draftDetails.tests);
  expect((screen.getByRole("checkbox",{name:"Check the diff for whitespace errors"}) as HTMLInputElement).checked).toBe(false);
}

it("retains edited handoff and build scope across navigation and requalifies the same draft before launch",async()=>{
  const f=await setup();await editCodeDraft();
  fireEvent.click(screen.getByRole("button",{name:"Meta-CEO"}));
  fireEvent.click(screen.getByRole("button",{name:"Projects"}));
  fireEvent.click(await screen.findByRole("button",{name:"Open project Alpha program"}));
  await screen.findByLabelText("Goal");
  expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe("My edited project goal.");
  expect((screen.getByLabelText("Profile") as HTMLSelectElement).value).toBe("bounded_code_change");
  expectDraftDetails();
  // The old acquisition cannot authorize a submission after its plan reader unmounts.
  fireEvent.click(screen.getByRole("button",{name:"Launch"}));
  expect(f.request.mock.calls.filter(c=>c[0]==="submit")).toHaveLength(0);
  await screen.findByText(/The project plan is no longer current/);
  fireEvent.click(screen.getByRole("button",{name:"Start work"}));
  await waitFor(()=>expect(f.request.mock.calls.filter(c=>c[0]==="preview")).toHaveLength(2));
  expectDraftDetails();
  fireEvent.click(screen.getByRole("button",{name:"Launch"}));
  await waitFor(()=>expect(f.request.mock.calls.filter(c=>c[0]==="submit")).toHaveLength(1));
  expect(f.request.mock.calls.find(c=>c[0]==="submit")![1]).toMatchObject({
    objective:'My edited project goal. [MASTERMIND_ACCEPTANCE_CRITERIA_V1:["First proof","Second proof"]]',handoff_text:draftDetails.handoff,execution_profile:"bounded_code_change",
    execution_binding_sha256:"e".repeat(64),
    allowed_write_paths:["app/source.ts","README.md"],validation:{pytest_targets:[draftDetails.tests],git_diff_check:false},
  });
});

it.each(["logout","new principal","discard"] as const)("protects a handoff-only draft through passive expiry and clears it on %s",async(boundary)=>{
  const f=await setup();await editCodeDraft();
  fireEvent.change(screen.getByLabelText("Goal"),{target:{value:""}});
  await act(async()=>f.publishAuth({status:"signed_out",reason:"TOKEN_EXPIRED",acquisition:false,content:false}));
  expectDraftDetails();
  expect(canNavigateForAutomaticSignIn()).toBe(false);
  expect(screen.queryByRole("button",{name:"Launch"})).toBeNull();
  expect(f.request.mock.calls.filter(c=>c[0]!=="preview")).toHaveLength(0);
  if(boundary==="discard"){
    fireEvent.click(screen.getByRole("button",{name:"Discard goal"}));
  }else{
    await act(async()=>f.publishAuth(boundary==="logout"
      ?{status:"signed_out",reason:"USER_SIGNED_OUT",acquisition:false,content:false}
      :signed,"b".repeat(64)));
  }
  expect(screen.queryByLabelText("Handoff (optional)")).toBeNull();
  expect(screen.queryByDisplayValue(draftDetails.handoff)).toBeNull();
  expect(screen.queryByDisplayValue(draftDetails.paths)).toBeNull();
  expect(screen.queryByDisplayValue(draftDetails.criteria)).toBeNull();
  expect(f.request.mock.calls.filter(c=>c[0]!=="preview")).toHaveLength(0);
});

it("reopens the original launch pointer in a fresh page owner without submitting another team",async()=>{
  const f=await setup({loseReply:true});
  fireEvent.click(screen.getByRole("button",{name:"Start work"}));await screen.findByLabelText("Goal");
  fireEvent.click(screen.getByRole("button",{name:"Launch"}));await screen.findByRole("button",{name:"Check status"});
  const original=f.saved.values().next().value!;
  f.view.unmount();f.rebind();render(<App/>);
  fireEvent.click(await screen.findByRole("button",{name:"Check status"}));
  await waitFor(()=>expect(f.saved.size).toBe(0));
  expect(f.request.mock.calls.filter(c=>c[0]==="submit")).toHaveLength(1);
  expect(f.request.mock.calls.filter(c=>c[0]==="status")).toHaveLength(1);
  expect(f.request).toHaveBeenCalledWith("status",{
    operation_key:original.operationKey,work_ref:"WS:ONE",
  },expect.any(AbortSignal));
  await waitFor(()=>expect(window.location.search).toBe("?work_ref=WS%3AONE&root_job_id=JOB-NEW"));
});

it("consumes accepted project details so the next launch starts with an empty handoff",async()=>{
  const f=await setup();await editCodeDraft();
  fireEvent.click(screen.getByRole("button",{name:"Launch"}));
  await waitFor(()=>expect(f.readMission).toHaveBeenCalled());
  await waitFor(()=>expect((screen.getByRole("button",{name:"Start work"}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"Start work"}));
  await screen.findByLabelText("Handoff (optional)");
  expect((screen.getByLabelText("Handoff (optional)") as HTMLTextAreaElement).value).toBe("");
  expect((screen.getByLabelText(/Acceptance criteria/) as HTMLTextAreaElement).value).toBe("");
  expect((screen.getByLabelText("Profile") as HTMLSelectElement).value).toBe("research_only");
  expect(screen.queryByLabelText("Paths to change")).toBeNull();
  expect(f.request.mock.calls.filter(c=>c[0]==="submit")).toHaveLength(1);
});
