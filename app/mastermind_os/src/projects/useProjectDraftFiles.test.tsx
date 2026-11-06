// @vitest-environment jsdom
/** Local selection/currency proof only. Server publication is qualified by the
 * separate actual source-owner fixture; these tests never synthesize a save. */
import {useState} from 'react';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {IDBFactory} from 'fake-indexeddb';
import {createNativeDraftRecoveryOwner} from '../auth-recovery/native-draft-owner';
import {createIndexedDbPendingPointerStore} from '../orchestration/indexeddb-pending-pointer-store';
import type {MissionHost} from '../host';
import {useProjectDraftFiles,type ProjectDraftFile,type ProjectDraftFilesProps} from './useProjectDraftFiles';
afterEach(cleanup);
function selected(raw='Literal 中文\r\n\\u4e2d'){
 const bytes=new TextEncoder().encode(raw),file=new File([bytes],'notes.md',{type:'text/markdown'});
 Object.defineProperty(file,'arrayBuffer',{value:async()=>bytes.slice().buffer,configurable:true});return file;
}
function setup(){
 let generation=1,allowed=true;
 const prepare=vi.fn(),submit=vi.fn(),read=vi.fn(),context=vi.fn(async ({action,workRef}:{action:string;workRef:string|null})=>({schema:'mastermind.workspace_source_operation_context.v1',selection:{action,work_ref:workRef},owner_context:{principal_scope:'a'.repeat(64)},can_inspect:true})),catalogue=vi.fn();
 const host={auth:{getState:()=>({status:'signed_in',acquisition:true})},invalidationGeneration:()=>generation,
  sourceOperations:{prepareSourceOperation:prepare,submitSourceOperation:submit,readSourceOperation:read,reconcileSourceOperation:read,advanceSourceOperation:vi.fn()},
  readSourceOperationContext:context,readProjectKnowledgeCatalogue:catalogue} as unknown as MissionHost;
 let privateScope='a'.repeat(64),clock=1000;
 const privacyInspect=vi.fn(async()=>({schema:'mastermind.native_draft_continuity.v1',owner_instance:'1'.repeat(32),privacy_epoch:1,phase:'QUALIFIED',cause:'OWNER_QUALIFIED',principal_scope:privateScope,valid_until_ms:5000}));
 const privacy=createNativeDraftRecoveryOwner({inspect:privacyInspect,sourceGeneration:()=>generation,signedIn:()=>allowed,now:()=>clock});
 Object.assign(host,{nativeDraftRecovery:privacy});
 const store=createIndexedDbPendingPointerStore(new IDBFactory());
 const onFiles=vi.fn();
 let last:ReturnType<typeof useProjectDraftFiles>;
 function Owner({locale='en'}:{locale?:'en'|'zh-CN'}){
  const [files,setFiles]=useState<readonly ProjectDraftFile[]>([]);
  last=useProjectDraftFiles({locale,host,store,isCurrent:()=>allowed,workRef:null,created:false,planningStarted:false,
   files,onFilesChange:value=>{onFiles(value);setFiles(value);},original:null,onOriginalChange:vi.fn()});
  return <>{last.control}{last.panel}<button onClick={()=>{}} disabled={last.blocksPlanning()}>Planning</button></>;
 }
 const view=render(<Owner/>);
 async function choose(file:File){fireEvent.click(screen.getByRole('button',{name:'Add files'}));await waitFor(()=>expect((screen.getByLabelText('Choose project files') as HTMLInputElement).disabled).toBe(false));fireEvent.change(screen.getByLabelText('Choose project files'),{target:{files:[file]}});}
 return {view,Owner,host,onFiles,prepare,submit,read,context,catalogue,choose,privacy,privacyInspect,setPrivateScope:(value:string)=>{privateScope=value;},expire:()=>{clock=5000;},get:()=>last!,revoke:()=>{allowed=false;},advance:()=>{generation++;}};
}
it('keeps selected literal File private, blocks planning, and performs no request or pointer effect',async()=>{
 const f=setup(),file=selected();await f.choose(file);
 await screen.findByText('notes.md');
 expect(f.onFiles).toHaveBeenCalledTimes(1);
 expect(f.onFiles.mock.calls[0][0][0]).toMatchObject({file,data:{content_utf8:'Literal 中文\r\n\\u4e2d'},request:null,savedRequestSha256:null});
 expect(screen.getByText('Selected file · Not added to the project yet')).toBeTruthy();
 expect((screen.getByRole('button',{name:'Planning'}) as HTMLButtonElement).disabled).toBe(true);
 for(const spy of [f.prepare,f.submit,f.read,f.catalogue])expect(spy).not.toHaveBeenCalled();
 expect(f.context).not.toHaveBeenCalled();expect(f.privacyInspect).toHaveBeenCalledTimes(3);
 expect(f.onFiles.mock.calls[0][0][0].origin.principalScope).toBe('a'.repeat(64));
 fireEvent.click(screen.getByRole('button',{name:'Remove'}));
 expect((screen.getByRole('button',{name:'Planning'}) as HTMLButtonElement).disabled).toBe(false);
});
it('keeps the actual File and chooser through locale rerender; selection never asserts upload',async()=>{
 const f=setup(),input=screen.getByLabelText('Choose project files'),file=selected();
 await f.choose(file);await screen.findByText('notes.md');
 f.view.rerender(<f.Owner locale="zh-CN"/>);
 expect(screen.getByLabelText('选择项目文件')).toBe(input);
 expect(f.onFiles.mock.calls[0][0][0].file).toBe(file);
 expect(screen.getByText('已选择文件 · 尚未添加到项目')).toBeTruthy();expect(f.prepare).not.toHaveBeenCalled();
});
it.each(['generation','revoke'] as const)('discards a late File read after %s changes without reauthorizing the old handler',async change=>{
 const f=setup(),file=selected('text');let finish!:(bytes:ArrayBuffer)=>void;
 Object.defineProperty(file,'arrayBuffer',{value:()=>new Promise<ArrayBuffer>(resolve=>{finish=resolve;}),configurable:true});
 await f.choose(file);
 await waitFor(()=>expect(typeof finish).toBe('function'));
 if(change==='generation'){f.advance();f.view.rerender(<f.Owner/>);}else f.revoke();
 finish(new TextEncoder().encode('text').buffer);
 await waitFor(()=>expect(f.onFiles).not.toHaveBeenCalled());
 expect(screen.queryByText('notes.md')).toBeNull();expect(f.prepare).not.toHaveBeenCalled();
});
it('rejects an oversized actual selection without losing an existing staged File',async()=>{
 const f=setup();await f.choose(selected());await screen.findByText('notes.md');
 const huge=new File(['x'.repeat(32769)],'huge.md',{type:'text/markdown'});
 fireEvent.change(screen.getByLabelText('Choose project files'),{target:{files:[huge]}});
 await screen.findByRole('status');expect(screen.getByText('notes.md')).toBeTruthy();expect(f.onFiles).toHaveBeenCalledTimes(1);expect(f.submit).not.toHaveBeenCalled();
});

