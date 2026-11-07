// @vitest-environment jsdom
/** UI paging/currentness uses explicit synthetic pages derived from the actual
 * signed-source fixture. Runtime multi-turn and UTF-8 proof lives in Python. */
import {act,cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import fixture from '../fixtures/project-fresh-conversation-owner.json';
import {canonicalJson,sha256Hex} from '../orchestration/operation-key';
import {decodeFreshConversationReadRequest,decodeFreshConversationReference,decodeFreshConversationWindow} from './fresh-conversation-reference';
import {createProjectConversationCatalogueOwner,type ProjectConversationCatalogueTransport} from './project-conversation-catalogue-owner';
import {ProjectConversations,type ProjectConversationsProps} from './ProjectConversations';

afterEach(cleanup);
const work=fixture.catalogue.work_ref,reference=fixture.catalogue.entries[0]!.reference;
function turn(index:number){
 const value=structuredClone(fixture.archived_read.turns[0]!);
 value.turn_key='history-turn-'+index;value.message='Saved message '+index;
 value.result.envelope.summary='Saved answer '+index;
 value.result.digest=sha256Hex(canonicalJson(value.result.envelope));return value;
}
function page(before:number|null,next:number|null,indices:number[]){
 return {...structuredClone(fixture.archived_read),schema:'mastermind.fresh_conversation_window.v2',
   state:'RETAINED',epoch:fixture.initial_read.epoch,
   initial_result:before===null?fixture.archived_read.initial_result:null,
   initial_digest:fixture.archived_read.initial_result.digest,
   turns:indices.map(turn),page:{kind:before===null?'initial':'history',before_event_id:before,next_before_event_id:next}};
}
function make(){
 const state={auth:1,latest:3};
 const listeners=new Set<()=>void>();
 const transport:ProjectConversationCatalogueTransport={
   context:()=>({workRef:work,principalScope:'1'.repeat(64),generation:'same-project'}),
   authGeneration:()=>state.auth,available:()=>true,subscribe(listener){listeners.add(listener);return()=>{listeners.delete(listener);};},
   catalogue:vi.fn(async()=>{throw Error('legacy population not supplied');}),read:vi.fn(async()=>{throw Error('not a legacy request');}),
   freshReferences:vi.fn(async()=>fixture.catalogue),
   readFreshReference:vi.fn(async request=>request.before_event_id===300?page(300,200,[2]):
     request.before_event_id===200?page(200,null,[1]):page(null,300,[state.latest])),
 };
 const owner=createProjectConversationCatalogueOwner({transport,workRef:()=>work,selectionGeneration:()=>'one'});
 return {state,transport,owner,notify:()=>{for(const listener of listeners)listener();}};
}

it('keeps cursors outside immutable reference identity and rejects non-progressing or unqualified pages',()=>{
 const first=decodeFreshConversationWindow(page(null,300,[3]),reference);
 expect(first.initial_result?.digest).toBe(fixture.initial_read.initial_result.digest);
 const request={...reference,before_event_id:300};
 expect(decodeFreshConversationReadRequest(request,work).before_event_id).toBe(300);
 expect(()=>decodeFreshConversationReference(request,work)).toThrow();
 const older=decodeFreshConversationWindow(page(300,200,[2]),request);
 expect(older.initial_result).toBeNull();expect(older.turns[0]!.result?.envelope.summary).toBe('Saved answer 2');
 for(const bad of [
   {...page(null,300,[3]),initial_result:null},
   {...page(300,200,[2]),initial_digest:'f'.repeat(64)},
   page(300,300,[2]),page(300,301,[2]),page(300,200,[]),
   {...page(300,200,[2]),page:{kind:'initial',before_event_id:300,next_before_event_id:200}},
   {...page(300,200,[2]),reference:request},
   page(300,200,[2,2]),
 ])expect(()=>decodeFreshConversationWindow(bad,bad.page.before_event_id===null?reference:request)).toThrow();
 for(const before_event_id of [null,true,0,-1,1.5,'300',Number.MAX_SAFE_INTEGER+1]){
   expect(()=>decodeFreshConversationReadRequest({...reference,before_event_id},work)).toThrow();
 }
});

it('older pages keep the initial witness, require its issued cursor and reject late auth results',async()=>{
 const s=make(),signal=new AbortController().signal;
 await s.owner.freshCatalogue({workRef:work,signal});
 const initial=await s.owner.readFresh(reference,signal);
 expect(s.owner.currentFresh(initial)).toBe(true);
 await expect(s.owner.readFreshOlder(initial,299,signal)).rejects.toThrow();
 expect(s.transport.readFreshReference).toHaveBeenCalledTimes(1);
 const older=await s.owner.readFreshOlder(initial,300,signal);
 expect(older.turns[0]!.message).toBe('Saved message 2');expect(s.owner.currentFresh(initial)).toBe(true);
 await expect(s.owner.readFreshOlder(initial,300,signal)).rejects.toThrow();
 let finish!:(value:unknown)=>void;
 vi.mocked(s.transport.readFreshReference!).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 const pending=s.owner.readFreshOlder(initial,200,signal).catch(error=>error);
 s.state.auth++;s.notify();finish(page(200,null,[1]));
 expect(await pending).toBeInstanceOf(Error);expect(s.owner.currentFresh(initial)).toBe(false);
 s.owner.dispose();
});

it('loads complete earlier messages and refreshes the same open conversation after a send',async()=>{
 const s=make();let supplied:Parameters<NonNullable<ProjectConversationsProps['renderFreshContinuation']>>[0]|null=null;
 render(<ProjectConversations workRef={work} owner={s.owner} renderFreshContinuation={source=>{supplied=source;return <p>Current composer</p>;}}/>);
 fireEvent.click(screen.getByRole('button',{name:'Read project conversations'}));
 fireEvent.click(await screen.findByRole('button',{name:'Open'}));
 await screen.findByText('Saved answer 3');const initial=supplied!;
 fireEvent.click(screen.getByRole('button',{name:'Load earlier messages'}));
 await screen.findByText('Saved answer 2');expect(initial.current()).toBe(true);expect(supplied).toBe(initial);
 expect(screen.queryByText('Saved message 3')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Load earlier messages'}));
 await screen.findByText('Saved answer 1');
 expect(screen.getByText('Saved message 1')).toBeTruthy();
 for(const index of [2,3])expect(screen.queryByText('Saved message '+index)).toBeNull();
 expect(screen.queryByRole('button',{name:'Load earlier messages'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Return to latest messages'}));
 await screen.findByText('Saved answer 3');expect(initial.current()).toBe(false);
 const latest=supplied!;s.state.latest=4;act(()=>latest.refresh());
 await screen.findByText('Saved answer 4');
 await waitFor(()=>expect(supplied!.current()).toBe(true));
 expect(initial.current()).toBe(false);
 expect(screen.getByRole('button',{name:'Back to conversations'})).toBeTruthy();
 expect(screen.queryByRole('textbox',{name:'Find in these conversations'})).toBeNull();
 expect(s.transport.freshReferences).toHaveBeenCalledTimes(1);
 expect(s.transport.readFreshReference).toHaveBeenCalledTimes(5);
});

it('replaces the visible history page and returns to latest without accumulating complete envelopes',async()=>{
 const s=make();
 vi.mocked(s.transport.readFreshReference!).mockImplementation(async request=>
  request.before_event_id===300?page(300,200,[9,10,11,12,13,14,15,16]):
  request.before_event_id===200?page(200,null,[1,2,3,4,5,6,7,8]):
  page(null,300,[17,18,19,20,21,22,23,24]));
 render(<ProjectConversations workRef={work} owner={s.owner}/>);
 fireEvent.click(screen.getByRole('button',{name:'Read project conversations'}));
 fireEvent.click(await screen.findByRole('button',{name:'Open'}));
 await screen.findByText('Saved answer 24');
 expect(screen.getAllByText(/^Saved message /)).toHaveLength(8);
 fireEvent.click(screen.getByRole('button',{name:'Load earlier messages'}));
 await screen.findByText('Saved answer 16');
 expect(screen.getAllByText(/^Saved message /)).toHaveLength(8);
 expect(screen.queryByText('Saved message 24')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Load earlier messages'}));
 await screen.findByText('Saved answer 8');
 expect(screen.getAllByText(/^Saved message /)).toHaveLength(8);
 expect(screen.queryByText('Saved message 16')).toBeNull();
 expect(screen.queryByRole('button',{name:'Load earlier messages'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Return to latest messages'}));
 await screen.findByText('Saved answer 24');
 expect(screen.getAllByText(/^Saved message /)).toHaveLength(8);
 expect(screen.queryByText('Saved message 8')).toBeNull();
 expect(s.transport.readFreshReference).toHaveBeenCalledTimes(4);s.owner.dispose();
});
