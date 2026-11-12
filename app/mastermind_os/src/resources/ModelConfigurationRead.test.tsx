// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { AuthState, MissionHost } from "../host";
import { ModelConfigurationRead } from "./ModelConfigurationRead";
import { displayObservationTime, explainConfiguredRoute, policyModelCounts } from "./model-route-explanation";
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
  let state: AuthState = { status: "signed_in", acquisition: true, content: false, reason: null };
  const listeners = new Set<() => void>();
  const read = vi.fn<(_request: { signal?: AbortSignal }) => Promise<ConfigurationRead>>();
  const host = {
    auth: { getState: () => state, subscribe: (listener: () => void) => {
      listeners.add(listener); return () => listeners.delete(listener);
    } },
    invalidationGeneration: () => 1,
    readModelConfiguration: read,
  } as unknown as MissionHost;
  return { host, read, revoke: () => {
    state = { ...state, acquisition: false };
    for (const listener of listeners) listener();
  } };
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

it("keeps qualification and physical capacity unproven when every model is enabled", async () => {
  const env = owner();
  const read = snapshot("a", ["p", "q"]);
  if (read.state !== "AVAILABLE") throw new Error("available fixture required");
  expect(policyModelCounts(read.configuration)).toEqual({ configured: 2, enabledInPolicy: 2,
    qualified: null, currentlyEligible: null, realPathProven: null, physicalAccounts: null });
  env.read.mockResolvedValue(read);
  render(<ModelConfigurationRead host={env.host} />);
  readConfiguration();
  await screen.findByText("p-model-a");
  expect(screen.getByText("Configured models").nextElementSibling?.textContent).toBe("2");
  expect(screen.getByText("Qualified").nextElementSibling?.textContent).toBe("Unproven");
  expect(screen.getByText("Eligible now").nextElementSibling?.textContent).toBe("Unknown");
  expect(screen.getByText("Real-path proven").nextElementSibling?.textContent).toBe("Unproven");
  expect(screen.getByText("Physical allowance owners").nextElementSibling?.textContent).toBe("Not joined");
});

it("preserves the owner route order and explains policy exclusions without live selection", () => {
  const read = snapshot("a", ["p", "q"]);
  if (read.state !== "AVAILABLE") throw new Error("available fixture required");
  const configuration = structuredClone(read.configuration);
  configuration.providers.p.enabled = false;
  configuration.models["model-p-a"].capabilities = [];
  configuration.routes.inspect.routine = [
    { tier_id: "first", model_aliases: ["model-q-a"] },
    { tier_id: "second", model_aliases: ["model-p-a"] },
  ];
  const before = JSON.stringify(configuration);
  const result = explainConfiguredRoute(configuration, "inspect", "routine");
  expect(result.rows.map(row => row.alias)).toEqual(["model-q-a", "model-p-a"]);
  expect(result.rows[1].reasons).toEqual(["PROVIDER_DISABLED", "AUTONOMOUS_DISABLED", "WORKER_NOT_ELIGIBLE", "CAPABILITIES_MISSING"]);
  expect(result.rows[1].missingCapabilities).toEqual(["reasoning"]);
  expect(result.accountSelection).toBe("NOT_OBSERVED");
  expect(result.servedModel).toBe("NOT_OBSERVED");
  expect(result.reservation).toBe("NONE");
  expect(result.liveEligibility).toBe("NOT_EVALUATED");
  expect(result.admissionAuthorized).toBe(false);
  expect(policyModelCounts(configuration).enabledInPolicy).toBe(1);
  expect(JSON.stringify(configuration)).toBe(before);
});

it("never substitutes another alias when an inspected exact alias is outside the route", () => {
  const read = snapshot("a", ["p", "q"]);
  if (read.state !== "AVAILABLE") throw new Error("available fixture required");
  const result = explainConfiguredRoute(read.configuration, "inspect", "elevated", "model-p-a");
  expect(result.pinState).toBe("OUTSIDE_ROUTE");
  expect(result.rows).toEqual([]);
  expect(explainConfiguredRoute(read.configuration, "inspect", "routine", "missing").pinState).toBe("UNKNOWN_ALIAS");
  expect(explainConfiguredRoute(read.configuration, "inspect", "routine", "model-q-a").rows.map(row => row.alias)).toEqual(["model-q-a"]);
});

it("inspects an empty policy tier without issuing another read or claiming all pools are busy", async () => {
  const env = owner();
  env.read.mockResolvedValue(snapshot("a", ["p", "q"]));
  render(<ModelConfigurationRead host={env.host} />);
  readConfiguration();
  await screen.findByText("p-model-a");
  fireEvent.click(screen.getByText("Explain configured routing"));
  fireEvent.change(screen.getByLabelText("Policy tier"), { target: { value: "elevated" } });
  expect(screen.getByText("No aliases are configured for this workload and tier. This is not evidence that all pools are busy.")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Inspect exact alias"), { target: { value: "model-p-a" } });
  expect(screen.getByText("The inspected alias is outside this configured route. No alternate is chosen.")).toBeTruthy();
  expect(screen.getByText("Policy inspection · no capacity reserved")).toBeTruthy();
  expect(env.read).toHaveBeenCalledTimes(1);
});

it("discards a delayed snapshot after Workspace acquisition access is revoked", async () => {
  const env = owner();
  let finish!: (read: ConfigurationRead) => void;
  let signal: AbortSignal | undefined;
  env.read.mockImplementation(request => {
    signal = request.signal;
    return new Promise(resolve => { finish = resolve; });
  });
  render(<ModelConfigurationRead host={env.host} />);
  readConfiguration();
  act(() => env.revoke());
  expect(signal?.aborted).toBe(true);
  await act(async () => { finish(snapshot("a", ["p", "q"])); });
  expect(screen.queryByText("Configured models")).toBeNull();
  expect(screen.queryByText("p-model-a")).toBeNull();
  expect((screen.getByRole("button", { name: "Read configuration" }) as HTMLButtonElement).disabled).toBe(true);
});

it("formats observation time with the requested zone across daylight saving and rejects invalid times", () => {
  // Use completed historical seasons; future civil-time rules can change between ICU versions.
  const summer = displayObservationTime("2025-07-01T12:00:00Z", "en", "America/Vancouver");
  const winter = displayObservationTime("2025-12-01T12:00:00Z", "en", "America/Vancouver");
  expect(summer).toContain("05:00:00");
  expect(winter).toContain("04:00:00");
  expect(summer).toMatch(/PDT|GMT-7/);
  expect(winter).toMatch(/PST|GMT-8/);
  expect(displayObservationTime("bad-time", "en", "UTC")).toBeNull();
  expect(displayObservationTime("2026-12-01T12:00:00Z", "en", "not/a-zone")).toBeNull();
});

