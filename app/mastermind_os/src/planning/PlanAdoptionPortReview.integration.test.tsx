// @vitest-environment jsdom
// Actual prepare decoder/port/controller/widget; only external transport and
// atomic pending-pointer storage are inert. No API/grant/live publication proof.
import { afterEach, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import fixture from "../fixtures/project-plan-v2-owner.json";
import { planAdoptionRequestFromRead } from "./plan-adoption-from-read";
import { canonicalJson, sha256Hex } from "../orchestration/operation-key";
import {
  OperationController,
  type OperationPointer,
  type PendingPointerStore,
} from "../orchestration/operation-controller";
import {
  createPlanAdoptionPort,
  preparePlanAdoption,
  type PlanAdoptionTransport,
} from "./plan-adoption-port";
import { PlanAdoptionReview } from "./PlanAdoptionReview";
import { planAdoptionPreparedReview } from "./PlanAdoptionPreparedSummary";

afterEach(cleanup);
const read = fixture.cases.available_pending,
  selection = { work_ref: "WS:PLAN-TEST" };
const request = planAdoptionRequestFromRead(
    read,
    selection,
    "PLAN-PROPOSAL",
    "mmos-project-adopt-" + "1".repeat(40),
  ),
  scope = "1".repeat(64),
  fp = "2".repeat(64);
function env() {
  let pending: OperationPointer | null = null;
  const store: PendingPointerStore = {
    read: () => pending,
    reserve: (_scope, p) => {
      if (pending) return { reserved: false as const, pointer: pending };
      pending = p;
      return { reserved: true as const };
    },
    clearIfEqual: (_scope, p) => {
      if (canonicalJson(p) !== canonicalJson(pending)) return false;
      pending = null;
      return true;
    },
  };
  const owner = {
    context: () => ({ principalScope: scope, generation: "auth-epoch-1" }),
    canAdopt: () => true,
    canInspect: () => true,
  };
  const transport: PlanAdoptionTransport = {
    prepareSourceOperation: vi.fn(async () => ({
      schema: "mastermind.workspace_source_operation_preview.v1",
      selection: {
        action: "ADOPT_PLAN",
        request_id: request.request_id,
        work_ref: request.work_ref,
      },
      owner_context: { principal_scope: scope },
      request_sha256: sha256Hex(canonicalJson(request)),
      recipe_fingerprint_sha256: fp,
      preview_witness: {
        original_input: {
          schema: "mastermind.terminal_original_input_reference.v1",
          input_ref: "terminal-input:" + "3".repeat(64),
          artifact_sha256: "4".repeat(64),
          payload_sha256: "5".repeat(64),
        },
        recipe_fingerprint_sha256: fp,
      },
      preview: {
        schema: "mastermind.project_plan_adoption_preview.v1",
        work_ref: request.work_ref,
        expected_commit: request.expected_commit,
        expected_adoption: request.expected_adoption,
        candidate_sha256: request.candidate_sha256,
        changed_frontmatter_fields: ["objective"],
        record_body_changed: true,
      },
    })),
    submitSourceOperation: vi.fn(async () => ({
      schema: "mastermind.workspace_source_operation_status.v1",
      selection: {
        action: "ADOPT_PLAN",
        request_id: request.request_id,
        work_ref: request.work_ref,
      },
      owner_context: { principal_scope: scope },
      disposition: "unknown",
      reason: "IN_PROGRESS",
      request_sha256: sha256Hex(canonicalJson(request)),
      recipe_fingerprint_sha256: fp,
      phase: "CANDIDATE",
      receipt: {
        kind: "PHASE_ATTEMPTED",
        event_id: 2,
        recorded_at_ms: 200,
        receipt_sha256: "6".repeat(64),
        sources: [],
        proposal: null,
      },
      advance: null,
    })),
    readSourceOperation: vi.fn(async () => ({
      schema: "mastermind.workspace_source_operation_status.v1",
      selection: {
        action: "ADOPT_PLAN",
        request_id: request.request_id,
        work_ref: request.work_ref,
      },
      owner_context: { principal_scope: scope },
      disposition: "unknown",
      reason: "ORIGINAL_OPERATION_NOT_OBSERVED",
      request_sha256: null,
      recipe_fingerprint_sha256: null,
      phase: null,
      receipt: null,
      advance: null,
    })),
  };
  return { owner, transport, store, pending: () => pending, seed:(pointer:OperationPointer)=>{pending=pointer;} };
}
it("restores through GET only and reconciles only the existing explicit Check gesture",async()=>{
  const e=env();e.seed({kind:'project_adopt',targetKey:request.work_ref,operationKey:request.request_id});
  const reconcile=vi.fn(async()=>await vi.mocked(e.transport.readSourceOperation).mock.results[0].value);
  e.transport.reconcileSourceOperation=reconcile;
  const port=createPlanAdoptionPort({workRef:request.work_ref,transport:e.transport,owner:e.owner,prepared:()=>null,isPreparedCurrent:()=>false});
  const controller=new OperationController(port,e.store);
  render(<PlanAdoptionReview workRef={request.work_ref} recoverOnMount binding={{controller,context:e.owner.context,canAdopt:e.owner.canAdopt,canInspect:e.owner.canInspect}}/>);
  await waitFor(()=>expect(e.transport.readSourceOperation).toHaveBeenCalledTimes(1));
  await waitFor(()=>expect((screen.getByRole('button',{name:'Check original operation'}) as HTMLButtonElement).disabled).toBe(false));
  expect(reconcile).not.toHaveBeenCalled();expect(e.transport.submitSourceOperation).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Check original operation'}));
  await waitFor(()=>expect(reconcile).toHaveBeenCalledTimes(1));
  expect(e.transport.readSourceOperation).toHaveBeenCalledTimes(1);expect(e.pending()?.operationKey).toBe(request.request_id);
});
it("refuses to attach a different READ baseline to the qualified original preview", async () => {
  const e = env(),
    prepared = await preparePlanAdoption(
      {
        workRef: request.work_ref,
        request,
        transport: e.transport,
        owner: e.owner,
        isCurrent: () => true,
      },
      new AbortController().signal,
    );
  expect(() =>
    planAdoptionPreparedReview(prepared, {
      read: fixture.cases.recorded_source_only,
      selection,
      proposalId: "PLAN-PROPOSAL",
      isCurrent: () => true,
      canReadComparison: () => true,
    }),
  ).toThrow("PLAN_ADOPTION_REVIEW_UNAVAILABLE");
  expect(e.transport.submitSourceOperation).not.toHaveBeenCalled();
});
it("hides comparison bodies on READ revocation while retaining same-original status recovery", async () => {
  const e = env();
  let canRead = true;
  const prepared = await preparePlanAdoption(
    {
      workRef: request.work_ref,
      request,
      transport: e.transport,
      owner: e.owner,
      isCurrent: () => true,
    },
    new AbortController().signal,
  );
  const port = createPlanAdoptionPort({
    workRef: request.work_ref,
    transport: e.transport,
    owner: e.owner,
    prepared: () => prepared,
    isPreparedCurrent: () => canRead,
  });
  const controller = new OperationController(port, e.store);
  const slot = planAdoptionPreparedReview(prepared, {
    read,
    selection,
    proposalId: "PLAN-PROPOSAL",
    isCurrent: () => true,
    canReadComparison: () => canRead,
  });
  const ui = () => (
    <PlanAdoptionReview
      workRef={request.work_ref}
      prepared={slot}
      binding={{
        controller,
        context: e.owner.context,
        canAdopt: e.owner.canAdopt,
        canInspect: e.owner.canInspect,
      }}
    />
  );
  const view = render(ui());
  fireEvent.click(screen.getByRole("button", { name: "Review plan" }));
  const text = read.continuity.proposals.items[0].comparison.candidate_text;
  expect(
    screen.getByText(
      (_content, node) => node?.tagName === "PRE" && node.textContent === text,
    ),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Adopt this plan" }));
  await waitFor(() =>
    expect(e.pending()?.operationKey).toBe(request.request_id),
  );
  await waitFor(() =>
    expect(e.transport.submitSourceOperation).toHaveBeenCalledTimes(1),
  );
  canRead = false;
  view.rerender(ui());
  expect(
    screen.queryByText(
      (_content, node) => node?.tagName === "PRE" && node.textContent === text,
    ),
  ).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: "Check original operation" }),
  );
  await waitFor(() =>
    expect(e.transport.readSourceOperation).toHaveBeenCalledTimes(1),
  );
  expect(e.pending()?.operationKey).toBe(request.request_id);
  expect(e.transport.submitSourceOperation).toHaveBeenCalledTimes(1);
});
it.each(["en", "zh-CN"] as const)(
  "joins actual qualified prepare to Review→explicit original submit (%s)",
  async (locale) => {
    const e = env(),
      prepared = await preparePlanAdoption(
        {
          workRef: request.work_ref,
          request,
          transport: e.transport,
          owner: e.owner,
          isCurrent: () => true,
        },
        new AbortController().signal,
      );
    const port = createPlanAdoptionPort({
      workRef: request.work_ref,
      transport: e.transport,
      owner: e.owner,
      prepared: () => prepared,
      isPreparedCurrent: () => true,
    });
    const controller = new OperationController(port, e.store);
    render(
      <PlanAdoptionReview
        workRef={request.work_ref}
        locale={locale}
        prepared={planAdoptionPreparedReview(prepared, {
          read,
          selection,
          proposalId: "PLAN-PROPOSAL",
          isCurrent: () => true,
          canReadComparison: () => true,
          locale,
        })}
        binding={{
          controller,
          context: e.owner.context,
          canAdopt: e.owner.canAdopt,
          canInspect: e.owner.canInspect,
        }}
      />,
    );
    expect(e.transport.submitSourceOperation).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", {
        name: locale === "en" ? "Review plan" : "审查计划",
      }),
    );
    expect(
      screen.getByText(
        locale === "en"
          ? "This proposal changes 1 recorded field."
          : "此提案将更改 1 个记录字段。",
      ),
    ).toBeTruthy();
    expect(e.transport.submitSourceOperation).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", {
        name: locale === "en" ? "Adopt this plan" : "采纳此计划",
      }),
    );
    await waitFor(() =>
      expect(e.transport.submitSourceOperation).toHaveBeenCalledTimes(1),
    );
    expect(e.pending()?.operationKey).toBe(request.request_id);
    expect(
      vi.mocked(e.transport.submitSourceOperation).mock.calls[0][0],
    ).toEqual({
      action: "ADOPT_PLAN",
      request_id: request.request_id,
      work_ref: request.work_ref,
      preview_witness: prepared.previewWitness,
    });
    await waitFor(() =>
      expect(
        screen.getByText(
          locale === "en"
            ? "The original adoption outcome is not known yet. Use “Check original operation” before doing anything else."
            : "此采纳的结果尚不确定。请先使用“检查原始操作”。",
        ),
      ).toBeTruthy(),
    );
  },
);
