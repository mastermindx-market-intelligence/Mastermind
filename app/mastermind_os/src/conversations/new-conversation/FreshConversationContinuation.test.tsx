// @vitest-environment jsdom
// Pure adapter over genuine A4 windows/frames; authority and transport inert.
import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import type {OperationPointer,OwnerContext,PendingPointerStore} from "../../orchestration/operation-controller";
import {decodeFreshConversationWindow} from "../fresh-conversation-reference";
import {createFreshConversationAttendedBinding,type FreshConversationOriginalRead} from "./fresh-conversation-attended-binding";
import {FreshConversationContinuation,type FreshConversationContinuationProps} from "./FreshConversationContinuation";
import fixture from "./fixtures/fresh-conversation-recovery-owner.json";
afterEach(cleanup);
function setup(){
  const owner:OwnerContext={principalScope:"adapter-unit-owner",generation:"auth-1"};
  let pointer:OperationPointer|null=null,current=true;
  const source=decodeFreshConversationWindow(fixture.initial_read,fixture.initial_read.reference);
  const currentSource=()=>current;
  if(!source.initial_result||!source.locator.job_id||!source.locator.attempt_id)throw Error("Actual fixture is incomplete");
  const initial:FreshConversationOriginalRead={selection:{work_ref:source.reference.work_ref,operation_key:fixture.request.operation_key},
    result:source.initial_result,locator:{work_ref:source.locator.work_ref,root_job_id:source.locator.root_job_id,
      job_id:source.locator.job_id,attempt_id:source.locator.attempt_id},current:currentSource};
  const store:PendingPointerStore={read:async()=>pointer,reserve:async(_scope,next)=>{
    if(pointer)return{reserved:false,pointer};pointer=next;return{reserved:true};
  },clearIfEqual:async(_scope,held)=>{if(pointer===held){pointer=null;return true;}return false;}};
  const transport={consume:vi.fn(async()=>fixture.lost_consume),consumeStatus:vi.fn(async()=>fixture.consume_status),
    turnPreview:vi.fn(async()=>fixture.turn_preview),turn:vi.fn(async()=>fixture.turn),turnStatus:vi.fn(async()=>fixture.status),turnRead:vi.fn(async()=>fixture.turn_read)};
  const binding=createFreshConversationAttendedBinding({owner:()=>owner,canModify:()=>true,store,transport,readInitial:async()=>initial});
  const props:FreshConversationContinuationProps={locale:"en",active:true,binding,host:{},authGeneration:1,
    entry:{kind:"reference",window:source,current:currentSource},message:fixture.turn_request.message,draftOwner:owner,
    onMessageChange:vi.fn(),onUnresolvedChange:vi.fn()};
  return{props,source,initial,currentSource,transport,peek:()=>pointer,setCurrent:(value:boolean)=>{current=value;}};
}
it("preserves the exact reference selector and source witness; no legacy key is invented",async()=>{
  const h=setup();render(<FreshConversationContinuation {...h.props}/>);
  await waitFor(()=>expect((screen.getByRole("button",{name:"Keep first response"}) as HTMLButtonElement).disabled).toBe(false));
  expect(h.transport.consume).not.toHaveBeenCalled();fireEvent.click(screen.getByRole("button",{name:"Keep first response"}));
  await waitFor(()=>expect(h.transport.consume).toHaveBeenCalledTimes(1));
  const calls=h.transport.consume.mock.calls as unknown as readonly[Record<string,unknown>,AbortSignal][];
  expect(calls[0]?.[0]).toEqual(fixture.consume_request);expect(calls[0]?.[0]).not.toHaveProperty("operation_key");
  expect(h.peek()?.kind).toBe("conversation_consume");expect(h.props.onUnresolvedChange).toHaveBeenLastCalledWith(true);
});
it("passes an actual initial-key read through without converting it to a reference",async()=>{
  const h=setup();render(<FreshConversationContinuation {...h.props} entry={{kind:"initial",read:h.initial}}/>);
  await waitFor(()=>expect((screen.getByRole("button",{name:"Keep first response"}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"Keep first response"}));await waitFor(()=>expect(h.transport.consume).toHaveBeenCalledTimes(1));
  const calls=h.transport.consume.mock.calls as unknown as readonly[Record<string,unknown>,AbortSignal][];
  expect(calls[0]?.[0]).toEqual({...h.initial.selection,initial_digest:h.initial.result.digest});
  expect(calls[0]?.[0]).not.toHaveProperty("reference");
});
it("leaves the actual archived recorded window to its existing readonly reader",async()=>{
  const h=setup();const archived=decodeFreshConversationWindow(fixture.archived_read,fixture.initial_read.reference);
  render(<FreshConversationContinuation {...h.props} entry={{kind:"reference",window:archived,current:h.currentSource}}/>);
  await waitFor(()=>expect(h.props.onUnresolvedChange).toHaveBeenLastCalledWith(false));
  expect(screen.queryByRole("heading",{name:"Continue this conversation"})).toBeNull();
  for(const fn of Object.values(h.transport))expect(fn).not.toHaveBeenCalled();
});
it("a revoked source window cannot offer Keep/Review/Send and unmount does not clear its original",async()=>{
  const h=setup();const mounted=render(<FreshConversationContinuation {...h.props}/>);
  await waitFor(()=>expect((screen.getByRole("button",{name:"Keep first response"}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"Keep first response"}));await waitFor(()=>expect(h.peek()).not.toBeNull());const original=h.peek();
  h.setCurrent(false);mounted.rerender(<FreshConversationContinuation {...h.props}/>);
  expect(screen.queryByRole("button",{name:"Keep first response"})).toBeNull();expect(screen.queryByRole("button",{name:"Review message"})).toBeNull();
  expect(screen.queryByRole("button",{name:"Send message"})).toBeNull();mounted.unmount();
  expect(h.peek()).toEqual(original);expect(h.props.onUnresolvedChange).toHaveBeenLastCalledWith(false);
});
