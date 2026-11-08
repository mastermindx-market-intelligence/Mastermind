// @vitest-environment jsdom
/** Real journey/controller/IndexedDB; actual owner envelopes through inert transport. */
import {afterEach,expect,it,vi} from 'vitest';
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {useState} from 'react';
import {IDBFactory} from 'fake-indexeddb';
import fixture from '../../fixtures/native-fresh-action-owner.json';
import recoveryFixture from '../../fixtures/native-fresh-recovery-owner.json';
import type {NativeControlTransport} from './native-conversation-controls';
import {createFreshConversationBinding,type FreshConversationTransport} from './fresh-conversation-command-binding';
import {useFreshConversationJourney,type NativeFreshConversationObservation} from './useFreshConversationJourney';
import {createIndexedDbPendingPointerStore} from '../../orchestration/indexeddb-pending-pointer-store';
import {freshConversationTarget} from '../../orchestration/fresh-conversation-target';
import type {OperationPointer,OwnerContext} from '../../orchestration/operation-controller';
const samples=fixture.samples,request=samples[10].arguments;
const selection={work_ref:request.work_ref,operation_key:request.operation_key!};
const scope='e'.repeat(64),HOST={},PROJECTS=[{workRef:selection.work_ref,title:'Native project'}];
function defer<T>(){let resolve!:(v:T)=>void;const promise=new Promise<T>(r=>{resolve=r;});return {promise,resolve};}
function rig(native=false){
 const store=createIndexedDbPendingPointerStore(new IDBFactory());
 let owner:OwnerContext|null={principalScope:scope,generation:'native-ui-1'};
 const create=defer<unknown>(),entered=defer<void>();let signal:AbortSignal|undefined;
 const transport:FreshConversationTransport={
  preview:vi.fn(async()=>samples[10].response),
  create:vi.fn((_request,s)=>{signal=s;entered.resolve();return create.promise;}),
  status:vi.fn(async()=>samples[9].response),read:vi.fn(async()=>samples[12].response),
 };
 vi.stubGlobal('crypto',{getRandomValues:(bytes:Uint8Array)=>{bytes.fill(0xaa);return bytes;}});
 const nativeTransport:NativeControlTransport={request:vi.fn(async()=>recoveryFixture.samples[0].response)};
 const binding=createFreshConversationBinding({newContract:'native-v2',owner:()=>owner,canPreviewCreate:()=>true,transport,store,...(native?{nativeTransport}:{})});
 return {store,binding,transport,nativeTransport,create,entered,get signal(){return signal;},withdraw:()=>{owner=null;},get owner(){return owner;}};
}
let journey:ReturnType<typeof useFreshConversationJourney>|null=null,shown:NativeFreshConversationObservation|null=null;
const selected=vi.fn();
function Harness({e,auth=0,lookup=false}:{e:ReturnType<typeof rig>;auth?:number;lookup?:boolean}){
 const [message,setMessage]=useState(request.message!);
 journey=useFreshConversationJourney({locale:'en',active:true,binding:e.binding,authGeneration:auth,host:HOST,
  projects:PROJECTS,projectsState:'available',projectReadIdentity:PROJECTS,isProjectCurrent:()=>true,
  workRef:selection.work_ref,message,draftOwner:e.owner,onWorkRefChange:()=>{},onMessageChange:setMessage,
  onOriginalKeySelected:selected,originalLookup:lookup&&e.owner?{owner:e.owner,selection:{...selection,operation_key:'mmos-native-create-'+'f'.repeat(40)}}:null,
  onBack:()=>{},renderNativeContinuation:observation=>{shown=observation;return <p data-testid="native-state">{observation.current()?observation.data?.state??'awaiting':'withdrawn'}</p>;}});
 return journey.panel;
}
async function begin(e:ReturnType<typeof rig>){
 await waitFor(()=>expect((screen.getByRole('button',{name:'Review conversation'}) as HTMLButtonElement).disabled).toBe(false));
 fireEvent.click(screen.getByRole('button',{name:'Review conversation'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Create conversation'})).toBeTruthy());
 fireEvent.click(screen.getByRole('button',{name:'Create conversation'}));
 await act(async()=>{await e.entered.promise;});
}
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();selected.mockReset();journey=null;shown=null;});
it('observes ACTIVE while the original create remains pending without recovery, resend or abort',async()=>{
 const e=rig();e.transport.read=vi.fn(async()=>({...samples[15].response,operation:'read'}));
 render(<Harness e={e}/>);await begin(e);
 fireEvent.click(screen.getByRole('button',{name:'Check initial request'}));
 await waitFor(()=>expect(screen.getByTestId('native-state').textContent).toBe('ACTIVE'));
 expect(screen.getByText('The response is running.')).toBeTruthy();
 expect(e.transport.status).not.toHaveBeenCalled();expect(e.transport.create).toHaveBeenCalledTimes(1);
 expect(e.signal?.aborted).toBe(false);expect(await e.store.read(scope)).toEqual({kind:'conversation_create',operationKey:selection.operation_key,targetKey:selection.work_ref});
 e.transport.read=vi.fn(async()=>samples[12].response);
 await act(async()=>{e.create.resolve(samples[11].response);});
 await waitFor(()=>expect(screen.getByTestId('native-state').textContent).toBe('CREATED'));
});
it('a late ACTIVE read cannot overwrite the completion read',async()=>{
 const e=rig(),old=defer<unknown>();let reads=0;
 e.transport.read=vi.fn(async()=>++reads===1?old.promise:samples[12].response);
 render(<Harness e={e}/>);await begin(e);fireEvent.click(screen.getByRole('button',{name:'Check initial request'}));
 await waitFor(()=>expect(e.transport.read).toHaveBeenCalledTimes(1));
 await act(async()=>{e.create.resolve(samples[11].response);});
 await waitFor(()=>expect(screen.getByTestId('native-state').textContent).toBe('CREATED'));
 await act(async()=>{old.resolve({...samples[15].response,operation:'read'});});
 expect(screen.getByTestId('native-state').textContent).toBe('CREATED');
 expect(e.transport.create).toHaveBeenCalledTimes(1);
});
it('a foreign reservation never publishes that parent as the unsubmitted native original',async()=>{
 const e=rig();render(<Harness e={e}/>);
 await waitFor(()=>expect((screen.getByRole('button',{name:'Review conversation'}) as HTMLButtonElement).disabled).toBe(false));
 fireEvent.click(screen.getByRole('button',{name:'Review conversation'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Create conversation'})).toBeTruthy());
 const foreign:OperationPointer={kind:'conversation_create',operationKey:'mmos-native-create-'+'b'.repeat(40),targetKey:selection.work_ref};
 await e.store.reserve(scope,foreign);
 fireEvent.click(screen.getByRole('button',{name:'Create conversation'}));
 await waitFor(()=>expect(screen.getByText('Another request needs its existing status controls before a new conversation can be created.')).toBeTruthy());
 expect(screen.queryByTestId('native-state')).toBeNull();expect(e.transport.create).not.toHaveBeenCalled();expect(e.transport.read).not.toHaveBeenCalled();
 expect(await e.store.read(scope)).toEqual(foreign);
});
it('pending native recovery selects its actual lookup before status can clear the durable row',async()=>{
 const e=rig(),status=defer<unknown>();e.transport.status=vi.fn(()=>status.promise);
 await e.store.reserve(scope,{kind:'conversation_create',operationKey:selection.operation_key,targetKey:selection.work_ref});
 render(<Harness e={e} lookup/>);
 await waitFor(()=>expect(screen.getByTestId('native-state')).toBeTruthy());
 fireEvent.click(screen.getByRole('button',{name:'Check initial request'}));
 await waitFor(()=>expect(e.transport.status).toHaveBeenCalledTimes(1));
 expect(selected).toHaveBeenCalledWith(selection);expect(await e.store.read(scope)).not.toBeNull();
 await act(async()=>{status.resolve(samples[9].response);});
 await waitFor(()=>expect(screen.getByTestId('native-state').textContent).toBe('CREATED'));
 expect(await e.store.read(scope)).toBeNull();expect(e.transport.create).not.toHaveBeenCalled();
});
it('auth withdrawal hides a pending native observation and its late body',async()=>{
 const e=rig(),old=defer<unknown>();e.transport.read=vi.fn(()=>old.promise);
 const mounted=render(<Harness e={e}/>);await begin(e);
 fireEvent.click(screen.getByRole('button',{name:'Check initial request'}));await waitFor(()=>expect(e.transport.read).toHaveBeenCalledTimes(1));
 e.withdraw();mounted.rerender(<Harness e={e} auth={1}/>);
 await act(async()=>{old.resolve({...samples[15].response,operation:'read'});e.create.resolve(samples[11].response);});
 expect(screen.queryByTestId('native-state')).toBeNull();expect(screen.queryByText('The response is running.')).toBeNull();
 expect(await e.store.read(scope)).not.toBeNull();
});
it.each(['conversation_stop','conversation_resume'] as const)('qualified %s settlement retires only its stale presentation hint',async(kind)=>{
 const e=rig(),pointer:OperationPointer={kind,operationKey:'mmos-native-'+kind.slice('conversation_'.length)+'-'+'b'.repeat(40),targetKey:freshConversationTarget(selection)};
 await e.store.reserve(scope,pointer);render(<Harness e={e}/>);
 await waitFor(()=>expect(journey?.hasUnresolvedOriginal).toBe(true));
 // Test seam: the original control owner already settled and cleared this exact row.
 await e.store.clearIfEqual(scope,pointer);
 await act(async()=>{expect(await journey!.refreshPendingOriginal()).toBe(true);});
 expect(journey!.hasUnresolvedOriginal).toBe(false);
 expect(e.transport.create).not.toHaveBeenCalled();expect(e.transport.read).not.toHaveBeenCalled();
});

it('keeps the sealed initial witness across equivalent status replacement while retiring live control facts',async()=>{
 const e=rig();render(<Harness e={e}/>);await begin(e);
 await act(async()=>{e.create.resolve(samples[11].response);});
 await waitFor(()=>expect(screen.getByTestId('native-state').textContent).toBe('CREATED'));
 const first=shown!;expect(first.current()).toBe(true);expect(first.initialCurrent()).toBe(true);
 e.transport.read=vi.fn(async()=>structuredClone(samples[12].response));
 await act(async()=>{
  await first.refresh();
  // Observe the source ref before the enclosing React act has committed props.
  expect(first.current()).toBe(false);
  expect(first.initialCurrent()).toBe(true);
 });
 expect(shown!.initialCurrent()).toBe(true);
 expect(e.transport.create).toHaveBeenCalledTimes(1);
 e.withdraw();
 expect(first.initialCurrent()).toBe(false);expect(shown!.initialCurrent()).toBe(false);
});
it('a different actual initial result retires the previous sealed initial witness',async()=>{
 const e=rig();render(<Harness e={e}/>);await begin(e);
 await act(async()=>{e.create.resolve(samples[11].response);});
 await waitFor(()=>expect(screen.getByTestId('native-state').textContent).toBe('CREATED'));
 const first=shown!;
 // The earlier owner cohort has a different original input/result seal.
 expect(samples[2].operation).toBe('read');
 e.transport.read=vi.fn(async()=>structuredClone(samples[2].response));
 await act(async()=>{await first.refresh();});
 expect(first.current()).toBe(false);expect(first.initialCurrent()).toBe(false);
 expect(e.transport.create).toHaveBeenCalledTimes(1);
});

it('post-control refresh stays passive until the user explicitly checks the original request',async()=>{
 const e=rig(true),pointer:OperationPointer={kind:'conversation_create',operationKey:selection.operation_key,targetKey:selection.work_ref};
 await e.store.reserve(scope,pointer);render(<Harness e={e}/>);
 await waitFor(()=>expect(shown).not.toBeNull());
 await act(async()=>{await shown!.refresh();});
 expect(e.transport.read).toHaveBeenCalledTimes(1);expect(e.transport.status).not.toHaveBeenCalled();
 expect(e.nativeTransport.request).not.toHaveBeenCalled();expect(await e.store.read(scope)).toEqual(pointer);
 fireEvent.click(screen.getByRole('button',{name:'Check initial request'}));
 await waitFor(()=>expect(e.nativeTransport.request).toHaveBeenCalledTimes(1));
 expect(e.nativeTransport.request).toHaveBeenCalledWith('recover',selection,expect.any(AbortSignal));
 await waitFor(async()=>expect(await e.store.read(scope)).toBeNull());
 expect(e.transport.create).not.toHaveBeenCalled();
});
