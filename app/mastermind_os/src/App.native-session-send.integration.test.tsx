// @vitest-environment jsdom
// Real NativeClient/Host/App/session controller+IDB, exact signed BFF fixture
// (actual Runtime projector with inert current-material/private peer premises).
// No live target/provider/enrollment is asserted or contacted.
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';
import {createNativeClient} from './host';
import {completeExecutiveSessionBinding} from './orchestration/os-executive-session-host';
import {composeMissionHost} from './compose-mission-host';
import unavailableContext from './fixtures/native-session-context-unavailable.json';
import fixture from './fixtures/native-session-send-producer.json';
import programs from './fixtures/programs-available-workspace-service.json';
import paired from './fixtures/window-mission-association-producer.json';
import {decodeMissionv3} from './mission';
import {controlRoomFixture} from './test-fixtures';
import namespace from './auth-recovery/fixtures/native-draft-owner-sequence.json';
const disposals:Array<()=>void>=[];
beforeEach(()=>{history.replaceState(null,'',`/os/?work_ref=${fixture.selection.work_ref}&root_job_id=${fixture.selection.root_job_id}`);localStorage.clear();vi.spyOn(Date,'now').mockReturnValue(fixture.now_ms);Object.assign(window,{__TAURI_INTERNALS__:{}});});
afterEach(()=>{cleanup();disposals.splice(0).forEach(f=>f());vi.restoreAllMocks();delete window.MastermindMissionHost;delete (window as unknown as {__TAURI_INTERNALS__?:unknown}).__TAURI_INTERNALS__;});
async function setup(options:{readOnly?:boolean;unknown?:boolean;pending?:boolean;office?:boolean;unavailable?:boolean}={}){
 const room=controlRoomFixture(),row=structuredClone(room.work[0]);row.work_ref=fixture.selection.work_ref;row.agent_os.workstream=fixture.selection.work_ref.slice(3);row.agent_os.title='Inert supplied Office project';room.work=[row];
 const responsibility=structuredClone(room.autonomy.responsibilities[0]);Object.assign(responsibility,{responsibility_ref:fixture.selection.work_ref,root_job_id:fixture.selection.root_job_id,root_job_candidates:[fixture.selection.root_job_id],root_job_ambiguous:false,runtime_root_state:'RESOLVED'});room.autonomy.responsibilities=[responsibility];
 // Explicit inert Workspace source premises. No extra Runtime target or
 // permission is derived from these display documents.
 const mission=JSON.parse(JSON.stringify(paired.mission).replaceAll(paired.selection.work_ref,fixture.selection.work_ref).replaceAll(paired.selection.root_job_id,fixture.selection.root_job_id));
 mission.result_refs.absent_job_ids.sort();mission.result_refs.omitted_job_ids.sort();
 if(options.office)expect(decodeMissionv3(mission,{workRef:fixture.selection.work_ref,rootJobId:fixture.selection.root_job_id})).not.toBeNull();
 const events=new Map<string,Set<(event:{payload:unknown})=>void>>();
 let sendHeld:Promise<unknown>|null=null;
 const invoke=vi.fn(async(command:string,args?:Record<string,unknown>):Promise<unknown>=>{
  if(command==='auth_status')return options.office?{status:'signed_in',reason:null,acquisition:true,content:true}:namespace.expired_auth;
  if(options.office&&command==='read_programs')return {...structuredClone(programs),control_room:room};
  if(options.office&&command==='read_mission_v3')return mission;
  if(command==='executive_auth_status')return {generation:1,available:true};
  if(command==='executive_session_context')return structuredClone(options.unavailable?unavailableContext:options.readOnly?fixture.read_context:fixture.context);
  if(command==='read_native_draft_continuity')return namespace.expired;
  if(command==='executive_session_send')return sendHeld??structuredClone(options.unknown?fixture.unknown:fixture.sent);
  if(command==='executive_session_reply')return structuredClone(fixture.reply);
  throw Error('SOURCE_NOT_SUPPLIED');
 });
 const raw=await createNativeClient(invoke as never,async(name,fn)=>{const set=events.get(name)??new Set();set.add(fn);events.set(name,set);return()=>set.delete(fn);});
 const composed=composeMissionHost(raw,null,new IDBFactory(),'native');disposals.push(composed.dispose);await composed.ready;await composed.sessionReady;
 const sessionBinding=completeExecutiveSessionBinding(composed.host.sessionCommandBinding)!;
 const pointer={kind:'message' as const,operationKey:fixture.arguments.operation_key,targetKey:fixture.arguments.target_ref};
 if(options.pending)await sessionBinding.store.reserve(fixture.context.data.principal_scope,pointer);
 window.MastermindMissionHost=composed.host;render(<App/>);
 if(!options.office&&!options.unavailable)fireEvent.click(await screen.findByRole('button',{name:'Open session requests'}));
 const panel=()=>within(screen.getByRole('region',{name:'Session continuation'}));
 const edit=async()=>{const field=await screen.findByRole('textbox',{name:'What would you like done?'});fireEvent.focus(field);await waitFor(()=>expect(field).toHaveProperty('readOnly',false));fireEvent.change(field,{target:{value:fixture.arguments.instruction}});fireEvent.change(screen.getByRole('textbox',{name:'How will we know it is done?'}),{target:{value:fixture.arguments.stop_condition}});return field;};
 const saved=()=>sessionBinding.store.read(fixture.context.data.principal_scope);
 const noWorkspaceWrite=()=>expect(invoke.mock.calls.filter(([name])=>/executive_submit|consume|project_planning|fresh_conversation/.test(name))).toHaveLength(0);
 return {host:composed.host,invoke,pointer,panel,edit,saved,noWorkspaceWrite,
  restore:async()=>{await act(async()=>events.get('mastermind-executive-auth-state')?.forEach(fn=>fn({payload:{generation:3,available:true}})));},
  revoke:async()=>{await act(async()=>events.get('mastermind-executive-auth-state')?.forEach(fn=>fn({payload:{generation:2,available:false}})));},
  holdSend:()=>{let finish!:(value:unknown)=>void;sendHeld=new Promise(resolve=>finish=resolve);return finish;}};
}
it('real native E-only App sends once to actual owner target, retains original until qualified answer renders, then settles its same original pointer',async()=>{
 const e=await setup();await e.edit();await waitFor(()=>expect(e.panel().getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));
 fireEvent.click(e.panel().getByRole('button',{name:'Send'}));
 await waitFor(()=>expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(1));
 expect(e.invoke.mock.calls.find(([name])=>name==='executive_session_send')?.[1]).toEqual({arguments:fixture.arguments});
 await waitFor(async()=>expect(await e.saved()).toEqual(e.pointer));expect(screen.queryByText(fixture.reply.data.text)).toBeNull();
 fireEvent.click(await e.panel().findByRole('button',{name:'Check status'}));
 expect((await screen.findByRole('region',{name:'Original reply'})).textContent).toContain(fixture.reply.data.text);
 await waitFor(async()=>expect(await e.saved()).toBeNull());
 expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(1);
 expect(e.invoke.mock.calls.find(([name])=>name==='executive_session_reply')?.[1]).toEqual({operationKey:e.pointer.operationKey});e.noWorkspaceWrite();
});
it('actual read-only BFF context supplies original observation but no native continuation target/action',async()=>{
 const e=await setup({readOnly:true});await screen.findByRole('region',{name:'Session continuation'});
 expect(screen.queryByRole('textbox',{name:'What would you like done?'})).toBeNull();expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(0);e.noWorkspaceWrite();
});
it('UNKNOWN source send retains original IDB key and explicit status reads that key without resubmission',async()=>{
 const e=await setup({unknown:true});await e.edit();await waitFor(()=>expect(e.panel().getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));fireEvent.click(e.panel().getByRole('button',{name:'Send'}));
 await waitFor(async()=>expect(await e.saved()).toEqual(e.pointer));fireEvent.click(await e.panel().findByRole('button',{name:'Check status'}));
 await waitFor(async()=>expect(await e.saved()).toBeNull());expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(1);e.noWorkspaceWrite();
});
it('E-only reopen recovers the original source pointer/answer with zero prepare or send',async()=>{
 const e=await setup({pending:true});fireEvent.click(await screen.findByRole('button',{name:'Check status'}));
 await waitFor(async()=>expect(await e.saved()).toBeNull());expect(await screen.findByText(fixture.reply.data.text)).toBeTruthy();
 expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(0);e.noWorkspaceWrite();
});
it('no-render copied Host cannot borrow the prior view target to send',async()=>{
 const e=await setup();await e.edit();const send=e.panel().getByRole('button',{name:'Send'});await waitFor(()=>expect(send).toHaveProperty('disabled',false));window.MastermindMissionHost={...e.host};fireEvent.click(send);await act(async()=>{});
 expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(0);expect(await e.saved()).toBeNull();e.noWorkspaceWrite();
});
it('actual native E epoch revocation after entered send retains UNKNOWN and withholds late success with zero retry',async()=>{
 const e=await setup();await e.edit();const finish=e.holdSend();await waitFor(()=>expect(e.panel().getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));fireEvent.click(e.panel().getByRole('button',{name:'Send'}));
 await waitFor(()=>expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(1));await e.revoke();await act(async()=>finish(fixture.sent));
 expect(await e.saved()).toEqual(e.pointer);expect(screen.queryByText(fixture.reply.data.text)).toBeNull();expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(1);e.noWorkspaceWrite();
});

