// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ActivationFacts } from "./ActivationFacts";
import { activationFacts } from "./activation-facts";
afterEach(cleanup);
const model = activationFacts(
  {
    pointer: { operationKey: "request-1", kind: "launch", targetKey: "opaque" },
    owner: { principalScope: "owner", generation: "1" },
    status: "accepted",
    missionSelection: { workRef: "WS:ALPHA", rootJobId: "JOB-1" },
  },
  null,
)!;
it.each(["en", "zh-CN"] as const)(
  "shows all six independent unavailable facts with no mount navigation in %s",
  (locale) => {
    const navigate = vi.fn();
    const { container } = render(
      <ActivationFacts locale={locale} model={model} onNavigate={navigate} />,
    );
    expect(
      container.querySelectorAll(".activation-facts__rows > div"),
    ).toHaveLength(6);
    expect(navigate).not.toHaveBeenCalled();
    expect(
      screen.getAllByText(
        locale === "en" ? "Not reported by this source" : "此来源未报告",
      ),
    ).toHaveLength(5);
    expect(container.querySelector("section")?.lang).toBe(locale);
    expect(
      screen.getByText(locale === "en" ? "Request accepted" : "请求已接受"),
    ).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", {
        name: locale === "en" ? "Open Work" : "打开工作",
      }),
    );
    expect(navigate).toHaveBeenCalledExactlyOnceWith("work");
  },
);
it("keeps a missing original explicitly unavailable with no invented navigation", () => {
  const { container } = render(<ActivationFacts model={null} />);
  expect(
    screen.getByText("Original request identity unavailable."),
  ).toBeTruthy();
  expect(container.querySelectorAll("button")).toHaveLength(0);
  expect(screen.getAllByText("Not reported by this source")).toHaveLength(6);
});
it("unknown exposes only original status, with exact metadata in a disclosure", () => {
  const navigate = vi.fn();
  const unknown = activationFacts(
    {
      pointer: {
        operationKey: "request-unknown",
        kind: "launch",
        targetKey: null,
      },
      owner: { principalScope: "owner", generation: "1" },
      status: "unknown",
      missionSelection: null,
    },
    null,
  );
  render(<ActivationFacts model={unknown} onNavigate={navigate} />);
  expect(screen.queryByRole("button", { name: "Open Work" })).toBeNull();
  expect(
    screen.getByRole("button", { name: "Read original status" }),
  ).toBeTruthy();
  expect(
    within(screen.getByText("Receipt evidence").closest("details")!).getByText(
      "request-unknown",
    ),
  ).toBeTruthy();
});
