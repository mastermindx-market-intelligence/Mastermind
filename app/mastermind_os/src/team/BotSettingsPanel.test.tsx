// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BotSettingsPanel } from "./BotSettingsPanel";
// The roster and configuration fixtures pass through the REAL fail-closed
// parsers, so every rendered value is contract-valid by construction.
import { parseTeamRoster } from "../hermes-native/team-roster-contract";
import { decodeModelConfiguration } from "../resources/model-configuration";
import type { MissionHost } from "../host";
afterEach(cleanup);

const rosterBot = parseTeamRoster({
  schema: "mastermind.team_roster/v1", generatedAt: "2026-11-09T12:00:00Z",
  host: "m2studio",
  bots: [{
    id: "bot-alpha", displayName: "Alpha Bot", role: "Research lead",
    profilePath: "/Users/operator/.hermes/profiles/alpha", managed: true,
    host: "m2studio",
    gateway: { observed: true, source: "control_socket_identify", instanceId: "gw-1",
      authorityEpoch: 4, codeVersion: "0.23.0", pid: 1234, state: "ready" },
    readiness: "ready", readinessReason: "GATEWAY_IDENTIFY_READY",
    lastActivity: "2026-11-09T00:00:00Z", activitySummary: "Reading regime data",
  }],
}).bots[0]!;

const configPayload = {
  schema: "mastermind.workspace_model_configuration.v1",
  availability: "AVAILABLE", observed_at: "2026-11-09T12:00:00Z",
  source_owner: "model_router", reason_codes: [],
  configuration: {
    schema: "mastermind.model_router_configuration.v1", owner: "model_router",
    scope: "EXECUTIVE_ROUTING_POLICY", revision: "a".repeat(64),
    policy_version: "policy-2026-11", capability_policy_version: "cap-2026-11",
    capability_policy_digest: "b".repeat(64), physical_account_pools: "NOT_JOINED",
    live_capacity: "NOT_OBSERVED", admission_authorized: false,
    writes_applied: false, credential_resolution_performed: false,
    providers: {
      "fabric-one": { adapter_id: "adapter-fabric", enabled: true, autonomous_allowed: true },
      "bench-two": { adapter_id: "adapter-bench", enabled: false, autonomous_allowed: false },
    },
    models: {
      scout: { provider_alias: "fabric-one", adapter_id: "adapter-fabric", model: "scout-v2",
        effort: "medium", cost_class: "standard", capabilities: ["code"], worker_eligible: true,
        execution_profile_id: "profile-scout", execution_profile_digest: "c".repeat(64) },
      atlas: { provider_alias: "fabric-one", adapter_id: "adapter-fabric", model: "atlas-v1",
        effort: "high", cost_class: "standard", capabilities: ["code", "review"], worker_eligible: false,
        execution_profile_id: "profile-atlas", execution_profile_digest: "d".repeat(64) },
    },
    routes: {
      coding: { required_capabilities: ["code"],
        routine: [{ tier_id: "t1", model_aliases: ["scout"] }],
        elevated: [{ tier_id: "t1", model_aliases: ["atlas"] }] },
    },
  },
};

const signedInAuth = {
  getState: () => ({ status: "signed_in", reason: null, acquisition: true, content: false }),
  subscribe: () => () => {},
  signIn: async () => {},
  signOut: async () => {},
};
function hostWith(
  behaviour: () => Promise<unknown>,
  auth: unknown = signedInAuth,
): { host: MissionHost; reader: ReturnType<typeof vi.fn> } {
  const reader = vi.fn(behaviour);
  return { host: { auth, readModelConfiguration: reader } as unknown as MissionHost, reader };
}

const PAPER_SAMPLES = /Ryan|Meta-CEO|Secretary|Engineering|GLM 5\.3|GLM Fabric/i;

