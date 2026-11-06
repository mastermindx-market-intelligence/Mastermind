// @vitest-environment jsdom
// Actual App -> NativeClient -> composed Host -> incumbent Journey/IndexedDB.
// Only native invoke/listen and source-unavailable reads are inert. These exact
// continuity frames came from actual Rust InnerToken/serde, whose principal is
// the real signed Workspace READ identity fixture. No public auth reason grants
// recovery, no body is stored by the native facet, no action is dispatched.
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';
import {createNativeClient} from './host';
import {composeMissionHost} from './compose-mission-host';
import {decodeLaunchBindingConfig} from './launch-config';
import sequence from './auth-recovery/fixtures/native-draft-owner-sequence.json';
import signedIdentity from './auth-recovery/fixtures/native-draft-identity-owner.json';
const text='Private project goal\n  保持原文与空格\n';
const signed={status:'signed_in',reason:null,acquisition:true,content:false};
const disposals:Array<()=>void>=[];
beforeEach(()=>{
 history.replaceState(null,'','/os/?new_project=1');localStorage.clear();
 vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(sequence.now_ms);
 Object.assign(window,{__TAURI_INTERNALS__:{}});
 expect(sequence.qualified.principal_scope).toBe(signedIdentity.first.principal_scope);
});
afterEach(()=>{cleanup();disposals.splice(0).forEach(dispose=>dispose());vi.useRealTimers();vi.restoreAllMocks();delete window.MastermindMissionHost;delete (window as unknown as {__TAURI_INTERNALS__?:unknown}).__TAURI_INTERNALS__;});
async function setup({legacyOwner=false,unavailableIdentity=false}={}){
 let state:unknown=signed,frame:unknown=sequence.qualified,held:Promise<unknown>|null=null;
 const events=new Map<string,Set<(event:{payload:unknown})=>void>>();
 const invoke=vi.fn(async(command:string):Promise<unknown>=>{
  if(command==='auth_status')return structuredClone(state);
  if(command==='executive_auth_status')return {generation:0,available:false};
  if(command==='read_native_draft_continuity'){if(unavailableIdentity)throw Error('IDENTITY_SOURCE_UNAVAILABLE');return held??structuredClone(frame);}
  if(command==='sign_in')return {status:'signing_in',reason:null,acquisition:false,content:false};
  if(command==='sign_out')return undefined;
  throw Error('Source not supplied by inert goal-only native fixture');
 });
 const raw=await createNativeClient(invoke as never,async(name,handler)=>{
  const handlers=events.get(name)??new Set();handlers.add(handler);events.set(name,handlers);
  return()=>{handlers.delete(handler);};
 });
 const config=decodeLaunchBindingConfig(JSON.stringify({v:1,workstream:'WS:GOAL-RECOVERY',priority:0,attemptLimit:1,
  projects:[{ref:'executive-infrastructure',label:'Infrastructure'}],profiles:[{ref:'research_only',label:'Research'},{ref:'native_research_only',label:'Native research'}]}))!;
 const composed=composeMissionHost(raw,config,new IDBFactory(),'native');disposals.push(composed.dispose);
 await composed.ready;await composed.sessionReady;
 if(legacyOwner)Reflect.deleteProperty(composed.host,"nativeDraftRecovery");
 window.MastermindMissionHost=composed.host;
 render(<App/>);
 await screen.findByRole('textbox',{name:'Your goal'});
 const notify=async(next:unknown,continuity:unknown)=>{
  state=next;frame=continuity;
  await act(async()=>events.get('mastermind-auth-state')?.forEach(handler=>handler({payload:next})));
 };
 const edit=async()=>{
  fireEvent.focus(screen.getByRole('textbox',{name:'Your goal'}));
  await waitFor(()=>expect(screen.getByRole('textbox',{name:'Your goal'})).toHaveProperty('readOnly',false));
  fireEvent.change(screen.getByRole('textbox',{name:'Your goal'}),{target:{value:text}});
  await waitFor(()=>expect(invoke.mock.calls.filter(([name])=>name==='read_native_draft_continuity')).toHaveLength(legacyOwner?0:1));
  await act(async()=>{});
 };
 const expire=async()=>{
  await edit();await notify(sequence.expired_auth,sequence.expired);
  expect(screen.queryByDisplayValue(text)).toBeNull();expect(document.body.textContent).not.toContain(text);
  expect(await screen.findByText('Your unsent work is kept in this window. Sign in to recover it.')).toBeTruthy();
 };
 const returnSame=async()=>{
  await notify({status:'signing_in',reason:null,acquisition:false,content:false},sequence.reauthenticating);
  expect(screen.queryByDisplayValue(text)).toBeNull();
  await notify(signed,sequence.same);expect(screen.queryByDisplayValue(text)).toBeNull();
 };
 const noActions=()=>expect(invoke.mock.calls.map(([command])=>command).filter(command=>/submit|source_operation|executive_project_planning|executive_session_(send|stop)|fresh_conversation/.test(command))).toEqual([]);
 return {host:composed.host,raw,invoke,notify,edit,expire,returnSame,noActions,recoverIdentity:()=>{unavailableIdentity=false;},
  hold:()=>{let finish!:(value:unknown)=>void;held=new Promise(resolve=>{finish=resolve;});return finish;}};
}
it('genuine native expiry hides exact goal through sign-in and explicitly returns the same original text without action or pointer effects',async()=>{
 const e=await setup();await e.expire();
 const store=e.host.commandBinding!.store,scope=sequence.qualified.principal_scope;
 const pointer={kind:'launch' as const,operationKey:'mmos-launch-'+'1'.repeat(40),targetKey:'WS:GOAL-RECOVERY'};
 await store.reserve(scope,pointer);
 fireEvent.click(screen.getByRole('button',{name:'Sign in'}));await act(async()=>{});
 expect(screen.queryByDisplayValue(text)).toBeNull();
 await e.returnSame();fireEvent.click(screen.getByRole('button',{name:'Recover unsent work'}));
 expect(await screen.findByRole('textbox',{name:'Your goal'})).toHaveProperty('value',text);
 expect(location.search).toBe('?new_project=1');expect(await store.read(scope)).toEqual(pointer);
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_native_draft_continuity')).toHaveLength(2);e.noActions();
});
it.each(['logout','different'] as const)('%s clears the original goal rather than returning it',async kind=>{
 const e=await setup();await e.expire();
 if(kind==='logout')await e.notify(sequence.logout_auth,sequence.logout);
 else{await e.notify(signed,sequence.different);fireEvent.click(screen.getByRole('button',{name:'Recover unsent work'}));await act(async()=>{});}
 expect(screen.queryByDisplayValue(text)).toBeNull();expect(document.body.textContent).not.toContain(text);
 expect(screen.queryByRole('button',{name:'Recover unsent work'})).toBeNull();e.noActions();
});
it('a genuinely issued same-scope foreign Host cannot restore through the original rendered recovery gesture',async()=>{
 const e=await setup();await e.expire();await e.returnSame();
 const button=screen.getByRole('button',{name:'Recover unsent work'});
 const foreignRaw=await createNativeClient((async(command:string)=>command==='read_native_draft_continuity'?sequence.same:command==='executive_auth_status'?{generation:0,available:false}:signed) as never,async()=>()=>{});
 const foreign=composeMissionHost(foreignRaw,null,new IDBFactory(),'native');disposals.push(foreign.dispose);
 const origin=await foreign.host.nativeDraftRecovery!.capture('project-goal.v1:blank');
 expect(origin).not.toBeNull();expect(await foreign.host.nativeDraftRecovery!.check(origin!)).toBe('RETURNABLE');
 const before=e.invoke.mock.calls.length;window.MastermindMissionHost=foreign.host;
 fireEvent.click(button);await act(async()=>{});
 expect(screen.queryByDisplayValue(text)).toBeNull();expect(e.invoke.mock.calls.length).toBe(before);e.noActions();
});
it.each(['epoch','host'] as const)('a late identity read after %s withdrawal cannot restore the private goal',async kind=>{
 const e=await setup();await e.expire();await e.returnSame();
 const finish=e.hold();fireEvent.click(screen.getByRole('button',{name:'Recover unsent work'}));
 await waitFor(()=>expect(e.invoke.mock.calls.filter(([name])=>name==='read_native_draft_continuity')).toHaveLength(2));
 if(kind==='epoch')await e.notify(sequence.expired_auth,sequence.expired);
 else window.MastermindMissionHost={...e.host};
 await act(async()=>finish(structuredClone(sequence.same)));
 expect(screen.queryByDisplayValue(text)).toBeNull();expect(document.body.textContent).not.toContain(text);e.noActions();
});
it('explicit Discard clears only the quarantined goal and leaves the original pending pointer unchanged',async()=>{
 const e=await setup();await e.expire();const scope=sequence.qualified.principal_scope;
 const pointer={kind:'launch' as const,operationKey:'mmos-launch-'+'2'.repeat(40),targetKey:'WS:GOAL-RECOVERY'};
 await e.host.commandBinding!.store.reserve(scope,pointer);
 fireEvent.click(screen.getByRole('button',{name:'Discard unsent work'}));
 expect(screen.queryByRole('button',{name:'Recover unsent work'})).toBeNull();
 expect(await e.host.commandBinding!.store.read(scope)).toEqual(pointer);e.noActions();
});

