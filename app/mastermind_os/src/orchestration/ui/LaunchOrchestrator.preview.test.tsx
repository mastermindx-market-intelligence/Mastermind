// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { LaunchOrchestrator, type LaunchForm, type LaunchOrchestratorProps, composeAcceptanceGoal } from "./LaunchOrchestrator";

afterEach(cleanup);
function mount(overrides: Partial<LaunchOrchestratorProps> = {}) {
  const previewRequest = vi.fn((form: LaunchForm) => ({ state: "PREPARED" as const,
    ...form, frontierModelAlias: form.frontierModelAlias ?? null, targetKey: "WS:ONE" }));
  const onSubmit = vi.fn();
  const props: LaunchOrchestratorProps = { projects: [{ref:"research",label:"Research"}],
    profiles: [{ref:"research_only",label:"Read-only research"}], submitting:false,
    onSubmit, onCancel:vi.fn(), previewRequest, ...overrides };
  const view = render(<LaunchOrchestrator {...props} />);
  fireEvent.change(screen.getByLabelText("Goal"), {target:{value:"Review the actual source"}});
  return { ...view, props, previewRequest, onSubmit };
}
describe("Launch request preview integration", () => {
  it("previews only on an explicit click, preserves the actual draft and never launches", () => {
    const x = mount();
    expect(x.previewRequest).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", {name:"Preview requested scope"}));
    expect(x.previewRequest).toHaveBeenCalledExactlyOnceWith({goal:"Review the actual source",
      projectRef:"research",profileRef:"research_only"});
    expect(x.onSubmit).not.toHaveBeenCalled();
    expect((screen.getByLabelText("Goal") as HTMLTextAreaElement).value).toBe("Review the actual source");
    expect(screen.getByText("Requested scope preview")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Goal"), {target:{value:"A corrected request"}});
    expect(screen.queryByText("Requested scope preview")).toBeNull();
    expect(x.previewRequest).toHaveBeenCalledTimes(1);
  });
  it("withholds the old preparation after a catalog or mapper changes", () => {
    const x = mount();
    fireEvent.click(screen.getByRole("button", {name:"Preview requested scope"}));
    x.rerender(<LaunchOrchestrator {...x.props} profiles={[...x.props.profiles]} />);
    expect(screen.queryByText("Requested scope preview")).toBeNull();
    expect(x.previewRequest).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", {name:"Preview requested scope"}));
    expect(x.previewRequest).toHaveBeenCalledTimes(2);
    const changed = vi.fn(() => ({state:"UNAVAILABLE" as const}));
    x.rerender(<LaunchOrchestrator {...x.props} previewRequest={changed} />);
    expect(screen.queryByText("Requested scope preview")).toBeNull();
    expect(changed).not.toHaveBeenCalled();
  });
  it("cannot preview through the original pending-operation hold or release its launch latch", () => {
    const x = mount();
    fireEvent.click(screen.getByRole("button", {name:"Launch"}));
    expect(x.onSubmit).toHaveBeenCalledTimes(1);
    const preview = screen.getByRole("button", {name:"Preview requested scope"}) as HTMLButtonElement;
    expect(preview.disabled).toBe(true);
    fireEvent.click(preview);
    expect(x.previewRequest).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", {name:"Launching…"}));
    expect(x.onSubmit).toHaveBeenCalledTimes(1);
  });
  it("does not add a preview when the original owner supplies none", () => {
    mount({previewRequest:undefined});
    expect(screen.queryByRole("button", {name:"Preview requested scope"})).toBeNull();
  });
});

it('renders only the same frozen user goal and criteria while mapper and submit keep exact wire bytes',()=>{
 const x=mount({presentation:'composer'});
 const goal='  First\tparagraph\n保持原文  ',criteria='First useful proof\n 第二个验收条件 ';
 fireEvent.change(screen.getByLabelText('Goal'),{target:{value:goal}});
 fireEvent.change(screen.getByLabelText(/Acceptance criteria/),{target:{value:criteria}});
 fireEvent.click(screen.getByRole('button',{name:'Preview requested scope'}));
 expect(document.querySelector('.launch-request-preview-goal')?.textContent).toBe(goal);
 expect(screen.getByText('First useful proof')).toBeTruthy();expect(screen.getByText('第二个验收条件')).toBeTruthy();
 expect(document.querySelector('.launch-request-preview')?.textContent).not.toContain('MASTERMIND_ACCEPTANCE_CRITERIA_V1');
 expect(x.previewRequest.mock.calls[0][0].goal).toBe(composeAcceptanceGoal(goal,criteria));
 expect(x.onSubmit).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Launch'}));
 expect(x.onSubmit.mock.calls[0][0]).toEqual(x.previewRequest.mock.calls[0][0]);
});
it('a raw form edit that preserves normalized wire still invalidates the old presentation without any effect',()=>{
 const x=mount();fireEvent.click(screen.getByRole('button',{name:'Preview requested scope'}));
 const wire=x.previewRequest.mock.calls[0][0].goal;
 fireEvent.change(screen.getByLabelText('Goal'),{target:{value:'  Review the actual source  '}});
 expect(composeAcceptanceGoal('  Review the actual source  ','')).toBe(wire);
 expect(screen.queryByText('Requested scope preview')).toBeNull();
 expect(x.previewRequest).toHaveBeenCalledTimes(1);expect(x.onSubmit).not.toHaveBeenCalled();
});
