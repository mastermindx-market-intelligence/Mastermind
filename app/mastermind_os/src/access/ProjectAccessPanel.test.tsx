// @vitest-environment jsdom
import { afterEach, it, expect, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import fixture from "./fixtures/current-grants.json";
import v5 from "./fixtures/v5-current-grants.json";
import { ProjectAccessPanel } from "./ProjectAccessPanel";
afterEach(cleanup);
const props = () => ({
  selection: { work_ref: "WS:ONE" },
  canRead: true,
  sourceGeneration: "1",
  source: { data: fixture, generation: "1" },
  onReadCurrent: vi.fn(),
});
it("shows current grants with one read action, no editor or action eligibility", () => {
  const p = props();
  render(<ProjectAccessPanel {...p} />);
  expect(
    screen.getByText("You can read this project’s information."),
  ).toBeTruthy();
  expect(screen.getAllByText("Supplied")).toHaveLength(3);
  expect(screen.getAllByText("Not supplied here")).toHaveLength(5);
  expect(screen.getAllByRole("button")).toHaveLength(1);
  expect(p.onReadCurrent).not.toHaveBeenCalled();
  expect(screen.getByText("Source details").closest("details")?.open).toBe(
    false,
  );
  fireEvent.click(screen.getByRole("button", { name: "Read current access" }));
  expect(p.onReadCurrent).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("6".repeat(64))).toBeNull();
});
it("keeps not declared distinct from unavailable and masks foreign scope/auth", () => {
  const p = props(),
    view = render(
      <ProjectAccessPanel
        {...p}
        source={{
          data: { ...fixture, declaration: "NOT_DECLARED", grants: null },
          generation: "1",
        }}
      />,
    );
  expect(
    screen.getByText(
      "Additional project permissions were not declared in this membership.",
    ),
  ).toBeTruthy();
  expect(screen.queryByText("Not supplied here")).toBeNull();
  view.rerender(
    <ProjectAccessPanel
      {...p}
      source={{
        data: { ...fixture, selection: { work_ref: "WS:OTHER" } },
        generation: "1",
      }}
    />,
  );
  expect(screen.getByText("Current permissions are unavailable.")).toBeTruthy();
  expect(screen.queryByText("WS:OTHER")).toBeNull();
  view.rerender(
    <ProjectAccessPanel {...p} canRead={false} sourceGeneration="2" />,
  );
  expect(screen.queryByText("Pause new project work")).toBeNull();
  expect(screen.getByText("Current permissions are unavailable.")).toBeTruthy();
  expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button"));expect(p.onReadCurrent).not.toHaveBeenCalled();
});
it("uses Chinese semantics and reports transport failure without synthesizing owner state", () => {
  render(
    <ProjectAccessPanel {...props()} locale="zh-CN" source={null} failed />,
  );
  expect(screen.getByText("暂时无法获取当前权限。")).toBeTruthy();
  expect(screen.getByRole("region").lang).toBe("zh-CN");
  expect(screen.queryByText("已提供")).toBeNull();
});

it("shows distinct latest-data/proposal records under v5 with at most eight first-level rows", () => {
  render(
    <ProjectAccessPanel {...props()} source={{ data: v5, generation: "1" }} />,
  );
  const rows = document.querySelector(".project-access__grants");
  expect(rows?.children).toHaveLength(8);
  expect(rows?.firstElementChild?.textContent).toContain(
    "Read the latest project data",
  );
  const summary = screen.getByText("Other permission records (2)");
  expect(summary.closest("details")?.open).toBe(false);
  expect(screen.getByText("Publish a draft plan proposal")).toBeTruthy();
  expect(screen.getAllByRole("button")).toHaveLength(1);
});
