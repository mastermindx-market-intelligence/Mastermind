// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import fixture from "../fixtures/project-plan-canonical-owner.json";
import { decodeProjectPlan } from "./project-plan";
import { ProjectStartWork, type ProjectStartWorkProps } from "./ProjectStartWork";
import type { ProjectLaunchOutcome } from "./project-launch-handoff";
afterEach(cleanup);
function inspection() {
  let current=true;
  return {read:decodeProjectPlan(fixture,{work_ref:"WS:ONE"}),selection:{work_ref:"WS:ONE"},
    isCurrent:()=>current,withdraw:()=>{current=false;}};
}
it("opens the exact current project objective once while a preview is pending",async()=>{
  const view=inspection();let finish!:(value:ProjectLaunchOutcome)=>void;
  const start=vi.fn<ProjectStartWorkProps["onStart"]>(()=>new Promise<ProjectLaunchOutcome>(resolve=>{finish=resolve;}));
  render(<ProjectStartWork inspection={view} onStart={start}/>);
  const button=screen.getByRole("button",{name:"Start work"});
  fireEvent.click(button);fireEvent.click(button);
  expect(start).toHaveBeenCalledTimes(1);
  expect(start.mock.calls[0][0]).toMatchObject({goal:"Deliver the real owner content.",context:{workRef:"WS:ONE"}});
  await act(async()=>finish({status:"OPENED",reuseExisting:false}));
  expect(screen.getByRole("status").textContent).toContain("Review");
});
it("refuses a stale source at click time without opening a launch",()=>{
  const view=inspection(),start=vi.fn();render(<ProjectStartWork inspection={view} onStart={start}/>);
  view.withdraw();fireEvent.click(screen.getByRole("button",{name:"Start work"}));
  expect(start).not.toHaveBeenCalled();expect(screen.getByRole("alert").textContent).toContain("Refresh");
});
it("does not publish the previous project preview after changing project acquisition",async()=>{
  const first=inspection();let finish!:(value:ProjectLaunchOutcome)=>void;
  const start=vi.fn<ProjectStartWorkProps["onStart"]>(()=>new Promise<ProjectLaunchOutcome>(resolve=>{finish=resolve;}));
  const view=render(<ProjectStartWork inspection={first} onStart={start}/>);
  fireEvent.click(screen.getByRole("button",{name:"Start work"}));
  first.withdraw();view.rerender(<ProjectStartWork inspection={inspection()} onStart={start}/>);
  await act(async()=>finish({status:"OPENED",reuseExisting:false}));
  expect(screen.queryByText(/Review the launch/)).toBeNull();
});

it("waits for original-operation discovery and distinguishes pending work from sign-in",async()=>{
  const source=inspection();
  const start=vi.fn<ProjectStartWorkProps["onStart"]>(async()=>({status:"OPENED",reuseExisting:false}));
  const view=render(<ProjectStartWork inspection={source} operationHold="checking" onStart={start}/>);
  const button=screen.getByRole("button",{name:"Start work"}) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  expect(screen.getByRole("status").textContent).toBe("Checking previous work…");
  fireEvent.click(button);expect(start).not.toHaveBeenCalled();
  view.rerender(<ProjectStartWork inspection={source} operationHold="pending" locale="zh-CN" onStart={start}/>);
  expect((screen.getByRole("button",{name:"开始工作"}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole("status").textContent).toContain("之前工作的状态");
  view.rerender(<ProjectStartWork inspection={source} operationHold={null} onStart={start}/>);
  await act(async()=>fireEvent.click(screen.getByRole("button",{name:"Start work"})));
  expect(start).toHaveBeenCalledTimes(1);
});
