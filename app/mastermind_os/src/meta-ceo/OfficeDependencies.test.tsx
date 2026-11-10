// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { OfficeDependencies } from "./OfficeDependencies";
import type { OfficeProjection } from "./projection";
afterEach(cleanup);
function read(): OfficeProjection["programs"] {
  return {
    source: {
      owner: "AGENT_OS",
      ref: "digest",
      revision: "rev",
      observed_at: "2026-11-08T00:00:00Z",
      state: "CURRENT",
      coverage: "SUPPLIED_COLLECTION",
    },
    reason: null,
    value: {
      state: "AVAILABLE",
      reason: "owner supplied",
      programs: [],
      dependencies: [
        {
          workRef: "WS:ONE",
          title: "One",
          state: "AVAILABLE",
          source: "agentos/workstreams/WS-ONE.md",
          readiness: "blocked",
          declared: ["WS:OUTSIDE"],
          unmet: ["WS:OUTSIDE"],
        },
      ],
    },
  };
}
it("inspects an unavailable outside endpoint and returns focus without an action grant", () => {
  render(<OfficeDependencies read={read()} locale="en" />);
  const trigger = screen.getByRole("button", {
    name: "Inspect dependencies for One",
  });
  trigger.focus();
  fireEvent.click(trigger);
  expect(document.activeElement).toBe(
    screen.getByRole("heading", { level: 3, name: "One" }),
  );
  expect(
    screen.getByText(
      "Outside the supplied collection; project details are unavailable here.",
    ),
  ).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Open project" })).toBeNull();
  fireEvent.keyDown(document.activeElement!, { key: "Escape" });
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "Inspect dependencies for One" }),
  );
});
it.each([
  "STALE",
  "WITHHELD",
  "UNASSOCIATED",
  "UNKNOWN",
  "UNAVAILABLE",
] as const)("withholds previously selected protected data on %s", (state) => {
  const r = read();
  const view = render(<OfficeDependencies read={r} locale="en" />);
  fireEvent.click(
    screen.getByRole("button", { name: "Inspect dependencies for One" }),
  );
  const before = document.activeElement;
  view.rerender(
    <OfficeDependencies
      read={{ ...r, source: { ...r.source, state } }}
      locale="en"
    />,
  );
  expect(screen.queryByText("WS:OUTSIDE")).toBeNull();
  expect(
    screen.queryByRole("button", { name: "Back to dependencies" }),
  ).toBeNull();
  expect(document.activeElement).not.toBe(
    screen.getByRole("heading", { level: 2 }),
  );
  expect(before?.isConnected).toBe(false);
});
it("does not reuse an inspected row across a different collection revision", () => {
  const r = read(),
    view = render(<OfficeDependencies read={r} locale="zh-CN" />);
  fireEvent.click(screen.getByRole("button", { name: "查看 One 的依赖" }));
  view.rerender(
    <OfficeDependencies
      read={{ ...r, source: { ...r.source, revision: "new" } }}
      locale="zh-CN"
    />,
  );
  expect(screen.queryByRole("heading", { level: 3 })).toBeNull();
  expect(screen.getByRole("button", { name: "查看 One 的依赖" })).toBeTruthy();
});
it("limits the first view to eight supplied records and exposes explicit page navigation", () => {
  const r = read();
  r.value!.dependencies = Array.from({ length: 9 }, (_, i) => ({
    ...r.value!.dependencies![0],
    workRef: `WS:PROJECT-${i}`,
    title: `Project ${i}`,
  }));
  render(<OfficeDependencies read={r} locale="en" />);
  expect(
    screen.getAllByRole("button", { name: /Inspect dependencies for/ }),
  ).toHaveLength(8);
  expect(
    screen.queryByRole("button", {
      name: "Inspect dependencies for Project 8",
    }),
  ).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Next projects" }));
  expect(
    screen.getAllByRole("button", { name: /Inspect dependencies for/ }),
  ).toHaveLength(1);
  expect(
    screen.getByRole("button", { name: "Inspect dependencies for Project 8" }),
  ).toBeTruthy();
});
