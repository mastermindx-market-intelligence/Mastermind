// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, it, expect, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { App } from "./App";
import { composeMissionHost } from "./compose-mission-host";
import { decodeLaunchBindingConfig } from "./launch-config";
import {
  intentIdForOperationKey,
  requestRefForOperationKey,
} from "./orchestration/operation-key";
import { navigateCompanyOperation } from "./test-operational-navigation";
import type { RawClient } from "./host";
import type { DirectNativeTransport } from "./direct-native-result";
let dispose = () => {};
afterEach(() => {
  cleanup();
  dispose();
  delete window.MastermindMissionHost;
  history.replaceState(null, "", "/os/");
});
it("actual frontend Launch→selected direct result→explicit consume preserves one operation", async () => {
  let consumed = false;
  const config = decodeLaunchBindingConfig(
    JSON.stringify({
      v: 1,
      workstream: "WS:H2-FIXTURE",
      priority: 0,
      attemptLimit: 1,
      projects: [{ ref: "executive-infrastructure", label: "Infrastructure" }],
      profiles: [
        { ref: "research_only", label: "Research" },
        { ref: "native_research_only", label: "Direct native research" },
      ],
    }),
  )!;
  const output = () => ({
    schema: "mastermind.direct_native_result_response.v1",
    selection: {
      work_ref: config.workstream,
      job_id: "JOB-123",
      attempt_id: "ATT-456",
    },
    availability: "AVAILABLE",
    reason_codes: [],
    result: {
      result_digest: "d".repeat(64),
      summary: "Exact retained direct result",
      current_state: "Completed",
      completed_steps: ["Read supplied fixture evidence"],
      next_actions: [],
    },
    consumption: consumed
      ? { state: "CONSUMED", receipt_digest: "c".repeat(64) }
      : { state: "UNCONSUMED", receipt_digest: null },
  });
  const direct = {
    read: vi.fn<DirectNativeTransport["read"]>(async () => output()),
    consume: vi.fn<DirectNativeTransport["consume"]>(async () => {
      consumed = true;
      return output();
    }),
  };
  const submit = vi.fn(async (args: Readonly<Record<string, unknown>>) => ({
    ok: true,
    status: "accepted",
    request_ref: requestRefForOperationKey(String(args.operation_key)),
    receipt: {
      schema: "mastermind.ceo_direct_native_receipt.v1",
      intent_id: intentIdForOperationKey(String(args.operation_key)),
      fingerprint: "f".repeat(64),
      job_id: "JOB-123",
      status: "QUEUED",
      accepted: true,
      duplicate: false,
      dispatched: false,
      authority: {
        requested: ["READ", "RESEARCH"],
        policy_sha256: "a".repeat(64),
        authority_level: "A0",
      },
      grounding: {},
      created_at_ms: 0,
      work_ref: config.workstream,
    },
  }));
  const client: RawClient = {
    getState: () => ({
      status: "signed_in",
      reason: null,
      acquisition: true,
      content: true,
    }),
    subscribe: () => () => {},
    signIn: async () => {},
    signOut: async () => {},
    readPrograms: async () => ({}),
    readWork: async () => ({}),
    readMission: async () => ({}),
    readCurrentWindow: async () => ({}),
    executive: {
      available: () => true,
      authGeneration: () => 1,
      subscribe: () => () => {},
      context: async () => ({
        schema: "mastermind.os.executive.owner_context.v1",
        principal_scope: "a".repeat(64),
        verified_expiry: Math.floor(Date.now() / 1000) + 600,
        profile: { name: "web_ceo_v3", server_version: "1.5.0" },
      }),
      submit,
      status: vi.fn(),
      directNative: direct,
    },
  };
  const composed = composeMissionHost(client, config, new IDBFactory());
  dispose = composed.dispose;
  await composed.ready;
  window.MastermindMissionHost = composed.host;
  const page = render(<App />),
    user = userEvent.setup();
  await navigateCompanyOperation(user, "Work");
  await user.selectOptions(
    screen.getByLabelText("Profile"),
    "native_research_only",
  );
  await user.type(
    screen.getByLabelText("Goal"),
    "Analyze supplied evidence only.",
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Launch" }).hasAttribute("disabled"),
    ).toBe(false),
  );
  await user.click(screen.getByRole("button", { name: "Launch" }));
  expect(
    await screen.findByRole("heading", { name: "Native task result" }),
  ).toBeTruthy();
  expect(window.location.search).toContain("direct_native_job=JOB-123");
  expect(submit).toHaveBeenCalledTimes(1);
  expect(submit.mock.calls[0][0].execution_profile).toBe(
    "native_research_only",
  );
  expect(direct.read).not.toHaveBeenCalled();
  expect(direct.consume).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Read current result" }));
  expect(await screen.findByText("Exact retained direct result")).toBeTruthy();
  expect(direct.consume).not.toHaveBeenCalled();
  await user.click(
    screen.getByRole("button", { name: "Acknowledge this result" }),
  );
  expect(
    await screen.findByText(/original commissioning parent acknowledged/),
  ).toBeTruthy();
  expect(direct.consume).toHaveBeenCalledTimes(1);
  expect(submit).toHaveBeenCalledTimes(1);
  expect(direct.consume.mock.calls[0][0]).toMatchObject({
    job_id: "JOB-123",
    attempt_id: "ATT-456",
    result_digest: "d".repeat(64),
  });
  page.unmount();
  render(<App />);
  expect(
    await screen.findByRole("heading", { name: "Native task result" }),
  ).toBeTruthy();
  expect(submit).toHaveBeenCalledTimes(1);
  expect(direct.consume).toHaveBeenCalledTimes(1);
});
