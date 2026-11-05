// @vitest-environment jsdom
import { afterEach, it, expect, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import fixture from "./fixtures/current-grants.json";
import type { ProjectAccessRequest } from "./project-access-host";
import {
  useProjectAccessWorkspace,
  type ProjectAccessWorkspaceProps,
} from "./useProjectAccessWorkspace";
afterEach(cleanup);
function Harness(p: ProjectAccessWorkspaceProps) {
  return useProjectAccessWorkspace(p);
}
const make = () => ({
  selection: { work_ref: "WS:ONE" },
  authGeneration: 1,
  sourceGeneration: () => 0,
  canRead: () => true,
  readCurrent: vi.fn(
    async (_request: ProjectAccessRequest): Promise<unknown> => fixture,
  ),
  locale: "en" as const,
});
it("does no mount read and publishes only after the explicit current owner read", async () => {
  const p = make();
  render(<Harness {...p} />);
  expect(p.readCurrent).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Read current access" }));
  await screen.findByText("You can read this project’s information.");
  expect(p.readCurrent).toHaveBeenCalledTimes(1);
  expect(p.readCurrent.mock.calls[0][0]).toMatchObject({
    selection: { work_ref: "WS:ONE" },
  });
});
it("withholds a late response after source departure and never revives old project facts on A-B-A", async () => {
  const p = make();
  let generation = 0,
    finish!: (body: unknown) => void;
  p.sourceGeneration = () => generation;
  p.readCurrent = vi.fn(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const view = render(<Harness {...p} />);
  fireEvent.click(screen.getByRole("button", { name: "Read current access" }));
  generation++;
  finish(fixture);
  await waitFor(() =>
    expect(
      screen.queryByText("You can read this project’s information."),
    ).toBeNull(),
  );
  p.readCurrent = vi.fn(async () => fixture);
  view.rerender(<Harness {...p} />);
  fireEvent.click(screen.getByRole("button", { name: "Read current access" }));
  await screen.findByText("You can read this project’s information.");
  view.rerender(<Harness {...p} selection={{ work_ref: "WS:OTHER" }} />);
  expect(screen.queryByText("Pause new project work")).toBeNull();
  view.rerender(<Harness {...p} />);
  expect(screen.queryByText("Pause new project work")).toBeNull();
});
it("checks live generation on the read gesture before any IO and clears body on auth/method departure", async () => {
  const p = make();
  let generation = 0;
  p.sourceGeneration = () => generation;
  const view = render(<Harness {...p} />);
  generation++;
  fireEvent.click(screen.getByRole("button", { name: "Read current access" }));
  expect(p.readCurrent).not.toHaveBeenCalled();
  view.rerender(<Harness {...p} />);
  fireEvent.click(screen.getByRole("button", { name: "Read current access" }));
  await screen.findByText("You can read this project’s information.");
  view.rerender(<Harness {...p} authGeneration={2} canRead={() => false} />);
  expect(screen.queryByText("Pause new project work")).toBeNull();
  expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
});
