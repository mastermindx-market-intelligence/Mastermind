// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
/** Real App/NativeClient/Host/IDB; source replies are the unchanged whole6cb8
 * same-run recording. Inert native auth/continuity premises are explicit. */
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {App} from './App';
import {createFileConsumerFixture,fixture} from './projects/project-draft-files-consumer-fixture';
let dispose=()=>{};let lastCalls:{command:string;args:unknown;sequence:number|null}[]=[];
afterEach(()=>{console.info('FILE_APP_BOUNDARY',lastCalls.map(c=>[c.command,c.sequence]));console.info('FILE_APP_PANEL',screen.queryByRole('region',{name:'Project files'})?.textContent);cleanup();dispose();vi.restoreAllMocks();delete window.MastermindMissionHost;delete (window as unknown as {__TAURI_INTERNALS__?:unknown}).__TAURI_INTERNALS__;history.replaceState(null,'','/os/');});
async function setup(negative?:{wrongOrigin?:boolean}){
 Object.assign(window,{__TAURI_INTERNALS__:{}});
 vi.spyOn(Date,'now').mockReturnValue(fixture.recorded_at_ms);
 const bytes=[0xcc,0xbb];const actual=crypto.getRandomValues.bind(crypto);
 vi.spyOn(crypto,'getRandomValues').mockImplementation((array:ArrayBufferView<ArrayBuffer>)=>{const a=array as unknown as Uint8Array;if(a instanceof Uint8Array&&a.byteLength===20){a.fill(bytes.shift()??0xee);return array;}return actual(array);});
 const h=await createFileConsumerFixture(new IDBFactory(),negative);lastCalls=h.calls;const page=render(<App/>);dispose=()=>{page.unmount();h.dispose();};
 fireEvent.click(await screen.findByRole('button',{name:'Projects'}));fireEvent.click(await screen.findByRole('button',{name:'New project'}));
 await screen.findByLabelText('Your goal');return h;
}
async function stage(){
 const spec=fixture.consumer_inputs.file,bytes=new TextEncoder().encode(spec.content_utf8),file=new File([bytes],spec.display_name,{type:spec.media_type});
 Object.defineProperty(file,'arrayBuffer',{value:async()=>bytes.slice().buffer});
 fireEvent.click(screen.getByRole('button',{name:'Add files'}));await waitFor(()=>expect((screen.getByLabelText('Choose project files') as HTMLInputElement).disabled).toBe(false));
 fireEvent.change(screen.getByLabelText('Choose project files'),{target:{files:[file]}});await screen.findByText(spec.display_name);return file;
}
async function createProject(){
 fireEvent.focus(screen.getByLabelText('Your goal'));await waitFor(()=>expect((screen.getByLabelText('Your goal') as HTMLTextAreaElement).readOnly).toBe(false));
 fireEvent.change(screen.getByLabelText('Your goal'),{target:{value:fixture.consumer_inputs.create_goal}});
 fireEvent.click(screen.getByRole('button',{name:'Options'}));fireEvent.click(await screen.findByRole('button',{name:'Load project options'}));
 fireEvent.click(await screen.findByRole('radio',{name:'Mastermind OS delivery'}));fireEvent.click(screen.getByRole('button',{name:'Prepare preview'}));
 fireEvent.click(await screen.findByRole('button',{name:'Create project'}));
 fireEvent.click(await screen.findByRole('button',{name:'Check project creation'}));await screen.findAllByText('Project created.');
}
async function clickReady(name:string){const button=await screen.findByRole('button',{name});await waitFor(()=>expect((button as HTMLButtonElement).disabled).toBe(false));fireEvent.click(button);}
async function publishFile(expectConfirmed=true){
 await clickReady('Check current file access');
 await clickReady('Prepare file preview');
 await clickReady('Add file to project');
 await clickReady('Check original file request');
 await clickReady('Check current file access');if(expectConfirmed)await screen.findByText(/Added to the project/);
}
async function plan(){
 fireEvent.click(screen.getByRole('radio',{name:'Plan'}));
 fireEvent.change(screen.getByLabelText('Initial request'),{target:{value:fixture.consumer_inputs.create_goal}});
 fireEvent.click(screen.getByRole('button',{name:'Send initial planning request'}));
}
it('stages privately before CREATE, preserves same File through Back, publishes explicitly, then admits planning once',async()=>{
 const h=await setup();await stage();expect(h.calls.filter(c=>c.command==='source_operation_prepare')).toHaveLength(0);
 fireEvent.click(screen.getByRole('button',{name:'Back to projects'}));fireEvent.click(await screen.findByRole('button',{name:'New project'}));await screen.findByText('Context.md');
 await createProject();expect(screen.queryByRole('button',{name:'Send initial planning request'})).toBeNull();expect(screen.getByText('Add all selected files to the project, or remove unsent files, before initial planning.')).toBeTruthy();
 await publishFile();await plan();await screen.findByText('Planning request accepted.');
 const planning=h.calls.filter(c=>c.command==='executive_project_planning'&&(c.args as {operation:string}).operation==='submit');expect(planning).toHaveLength(1);
 expect((planning[0].args as {arguments:{operation_key:string}}).arguments.operation_key).toBe(fixture.identities.planning_operation_key);
 expect(h.calls.filter(c=>c.command==='source_operation_submit')).toHaveLength(2);
 expect(location.href).toContain('project_file_original');expect(location.href).not.toContain('Context');expect(location.href).not.toContain('content_utf8');
});
it('withdraws File bytes and effects on passive auth loss; no native or source authority is synthesized',async()=>{
 const h=await setup();await stage();await act(async()=>{h.expire();});
 expect(screen.queryByText('Context.md')).toBeNull();expect(h.calls.filter(c=>c.command==='source_operation_prepare'||c.command==='source_operation_submit')).toHaveLength(0);
});
it('no-render global Host replacement refuses existing preview gesture with staged File',async()=>{
 const h=await setup();await stage();fireEvent.focus(screen.getByLabelText('Your goal'));await waitFor(()=>expect((screen.getByLabelText('Your goal') as HTMLTextAreaElement).readOnly).toBe(false));fireEvent.change(screen.getByLabelText('Your goal'),{target:{value:fixture.consumer_inputs.create_goal}});
 fireEvent.click(screen.getByRole('button',{name:'Options'}));fireEvent.click(await screen.findByRole('button',{name:'Load project options'}));fireEvent.click(await screen.findByRole('radio',{name:'Mastermind OS delivery'}));
 window.MastermindMissionHost={} as typeof window.MastermindMissionHost;fireEvent.click(screen.getByRole('button',{name:'Prepare preview'}));
 expect(h.calls.filter(c=>c.command==='source_operation_prepare')).toHaveLength(0);
});

