// @vitest-environment jsdom
import {act,cleanup,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {App} from './App';
import {bindMissionHost,createNativeClient} from './host';
import {controlRoomFixture} from './test-fixtures';
import programs from './fixtures/programs-available-workspace-service.json';
import archive from './projects/archive/fixtures/project-archive-owner.json';
const signed={status:'signed_in',reason:null,acquisition:true,content:true};
beforeEach(async()=>{history.replaceState(null,'','/os/');delete window.MastermindMissionHost;delete (window as any).__TAURI_INTERNALS__;
 const {webcrypto}=await vi.importActual<{webcrypto:Crypto}>('node:crypto');vi.stubGlobal('crypto',webcrypto);});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();delete window.MastermindMissionHost;});
async function setup(pending=false,legacy=false){
 const room=controlRoomFixture(),sample=structuredClone(room.work[0]);
 room.work=archive.catalogue.work_refs.map((ref,i)=>{const row=structuredClone(sample);row.work_ref=ref;row.agent_os.workstream=ref.slice(3);
  row.agent_os.title=i===0?archive.sample.items[0].title:'Unarchived rootless project';row.executive.jobs=[];row.bindings=[];return row;});
 room.autonomy.responsibilities=[];
 const collection={...structuredClone(programs),control_room:room};
 collection.source_observation.control_room.document_digest=archive.catalogue.document_digest;
 let notify!:(event:{payload:unknown})=>void,finish!:(value:unknown)=>void;
 const held=new Promise(resolve=>{finish=resolve;});
 const invoke=vi.fn(async(command:string,args?:unknown)=>{
  if(command==='auth_status')return signed;
  if(command==='read_programs')return structuredClone(collection);
  if(command==='read_project_archive'){expect(args).toBeUndefined();return pending?held:structuredClone(archive);}
  throw new Error('Unexpected fixture command');
 });
 const raw=await createNativeClient(invoke as never,async(_name,listener)=>{notify=listener;return()=>{};});
 const host=bindMissionHost(raw);
 if(legacy){delete host.readProjectArchive;delete host.readProjectArchivePage;}
 window.MastermindMissionHost=host;
 render(<App/>);fireEvent.click(screen.getByRole('button',{name:'Projects'}));
 await screen.findByRole('button',{name:'Open project Unarchived rootless project'});
 return {invoke,finish,notify};
}
it('opens an actual fixed-port archived record as rootless read-only inspection without Mission or command promotion',async()=>{
 const e=await setup();
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_project_archive')).toHaveLength(0);
 fireEvent.click(screen.getByRole('button',{name:'Archived projects'}));
 const open=await screen.findByRole('button',{name:'Open read-only '+archive.sample.items[0].title});
 fireEvent.click(open);
 expect(await screen.findByRole('article',{name:'Archived record (read-only)'})).toHaveProperty('textContent',expect.stringContaining(archive.sample.items[0].objective));
 expect(within(screen.getByRole('article',{name:'Archived record (read-only)'})).queryByRole('button',{name:/^(Pause new work|Resume new work|Restore|Create project|New project|Adopt|Start project)$/})).toBeNull();
 expect(e.invoke.mock.calls.filter(([name])=>/mission|project_admission|project_plan|project_direction|project_session|submit|prepare|launch|create|adopt|pause|resume/.test(name))).toHaveLength(0);
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_project_archive')).toHaveLength(1);
 expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
 fireEvent.click(screen.getByRole('button',{name:'Back to archived list'}));
 fireEvent.click(screen.getByRole('button',{name:'Back to projects'}));
 expect(screen.getByRole('button',{name:'Open project Unarchived rootless project'})).toBeTruthy();
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_project_archive')).toHaveLength(1);
});
it('withdraws an in-flight archive owner read on actual auth change and rejects its late body',async()=>{
 const e=await setup(true);fireEvent.click(screen.getByRole('button',{name:'Archived projects'}));
 await waitFor(()=>expect(e.invoke.mock.calls.filter(([name])=>name==='read_project_archive')).toHaveLength(1));
 act(()=>e.notify({payload:{status:'signed_out',reason:'AUTHENTICATION_REQUIRED',acquisition:false,content:false}}));
 await act(async()=>e.finish(structuredClone(archive)));
 expect(screen.queryByRole('button',{name:'Open read-only '+archive.sample.items[0].title})).toBeNull();
 expect(document.body.textContent).not.toContain(archive.sample.items[0].archive.archived_by);
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_project_archive')).toHaveLength(1);
});
it('preserves the existing rootless catalogue view for an older host without archive methods',async()=>{
 const e=await setup(false,true);
 expect(screen.getByRole('heading',{name:'Your projects, in perspective.'})).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Archived projects'})).toBeNull();
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_project_archive')).toHaveLength(0);
});
it.each([
 {host:'native',legacy:false,collection:'Projects'},
 {host:'legacy',legacy:true,collection:'Your projects, in perspective.'},
])('returns to the Projects collection from Today View all after a rootless project was opened ($host host)',async({legacy,collection})=>{
 const e=await setup(false,legacy);
 fireEvent.click(screen.getByRole('button',{name:'Open project Unarchived rootless project'}));
 expect(screen.getByRole('heading',{level:1,name:'Unarchived rootless project'})).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'Today'}));
 fireEvent.click(screen.getByRole('button',{name:'View all'}));
 expect(screen.getByRole('heading',{level:1,name:collection})).toBeTruthy();
 expect(screen.getByRole('button',{name:'Open project Unarchived rootless project'})).toBeTruthy();
 expect(screen.queryByRole('heading',{level:1,name:'Unarchived rootless project'})).toBeNull();
 expect(e.invoke.mock.calls.filter(([name])=>name==='read_project_archive')).toHaveLength(0);
});
