// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ render: vi.fn(), createWebAuth: vi.fn(), compose: vi.fn() }));
vi.mock("react-dom/client", () => ({ createRoot: () => ({ render: mocks.render }) }));
vi.mock("@tauri-apps/api/core", () => ({ isTauri: () => false, invoke: vi.fn() }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn() }));
vi.mock("../App", () => ({ App: () => null }));
vi.mock("../web-auth", () => ({ createWebAuth: mocks.createWebAuth, handleWebAuthCallback: () => false }));
vi.mock("../compose-mission-host", () => ({ composeMissionHost: mocks.compose }));
const id = `rvitem.v1.${"a".repeat(64)}`;
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); vi.resetModules(); });
it("actual main route mounts citation entry with the private transport and no OS composition", async () => {
  const transport = { available: () => false };
  mocks.createWebAuth.mockReturnValue({ research: transport, signOut: async () => {} });
  vi.stubGlobal("location", { origin: "https://mcp.mastermind-x.com", pathname: `/os/research/evidence/${id}`, search: "", hash: "" });
  await import("../main");
  const element = mocks.render.mock.calls[0][0].props.children;
  expect(element.type.name).toBe("ResearchEvidenceEntry");
  expect(element.props.itemId).toBe(id); expect(element.props.transport).toBe(transport);
  expect(mocks.compose).not.toHaveBeenCalled();
});
it("actual main route refuses a query alias before creating private auth owner", async () => {
  vi.stubGlobal("location", { origin: "https://mcp.mastermind-x.com", pathname: `/os/research/evidence/${id}`, search: "?token=ignored", hash: "" });
  await import("../main");
  expect(mocks.render.mock.calls[0][0].props.children.props.itemId).toBeNull();
  expect(mocks.createWebAuth).not.toHaveBeenCalled(); expect(mocks.compose).not.toHaveBeenCalled();
});
