// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { programsFromControlRoom } from "./mission";
import { controlRoomFixture } from "./test-fixtures";
import { WorkMissionLink } from "./WorkMissionLink";

const props = () => ({
  rootJobId: "JOB-A",
  programs: programsFromControlRoom(controlRoomFixture()),
  acquisitionAllowed: true,
  workObservationAvailable: true,
  onOpenMission: vi.fn(),
});
afterEach(cleanup);

describe("Work Mission link rendered consumer", () => {
  it("retains root identity and opens only the exact pair via keyboard", async () => {
    const p = props();
    const user = userEvent.setup();
    render(<WorkMissionLink {...p} />);
    expect(screen.getByText("JOB-A")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Alpha program" })).toBeTruthy();
    const button = screen.getByRole("button", { name: "Open Mission" });
    await user.tab();
    expect(document.activeElement).toBe(button);
    await user.keyboard("{Enter}");
    expect(p.onOpenMission).toHaveBeenCalledExactlyOnceWith({
      workRef: "WS:ALPHA",
      rootJobId: "JOB-A",
    });
  });
  it.each(["acquisitionAllowed", "workObservationAvailable"] as const)(
    "withdraws the link and friendly title after %s changes",
    async (key) => {
      const p = props();
      const user = userEvent.setup();
      const view = render(<WorkMissionLink {...p} />);
      view.rerender(<WorkMissionLink {...p} {...{ [key]: false }} />);
      const button = screen.getByRole("button", {
        name: "Mission unavailable",
      }) as HTMLButtonElement;
      expect(button.disabled).toBe(true);
      expect(screen.getByText("JOB-A")).toBeTruthy();
      expect(
        screen.queryByRole("heading", { name: "Alpha program" }),
      ).toBeNull();
      await user.click(button);
      expect(p.onOpenMission).not.toHaveBeenCalled();
    },
  );
  it("does not retain the old pair when Programs becomes unavailable", async () => {
    const p = props();
    const user = userEvent.setup();
    const view = render(<WorkMissionLink {...p} />);
    view.rerender(<WorkMissionLink {...p} programs={null} />);
    await user.click(
      screen.getByRole("button", { name: "Mission unavailable" }),
    );
    expect(screen.getByText("JOB-A")).toBeTruthy();
    expect(p.onOpenMission).not.toHaveBeenCalled();
  });
  it("navigates the new selected root rather than its predecessor", async () => {
    const p = props();
    const user = userEvent.setup();
    const view = render(<WorkMissionLink {...p} />);
    view.rerender(<WorkMissionLink {...p} rootJobId="JOB-B" />);
    await user.click(screen.getByRole("button", { name: "Open Mission" }));
    expect(p.onOpenMission).toHaveBeenCalledExactlyOnceWith({
      workRef: "WS:BETA",
      rootJobId: "JOB-B",
    });
  });
  it("retains a missing-link root without presenting another mission's title", () => {
    render(<WorkMissionLink {...props()} rootJobId="JOB-ABSENT" />);
    expect(screen.getByText("JOB-ABSENT")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Alpha program" })).toBeNull();
    expect(
      (
        screen.getByRole("button", {
          name: "Mission unavailable",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });
  it("renders hostile source titles only as inert text", () => {
    const p = props();
    const title = '<img src=x onerror="alert(1)">';
    p.programs.programs[0].title = title;
    const view = render(<WorkMissionLink {...p} />);
    expect(screen.getByRole("heading", { name: title })).toBeTruthy();
    expect(view.container.querySelector("img")).toBeNull();
  });
  it("refuses a conflicting source mutation even before its caller rerenders", async () => {
    const p = props();
    const user = userEvent.setup();
    render(<WorkMissionLink {...p} />);
    p.programs.programs[1].rootCandidates = ["JOB-A", "JOB-B"];
    await user.click(screen.getByRole("button", { name: "Open Mission" }));
    expect(p.onOpenMission).not.toHaveBeenCalled();
  });
  it("does not silently retarget an already-painted link after in-place pair replacement", async () => {
    const p = props();
    const user = userEvent.setup();
    render(<WorkMissionLink {...p} />);
    p.programs.programs[0].workRef = "WS:REPLACEMENT";
    await user.click(screen.getByRole("button", { name: "Open Mission" }));
    expect(p.onOpenMission).not.toHaveBeenCalled();
  });
  it("does not call navigation on render, source read failure or unmount", () => {
    const p = props();
    const view = render(<WorkMissionLink {...p} />);
    view.rerender(
      <WorkMissionLink {...p} programs={programsFromControlRoom(null)} />,
    );
    view.unmount();
    expect(p.onOpenMission).not.toHaveBeenCalled();
  });
});
