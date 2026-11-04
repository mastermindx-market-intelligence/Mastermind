// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import knowledgeCss from "./knowledge/knowledge.css?raw";
import { bindMissionHost, createNativeClient } from "./host";
import { controlRoomFixture } from "./test-fixtures";
import { decodeResultEnvelope } from "./result";
import { decodeResultReferencesEnvelope } from "./result-references";
import { decodeWindow, observedMissionAssociation } from "./workspace-contract";
import { decodeMissionv3 } from "./mission";
import programs from "./fixtures/programs-available-workspace-service.json";
import paired from "./fixtures/window-mission-association-producer.json";
import resultFixture from "./fixtures/result-design-available-reject-unicode.json";
import work from "./fixtures/work-service-available.json";

let style: HTMLStyleElement;
const signed = {status:"signed_in",reason:null,acquisition:true,content:true};
const question = "Keep this original App-owned question.";
async function fixture(holdResult = false) {
  const selected = {workRef:paired.selection.work_ref,rootJobId:paired.selection.root_job_id};
  const room = controlRoomFixture(); room.work = [room.work[0]];
  room.autonomy.responsibilities = [room.autonomy.responsibilities[0]];
  room.work[0].work_ref = selected.workRef;
  Object.assign(room.autonomy.responsibilities[0], {responsibility_ref:selected.workRef,
    root_job_id:selected.rootJobId,root_job_candidates:[selected.rootJobId],root_job_ambiguous:false,runtime_root_state:"RESOLVED"});
  const result = structuredClone(resultFixture);
  Object.assign(result.selection,{work_ref:selected.workRef,root_job_id:selected.rootJobId});
  result.result.selection.root_job_id = selected.rootJobId;
  result.source_observation.selection = {...result.selection};
  const exact = {...selected,jobId:result.selection.job_id,attemptId:result.selection.attempt_id,
    resultEnvelopeDigest:result.selection.result_envelope_digest};
  expect(decodeResultEnvelope(result,exact)).not.toBeNull();
  const window = await decodeWindow(structuredClone(paired.window));
  const mission = decodeMissionv3(structuredClone(paired.mission),selected);
  const association = observedMissionAssociation(window,mission,selected);
  expect(association).not.toBeNull();
  expect(association!.job_id).not.toBe(exact.jobId);
  const list = {schema:"mastermind.workspace_result_references.v1",selection:{work_ref:selected.workRef,root_job_id:selected.rootJobId},
    availability:"AVAILABLE",reason_codes:[],index:{schema:"mastermind.fabric_result_reference_index.v1",root_job_id:selected.rootJobId,
      snapshot_digest:"b".repeat(64),generation:result.result.generation,availability:"AVAILABLE",
      refs:[{...result.result.selection,orchestration_role:result.result.role,validation:"UNVALIDATED"}],
      absent_job_ids:[selected.rootJobId],omitted_job_ids:[],truncated:false},
    source_observation:{...result.source_observation,schema:"mastermind.workspace_source_observation.v1",
      selection:{work_ref:selected.workRef,root_job_id:selected.rootJobId}},
    catalogue:{generated_at:"2026-10-31T15:45:00Z",freshness:"CURRENT"}};
  expect(decodeResultReferencesEnvelope(list,selected)).not.toBeNull();
  let notify!: (event:{payload:unknown})=>void, settle!:()=>void;
  const pending = new Promise<unknown>(resolve=>{settle=()=>resolve(structuredClone(result));});
  const invoke = vi.fn(async (command:string) => {
    if(command==="auth_status")return signed;
    if(command==="read_programs")return {...structuredClone(programs),control_room:room};
    if(command==="read_mission_v3")return structuredClone(paired.mission);
    if(command==="read_work")return structuredClone(work);
    if(command==="read_current_window")return structuredClone(paired.window);
    if(command==="read_result_references")return structuredClone(list);
    if(command==="read_result")return holdResult?pending:structuredClone(result);
    throw new Error("Unexpected fixture command");
  });
  const client = await createNativeClient(invoke as never,async (_event,listener)=>{notify=listener;return()=>{};});
  const host = bindMissionHost(client), read = vi.spyOn(host,"readResult");
  return {host,read,invoke,notify,settle,exact,result,room};
}
async function start(f:Awaited<ReturnType<typeof fixture>>) {
  window.MastermindMissionHost=f.host;render(<App/>);
  fireEvent.click(screen.getByRole("button",{name:"Conversations"}));
  await screen.findByText(paired.window.view.items.find(item=>item.text)!.text!);
  fireEvent.click(screen.getByRole("button",{name:"Unsent notes"}));
  fireEvent.change(screen.getByRole("textbox",{name:"Unsent notes"}),{target:{value:question}});
  fireEvent.click(screen.getByRole("button",{name:"Knowledge"}));
  fireEvent.click(await screen.findByRole("button",{name:"Show retained results"}));
  fireEvent.click(await screen.findByRole("button",{name:`Open retained result — ${f.exact.jobId}`}));
}
beforeEach(async()=>{
  style=document.createElement("style");style.textContent=knowledgeCss;document.head.append(style);
  history.replaceState(null,"",`/os/?work_ref=${encodeURIComponent(paired.selection.work_ref)}&root_job_id=${paired.selection.root_job_id}`);
  delete window.MastermindMissionHost;delete (window as any).__TAURI_INTERNALS__;
  const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>("node:crypto");vi.stubGlobal("crypto",webcrypto);
});
afterEach(()=>{cleanup();style.remove();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
it("joins a same-root cross-child source to the real current App draft and Undo without SEND",async()=>{
  const f=await fixture();await start(f);
  fireEvent.click(await screen.findByRole("button",{name:"Add excerpt to draft"}));
  expect(screen.getAllByRole("heading",{level:1})).toHaveLength(1);
  const companion=screen.getByRole("region",{name:"Original draft"});
  expect(companion.textContent).toContain(question);
  expect(companion.textContent).toContain(f.result.result.content.summary);
  expect(companion.textContent).toContain(f.exact.resultEnvelopeDigest);
  expect(companion.textContent).toContain("Added to draft · Not sent");
  fireEvent.click(screen.getByRole("button",{name:"Undo source insertion"}));
  expect(companion.textContent).toContain(question);
  expect(companion.querySelector("p.knowledge-muted")?.textContent).toBe(question);
  fireEvent.click(screen.getByRole("button",{name:"Conversations"}));
  fireEvent.click(await screen.findByRole("button",{name:"Unsent notes"}));
  expect(screen.getByRole<HTMLTextAreaElement>("textbox",{name:"Unsent notes"}).value).toBe(question);
  expect(f.read).toHaveBeenCalledExactlyOnceWith({...f.exact,signal:expect.any(AbortSignal)});
  expect(f.invoke.mock.calls.some(([command])=>/^(submit|send|launch|consume|open_|bind_|unbind_)/.test(command))).toBe(false);
});
it("clears the actual draft and aborts a source read before a new auth epoch can accept late content",async()=>{
  const f=await fixture(true);await start(f);
  await waitFor(()=>expect(f.read).toHaveBeenCalledTimes(1));
  const signal=f.read.mock.calls[0][0].signal;
  act(()=>f.notify({payload:signed}));
  expect(signal.aborted).toBe(true);
  await act(async()=>f.settle());
  expect(document.body.textContent).not.toContain(question);
  expect(screen.queryByRole("button",{name:"Add excerpt to draft"})).toBeNull();
  expect(screen.queryByRole("article",{name:"Retained result document"})).toBeNull();
});

it("invalidates the current source and draft when the actual selected work/root changes",async()=>{
  const f=await fixture(true);await start(f);
  await waitFor(()=>expect(f.read).toHaveBeenCalledTimes(1));
  const signal=f.read.mock.calls[0][0].signal;
  act(()=>{history.pushState(null,"","/os/?work_ref=WS%3AOTHER&root_job_id=JOB-OTHER");window.dispatchEvent(new PopStateEvent("popstate"));});
  expect(signal.aborted).toBe(true);
  await act(async()=>f.settle());
  expect(document.body.textContent).not.toContain(question);
  expect(screen.queryByRole("button",{name:"Add excerpt to draft"})).toBeNull();
  expect(screen.queryByRole("article",{name:"Retained result document"})).toBeNull();
});


it("opens the actual conversation as the project default and preserves its mounted draft across Details",async()=>{
  const f=await fixture();window.MastermindMissionHost=f.host;render(<App/>);
  fireEvent.click(screen.getByRole("button",{name:"Projects"}));
  const action = await screen.findByRole("button",{name:"Open project Alpha program"});
  action.focus();fireEvent.click(action);
  await screen.findByText(paired.window.view.items.find(item=>item.text)!.text!);
  expect(document.activeElement).toBe(screen.getByRole("heading",{name:"Alpha program",level:1}));
  fireEvent.click(screen.getByRole("button",{name:"Unsent notes"}));
  const draft=screen.getByRole("textbox",{name:"Unsent notes"});
  fireEvent.change(draft,{target:{value:question}});
  fireEvent.click(screen.getByRole("button",{name:"Project details"}));
  expect(screen.getByRole("textbox",{name:"Unsent notes"})).toBe(draft);
  expect(draft).toHaveProperty("value",question);
  fireEvent.click(screen.getByRole("button",{name:"Project details"}));
  expect(screen.getByRole("textbox",{name:"Unsent notes"})).toBe(draft);
  expect(draft).toHaveProperty("value",question);
  expect(f.invoke.mock.calls.some(([name])=>/submit|prepare|send/.test(name))).toBe(false);
});


it.each(["different-root","unknown","conflict"] as const)("does not activate a project conversation for a same-work %s catalogue",async mode=>{
  const f=await fixture();
  if(mode==="unknown")f.room.autonomy.responsibilities=[];
  if(mode==="conflict")Object.assign(f.room.autonomy.responsibilities[0],{
    runtime_root_state:"CONFLICT",root_job_id:null,root_job_candidates:[paired.selection.root_job_id,"JOB-OTHER"],root_job_ambiguous:true});
  window.MastermindMissionHost=f.host;render(<App/>);
  act(()=>{history.pushState(null,"",`/os/?work_ref=${encodeURIComponent(paired.selection.work_ref)}&root_job_id=${mode==="different-root"?"JOB-WRONG":paired.selection.root_job_id}`);window.dispatchEvent(new PopStateEvent("popstate"));});
  await screen.findByRole("heading",{name:"Alpha program",level:1});
  expect(f.invoke.mock.calls.filter(([name])=>name==="read_current_window")).toHaveLength(0);
  expect(screen.queryByText(paired.window.view.items.find(item=>item.text)!.text!)).toBeNull();
});
