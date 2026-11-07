// @vitest-environment jsdom
// Actual exported Runtime data + real App, read owner, command port and IndexedDB.
// Fixture transport responses are inert; this is not installed-runtime proof.
import {act,cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {IDBFactory} from "fake-indexeddb";
import {App} from "./App";
import {createProjectExecutionProofFixture,PROJECT_EXECUTION_PROOF_GOAL} from "./project-execution-proof-fixture";
import {createIndexedDbPendingPointerStore} from "./orchestration/indexeddb-pending-pointer-store";

beforeEach(async()=>{
  history.replaceState(null,"","/os/");delete window.MastermindMissionHost;delete (window as any).__TAURI_INTERNALS__;
  vi.stubEnv("VITE_MM_LAUNCH_CONFIG","");
  const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>("node:crypto");vi.stubGlobal("crypto",webcrypto);
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.unstubAllEnvs();delete window.MastermindMissionHost;});

async function setup(options:Parameters<typeof createProjectExecutionProofFixture>[1]={},database=new IDBFactory()){
  const fixture=await createProjectExecutionProofFixture(createIndexedDbPendingPointerStore(database),{multipleRoots:true,...options});
  window.MastermindMissionHost=fixture.host;
  const view=render(<App/>);
  fireEvent.click(screen.getByRole("button",{name:"Projects"}));
  fireEvent.click(await screen.findByRole("button",{name:"Open project Project team fixture"}));
  await screen.findByText(PROJECT_EXECUTION_PROOF_GOAL);
  return {...fixture,view};
}
async function readCompletedRun(){
  await waitFor(()=>expect((screen.getByRole("button",{name:"Read project runs"}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"Read project runs"}));
  fireEvent.click(await screen.findByRole("button",{name:"Open run"}));
  await screen.findByRole("button",{name:"Reply to project team"});
}
async function openFollowUp(){
  await readCompletedRun();
  fireEvent.click(screen.getByRole("button",{name:"Reply to project team"}));
  return await screen.findByLabelText("Follow-up message") as HTMLTextAreaElement;
}

it("continues an exact completed run with a new message despite multiple historical roots",async()=>{
  const f=await setup(),message=await openFollowUp();
  expect(message.value).toBe("");
  await waitFor(() => expect(document.activeElement).toBe(message));
  expect(f.requests.filter(x=>x.operation==="preview")[0].arguments.previous_run).toEqual(f.witness);
  fireEvent.change(message,{target:{value:"Add a final comparison to the accepted project result."}});
  const launch=screen.getByRole("button",{name:"Launch"});
  fireEvent.click(launch);fireEvent.click(launch);
  await waitFor(()=>expect(f.requests.filter(x=>x.operation==="submit")).toHaveLength(1));
  expect(f.requests.find(x=>x.operation==="submit")!.arguments).toMatchObject({
    work_ref:f.workRef,previous_run:f.witness,objective:"Add a final comparison to the accepted project result.",
  });
  await waitFor(async()=>expect(await f.store.read(f.scope)).toBeNull());
  expect(window.location.search).toContain("root_job_id=JOB-002");
});

it("withdraws a follow-up preview if its actual history acquisition changes while the request waits",async()=>{
  const f=await setup();await readCompletedRun();f.holdPreview(true);
  fireEvent.click(screen.getByRole("button",{name:"Reply to project team"}));
  await waitFor(()=>expect(f.requests.filter(x=>x.operation==="preview")).toHaveLength(1));
  await act(async()=>{f.invalidateHistory();f.releasePreviews();});
  expect(screen.queryByLabelText("Follow-up message")).toBeNull();
  expect(f.requests.filter(x=>x.operation==="submit")).toHaveLength(0);
  expect(await f.store.read(f.scope)).toBeNull();
});

it("preserves the user's follow-up but refuses a submit after the previous-result read becomes stale",async()=>{
  const f=await setup(),message=await openFollowUp();
  fireEvent.change(message,{target:{value:"Keep my exact next message."}});
  await act(async()=>f.invalidateHistory());
  fireEvent.click(screen.getByRole("button",{name:"Launch"}));
  await screen.findByText(/no longer current/);
  expect((screen.getByLabelText("Follow-up message") as HTMLTextAreaElement).value).toBe("Keep my exact next message.");
  expect(f.requests.filter(x=>x.operation==="submit")).toHaveLength(0);
  expect(await f.store.read(f.scope)).toBeNull();
});

it("cannot replace another unsent project goal or handoff when replying to a historical run",async()=>{
  const f=await setup();
  await waitFor(()=>expect((screen.getByRole("button",{name:"Start work"}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"Start work"}));
  await waitFor(()=>expect(screen.queryByLabelText("Goal"),document.body.textContent ?? "").not.toBeNull());
  fireEvent.change(screen.getByLabelText("Goal"),{target:{value:"My existing unsent work."}});
  fireEvent.change(screen.getByLabelText("Handoff (optional)"),{target:{value:"Preserve this handoff too."}});
  await readCompletedRun();fireEvent.click(screen.getByRole("button",{name:"Reply to project team"}));
  await screen.findByText(/Finish or cancel that draft first/);
  expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe("My existing unsent work.");
  expect((screen.getByLabelText("Handoff (optional)") as HTMLTextAreaElement).value).toBe("Preserve this handoff too.");
  expect(screen.queryByLabelText("Follow-up message")).toBeNull();
  expect(f.requests.filter(x=>x.operation==="preview")).toHaveLength(1);
  expect(f.requests.filter(x=>x.operation==="submit")).toHaveLength(0);
});

it("requalifies the same completed-run witness without replacing the edited follow-up message",async()=>{
  const f=await setup(),message=await openFollowUp();
  fireEvent.change(message,{target:{value:"Retain this revised follow-up."}});
  fireEvent.click(screen.getByRole("button",{name:"Back to project runs"}));
  fireEvent.click(await screen.findByRole("button",{name:"Open run"}));
  fireEvent.click(await screen.findByRole("button",{name:"Reply to project team"}));
  await waitFor(()=>expect(f.requests.filter(x=>x.operation==="preview")).toHaveLength(2));
  await waitFor(()=>expect((screen.getByRole("button",{name:"Reply to project team"}) as HTMLButtonElement).disabled).toBe(false));
  expect((screen.getByLabelText("Follow-up message") as HTMLTextAreaElement).value).toBe("Retain this revised follow-up.");
  fireEvent.click(screen.getByRole("button",{name:"Launch"}));
  await waitFor(()=>expect(f.requests.filter(x=>x.operation==="submit")).toHaveLength(1));
});


it("recovers a browser-reopened project execution using only its original real IndexedDB pointer",async()=>{
  const database=new IDBFactory();
  const first=await setup({history:"empty",mode:"lost_reply"},database);
  await waitFor(()=>expect((screen.getByRole("button",{name:"Start work"}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"Start work"}));
  await waitFor(()=>expect(screen.queryByLabelText("Goal"),document.body.textContent ?? "").not.toBeNull());
  await waitFor(()=>expect((screen.getByRole("button",{name:"Launch"}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"Launch"}));
  await waitFor(()=>expect(first.requests.filter(x=>x.operation==="submit")).toHaveLength(1));
  await screen.findByRole("button",{name:"Check status"});
  const original=await first.store.read(first.scope);
  expect(original).toEqual({kind:"launch",targetKey:first.workRef,operationKey:expect.stringMatching(/^mmos-project-execute-[0-9a-f]{40}$/)});
  first.view.unmount();

  // A fresh App, authenticated host, command port and IDB connection share only
  // the existing database. No in-memory draft/request survives this page reopen.
  const reopened=await createProjectExecutionProofFixture(createIndexedDbPendingPointerStore(database),{history:"empty"});
  window.MastermindMissionHost=reopened.host;render(<App/>);
  fireEvent.click(await screen.findByRole("button",{name:"Check status"}));
  await waitFor(async()=>expect(await reopened.store.read(reopened.scope)).toBeNull());
  expect(first.requests.filter(x=>x.operation==="submit")).toHaveLength(1);
  expect(reopened.requests).toEqual([{operation:"status",arguments:{operation_key:original!.operationKey,work_ref:first.workRef}}]);
  await waitFor(()=>expect(window.location.search).toBe("?work_ref=WS%3ANEW-PROJECT&root_job_id=JOB-002"));
});

it("keeps a pre-execution refusal editable without retaining an unknown original in IndexedDB",async()=>{
  const f=await setup({history:"empty",mode:"refused"});
  await waitFor(()=>expect((screen.getByRole("button",{name:"Start work"}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"Start work"}));
  await waitFor(()=>expect(screen.queryByLabelText("Goal"),document.body.textContent ?? "").not.toBeNull());
  fireEvent.change(screen.getByLabelText("Handoff (optional)"),{target:{value:"Retain this useful context after refusal."}});
  fireEvent.click(screen.getByRole("button",{name:"Launch"}));
  expect((await screen.findByRole("alert")).textContent).toBe("REFUSED");
  expect(await f.store.read(f.scope)).toBeNull();
  expect((screen.getByLabelText("Handoff (optional)") as HTMLTextAreaElement).value).toBe("Retain this useful context after refusal.");
  expect(f.requests.filter(x=>x.operation==="submit")).toHaveLength(1);
  expect(f.requests.filter(x=>x.operation==="status")).toHaveLength(0);
});
