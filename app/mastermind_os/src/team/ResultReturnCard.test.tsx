// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ResultReturnCard, type TaskResultReturn } from "./ResultReturnCard";
afterEach(cleanup);

function result(extra: Partial<TaskResultReturn> = {}): TaskResultReturn {
  return {
    resultId: "res-1",
    title: "Fabric launch repair",
    deliveredTo: "Team Hermes · bot-alpha",
    deliveredAt: "2026-11-09T01:00:00Z",
    accepted: false,
    evidence: [
      { label: "Commit", value: "d995f7bc6" },
      { label: "Tests", value: "vitest 7005 passed" },
    ],
    ...extra,
  };
}

describe("ResultReturnCard — delivery is never acceptance (HC08)", () => {
  it("shows Delivered and Accepted as separate states with the not-accepted reason", () => {
    render(<ResultReturnCard result={result()} />);
    expect(
      screen.getByText("Delivered to Team Hermes · bot-alpha"),
    ).toBeTruthy();
    expect(
      screen.getByText("Delivery observed 2026-11-09T01:00:00Z"),
    ).toBeTruthy();
    const accepted = document.querySelector("[data-accepted='false']");
    expect(accepted?.textContent).toContain("Not yet accepted");
    expect(
      screen.getByText(
        /Delivery is not acceptance\. The receiving owner still reviews this result/i,
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Accepted")).not.toBeNull(); // the dt label stays present
  });
  it("marks actual acceptance without the caution note", () => {
    render(<ResultReturnCard result={result({ accepted: true })} />);
    expect(
      document.querySelector("[data-accepted='true']")?.textContent,
    ).toContain("Accepted");
    expect(screen.queryByText(/Delivery is not acceptance/i)).toBeNull();
  });
  it("lists attached evidence and stays honest when none exists", () => {
    render(<ResultReturnCard result={result()} />);
    expect(screen.getByText("Commit")).toBeTruthy();
    expect(screen.getByText("d995f7bc6")).toBeTruthy();
    expect(screen.getByText("Tests")).toBeTruthy();
    expect(screen.getByText("vitest 7005 passed")).toBeTruthy();
  });
  it("keeps delivery observable without a timestamp and opens the origin on request", () => {
    const onOpenOrigin = vi.fn();
    render(
      <ResultReturnCard
        result={result({ deliveredAt: null })}
        onOpenOrigin={onOpenOrigin}
      />,
    );
    expect(screen.queryByText(/Delivery observed/i)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open origin →" }));
    expect(onOpenOrigin).toHaveBeenCalledTimes(1);
  });
  it("renders the honest zh-CN copy", () => {
    render(<ResultReturnCard result={result()} locale="zh-CN" />);
    expect(screen.getByText("结果已返回来源")).toBeTruthy();
    expect(screen.getByText("已交付给 Team Hermes · bot-alpha")).toBeTruthy();
    expect(
      document.querySelector("[data-accepted='false']")?.textContent,
    ).toContain("尚未接受");
    expect(
      screen.getByText(/交付不等于接受。接收方负责人仍需审阅该结果。/),
    ).toBeTruthy();
    expect(screen.getByText("证据")).toBeTruthy();
  });
});