it('current local instruction/completion owner keeps its stricter clear policy across E withdrawal, without restoring text or sending',async()=>{
 const e=await setup();await e.edit();await e.revoke();expect(screen.queryByDisplayValue(fixture.arguments.instruction)).toBeNull();expect(screen.queryByDisplayValue(fixture.arguments.stop_condition)).toBeNull();
 await e.restore();expect(screen.queryByDisplayValue(fixture.arguments.instruction)).toBeNull();
 const entry=screen.queryByRole('button',{name:'Open session requests'});if(entry)fireEvent.click(entry);
 expect(await screen.findByRole('textbox',{name:'What would you like done?'})).toHaveProperty('value','');
 expect(screen.getByRole('textbox',{name:'How will we know it is done?'})).toHaveProperty('value','');
 expect(screen.queryByRole('button',{name:'Recover unsent work'})).toBeNull();expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(0);expect(await e.saved()).toBeNull();e.noWorkspaceWrite();
});
it('no-render issuing binding replacement cannot borrow a still-callable former E target or author',async()=>{
 const e=await setup();await e.edit();const send=e.panel().getByRole('button',{name:'Send'});await waitFor(()=>expect(send).toHaveProperty('disabled',false));
 const binding=e.host.sessionCommandBinding;Object.defineProperty(e.host,'sessionCommandBinding',{value:{...binding as object},configurable:true});
 fireEvent.click(send);await act(async()=>{});expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(0);expect(await e.saved()).toBeNull();e.noWorkspaceWrite();
});