it('restores exact original nonblank create scope and URL without issuing or re-keying that operation',async()=>{
 const original='mmos-project-create-'+'a'.repeat(40);
 history.replaceState(null,'','/os/?new_project=1&project_create_request='+original);
 const e=await setup();await e.expire();await e.returnSame();
 fireEvent.click(screen.getByRole('button',{name:'Recover unsent work'}));
 expect(await screen.findByRole('textbox',{name:'Your goal'})).toHaveProperty('value',text);
 expect(new URL(location.href).searchParams.get('project_create_request')).toBe(original);
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_native_draft_continuity')).toHaveLength(2);e.noActions();
});
it('the actual explicit Sign out action destroys the goal before native logout completion',async()=>{
 const e=await setup();await e.edit();
 fireEvent.click(screen.getByRole('button',{name:'Sign out'}));await act(async()=>{});
 expect(screen.queryByDisplayValue(text)).toBeNull();
 expect(screen.queryByRole('button',{name:'Recover unsent work'})).toBeNull();
 await e.notify(signed,sequence.same);expect(screen.queryByDisplayValue(text)).toBeNull();e.noActions();
});
it('keeps unchanged returned text recoverable across a second genuine expiry without requiring another edit',async()=>{
 const e=await setup();await e.expire();await e.returnSame();
 fireEvent.click(screen.getByRole('button',{name:'Recover unsent work'}));
 expect(await screen.findByRole('textbox',{name:'Your goal'})).toHaveProperty('value',text);
 await act(async()=>{});
 await e.notify(sequence.expired_auth,sequence.expired);expect(screen.queryByDisplayValue(text)).toBeNull();
 await e.returnSame();
 expect((screen.getByRole('button',{name:'Recover unsent work'}) as HTMLButtonElement).disabled).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'Recover unsent work'}));
 expect(await screen.findByRole('textbox',{name:'Your goal'})).toHaveProperty('value',text);e.noActions();
});
it('never attributes a first edit to a later native principal while initial identity inspection is pending',async()=>{
 const e=await setup();const finish=e.hold();const goal=screen.getByRole('textbox',{name:'Your goal'});
 fireEvent.focus(goal);
 // Deliberately dispatch even while readOnly: the App callback must also gate
 // programmatic/stale edits, not rely on the browser's DOM input treatment.
 fireEvent.change(goal,{target:{value:text}});
 await waitFor(()=>expect(e.invoke.mock.calls.filter(([name])=>name==='read_native_draft_continuity')).toHaveLength(1));
 expect(screen.queryByDisplayValue(text)).toBeNull();
 await act(async()=>finish(structuredClone(sequence.different)));
 await e.notify(sequence.expired_auth,sequence.expired);await e.notify(signed,sequence.different);
 expect(screen.queryByDisplayValue(text)).toBeNull();
 expect(screen.queryByRole('button',{name:'Recover unsent work'})).toBeNull();e.noActions();
});

