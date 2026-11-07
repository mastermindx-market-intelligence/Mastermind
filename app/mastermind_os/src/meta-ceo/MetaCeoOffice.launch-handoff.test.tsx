// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { MetaCeoOffice } from "./MetaCeoOffice";
import { projectOffice, type ProjectionContext } from "./projection";
import type { DirectionPreview, OfficeLaunchOutcome } from "./preview";

afterEach(cleanup);
const context: ProjectionContext = {
  authGeneration: 1,
  selection: { workRef: "WS:ONE", rootJobId: "JOB-1" },
  sessionRef: null,
  bindingGeneration: null,
  revisions: { mission: null, programs: null, result: null, conversation: null },
};
const empty = { mission: null, programs: null, result: null, conversation: null };
const DIRECTION = "Keep the highest-value safe next step moving.";

function ControlledOffice(props: {
  onStartNewWork?: (preview: DirectionPreview) => OfficeLaunchOutcome;
}) {
  const [draft, setDraft] = useState("");
  return <MetaCeoOffice projection={projectOffice(empty, context)} draft={{ text: draft, context }}
    onDraftChange={setDraft} {...props} />;
}

it("hands the exact frozen preview to the existing launch owner and keeps the Office draft", () => {
  const onStartNewWork = vi.fn((_preview: DirectionPreview) => ({ status: "OPENED" }) as OfficeLaunchOutcome);
  render(<ControlledOffice onStartNewWork={onStartNewWork} />);
  fireEvent.change(screen.getByLabelText("Direction to Meta-CEO"), { target: { value: DIRECTION } });
  fireEvent.click(screen.getByRole("button", { name: "Review direction preview" }));
  const preview = screen.getByRole("region", { name: "Direction preview" });
  expect(preview.textContent).toContain(DIRECTION);
  fireEvent.click(within(preview).getByRole("button", { name: "Start new work" }));
  expect(onStartNewWork).toHaveBeenCalledTimes(1);
  const handed = onStartNewWork.mock.calls[0]![0];
  expect(handed.draft).toBe(DIRECTION);
  expect(handed.context).toEqual(context);
  expect(handed.effectExpectation).toBe("NONE");
  expect((screen.getByLabelText("Direction to Meta-CEO") as HTMLTextAreaElement).value).toBe(DIRECTION);
  expect(within(preview).getByRole("status").textContent).toContain("existing launch form");
});

it("shows an honest refusal inside the preview and keeps the Office draft", () => {
  const onStartNewWork = vi.fn((_preview: DirectionPreview) => (
    { status: "REFUSED", reason: "LAUNCH_GOAL_PRESERVED" } as OfficeLaunchOutcome
  ));
  render(<ControlledOffice onStartNewWork={onStartNewWork} />);
  fireEvent.change(screen.getByLabelText("Direction to Meta-CEO"), { target: { value: DIRECTION } });
  fireEvent.click(screen.getByRole("button", { name: "Review direction preview" }));
  const preview = screen.getByRole("region", { name: "Direction preview" });
  fireEvent.click(within(preview).getByRole("button", { name: "Start new work" }));
  expect(within(preview).getByRole("alert").textContent).toContain("unsent launch goal");
  expect((screen.getByLabelText("Direction to Meta-CEO") as HTMLTextAreaElement).value).toBe(DIRECTION);
});

it("offers no start action when the existing launch owner cannot offer a handoff", () => {
  render(<ControlledOffice />);
  fireEvent.change(screen.getByLabelText("Direction to Meta-CEO"), { target: { value: DIRECTION } });
  fireEvent.click(screen.getByRole("button", { name: "Review direction preview" }));
  const preview = screen.getByRole("region", { name: "Direction preview" });
  expect(within(preview).queryByRole("button", { name: "Start new work" })).toBeNull();
  expect(preview.textContent).toContain("EFFECT_NONE");
});