describe("BotSettingsPanel (HC09) — Models tab on the real host read", () => {
  it("opens on the Models tab with the honest read-only contract", async () => {
    const { host } = hostWith(async () => decodeModelConfiguration(configPayload));
    render(<BotSettingsPanel bot={rosterBot} host={host} onClose={() => {}} />);
    expect(
      screen.getByRole("tab", { name: "Models" }).getAttribute("aria-selected"),
    ).toBe("true");
    expect(screen.getByText("Model defaults")).toBeTruthy();
    expect(screen.getByText("Used when this bot starts a new session.")).toBeTruthy();
    expect(screen.getByText("EFFECT·NONE")).toBeTruthy();
    expect(
      screen.getByText(/preview the policy and apply nothing/i),
    ).toBeTruthy();
    // The read is real: the configured providers arrive from the host.
    // The provider string rides both the select option and the scope row.
    expect((await screen.findAllByText("fabric-one · Enabled in policy")).length).toBeGreaterThan(0);
  });

  it("populates provider, model and reasoning only from the real configuration", async () => {
    const { host } = hostWith(async () => decodeModelConfiguration(configPayload));
    render(<BotSettingsPanel bot={rosterBot} host={host} onClose={() => {}} />);
    const provider = await screen.findByLabelText("Provider connection");
    const options = Array.from((provider as HTMLSelectElement).options).map(
      (option) => option.textContent,
    );
    expect(options).toContain("Team default");
    expect(options).toContain("fabric-one · Enabled in policy");
    expect(options).toContain("bench-two · Disabled in policy");
    expect(options.length).toBe(3);

    const model = screen.getByLabelText("Main model") as HTMLSelectElement;
    expect(
      Array.from(model.options).map((option) => option.textContent),
    ).toEqual(["Follow team policy", "scout · scout-v2", "atlas · atlas-v1"]);

    // Reasoning follows the selected alias's configured effort.
    expect(screen.getByText("Follows the selected model's policy")).toBeTruthy();
    fireEvent.change(model, { target: { value: "atlas" } });
    expect(screen.getByText("high")).toBeTruthy();
  });

  it("shows the configured fallback order and policy-owned rows", async () => {
    const { host } = hostWith(async () => decodeModelConfiguration(configPayload));
    render(<BotSettingsPanel bot={rosterBot} host={host} onClose={() => {}} />);
    // The provider string rides both the select option and the scope row.
    expect((await screen.findAllByText("fabric-one · Enabled in policy")).length).toBeGreaterThan(0);
    expect(screen.getByText(/Used only when the selected provider is unavailable/i)).toBeTruthy();
    expect(screen.getByText(/Configured fallback order: coding: scout/i)).toBeTruthy();
    // "Team default" rides the provider select option and the auxiliary row.
    expect(screen.getAllByText("Team default").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/Follows the team policy \(2 configured model aliases\)/i)).toBeTruthy();
    expect(screen.getByText("Managed placement ›")).toBeTruthy();
    expect(screen.getByText(/model router owns it/i)).toBeTruthy();
  });

  it("renders the honest unavailable state when no host exposes the read", () => {
    render(<BotSettingsPanel bot={rosterBot} onClose={() => {}} />);
    expect(screen.getByText("Model policy not verified")).toBeTruthy();
    expect(
      screen.getByText(
        "The team's model configuration could not be read on this connection. No provider, model or reasoning level is shown or inferred.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("READ_NOT_EXPOSED")).toBeTruthy();
    expect(screen.getByText(/This host does not expose the model-configuration read/i)).toBeTruthy();
    // No selects are populated with invented providers or models.
    expect(screen.queryByLabelText("Provider connection")).toBeNull();
    expect(screen.queryByLabelText("Main model")).toBeNull();
    expect(document.body.textContent).not.toMatch(PAPER_SAMPLES);
  });

  it("does not call the read while signed out and reports the closed code", () => {
    const signedOutAuth = {
      getState: () => ({ status: "signed_out", reason: null, acquisition: false, content: false }),
      subscribe: () => () => {},
      signIn: async () => {},
      signOut: async () => {},
    };
    const { host, reader } = hostWith(
      async () => decodeModelConfiguration(configPayload),
      signedOutAuth,
    );
    render(<BotSettingsPanel bot={rosterBot} host={host} onClose={() => {}} />);
    expect(screen.getByText("MODEL_CONFIGURATION_UNAUTHORIZED")).toBeTruthy();
    expect(reader).not.toHaveBeenCalled(); // no call, no inference
  });

  it("maps a refused read and a thrown refusal to their honest reason codes", async () => {
    const refused = hostWith(async () =>
      decodeModelConfiguration({
        ...configPayload, availability: "UNAVAILABLE", observed_at: null,
        configuration: null, reason_codes: ["SOURCE_CHANGED"],
      }),
    );
    render(<BotSettingsPanel bot={rosterBot} host={refused.host} onClose={() => {}} />);
    await screen.findByText("SOURCE_CHANGED");
    expect(screen.getByText(/The source changed while being read/i)).toBeTruthy();
    cleanup();
    const throwing = hostWith(async () => {
      throw new Error("MODEL_CONFIGURATION_UNAUTHORIZED");
    });
    render(<BotSettingsPanel bot={rosterBot} host={throwing.host} onClose={() => {}} />);
    await screen.findByText("MODEL_CONFIGURATION_UNAUTHORIZED");
  });

  it("keeps other tabs as honest not-projected placeholders with tab keyboard order", async () => {
    const { host } = hostWith(async () => decodeModelConfiguration(configPayload));
    render(<BotSettingsPanel bot={rosterBot} host={host} onClose={() => {}} />);
    // The provider string rides both the select option and the scope row.
    expect((await screen.findAllByText("fabric-one · Enabled in policy")).length).toBeGreaterThan(0);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      "Overview", "Models", "Capabilities", "Memory", "Routines",
    ]);
    fireEvent.click(screen.getByRole("tab", { name: "Overview" }));
    expect(
      screen.getAllByText("Not projected in this build").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(/This section of bot settings is not projected in this build/i),
    ).toBeTruthy();
    // Arrow keys move the tab selection.
    const tablist = screen.getByRole("tablist", { name: "Bot settings sections" });
    fireEvent.keyDown(tablist, { key: "ArrowRight" }); // overview -> models
    expect(
      screen.getByRole("tab", { name: "Models" }).getAttribute("aria-selected"),
    ).toBe("true");
    fireEvent.keyDown(tablist, { key: "ArrowLeft" }); // models -> overview
    expect(
      screen.getByRole("tab", { name: "Overview" }).getAttribute("aria-selected"),
    ).toBe("true");
  });

  it("scope panel carries the real bot and honest conversation/connection rows", async () => {
    const { host } = hostWith(async () => decodeModelConfiguration(configPayload));
    render(<BotSettingsPanel bot={rosterBot} host={host} onClose={() => {}} />);
    await screen.findByText("APPLIES TO");
    expect(screen.getByText("Alpha Bot")).toBeTruthy(); // real roster name
    expect(screen.getByText("Current conversation")).toBeTruthy();
    expect(screen.getByText("Use its composer to change the active model.")).toBeTruthy();
    expect(screen.getByText("Credentials are held by this connection.")).toBeTruthy();
    const manage = screen.getByRole("button", { name: "Manage providers →" });
    expect(manage.hasAttribute("disabled")).toBe(true);
    expect(
      screen.getByText(/Provider and capability management is not wired/i),
    ).toBeTruthy();
  });

  it("closes on Escape and returns focus to the trigger", () => {
    function Harness() {
      const [open, setOpen] = React.useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            Open settings
          </button>
          {open ? (
            <BotSettingsPanel bot={rosterBot} onClose={() => setOpen(false)} />
          ) : null}
        </>
      );
    }
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "Open settings" });
    trigger.focus();
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Bot settings" })).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("renders the zh-CN copy (TD10/HC15)", async () => {
    const { host } = hostWith(async () => decodeModelConfiguration(configPayload));
    render(
      <BotSettingsPanel bot={rosterBot} host={host} locale="zh-CN" onClose={() => {}} />,
    );
    await screen.findByText("模型默认值");
    expect(screen.getByText("在此机器人开始新会话时使用。")).toBeTruthy();
    expect(screen.getByText("提供商连接")).toBeTruthy();
    expect(screen.getByText("主模型")).toBeTruthy();
    expect(screen.getByText("无效果")).toBeTruthy();
    expect(screen.getByText("适用范围")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(PAPER_SAMPLES);
  });

  it("carries no Paper sample model names in any state", async () => {
    const { host } = hostWith(async () => decodeModelConfiguration(configPayload));
    const { unmount } = render(
      <BotSettingsPanel bot={rosterBot} host={host} onClose={() => {}} />,
    );
    // The provider string rides both the select option and the scope row.
    expect((await screen.findAllByText("fabric-one · Enabled in policy")).length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(PAPER_SAMPLES);
    unmount();
    render(<BotSettingsPanel bot={rosterBot} onClose={() => {}} />);
    expect(document.body.textContent).not.toMatch(PAPER_SAMPLES);
  });
});