it.each(['unavailable','legacy'] as const)('%s identity permits ordinary UNBOUND editing without later attribution or recovery',async kind=>{
 const e=await setup({legacyOwner:kind==='legacy',unavailableIdentity:kind==='unavailable'});
 await e.edit();expect(screen.getByRole('textbox',{name:'Your goal'})).toHaveProperty('value',text);
 const reads=e.invoke.mock.calls.filter(([name])=>name==='read_native_draft_continuity').length;
 e.recoverIdentity(); // Endpoint is now qualified; existing UNBOUND text still cannot acquire it.
 fireEvent.blur(screen.getByRole('textbox',{name:'Your goal'}));
 fireEvent.focus(screen.getByRole('textbox',{name:'Your goal'}));await act(async()=>{});
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_native_draft_continuity')).toHaveLength(reads);
 await e.notify(sequence.expired_auth,sequence.expired);await e.notify(signed,sequence.same);
 expect(screen.queryByDisplayValue(text)).toBeNull();
 expect(screen.queryByRole('button',{name:'Recover unsent work'})).toBeNull();e.noActions();
});

it('a first-focus identity response arriving after auth withdrawal cannot authorize editing or retain the attempted text',async()=>{
 const e=await setup();const finish=e.hold();const goal=screen.getByRole('textbox',{name:'Your goal'});
 fireEvent.focus(goal);
 await waitFor(()=>expect(e.invoke.mock.calls.filter(([name])=>name==='read_native_draft_continuity')).toHaveLength(1));
 fireEvent.change(goal,{target:{value:text}});
 await e.notify(sequence.expired_auth,sequence.expired);await e.notify(signed,sequence.different);
 await act(async()=>finish(structuredClone(sequence.qualified)));
 expect(screen.getByRole('textbox',{name:'Your goal'})).toHaveProperty('readOnly',true);
 expect(screen.queryByDisplayValue(text)).toBeNull();
 expect(screen.queryByRole('button',{name:'Recover unsent work'})).toBeNull();e.noActions();
});
it('returned text keeps its original nominal principal instead of rebinding at another focus',async()=>{
 const e=await setup();await e.expire();await e.returnSame();
 fireEvent.click(screen.getByRole('button',{name:'Recover unsent work'}));
 const goal=await screen.findByRole('textbox',{name:'Your goal'});expect(goal).toHaveProperty('value',text);
 fireEvent.focus(goal);await act(async()=>{});
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_native_draft_continuity')).toHaveLength(2);
 await e.notify(signed,sequence.different);fireEvent.click(screen.getByRole('button',{name:'Recover unsent work'}));
 await act(async()=>{});expect(screen.queryByDisplayValue(text)).toBeNull();
 expect(screen.queryByRole('button',{name:'Recover unsent work'})).toBeNull();e.noActions();
});
