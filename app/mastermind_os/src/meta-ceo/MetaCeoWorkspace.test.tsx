// @vitest-environment jsdom
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { projectOffice, type ProjectionContext } from "./projection";
import { MetaCeoWorkspace } from "./MetaCeoWorkspace";

vi.mock("../hermes-native/native-port", () => ({ nativeHermesPort: { available: () => true } }));
vi.mock("../hermes-native/HermesNativePanel", () => ({ HermesNativePanel: () => {
  const [draft, setDraft] = useState("");
  return <input aria-label="Native draft" value={draft} onChange={e => setDraft(e.target.value)} />;
} }));
vi.mock("./MetaCeoOffice", () => ({ MetaCeoOffice: () => {
  const [draft, setDraft] = useState("");
  return <input aria-label="Company draft" value={draft} onChange={e => setDraft(e.target.value)} />;
} }));
vi.mock("../conversations/DeepSeekNativeEntry", () => ({ DeepSeekNativeEntry: () => null }));
afterEach(cleanup);

it("retains drafts across tab/source refresh, resets company context, and clears native state on auth change", () => {
  const context: ProjectionContext = { authGeneration: 1, selection: { workRef: "WS:ONE", rootJobId: "JOB-1" },
    sessionRef: "original", bindingGeneration: 1, revisions: { mission: "one", programs: null, result: null, conversation: null } };
  const show = (ctx: ProjectionContext) => <MetaCeoWorkspace locale="en"
    projection={projectOffice({ mission: null, programs: null, result: null, conversation: null }, ctx)} />;
  const page = render(show(context));
  fireEvent.change(screen.getByLabelText("Native draft"), { target: { value: "Next native thought" } });
  fireEvent.click(screen.getByRole("tab", { name: "Company workspace" }));
  fireEvent.change(screen.getByLabelText("Company draft"), { target: { value: "Company direction" } });
  page.rerender(show({ ...context, revisions: { ...context.revisions, mission: "two" } }));
  expect((screen.getByLabelText("Company draft") as HTMLInputElement).value).toBe("Company direction");
  fireEvent.click(screen.getByRole("tab", { name: "Hermes" }));
  expect((screen.getByLabelText("Native draft") as HTMLInputElement).value).toBe("Next native thought");
  page.rerender(show({ ...context, selection: { workRef: "WS:TWO", rootJobId: "JOB-2" } }));
  expect((screen.getByLabelText("Company draft") as HTMLInputElement).value).toBe("");
  expect((screen.getByLabelText("Native draft") as HTMLInputElement).value).toBe("Next native thought");
  page.rerender(show({ ...context, authGeneration: 2 }));
  expect((screen.getByLabelText("Native draft") as HTMLInputElement).value).toBe("");
});