it('retains genuine File publication and planning UNKNOWN keys across Back; checks originals without second submit',async()=>{
 const h=await setup();await stage();await createProject();h.lose('source_operation_submit');await publishFile();
 h.lose('planning');await plan();await waitFor(()=>expect(h.calls.filter(c=>c.command==='executive_project_planning'&&(c.args as {operation:string}).operation==='submit')).toHaveLength(1));await waitFor(()=>expect((screen.getByRole('button',{name:'Check original planning request'}) as HTMLButtonElement).disabled).toBe(false));
 fireEvent.click(screen.getByRole('button',{name:'Back to projects'}));fireEvent.click(await screen.findByRole('button',{name:'Continue project setup'}));
 await clickReady('Check planning status');await waitFor(()=>expect(location.href).toContain('project_planning_job='));await clickReady('Check original project request');await screen.findByText('Planning request accepted.');
 expect(h.calls.filter(c=>c.command==='source_operation_submit')).toHaveLength(2);
 expect(h.calls.filter(c=>c.command==='executive_project_planning'&&(c.args as {operation:string}).operation==='submit')).toHaveLength(1);
});
it('does not substitute public request digest for the actual File recipe origin or allow planning',async()=>{
 const h=await setup({wrongOrigin:true});await stage();await createProject();await publishFile(false);
 await waitFor(()=>expect(h.calls.filter(c=>c.command==='read_project_knowledge_catalogue')).toHaveLength(2));
 expect(screen.queryByText(/Added to the project/)).toBeNull();expect(screen.queryByRole('button',{name:'Send initial planning request'})).toBeNull();
 expect(h.calls.filter(c=>c.command==='executive_project_planning')).toHaveLength(0);
});
