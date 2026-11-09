// @vitest-environment jsdom
/** Whole SAME canonical source export; no projected body/principal/clock rewrite. */
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';import {createNativeClient} from './host';import {composeMissionHost} from './compose-mission-host';import {decodeLaunchBindingConfig} from './launch-config';
import source from './fixtures/office-whole-source.json';
let dispose=()=>{};
beforeEach(async()=>{history.replaceState(null,'','/os/');delete window.MastermindMissionHost;const{webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');vi.stubGlobal('crypto',webcrypto);vi.spyOn(Date,'now').mockReturnValue(source.clock.verified_at*1000);});
afterEach(()=>{cleanup();dispose();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup(hold=false){
 let armedHold=false;let resolve!:(v:unknown)=>void;const pending=new Promise(r=>resolve=r),events=new Map<string,Set<(e:{payload:unknown})=>void>>();
 const invoke=vi.fn(async(command:string,args?:unknown):Promise<unknown>=>{
  if(command==='auth_status')return{status:'signed_in',reason:null,acquisition:true,content:false};
  if(command==='executive_auth_status')return{generation:0,available:false};
  if(command==='read_programs')return structuredClone(source.responses.programs.body);
  if(command==='read_project_plan'||command==='read_project_direction'){
   expect(args).toEqual({selection:{work_ref:source.work_ref}});
   if(command==='read_project_plan'&&hold&&armedHold)return pending;
   return structuredClone(command==='read_project_plan'?source.responses.objective.body:source.responses.direction.body);
  }throw Error('No Mission, session, Executive or write capability supplied');
 });
 const client=await createNativeClient(invoke as never,async(name,listener)=>{const s=events.get(name)??new Set();s.add(listener);events.set(name,s);return()=>s.delete(listener);});
 const cfg=decodeLaunchBindingConfig(JSON.stringify({v:1,workstream:'WS:EXECUTIVE-ECOSYSTEM-COMPLETION',priority:0,attemptLimit:1,projects:[{ref:'executive-infrastructure',label:'Infrastructure'}],profiles:[{ref:'research_only',label:'Research'}]}))!;
 const composed=composeMissionHost(client,cfg,new IDBFactory(),'native');await composed.ready;await composed.sessionReady;window.MastermindMissionHost=composed.host;
 const view=render(<App/>);dispose=()=>{view.unmount();composed.dispose();};
 fireEvent.click(screen.getByRole('button',{name:'Projects'}));const title=source.responses.programs.body.control_room.work[0].agent_os.title;
 fireEvent.click(await screen.findByRole('button',{name:`Open project ${title}`}));fireEvent.click(screen.getByRole('button',{name:'Meta-CEO',exact:true}));await screen.findByRole('region',{name:'Meta-CEO office'});armedHold=true;
 const initialPlanReads=invoke.mock.calls.filter(([c])=>c==='read_project_plan').length;
 return{initialPlanReads,invoke,resolve,host:composed.host,notify:(payload:unknown)=>events.get('mastermind-auth-state')?.forEach(fn=>fn({payload})),count:(n:string)=>invoke.mock.calls.filter(([c])=>c===n).length};
}
it('composes exact rootless project, authored objective and accepted Direction without inferred Mission or Send; draft survives project return',async()=>{
 const e=await setup();const office=screen.getByRole('region',{name:'Meta-CEO office'});expect(within(office).getByRole('heading',{level:2,name:'Source-backed programme'})).toBeTruthy();
 expect(e.count('read_project_plan')).toBe(e.initialPlanReads);expect(e.count('read_project_direction')).toBe(0);expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
 const draft=within(office).getByRole('textbox',{name:'Direction to Meta-CEO'});fireEvent.change(draft,{target:{value:'Keep this exact unsent direction.\nSecond line.'}});
 fireEvent.click(within(office).getByText('Authored project objective'));fireEvent.click(within(office).getByRole('button',{name:'Read programme objective'}));
 await screen.findByText(source.responses.objective.body.plan.objective);expect(e.count('read_project_plan')).toBe(e.initialPlanReads+1);
 fireEvent.click(within(office).getByText('Accepted direction and history'));fireEvent.click(within(office).getByRole('button',{name:'Read Direction'}));
 expect((await screen.findByRole('article',{name:'Current accepted Direction'})).textContent).toContain(source.responses.direction.body.direction.current.answer);expect(e.count('read_project_direction')).toBe(1);
 fireEvent.click(within(office).getByRole('button',{name:'Review direction preview'}));const preview=screen.getByRole('region',{name:'Direction preview'});expect(preview.textContent).toContain('Keep this exact unsent direction.');fireEvent.keyDown(preview,{key:'Escape'});
 expect(document.activeElement).toBe(within(office).getByRole('button',{name:'Review direction preview'}));expect((draft as HTMLTextAreaElement).value).toBe('Keep this exact unsent direction.\nSecond line.');
 expect(within(office).getByRole('button',{name:'Send unavailable'}).hasAttribute('disabled')).toBe(true);
 fireEvent.click(within(office).getByRole('button',{name:'View project'}));expect(screen.queryByRole('region',{name:'Meta-CEO office'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Meta-CEO',exact:true}));expect((await screen.findByRole('textbox',{name:'Direction to Meta-CEO'}) as HTMLTextAreaElement).value).toBe('Keep this exact unsent direction.\nSecond line.');
 expect(e.invoke.mock.calls.filter(([n])=>/submit|prepare|pause|resume|consume|send|mission|current_window/.test(n))).toHaveLength(0);
});
it('withdraws late objective on actual auth departure',async()=>{const e=await setup(true);fireEvent.click(screen.getByText('Authored project objective'));fireEvent.click(screen.getByRole('button',{name:'Read programme objective'}));await waitFor(()=>expect(e.count('read_project_plan')).toBe(e.initialPlanReads+1));act(()=>e.notify({status:'signed_out',reason:null,acquisition:false,content:false}));await act(async()=>e.resolve(source.responses.objective.body));expect(document.body.textContent).not.toContain(source.responses.objective.body.plan.objective);});
it('withdraws late objective on actual Host replacement',async()=>{const e=await setup(true);fireEvent.click(screen.getByText('Authored project objective'));fireEvent.click(screen.getByRole('button',{name:'Read programme objective'}));await waitFor(()=>expect(e.count('read_project_plan')).toBe(e.initialPlanReads+1));window.MastermindMissionHost={...e.host};fireEvent.click(screen.getByRole('button',{name:'Today',exact:true}));await act(async()=>e.resolve(source.responses.objective.body));expect(document.body.textContent).not.toContain(source.responses.objective.body.plan.objective);});

it('keeps rootless Office source diagnostics in its closed header without duplicate h1 or a choose-Mission instruction',async()=>{await setup();const header=document.querySelector('.workspace-header')!;expect(header.classList.contains('workspace-header-quiet')).toBe(true);expect(header.querySelector('h1')).toBeNull();const details=header.querySelector('details')!;expect(details).not.toBeNull();expect(details.open).toBe(false);expect(details.querySelector('summary')!.textContent).toBe('Sources and access ');expect(document.querySelector('main > .notice')?.textContent??'').not.toContain('Choose a project');});
