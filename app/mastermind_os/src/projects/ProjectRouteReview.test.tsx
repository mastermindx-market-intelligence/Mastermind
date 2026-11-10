// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ProjectRouteReview } from "./ProjectRouteReview";
import type { DelegatedRouteReview } from "./delivery-route-run";
import { ProjectDeliveryPanel } from "./ProjectDeliveryPanel";
afterEach(cleanup);

const route: DelegatedRouteReview = {
  root_run_ref: "root-wo19-coding-7",
  immediate_parent_run_ref: "run-41",
  logical_child_key: "fleet-launch-repair",
  operation_key: "op-77",
  runtime_kind: "fabric-native",
  task_kind: "code",
  effective_complexity: "C2_COMPLEX_BOUNDED",
  request_digest: "a".repeat(64),
  host: null,
  runtime: null,
  engine: null,
  model: null,
  pool: null,
};

describe("ProjectRouteReview (TD06)", () => {
  it("renders fully from a null route with honest copy and zero fabricated values", () => {
    render(<ProjectRouteReview route={null} />);
    expect(screen.getByText("Confirm the work and proposed route. Nothing has started.")).toBeTruthy();
    expect(screen.getByText("No coding route is projected for this project yet.")).toBeTruthy();
    expect(screen.getByText("No admission binding is projected yet.")).toBeTruthy();
    // Honest absence with the reason naming the missing source.
    expect(screen.getByText("Admission has not proposed a route yet.")).toBeTruthy();
    expect(screen.getAllByText("Not projected").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Unknown").length).toBe(5); // readiness rows
    // Zero fabricated placement values: no host/OS/model names appear.
    for (const fabricated of [/ubuntu/i, /mac ?studio/i, /gpt-?\d/i, /claude/i, /sonnet/i, /opus/i, /haiku/i, /gemini/i]) {
      expect(screen.queryByText(fabricated)).toBeNull();
    }
  });

  it("renders binding facts and keeps submit disabled with a visible reason", () => {
    render(<ProjectRouteReview route={route} />);
    expect(screen.getByText("root-wo19-coding-7")).toBeTruthy();
    expect(screen.getByText("run-41")).toBeTruthy();
    expect(screen.getByText("fleet-launch-repair")).toBeTruthy();
    expect(screen.getByText("C2_COMPLEX_BOUNDED")).toBeTruthy();
    expect(screen.getByText("op-77")).toBeTruthy();
    const submit = screen.getByRole("button", { name: "Submit request" });
    expect(submit.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/This surface can only preview/)).toBeTruthy();
    // Placement slots are still honestly not projected.
    expect(screen.getByText("Admission has not proposed a route yet.")).toBeTruthy();
  });

  it("renders proposed placement values when admission projects them", () => {
    render(
      <ProjectRouteReview
        route={{ ...route, host: "m2-studio", runtime: "fabric-native", engine: "e1", model: "worker-a", pool: "fabric-main" }}
      />,
    );
    expect(screen.getByText("m2-studio")).toBeTruthy();
    expect(screen.getByText("worker-a")).toBeTruthy();
    expect(screen.getByText("fabric-main")).toBeTruthy();
    // The route-title slot has no source yet, so the honest admission note
    // stays visible even when every placement slot is proposed.
    expect(screen.getByText("Admission has not proposed a route yet.")).toBeTruthy();
  });

  it("supports the back action and the routing link", () => {
    const onBack = vi.fn(), onViewRouting = vi.fn();
    render(<ProjectRouteReview route={null} onBack={onBack} onViewRouting={onViewRouting} />);
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(onBack).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "View routing & limits" }));
    expect(onViewRouting).toHaveBeenCalledTimes(1);
  });

  it("carries zh-CN strings for the new surface copy", () => {
    render(<ProjectRouteReview route={route} locale="zh-CN" />);
    expect(screen.getByText("审阅编码路由")).toBeTruthy();
    expect(screen.getByText("确认工作内容与提议的路由。尚未开始任何执行。")).toBeTruthy();
    expect(screen.getByText("受理绑定")).toBeTruthy();
    expect(screen.getByText("root-wo19-coding-7")).toBeTruthy();
    expect(screen.getByText("受理尚未提出路由。")).toBeTruthy();
    expect(screen.getAllByText("提交请求").length).toBeGreaterThanOrEqual(2); // footer heading + button
    expect(screen.getByText("仅在受理之后才会开始执行。")).toBeTruthy();
    expect(screen.getByText(/此界面仅可预览/)).toBeTruthy();
    expect(screen.getAllByText("未知").length).toBe(5);
  });

  it("exposes keyboard focus targets on its heading", () => {
    render(<ProjectRouteReview route={null} />);
    const heading = document.getElementById("mm-route-review-heading");
    expect(heading?.getAttribute("tabindex")).toBe("-1");
  });

  it("mounts inside ProjectDeliveryPanel before the task section", () => {
    const { container } = render(
      <ProjectDeliveryPanel
        objective={null}
        owner={null}
        route={route}
        delegatedTask={null}
        run={null}
        executionReturn={null}
        trail={[]}
      />,
    );
    expect(screen.getByText("Review the route")).toBeTruthy();
    expect(screen.getByText("root-wo19-coding-7")).toBeTruthy();
    const sections = Array.from(container.querySelectorAll("section"));
    const routeIdx = sections.findIndex((s) => s.querySelector(".mm-route-review"));
    const codingIdx = sections.findIndex((s) => s.classList.contains("mm-delivery-coding"));
    expect(routeIdx).toBeGreaterThanOrEqual(0);
    expect(codingIdx).toBeGreaterThan(routeIdx);
  });
});
