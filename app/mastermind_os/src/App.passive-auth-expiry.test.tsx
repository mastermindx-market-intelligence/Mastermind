// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { bindMissionHost, type AuthState, type RawClient } from "./host";
import { canNavigateForAutomaticSignIn } from "./auth-navigation-guard";

const initial: AuthState = { status: "signed_in", reason: null, acquisition: true, content: false };
const expired: AuthState = { status: "signed_out", reason: null, acquisition: false, content: false };
const logoutKey = "mastermind-os-auth-logout-v1:synthetic-app";

function fakeWebOwner() {
  let state = initial, generation = 0;
  const listeners = new Set<(state: AuthState) => void>();
  const publish = (next: AuthState) => { state = next; for (const listener of listeners) listener(next); };
  const client: RawClient = {
    getState: () => state, invalidationGeneration: () => generation,
    subscribe: listener => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    signIn: async () => { generation++; publish({ status: "signing_in", reason: null, acquisition: false, content: false }); },
    signOut: async () => {
      localStorage.setItem(logoutKey, "1"); generation++; publish(expired);
    },
    readPrograms: async () => null, readWork: async () => null,
    readMission: async () => null, readCurrentWindow: async () => null,
  };
  return { host: bindMissionHost(client), publish };
}
beforeEach(() => {
  history.replaceState(null, "", "/os/");
  localStorage.removeItem(logoutKey);
  delete (window as any).__TAURI_INTERNALS__;
  delete window.MastermindMissionHost;
});
afterEach(() => {
  cleanup(); localStorage.removeItem(logoutKey);
  vi.restoreAllMocks(); delete window.MastermindMissionHost;
});

describe("passive web Auth0 expiry preserves ONLY this page's unsent user text", () => {
  it("retains a local Office draft without trusting expired permissions or navigating", async () => {
    const web = fakeWebOwner();
    window.MastermindMissionHost = web.host;
    render(<App />);
    const input = screen.getByRole("textbox", { name: "Direction to Meta-CEO" }) as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "Unsent exact private draft - retain." } });
    expect(canNavigateForAutomaticSignIn()).toBe(false);
    await act(async () => { web.publish(expired); });
    expect(input.value).toBe("Unsent exact private draft - retain.");
    expect(canNavigateForAutomaticSignIn()).toBe(false);
    expect(web.host.auth!.getState().acquisition).toBe(false);
    // A new identity may be about to authenticate. The old draft disappears
    // before a fresh credential can become usable.
    await act(async () => { await web.host.auth!.signIn(); });
    expect(screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Direction to Meta-CEO" }).value).toBe("");
  });

  it("clears retained text on explicit cross-tab logout and never bypasses the marker", async () => {
    const web = fakeWebOwner();
    window.MastermindMissionHost = web.host;
    render(<App />);
    fireEvent.change(screen.getByRole("textbox", { name: "Direction to Meta-CEO" }),
      { target: { value: "User text cannot cross sign-out." } });
    await act(async () => { web.publish(expired); });
    expect(screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Direction to Meta-CEO" }).value)
      .toBe("User text cannot cross sign-out.");
    await act(async () => { await web.host.auth!.signOut(); });
    expect(screen.getByRole<HTMLTextAreaElement>("textbox", { name: "Direction to Meta-CEO" }).value).toBe("");
    expect(localStorage.getItem(logoutKey)).toBe("1");
  });
});
