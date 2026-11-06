// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { AuthState, MissionHost } from "../host";
import { ModelConfigurationRead } from "./ModelConfigurationRead";
import {
  decodeModelConfiguration,
  MODEL_CONFIGURATION_SCHEMA,
  type ModelConfigurationRead as ConfigurationRead,
} from "./model-configuration";

afterEach(cleanup);

function snapshot(revision: "a" | "b" | "c", aliases: string[]): ConfigurationRead {
  const providers = Object.fromEntries(aliases.map(alias => [alias, {
    adapter_id: "test-adapter", enabled: true, autonomous_allowed: false,
  }]));
  const models = Object.fromEntries(aliases.map(alias => [`model-${alias}-${revision}`, {
    provider_alias: alias, adapter_id: "test-adapter", model: `${alias}-model-${revision}`,
    effort: "normal", cost_class: "test", capabilities: ["reasoning"],
    worker_eligible: false, execution_profile_id: `profile-${alias}`,
    execution_profile_digest: "f".repeat(64),
  }]));
  const read = decodeModelConfiguration({
    schema: MODEL_CONFIGURATION_SCHEMA, availability: "AVAILABLE",
    observed_at: "2026-11-06T12:00:00Z", source_owner: "model_router", reason_codes: [],
    configuration: {
      schema: "mastermind.model_router_configuration.v1", owner: "model_router",
      scope: "EXECUTIVE_ROUTING_POLICY", revision: revision.repeat(64),
      policy_version: "test-policy", capability_policy_version: "test-capabilities",
      capability_policy_digest: "e".repeat(64), physical_account_pools: "NOT_JOINED",
      live_capacity: "NOT_OBSERVED", admission_authorized: false,
      writes_applied: false, credential_resolution_performed: false,
      providers, models, routes: {
        inspect: { required_capabilities: ["reasoning"],
          routine: [{ tier_id: "default", model_aliases: Object.keys(models) }], elevated: [] },
      },
    },
  });
  if (read.state !== "AVAILABLE") throw new Error("The owner fixture must satisfy the real closed decoder");
  return read;
}

function owner() {
  const state: AuthState = { status: "signed_in", acquisition: true, content: false, reason: null };
  const read = vi.fn<(_request: { signal?: AbortSignal }) => Promise<ConfigurationRead>>();
  const host = {
    auth: { getState: () => state, subscribe: () => () => {} },
    invalidationGeneration: () => 1,
    readModelConfiguration: read,
  } as unknown as MissionHost;
  return { host, read };
}

function readConfiguration() {
  fireEvent.click(screen.getByRole("button", { name: "Read configuration" }));
}

function providerFilter() {
  return screen.getByRole("combobox", { name: "Provider alias" }) as HTMLSelectElement;
}

async function readAndSelectP(env: ReturnType<typeof owner>) {
  expect(env.read).not.toHaveBeenCalled();
  readConfiguration();
  await screen.findByText("p-model-a");
  fireEvent.change(providerFilter(), { target: { value: "p" } });
  expect(providerFilter().value).toBe("p");
  expect(screen.queryByText("q-model-a")).toBeNull();
}

it("shows the new models and All when an accepted reload removes the selected provider", async () => {
  const env = owner();
  env.read.mockResolvedValueOnce(snapshot("a", ["p", "q"]))
    .mockResolvedValueOnce(snapshot("b", ["q"]));
  render(<ModelConfigurationRead host={env.host} />);
  await readAndSelectP(env);

  readConfiguration();
  await screen.findByText("b".repeat(64));
  expect(providerFilter().value).toBe("");
  expect(providerFilter().selectedOptions[0].textContent).toBe("All configured providers");
  expect(screen.getByText("q-model-b")).toBeTruthy();
  expect(screen.queryByText("p-model-a")).toBeNull();
  expect(screen.getByText("Provider aliases").nextElementSibling?.textContent).toBe("1");
  expect(screen.getByText("Model aliases").nextElementSibling?.textContent).toBe("1");
  expect(screen.getByText("Showing 1 of 1 matching model aliases")).toBeTruthy();
  expect(env.read).toHaveBeenCalledTimes(2);
});

it("retains a provider that is still configured and preserves the search across a reload", async () => {
  const env = owner();
  env.read.mockResolvedValueOnce(snapshot("a", ["p", "q"]))
    .mockResolvedValueOnce(snapshot("b", ["p", "q"]));
  render(<ModelConfigurationRead host={env.host} />);
  await readAndSelectP(env);
  const search = screen.getByRole("searchbox", { name: "Find a model or capability" }) as HTMLInputElement;
  fireEvent.change(search, { target: { value: "REASON" } });

  readConfiguration();
  await screen.findByText("b".repeat(64));
  expect(providerFilter().value).toBe("p");
  expect((screen.getByRole("searchbox", { name: "Find a model or capability" }) as HTMLInputElement).value).toBe("REASON");
  expect(screen.getByText("p-model-b")).toBeTruthy();
  expect(screen.queryByText("q-model-b")).toBeNull();
  expect(screen.getByText("Showing 1 of 1 matching model aliases")).toBeTruthy();
});

it("does not clear the selected provider when the owner reports unavailable", async () => {
  const env = owner();
  env.read.mockResolvedValueOnce(snapshot("a", ["p", "q"]))
    .mockResolvedValueOnce({ state: "UNAVAILABLE", reason: "SOURCE_UNAVAILABLE" })
    .mockResolvedValueOnce(snapshot("b", ["p", "q"]));
  render(<ModelConfigurationRead host={env.host} />);
  await readAndSelectP(env);

  readConfiguration();
  await screen.findByText("The configuration could not be released by its owner. No empty pool or healthy state is inferred.");
  expect(screen.queryByRole("combobox", { name: "Provider alias" })).toBeNull();
  expect(screen.queryByText("p-model-a")).toBeNull();

  readConfiguration();
  await screen.findByText("b".repeat(64));
  expect(providerFilter().value).toBe("p");
  expect(screen.getByText("p-model-b")).toBeTruthy();
  expect(screen.queryByText("q-model-b")).toBeNull();
});

it("ignores a superseded aborted read without changing the current provider selection", async () => {
  const original = owner();
  let finishOld!: (read: ConfigurationRead) => void;
  let oldSignal: AbortSignal | undefined;
  original.read.mockResolvedValueOnce(snapshot("a", ["p", "q"]))
    .mockImplementationOnce(request => {
      oldSignal = request.signal;
      return new Promise(resolve => { finishOld = resolve; });
    });
  const { rerender } = render(<ModelConfigurationRead host={original.host} />);
  await readAndSelectP(original);
  readConfiguration();

  const current = owner();
  current.read.mockResolvedValue(snapshot("c", ["p", "q"]));
  rerender(<ModelConfigurationRead host={current.host} />);
  expect(oldSignal?.aborted).toBe(true);
  readConfiguration();
  await screen.findByText("c".repeat(64));
  expect(providerFilter().value).toBe("p");

  await act(async () => { finishOld(snapshot("b", ["q"])); });
  expect(providerFilter().value).toBe("p");
  expect(screen.getByText("p-model-c")).toBeTruthy();
  expect(screen.queryByText("q-model-c")).toBeNull();
  expect(screen.queryByText("b".repeat(64))).toBeNull();
  expect(screen.getByText("c".repeat(64))).toBeTruthy();
});
