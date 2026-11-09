// @vitest-environment jsdom
import userEvent from "@testing-library/user-event";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AutonomyPanel } from "./AutonomyPanel";
import {
  AUTONOMY_READ_BODY_SCHEMA,
  AUTONOMY_SOURCE_OBSERVATION_SCHEMA,
  AUTONOMY_RUNTIME_RECEIPT_SCHEMA,
} from "./autonomy-policy";

// Inert source DTO fixtures only: fixed hex strings, no crypto, no grants.
const SELECTION={workRef:"WS:FIXTURE",rootJobId:"JOB-7"};
const BODY_SELECTION={work_ref:"WS:FIXTURE",root_job_id:"JOB-7"};
const IDENTITY="a".repeat(32),DIGEST="b".repeat(64);
const BODY=()=>({schema:AUTONOMY_READ_BODY_SCHEMA,selection:{...BODY_SELECTION},availability:"AVAILABLE",
 reason_codes:[],source_observation:{schema:AUTONOMY_SOURCE_OBSERVATION_SCHEMA,state:"SAME",
  selection:{...BODY_SELECTION},
  runtime:{schema:AUTONOMY_RUNTIME_RECEIPT_SCHEMA,state:"SAME",source_identity:IDENTITY,before:11,after:11},
  control_room:{instance_before:"instance-fixture",instance_after:"instance-fixture",publication_before:4,publication_after:4,
   document_digest:DIGEST,source_validity_digest:DIGEST,cache_currentness_digest:DIGEST}},
 policy:{scope:"ADMITTED_ROOT",policy_sha:"c".repeat(64),source_sha256:"d".repeat(64),
  plan_digest:"e".repeat(64),reservation_digest:"f".repeat(64),
  limits:{schema_version:1,max_children_total:4,max_fan_out_per_parent:3,max_depth:6,
   max_attempts_per_orchestration_job:2,max_repair_rounds:1,max_review_attempts_per_job:3,
   review_job_attempt_limit:5,allowed_child_cost_classes:["standard","deep_research"]}}});
const UNAVAILABLE_BODY=()=>({schema:AUTONOMY_READ_BODY_SCHEMA,selection:{...BODY_SELECTION},
 availability:"UNAVAILABLE",reason_codes:["SOURCE_CHANGED"],source_observation:null,policy:null});
const deferred=()=>{let resolve!:(v:unknown)=>void;let reject!:(e:unknown)=>void;
 const promise=new Promise<unknown>((res,rej)=>{resolve=res;reject=rej;});return{promise,resolve,reject};};
function setup(){
 const read=vi.fn((_request:{work_ref:string;root_job_id:string;signal:AbortSignal})=>new Promise<unknown>(()=>{}));
 const props=()=>({selection:{...SELECTION},canRead:true,sourceGeneration:1,read});
 return{read,props};
}
const readButton=()=>screen.getByRole("button",{name:"Read existing limits"}) as HTMLButtonElement;
afterEach(()=>{cleanup();vi.restoreAllMocks();});

