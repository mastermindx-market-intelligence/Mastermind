// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import fixture from "../../../../research/evidence/native-capacity-owner-projection.json";
import { decodeHostCapacityRead } from "./host-capacity";
import { HostTelemetryPanel } from "./HostTelemetryPanel";
afterEach(cleanup);
it("renders actual owner-projection metric units without a ready/placement claim", () => {
  render(<HostTelemetryPanel state={{ state: "AVAILABLE", document: decodeHostCapacityRead(fixture) }} />);
  expect(screen.getByText("1,500 millicores_ceiling")).toBeTruthy();
  expect(screen.getByText("Not evaluated; cannot place work")).toBeTruthy();
  expect(screen.getByText(/OBSERVATION_ONLY/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: /place|reserve|start/i })).toBeNull();
});
it("retains partial unknown readings and removes metrics when qualified source is lost", () => {
  const raw = structuredClone(fixture);
  raw.metrics.disk_usable_bytes = { value: null, null_reason: "PERMISSION_DENIED", unit: "bytes_unprivileged" } as never;
  raw.unknown_fields = ["disk_usable_bytes"] as never;
  raw.telemetry_status = "PARTIAL";
  const { rerender } = render(<HostTelemetryPanel state={{ state: "AVAILABLE", document: decodeHostCapacityRead(raw) }} locale="zh-CN" />);
  expect(screen.getByText("未提供")).toBeTruthy();
  expect(screen.getByText(/PERMISSION_DENIED/)).toBeTruthy();
  rerender(<HostTelemetryPanel state={{ state: "UNAVAILABLE" }} locale="zh-CN" />);
  expect(screen.queryByText(/PERMISSION_DENIED/)).toBeNull();
  expect(screen.getByRole("status").textContent).toContain("仍然未知");
});
