// @vitest-environment jsdom
import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {createTerminalSharingHost} from '../terminal/terminal-sharing-host';
import feed from './fixtures/terminal-sharing-request-feed.json';
import {TerminalSharingInbox} from './TerminalSharingInbox';

afterEach(cleanup);

it('withdraws the prior handoff presentation when its own Terminal session identity changes at the same generation', async()=>{
 let session={state:'SIGNED_IN',generation:2,reason:null,available:true,...feed.viewer};
 let changed:((value:unknown)=>void)|undefined;
 const invoke=vi.fn(async(command:string,args?:Record<string,unknown>)=>{
  if(command==='terminal_session_status')return session;
  if(command==='read_terminal_sharing_requests')return {...structuredClone(feed),viewer:{principal_scope:session.principal_scope,session_scope:session.session_scope}};
  if(command==='open_terminal_sharing_request'){
   const selection=args?.selection as Record<string,unknown>;
   return {schema:'mastermind.terminal_sharing_handoff.v1',request_ref:selection.request_ref,
    revision:1,delivery_id:selection.delivery_id,outcome:'HANDOFF_REQUESTED'};
  }
  throw new Error('Inert fixture: no other native command');
 });
 const host=await createTerminalSharingHost(invoke,async(_event,listener)=>{changed=listener;return()=>{};});
 try{
  render(<TerminalSharingInbox locale="en" host={host}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Continue in Terminal'}));
  await screen.findByText('Continue in Terminal to review this request.',{exact:true});
  await act(async()=>{
   session={...session,session_scope:'9a'.repeat(32)};
   changed?.(session);
  });
  await screen.findByText(feed.requests[0].delivery.title);
  expect(screen.queryByText('Continue in Terminal to review this request.',{exact:true})).toBeNull();
  expect(invoke.mock.calls.filter(([name])=>name==='open_terminal_sharing_request')).toHaveLength(1);
 }finally{host.dispose();}
});