it('does not read or attribute a private File before actual origin identity; late identity cannot adopt old input',async()=>{
 const f=setup(),file=selected();const read=vi.fn(async()=>new TextEncoder().encode('text').buffer);
 Object.defineProperty(file,'arrayBuffer',{value:read,configurable:true});
 fireEvent.change(screen.getByLabelText('Choose project files'),{target:{files:[file]}});
 await waitFor(()=>expect(read).not.toHaveBeenCalled());expect((screen.getByLabelText('Choose project files') as HTMLInputElement).disabled).toBe(true);expect(f.onFiles).not.toHaveBeenCalled();
 let deliver!:(value:unknown)=>void;
 f.privacyInspect.mockImplementationOnce(()=>new Promise(resolve=>{deliver=resolve;}) as never);
 fireEvent.click(screen.getByRole('button',{name:'Add files'}));f.advance();f.view.rerender(<f.Owner/>);
 deliver({schema:'mastermind.native_draft_continuity.v1',owner_instance:'1'.repeat(32),privacy_epoch:1,phase:'QUALIFIED',cause:'OWNER_QUALIFIED',principal_scope:'b'.repeat(64),valid_until_ms:5000});
 await waitFor(()=>expect((screen.getByLabelText('Choose project files') as HTMLInputElement).disabled).toBe(true));
 expect(read).not.toHaveBeenCalled();expect(f.onFiles).not.toHaveBeenCalled();expect(f.prepare).not.toHaveBeenCalled();
});

it('never late-adopts an earlier private File into another principal or a forged native facet',async()=>{
 const f=setup();await f.choose(selected());await screen.findByText('notes.md');
 f.setPrivateScope('b'.repeat(64));fireEvent.click(screen.getByRole('button',{name:'Add files'}));
 await screen.findByText('The file draft is held for its original signed-in identity.');
 expect(screen.queryByText('notes.md')).toBeNull();expect(f.onFiles).toHaveBeenCalledTimes(1);expect(f.prepare).not.toHaveBeenCalled();
});
it('masks an expired private return proof without creating or publishing anything',async()=>{
 const f=setup();await f.choose(selected());await screen.findByText('notes.md');f.expire();f.view.rerender(<f.Owner/>);
 expect(screen.queryByText('notes.md')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Check file draft access'}));
 await screen.findByText('The file draft is held for its original signed-in identity.');
 expect(f.onFiles).toHaveBeenCalledTimes(1);expect(f.submit).not.toHaveBeenCalled();
});