describe("AutonomyPanel",()=>{
 it("performs no automatic reads and publishes the exact selected payload on one explicit click",async()=>{
  const e=setup(),flight=deferred();e.read.mockImplementationOnce(()=>flight.promise);
  const ui=render(<AutonomyPanel {...e.props()}/>);
  expect(e.read).not.toHaveBeenCalled();
  await act(async()=>{});
  expect(e.read).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("Existing plan limits")).toBeNull();
  const user=userEvent.setup();
  await user.click(readButton());
  expect(e.read).toHaveBeenCalledTimes(1);
  const request=e.read.mock.calls[0][0];
  expect(request).toMatchObject({work_ref:"WS:FIXTURE",root_job_id:"JOB-7"});
  expect(Object.keys(request).sort()).toEqual(["root_job_id","signal","work_ref"]);
  expect(request.signal).toBeInstanceOf(AbortSignal);
  expect(request.signal.aborted).toBe(false);
  expect(screen.getByRole("button",{name:"Reading…"})).toBeTruthy();
  await act(async()=>{flight.resolve(structuredClone(BODY()));await flight.promise;});
  expect(screen.getByRole("region",{name:"Autonomy"})).toBeTruthy();
  expect(screen.getByRole("heading",{name:"Autonomy"})).toBeTruthy();
  expect(screen.getByText("Review how work follows this selected mission.")).toBeTruthy();
  expect(screen.getByText("Existing plan limits")).toBeTruthy();
  const table=screen.getByLabelText("Existing plan limits");
  expect(within(table).getAllByRole("term")).toHaveLength(8);
  expect(screen.getByText("Policy ceilings, not remaining budget or permission for new work.").compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  const source = screen.getByText("Source details").closest("details")!;
  expect(source.open).toBe(false);
  expect(within(table).queryByText("max_attempts_per_orchestration_job")).toBeNull();
  expect(within(source).getByText("max_attempts_per_orchestration_job")).toBeTruthy();
  expect(within(table).getByText("Max children total").parentElement?.textContent).toContain("4");
  expect(within(table).getByText("Max fan-out per parent").parentElement?.textContent).toContain("3");
  expect(within(table).getByText("Allowed child cost classes").parentElement?.textContent).toContain("standard · deep_research");
  expect(screen.getByText("Policy ceilings, not remaining budget or permission for new work.")).toBeTruthy();
  expect(screen.getByText("Standing instructions are not supplied by this read.")).toBeTruthy();
  expect(screen.getByText("Project pause is not available from this read.")).toBeTruthy();
  expect(screen.getAllByRole("button")).toHaveLength(1);
  expect(screen.queryByRole("button",{name:/pause|cancel/i})).toBeNull();
  const details=screen.getByText("Source details").closest("details");
  expect(details).toBeTruthy();
  const proof=within(details as HTMLElement);
  expect(proof.getByText("WS:FIXTURE")).toBeTruthy();
  expect(proof.getByText("JOB-7")).toBeTruthy();
  expect(proof.getByText("c".repeat(64))).toBeTruthy();
  expect(proof.getByText("a".repeat(32))).toBeTruthy();
  // An unchanged passive rerender keeps the read displayed without re-reading.
  ui.rerender(<AutonomyPanel {...e.props()}/>);
  await act(async()=>{});
  expect(screen.getByText("Existing plan limits")).toBeTruthy();
  expect(e.read).toHaveBeenCalledTimes(1);
 });
 it("masks a stored read in the same render when the selected root changes",async()=>{
  const e=setup(),flight=deferred();e.read.mockImplementationOnce(()=>flight.promise);
  const ui=render(<AutonomyPanel {...e.props()}/>);
  const user=userEvent.setup();
  await user.click(readButton());
  await act(async()=>{flight.resolve(structuredClone(BODY()));await flight.promise;});
  expect(screen.getByText("Existing plan limits")).toBeTruthy();
  ui.rerender(<AutonomyPanel {...e.props()} selection={{workRef:"WS:NEXT",rootJobId:"JOB-8"}} sourceGeneration="gen-2"/>);
  expect(screen.queryByText("Existing plan limits")).toBeNull();
  expect(screen.queryByText("4")).toBeNull();
  expect(e.read).toHaveBeenCalledTimes(1);
 });
 it("masks a stored read when the reader identity changes (ABA)",async()=>{
  const e=setup(),flight=deferred();e.read.mockImplementationOnce(()=>flight.promise);
  const ui=render(<AutonomyPanel {...e.props()}/>);
  const user=userEvent.setup();
  await user.click(readButton());
  await act(async()=>{flight.resolve(structuredClone(BODY()));await flight.promise;});
  expect(screen.getByText("Existing plan limits")).toBeTruthy();
  const secondRead=vi.fn(()=>new Promise<unknown>(()=>{}));
  ui.rerender(<AutonomyPanel {...e.props()} read={secondRead}/>);
  expect(screen.queryByText("Existing plan limits")).toBeNull();
  expect(secondRead).not.toHaveBeenCalled();
 });
 it("aborts and withholds a pending read when the source generation changes",async()=>{
  const e=setup(),flight=deferred();e.read.mockImplementationOnce(()=>flight.promise);
  const ui=render(<AutonomyPanel {...e.props()}/>);
  const user=userEvent.setup();
  await user.click(readButton());
  const request=e.read.mock.calls[0][0];
  ui.rerender(<AutonomyPanel {...e.props()} sourceGeneration={2}/>);
  expect(request.signal.aborted).toBe(true);
  expect(e.read).toHaveBeenCalledTimes(1);
  await act(async()=>{flight.resolve(structuredClone(BODY()));await flight.promise;});
  expect(screen.queryByText("Existing plan limits")).toBeNull();
  expect(readButton().disabled).toBe(false);
 });
 it("withholds a late response after permission is revoked and stays cleared",async()=>{
  const e=setup(),flight=deferred();e.read.mockImplementationOnce(()=>flight.promise);
  const ui=render(<AutonomyPanel {...e.props()}/>);
  const user=userEvent.setup();
  await user.click(readButton());
  ui.rerender(<AutonomyPanel {...e.props()} canRead={false}/>);
  expect(screen.getByText("Reading is unavailable: the existing host has not confirmed current read permission.")).toBeTruthy();
  await act(async()=>{flight.resolve(structuredClone(BODY()));await flight.promise;});
  expect(screen.queryByText("Existing plan limits")).toBeNull();
  ui.rerender(<AutonomyPanel {...e.props()}/>);
  expect(screen.queryByText("Existing plan limits")).toBeNull();
  expect(e.read).toHaveBeenCalledTimes(1);
 });
 it("ignores a response that lands after unmount",async()=>{
  const e=setup(),flight=deferred();e.read.mockImplementationOnce(()=>flight.promise);
  const ui=render(<AutonomyPanel {...e.props()}/>);
  const user=userEvent.setup();
  await user.click(readButton());
  ui.unmount();
  await act(async()=>{flight.resolve(structuredClone(BODY()));await flight.promise;});
  expect(e.read).toHaveBeenCalledTimes(1);
 });
 it("shows a plain error for an undecodable response and keeps no stale read",async()=>{
  const e=setup(),good=deferred(),bad=deferred();
  e.read.mockImplementationOnce(()=>good.promise).mockImplementationOnce(()=>bad.promise);
  const ui=render(<AutonomyPanel {...e.props()}/>);
  const user=userEvent.setup();
  await user.click(readButton());
  await act(async()=>{good.resolve(structuredClone(BODY()));await good.promise;});
  expect(screen.getByText("Existing plan limits")).toBeTruthy();
  ui.rerender(<AutonomyPanel {...e.props()} selection={{workRef:"WS:NEXT",rootJobId:"JOB-8"}}/>);
  expect(screen.queryByText("Existing plan limits")).toBeNull();
  await user.click(readButton());
  await act(async()=>{bad.resolve({schema:"not-the-read-schema"});await bad.promise;});
  expect(screen.getByText("The autonomy read returned a response this panel cannot decode.")).toBeTruthy();
  expect(screen.queryByText("Existing plan limits")).toBeNull();
  expect(e.read).toHaveBeenCalledTimes(2);
 });
 it("shows a plain error when the read rejects and allows one retry",async()=>{
  const e=setup(),flight=deferred();e.read.mockImplementationOnce(()=>flight.promise);
  render(<AutonomyPanel {...e.props()}/>);
  const user=userEvent.setup();
  await user.click(readButton());
  await act(async()=>{flight.reject(new Error("private transport detail"));await flight.promise.catch(()=>{});});
  expect(screen.getByText("The autonomy read did not complete.")).toBeTruthy();
  expect(screen.queryByText("private transport detail")).toBeNull();
  expect(screen.queryByText("Existing plan limits")).toBeNull();
  expect(readButton().disabled).toBe(false);
 });
 it("shows the pending, denied, missing-reader and selection reasons instead of zero states",async()=>{
  const e=setup(),flight=deferred();e.read.mockImplementationOnce(()=>flight.promise);
  const ui=render(<AutonomyPanel {...e.props()}/>);
  const user=userEvent.setup();
  await user.click(readButton());
  expect(screen.queryByText("Select a mission to review its autonomy policy.")).toBeNull();
  expect(screen.queryByLabelText("Existing plan limits")).toBeNull();
  await act(async()=>{flight.resolve(structuredClone(UNAVAILABLE_BODY()));await flight.promise;});
  expect(screen.getByText("Existing execution limits are unavailable.")).toBeTruthy();
  expect(screen.getByText("SOURCE_CHANGED")).toBeTruthy();
  expect(screen.queryByText("Existing plan limits")).toBeNull();
  ui.rerender(<AutonomyPanel {...e.props()} selection={null}/>);
  expect(screen.getByText("Select a mission to review its autonomy policy.")).toBeTruthy();
  ui.rerender(<AutonomyPanel {...e.props()} selection={{workRef:"ws-lower",rootJobId:"JOB-7"}}/>);
  expect(screen.getByText("This selection does not match the autonomy read selection format.")).toBeTruthy();
  expect(readButton().disabled).toBe(true);
  ui.rerender(<AutonomyPanel {...e.props()} canRead={false}/>);
  expect(screen.getByText("Reading is unavailable: the existing host has not confirmed current read permission.")).toBeTruthy();
  await user.click(readButton());
  expect(e.read).toHaveBeenCalledTimes(1);
  ui.rerender(<AutonomyPanel selection={{...SELECTION}} canRead sourceGeneration={1}/>);
  expect(screen.getByText("No autonomy read is connected to this panel.")).toBeTruthy();
  expect(readButton().disabled).toBe(true);
  expect(screen.queryByLabelText("Existing plan limits")).toBeNull();
 });
 it("presents the same honest read in Chinese without fake pause or command controls",async()=>{
  const e=setup(),flight=deferred();e.read.mockImplementationOnce(()=>flight.promise);
  render(<AutonomyPanel {...e.props()} locale="zh-CN"/>);
  expect(screen.getByRole("region",{name:"自主工作"})).toBeTruthy();
  expect(screen.getByRole("heading",{name:"自主工作"})).toBeTruthy();
  expect(screen.getByText("查看工作如何遵循当前选定的任务。")).toBeTruthy();
  const user=userEvent.setup();
  await user.click(screen.getByRole("button",{name:"读取现有上限"}));
  await act(async()=>{flight.resolve(structuredClone(BODY()));await flight.promise;});
  expect(screen.getByText("现有计划上限")).toBeTruthy();
  const table=screen.getByLabelText("现有计划上限");
  expect(within(table).getAllByRole("term")).toHaveLength(8);
  expect(within(table).getByText("子工作总数上限").parentElement?.textContent).toContain("4");
  expect(within(table).getByText("允许的子工作成本类别").parentElement?.textContent).toContain("standard · deep_research");
  expect(screen.getByText("这些是策略上限，不是剩余预算，也不是新工作的许可。")).toBeTruthy();
  expect(screen.getByText("此读取不提供常设指令。")).toBeTruthy();
  expect(screen.getByText("此读取不提供项目暂停。")).toBeTruthy();
  expect(screen.getAllByRole("button")).toHaveLength(1);
  expect(screen.queryByRole("button",{name:/暂停|取消|命令/i})).toBeNull();
 });
});

describe("read callback and generation edges", () => {
 it("contains synchronous reader failures and allows another explicit read", async () => {
  const read = vi.fn((): Promise<unknown> => { throw new Error("private owner detail"); });
  render(<AutonomyPanel selection={SELECTION} canRead sourceGeneration={1} read={read} />);
  const user = userEvent.setup();
  await user.click(readButton());
  expect(screen.getByText("The autonomy read did not complete.")).toBeTruthy();
  expect(screen.queryByText("private owner detail")).toBeNull();
  expect(readButton().disabled).toBe(false);
 });
 it("withholds a result when a generation changes from numeric to textual", async () => {
  const read = vi.fn(async () => BODY());
  const ui = render(<AutonomyPanel selection={SELECTION} canRead sourceGeneration={1} read={read} />);
  await userEvent.setup().click(readButton());
  expect(screen.getByText("Existing plan limits")).toBeTruthy();
  ui.rerender(<AutonomyPanel selection={SELECTION} canRead sourceGeneration="1" read={read} />);
  expect(screen.queryByText("Existing plan limits")).toBeNull();
  expect(read).toHaveBeenCalledTimes(1);
 });
});