it('actual native Office composes its incumbent session owner only after supplied Workspace mission and genuine E target both qualify, then sends once',async()=>{
 const e=await setup({office:true});fireEvent.click(screen.getByRole('button',{name:'Meta-CEO'}));
 await waitFor(()=>expect(e.invoke.mock.calls.some(([name])=>name==='read_mission_v3')).toBe(true));
 await e.edit();await waitFor(()=>expect(e.panel().getByRole('button',{name:'Send'})).toHaveProperty('disabled',false));
 fireEvent.click(e.panel().getByRole('button',{name:'Send'}));await waitFor(()=>expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(1));
 expect(e.invoke.mock.calls.find(([name])=>name==='executive_session_send')?.[1]).toEqual({arguments:fixture.arguments});
 expect(await e.saved()).toEqual(e.pointer);expect(screen.queryByText(fixture.reply.data.text)).toBeNull();
 fireEvent.click(await e.panel().findByRole('button',{name:'Check status'}));expect(await screen.findByRole('region',{name:'Original reply'})).toBeTruthy();
 await waitFor(async()=>expect(await e.saved()).toBeNull());expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(1);e.noWorkspaceWrite();
});

it('ordinary unavailable Session context cannot turn public native availability into an entry, owner, target or SEND',async()=>{
 const e=await setup({unavailable:true});await waitFor(()=>expect(e.invoke.mock.calls.some(([name])=>name==='executive_session_context')).toBe(true));
 await act(async()=>{await Promise.resolve();await Promise.resolve();});
 expect(completeExecutiveSessionBinding(e.host.sessionCommandBinding)!.port.context()).toBeNull();
 expect(screen.queryByRole('button',{name:'Open session requests'})).toBeNull();expect(screen.queryByRole('textbox',{name:'What would you like done?'})).toBeNull();
 expect(e.invoke.mock.calls.filter(([name])=>name==='executive_session_send')).toHaveLength(0);e.noWorkspaceWrite();
});
