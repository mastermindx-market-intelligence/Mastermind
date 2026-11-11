// @vitest-environment jsdom
import { afterEach, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { decodeRetainedProviderCapacity } from "./retained-provider-capacity";
import { RetainedProviderCapacityPanel } from "./RetainedProviderCapacityPanel";
import ownerProjection from "./fixtures/retained-provider-owner-projection.json";
afterEach(cleanup);
const selection = { workRef: "WS:ONE", rootJobId: "JOB-1", jobId: "JOB-2", attemptId: "ATT-1" };
const document = () => ({
  schema: "mastermind.retained_provider_capacity.v1", root_job_id: "JOB-1", job_id: "JOB-2", attempt_id: "ATT-1",
  claim_event_id: 17, begin_event_id: 16, claim_recorded_at_ms: 100100, observed_at_ms: 100000, age_ms: 60000,
  source_snapshot_sha256: "a".repeat(64), source_release_commit: "b".repeat(40),
  host_ref: "host-" + "c".repeat(64), boot_ref: "boot-" + "d".repeat(64), provider: "minimax", provider_enabled: true,
  realm_auth: { state: "authenticated", source_quality: "native_provider" },
  provider_health: { state: "unknown", error_class: null },
  cooling: { active: null, kind: null, reset_at: null },
  quota_horizons: [{ name: "hourly", remaining: 3, limit: 20, reset_at: "2026-11-04T10:00:00Z" }],
  current_eligibility: "NOT_EVALUATED", can_place_work: false, observation_kind: "RETAINED_CLAIM",
});
it("consumes the actual inert Runtime claim/SAME-receipt projection across Python and TypeScript", () => {
  const read = decodeRetainedProviderCapacity(ownerProjection, {
    workRef: "WS:ONE", rootJobId: ownerProjection.root_job_id,
    jobId: ownerProjection.job_id, attemptId: ownerProjection.attempt_id,
  });
  expect(typeof read.claim_event_id).toBe("number");
  expect(typeof read.begin_event_id).toBe("number");
  expect(read.observation_kind).toBe("RETAINED_CLAIM");
  expect(read.current_eligibility).toBe("NOT_EVALUATED");
  expect(read.can_place_work).toBe(false);
});
it("keeps original receipt age/auth/quota separate from present eligibility in EN and ZH", () => {
  const value = decodeRetainedProviderCapacity(document(), selection);
  const { rerender } = render(<RetainedProviderCapacityPanel state={{ state: "AVAILABLE", document: value }} />);
  expect(screen.getByText("Authenticated")).toBeTruthy();
  expect(screen.getByText(/Observation age when read/).textContent).toContain("60 seconds");
  expect(screen.getByText(/Current eligibility has not been evaluated/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: /place|reserve|start/i })).toBeNull();
  rerender(<RetainedProviderCapacityPanel state={{ state: "AVAILABLE", document: value }} locale="zh-CN" />);
  expect(screen.getByText("已认证")).toBeTruthy();
  expect(screen.getByText(/尚未评估当前执行资格/)).toBeTruthy();
});
it("rejects foreign selections, new grants, secret-bearing extras and malformed quota counts", () => {
  expect(() => decodeRetainedProviderCapacity(document(), { ...selection, rootJobId: "FOREIGN" })).toThrow();
  expect(() => decodeRetainedProviderCapacity({ ...document(), can_place_work: true }, selection)).toThrow();
  expect(() => decodeRetainedProviderCapacity({ ...document(), account: "PRIVATE" }, selection)).toThrow();
  const nested = document(); nested.realm_auth = { ...nested.realm_auth, token: "PRIVATE" } as never;
  expect(() => decodeRetainedProviderCapacity(nested, selection)).toThrow();
  const quota = document(); quota.quota_horizons[0].remaining = 21;
  expect(() => decodeRetainedProviderCapacity(quota, selection)).toThrow();
});
it("refuses impossible claim age and unsafe integer identity", () => {
  expect(() => decodeRetainedProviderCapacity({ ...document(), claim_recorded_at_ms: 999999 }, selection)).toThrow();
  expect(() => decodeRetainedProviderCapacity({ ...document(), claim_event_id: Number.MAX_SAFE_INTEGER + 1 }, selection)).toThrow();
});
it("clears returned receipts when the source owner is no longer available", () => {
  const { rerender } = render(<RetainedProviderCapacityPanel state={{ state: "AVAILABLE", document: decodeRetainedProviderCapacity(document(), selection) }} />);
  expect(screen.getByText(/hourly/)).toBeTruthy();
  rerender(<RetainedProviderCapacityPanel state={{ state: "UNAVAILABLE" }} />);
  expect(screen.queryByText(/hourly/)).toBeNull();
  expect(screen.getByRole("status").textContent).toContain("No qualified retained claim");
});
