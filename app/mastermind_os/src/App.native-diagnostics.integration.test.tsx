// @vitest-environment jsdom
import {act} from 'react';
import {createRoot,type Root} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {App} from './App';
import {createNativeClient} from './host';
import {composeMissionHost} from './compose-mission-host';
(globalThis as typeof globalThis & {IS_REACT_ACT_ENVIRONMENT:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
let container:HTMLDivElement,root:Root|null=null;
let dispose:()=>void=()=>{};
beforeEach(()=>{history.replaceState(null,'','/os/');localStorage.clear();container=document.createElement('div');document.body.append(container);});
afterEach(async()=>{if(root)await act(async()=>root!.unmount());dispose();root=null;container.remove();delete window.MastermindMissionHost;vi.restoreAllMocks();});
const raw=()=>({schema:'mastermind.native_executive_status.v1',generation:2,available:true,configured:true,reason:'AVAILABLE',programs_read:{phase:'HTTP_FAILURE',http_status:503}});
async function mount(){
 const handlers=new Map<string,(e:{payload:unknown})=>void>();
 const invoke=vi.fn(async(command:string,args?:unknown):Promise<unknown>=>{
  if(command==='auth_status')return {status:'signed_in',reason:null,acquisition:true,content:true};
  if(command==='executive_auth_status')return args?raw():{generation:2,available:false};
  if(command==='read_programs')throw new Error('SOURCE_UNAVAILABLE');
  throw new Error('UNEXPECTED_NATIVE_COMMAND');
 });
 const client=await createNativeClient(invoke as never,async(event,handler)=>{handlers.set(event,handler);return ()=>{};});
 const composition=composeMissionHost(client,null,undefined,'native');dispose=composition.dispose;
 window.MastermindMissionHost=composition.host;
 await act(async()=>{root=createRoot(container);root.render(<App/>);});
 return {invoke,client,handlers,host:composition.host};
}
function button(){const found=[...container.querySelectorAll('button')].find(b=>b.textContent==='Refresh local native diagnostics');expect(found).toBeTruthy();return found!;}
async function open(){const d=[...container.querySelectorAll('details')].find(d=>d.querySelector('button')?.textContent==='Refresh local native diagnostics');expect(d).toBeTruthy();await act(async()=>{d!.querySelector('summary')!.click();});}
function field(term:string){return [...container.querySelectorAll('dt')].find(x=>x.textContent===term)?.nextElementSibling?.textContent;}
it('joins actual NativeClient/Host/App explicit local status without another Projects, Executive context or auth effect',async()=>{
 const f=await mount();expect(f.invoke.mock.calls.filter(([c,a])=>c==='executive_auth_status'&&a)).toHaveLength(0);
 const before=f.invoke.mock.calls.length;await open();expect(f.invoke.mock.calls).toHaveLength(before);
 await act(async()=>button().click());
 expect(f.invoke.mock.calls.slice(before)).toEqual([['executive_auth_status',{diagnostics:true}]]);
 expect(field('Executive availability')).toBe('No');expect(field('Local Executive availability')).toBe('Yes');
 expect(field('Native Executive resource')).toBe('Unknown');expect(field('Local Executive configured')).toBe('Yes');
 expect(field('Last Projects HTTP status')).toBe('503');expect(f.client.executive!.available()).toBe(false);
});
it('refuses no-render global Host replacement before dispatching the local metadata read',async()=>{
 const f=await mount();await open();const target=button(),before=f.invoke.mock.calls.length;
 window.MastermindMissionHost={...f.host};
 await act(async()=>target.click());expect(f.invoke.mock.calls).toHaveLength(before);
 expect(container.textContent).toContain('Local diagnostics unavailable.');expect(field('Local Executive reason')).toBeUndefined();
});
it('withdraws a delayed native diagnostic result on actual native auth loss',async()=>{
 const f=await mount();await open();let resolve!:(v:unknown)=>void;
 f.invoke.mockImplementationOnce(()=>new Promise(done=>{resolve=done;}));
 await act(async()=>button().click());
 await act(async()=>f.handlers.get('mastermind-auth-state')!({payload:{status:'signed_out',reason:null,acquisition:false,content:false}}));
 await act(async()=>resolve(raw()));
 expect(container.textContent).toContain('Sign in to your workspace.');expect(container.textContent).not.toContain('LAST_EXPLICIT_LOCAL_READ');
 expect(f.invoke.mock.calls.filter(([c])=>c==='sign_in'||c==='executive_context')).toHaveLength(0);
});
