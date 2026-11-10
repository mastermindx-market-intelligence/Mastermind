// @vitest-environment jsdom
// @vitest-environment-options {"url":"https://mcp.mastermind-x.com/os/"}
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { IDBFactory } from "fake-indexeddb";
import { App } from "./App";
import { createNativeClient } from "./host";
import { composeMissionHost } from "./compose-mission-host";
import { decodeLaunchBindingConfig } from "./launch-config";
import { intentIdForOperationKey, requestRefForOperationKey } from "./orchestration/operation-key";
import { navigateCompanyOperation } from "./test-operational-navigation";

let dispose = () => {};
afterEach(() => {
  cleanup(); dispose(); delete window.MastermindMissionHost;
  history.replaceState(null, "", "/os/");
});

it.each([false, true])("actual native client composes one H2 launch, retained read and explicit consume (lost response=%s)", async (loseConsumeResponse) => {
  const config = decodeLaunchBindingConfig(JSON.stringify({
    v: 1, workstream: "WS:NATIVE-H2", priority: 0, attemptLimit: 1,
    projects: [{ ref: "executive-infrastructure", label: "Infrastructure" }],
    profiles: [{ ref: "research_only", label: "Research" },
      { ref: "native_research_only", label: "Native research" }],
  }))!;
  if ("bindings" in config) throw new Error("Expected the legacy v1 fixture");
  let consumed = false;
  const selection = { work_ref: config.workstream, job_id: "JOB-native-original", attempt_id: "ATT-native-original" };
  const result = () => ({
    schema: "mastermind.direct_native_result_response.v1", selection,
    availability: "AVAILABLE", reason_codes: [],
    result: { result_digest: "d".repeat(64), summary: "Original native retained result",
      current_state: "Completed", completed_steps: ["Read supplied evidence"], next_actions: [] },
    consumption: consumed ? { state: "CONSUMED", receipt_digest: "c".repeat(64) }
      : { state: "UNCONSUMED", receipt_digest: null },
  });
  const invoke = vi.fn(async (command: string, input?: Record<string, unknown>): Promise<unknown> => {
    if (command === "auth_status") return { status: "signed_in", reason: null, acquisition: true, content: true };
    if (command === "executive_auth_status") return { generation: 4, available: true };
    if (command === "executive_context") return {
      schema: "mastermind.os.executive.owner_context.v1", principal_scope: "a".repeat(64),
      verified_expiry: Math.floor(Date.now() / 1000) + 600,
      profile: { name: "web_ceo_v3", server_version: "1.5.0" },
    };
    if (command === "executive_submit") {
      const args = input!.arguments as Record<string, unknown>;
      return { ok: true, status: "accepted", request_ref: requestRefForOperationKey(String(args.operation_key)), receipt: {
        schema: "mastermind.ceo_direct_native_receipt.v1", intent_id: intentIdForOperationKey(String(args.operation_key)),
        fingerprint: "f".repeat(64), job_id: selection.job_id, status: "QUEUED", accepted: true,
        duplicate: false, dispatched: false, authority: { requested: ["READ", "RESEARCH"], policy_sha256: "b".repeat(64), authority_level: "A0" },
        grounding: {}, created_at_ms: 0, work_ref: config.workstream,
      } };
    }
    if (command === "executive_direct_native_result") return result();
    if (command === "executive_direct_native_consume") {
      consumed = true;
      if (loseConsumeResponse) throw new Error("synthetic response loss after the retained acknowledgement");
      return result();
    }
    return {};
  });
  const client = await createNativeClient(invoke as never, async () => () => {});
  const composed = composeMissionHost(client, config, new IDBFactory());
  dispose = composed.dispose;
  await composed.ready;
  window.MastermindMissionHost = composed.host;
  const page = render(<App />), user = userEvent.setup();
  await navigateCompanyOperation(user, "Work");
  await user.selectOptions(screen.getByLabelText("Profile"), "native_research_only");
  await user.type(screen.getByLabelText("Goal"), "Read the supplied evidence only.");
  await waitFor(() => expect(screen.getByRole("button", { name: "Launch" }).hasAttribute("disabled")).toBe(false));
  await user.click(screen.getByRole("button", { name: "Launch" }));
  expect(await screen.findByRole("heading", { name: "Native task result" })).toBeTruthy();
  expect(window.location.search).toContain("direct_native_job=JOB-native-original");
  const calls = (command: string) => invoke.mock.calls.filter(([name]) => name === command);
  expect(calls("executive_submit")).toHaveLength(1);
  expect(calls("executive_submit")[0][1]!.arguments).toMatchObject({
    execution_profile: "native_research_only", attempt_limit: 1,
  });
  expect(calls("executive_submit")[0][1]!.arguments).not.toHaveProperty("frontier_model_alias");
  expect(calls("executive_direct_native_result")).toHaveLength(0);
  expect(calls("executive_direct_native_consume")).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "Read current result" }));
  expect(await screen.findByText("Original native retained result")).toBeTruthy();
  expect(calls("executive_direct_native_result")[0][1]).toEqual({ arguments: { ...selection, attempt_id: null } });
  await user.click(screen.getByRole("button", { name: "Acknowledge this result" }));
  if (loseConsumeResponse) {
    await user.click(await screen.findByRole("button", { name: "Check status" }));
  }
  expect(await screen.findByText(/original commissioning parent acknowledged/)).toBeTruthy();
  expect(calls("executive_direct_native_consume")).toHaveLength(1);
  expect(calls("executive_direct_native_consume")[0][1]!.arguments).toEqual({
    ...selection, result_digest: "d".repeat(64), operation_key: expect.stringMatching(/^mmos-consume-[0-9a-f]{40}$/),
  });
  if (loseConsumeResponse) {
    // The pending original consume resolves through the existing read owner.
    expect(calls("executive_direct_native_result")[1][1]).toEqual({ arguments: selection });
  }
  page.unmount(); render(<App />);
  expect(await screen.findByRole("heading", { name: "Native task result" })).toBeTruthy();
  expect(calls("executive_submit")).toHaveLength(1);
  expect(calls("executive_direct_native_consume")).toHaveLength(1);
  expect(calls("executive_status")).toHaveLength(0);
});
