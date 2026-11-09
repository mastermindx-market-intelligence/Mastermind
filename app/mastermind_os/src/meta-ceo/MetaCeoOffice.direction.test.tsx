// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MetaCeoOffice } from "./MetaCeoOffice";
import { projectOffice, type ProjectionContext } from "./projection";
import type { ProjectPlanRead } from "../planning/project-plan";

afterEach(cleanup);
const generation = () => 1, permission = () => true;
const base: ProjectionContext = { authGeneration: 1, selection: null, sessionRef: null,
  bindingGeneration: null, revisions: { mission: null, programs: null, result: null, conversation: null } };
const empty = { mission: null, programs: null, result: null, conversation: null };
const document = (): ProjectPlanRead => ({
  schema: "mastermind.workspace_project_plan.v1", selection: { work_ref: "WS:ROOTLESS" },
  availability: "AVAILABLE", source: { repository: "mastermindx-market-intelligence/macro",
    commit: "a".repeat(40), path: "agentos/workstreams/WS-ROOTLESS.md", content_sha256: "b".repeat(64) },
  plan: { title: "Rootless authored programme", objective: "Read the actual programme record.",
    status: "active", owner: "assigned-principal", next_action: "Continue the original programme.", waves: [],
    adoption: { state: "UNAVAILABLE", reason: "NOT_DECLARED" },
    version_history: { state: "UNAVAILABLE", reason: "NOT_SUPPLIED_BY_OWNER" } }, reason_codes: [],
});

it("reads an explicitly selected canonical programme without a Runtime Mission root", async () => {
  const read = vi.fn(async () => document());
  render(<MetaCeoOffice projection={projectOffice(empty, base)} draft={{ text: "", context: base }}
    onDraftChange={() => {}} programmeDirection={{ selection: { work_ref: "WS:ROOTLESS" },
      read, sourceGeneration: generation, canRead: permission }} />);
  fireEvent.click(screen.getByRole("button", { name: "Read programme objective" }));
  expect(await screen.findByText("Read the actual programme record.")).toBeTruthy();
  expect(read).toHaveBeenCalledWith({ work_ref: "WS:ROOTLESS", signal: expect.any(AbortSignal) });
  expect(screen.getByText("Not declared")).toBeTruthy();
});

it("clears the programme acquisition when the Office authenticated identity rotates", async () => {
  const read = vi.fn(async () => document());
  const props = { selection: { work_ref: "WS:ROOTLESS" }, read,
    sourceGeneration: generation, canRead: permission };
  const view = render(<MetaCeoOffice projection={projectOffice(empty, base)} draft={{ text: "", context: base }}
    onDraftChange={() => {}} programmeDirection={props} />);
  fireEvent.click(screen.getByRole("button", { name: "Read programme objective" }));
  await screen.findByText("Read the actual programme record.");
  const next = { ...base, authGeneration: 2 };
  view.rerender(<MetaCeoOffice projection={projectOffice(empty, next)} draft={{ text: "", context: next }}
    onDraftChange={() => {}} programmeDirection={props} />);
  expect(screen.queryByText("Read the actual programme record.")).toBeNull();
  expect(read).toHaveBeenCalledTimes(1);
});
