// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import { IDBFactory } from "fake-indexeddb";
import currentSupplier from "../fixtures/project-plan-proposal-source-issued-4fa354.json";
import { decodeDirectNativeResult } from "../direct-native-result";
import fixture from "../fixtures/project-journey-source-issued-388205.json";
import {
  ProjectPlanProposalWorkflow,
  type ProjectPlanProposalWorkflowProps,
} from "./ProjectPlanProposalWorkflow";
import { decodePlanProposalOriginal } from "./project-plan-proposal";
import { decodeProjectPlan } from "./project-plan";
import { createIndexedDbPendingPointerStore } from "../orchestration/indexeddb-pending-pointer-store";
import type { MissionHost } from "../host";
afterEach(cleanup);
const original = decodePlanProposalOriginal(
  (fixture.samples[12].request as { arguments: unknown }).arguments,
);
/** Finite consumer unit only: the context callback is an explicit inert test
 * owner, not the missing genuine prepublication context acceptance operand. */
function harness() {
  let generation = 1,
    current = true;
  const read = vi.fn(async () =>
    decodeProjectPlan(fixture.samples[16].response, {
      work_ref: original.work_ref,
    }),
  );
  const source = {
    prepareSourceOperation: vi.fn(),
    submitSourceOperation: vi.fn(),
    readSourceOperation: vi.fn(async () => fixture.samples[17].response),
    reconcileSourceOperation: vi.fn(async () => fixture.samples[15].response),
    advanceSourceOperation: vi.fn(),
  };
  const context = vi.fn(async () => ({
    schema: "mastermind.workspace_source_operation_context.v1",
    selection: {
      action: "publish_project_plan_proposal",
      work_ref: original.work_ref,
    },
    owner_context: { principal_scope: fixture.identities.workspace_scope },
    can_inspect: true,
  }));
  const store = createIndexedDbPendingPointerStore(new IDBFactory());
  const host = {
    commandBinding: { store },
    auth: {
      getState: () => ({ status: "signed_in", acquisition: true }),
      subscribe: () => () => {},
    },
    invalidationGeneration: () => generation,
    sourceOperations: source,
    readSourceOperationContext: context,
    readProjectPlan: read,
  } as unknown as MissionHost;
  const props: ProjectPlanProposalWorkflowProps = {
    host,
    store,
    workRef: original.work_ref,
    planningOperationKey: original.operation_key,
    result: null,
    consumed: false,
    hasDeclaration: false,
    executiveOwner: () => ({
      principalScope: fixture.identities.executive_context.principal_scope,
      generation: "1",
    }),
    isCurrent: () => current,
    original,
    currentOriginal: () => original,
    onOriginalChange: vi.fn(),
  };
  return {
    props,
    read,
    source,
    context,
    withdraw: () => {
      current = false;
    },
    bump: () => {
      generation++;
    },
  };
}
describe("S24 retained original independent consumer routes", () => {
  it("reopens original publication/current Compare while old S19 result is unavailable; no preparation/submit/consume", async () => {
    const h = harness();
    h.props.executiveOwner = () => null; // Workspace observation is independent of Executive preparation.
    render(<ProjectPlanProposalWorkflow {...h.props} />);
    expect(
      (
        screen.getByRole("button", {
          name: "Restore original proposal preview",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    fireEvent.click(
      screen.getByRole("button", { name: "Check original proposal" }),
    );
    await screen.findByText(
      "Proposal published. Compare it with the current plan; adoption is a separate step.",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "View current Plan and Compare" }),
    );
    await waitFor(() => expect(h.read).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByRole("region", { name: "Project plan" }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Back to proposal" }));
    expect(screen.queryByRole("region", { name: "Project plan" })).toBeNull();
    expect(h.source.readSourceOperation).toHaveBeenCalledTimes(1);
    expect(h.source.submitSourceOperation).not.toHaveBeenCalled();
    expect(h.props.onOriginalChange).not.toHaveBeenCalled();
  });
  it("no-render owner withdrawal refuses original read and Plan acquisition", async () => {
    const h = harness();
    render(<ProjectPlanProposalWorkflow {...h.props} />);
    h.withdraw();
    fireEvent.click(
      screen.getByRole("button", { name: "Check original proposal" }),
    );
    await screen.findByRole("status");
    fireEvent.click(
      screen.getByRole("button", { name: "View current Plan and Compare" }),
    );
    expect(h.context).not.toHaveBeenCalled();
    expect(h.read).not.toHaveBeenCalled();
    expect(h.source.readSourceOperation).not.toHaveBeenCalled();
  });
  it("drops a late original receipt after actual host generation changes", async () => {
    const h = harness();
    h.source.readSourceOperation.mockImplementation(async () => {
      h.bump();
      return fixture.samples[17].response;
    });
    render(<ProjectPlanProposalWorkflow {...h.props} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Check original proposal" }),
    );
    await waitFor(() =>
      expect(h.source.readSourceOperation).toHaveBeenCalledTimes(1),
    );
    expect(
      screen.queryByText(
        "Proposal published. Compare it with the current plan; adoption is a separate step.",
      ),
    ).toBeNull();
    expect(h.source.submitSourceOperation).not.toHaveBeenCalled();
  });
});

it("actual later canonical source cannot silently rebase an original preparation", async () => {
  const h = harness();
  const original = decodePlanProposalOriginal(
    (currentSupplier.samples[14].request as { arguments: unknown }).arguments,
  );
  const selection = original.proposal_request.selection;
  const result = decodeDirectNativeResult(
    (currentSupplier.samples[12].response as { data: unknown }).data,
    selection,
  );
  const planning = { request: vi.fn() };
  h.props = {
    ...h.props,
    host: { ...h.props.host!, projectPlanning: planning },
    workRef: original.work_ref,
    planningOperationKey: original.operation_key,
    original,
    currentOriginal: () => original,
    result,
    consumed: true,
    hasDeclaration: true,
  };
  h.read.mockResolvedValue(
    decodeProjectPlan(currentSupplier.samples[18].response, {
      work_ref: original.work_ref,
    }),
  );
  render(<ProjectPlanProposalWorkflow {...h.props} />);
  fireEvent.click(
    screen.getByRole("button", { name: "Restore original proposal preview" }),
  );
  await screen.findByRole("status");
  expect(planning.request).not.toHaveBeenCalled();
  expect(h.props.onOriginalChange).not.toHaveBeenCalled();
  expect(h.source.submitSourceOperation).not.toHaveBeenCalled();
});
