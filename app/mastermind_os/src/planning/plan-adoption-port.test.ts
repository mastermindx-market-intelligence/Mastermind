import { describe, expect, it, vi } from "vitest";
import fixture from "../fixtures/plan-adoption-request-owner.json";
import { canonicalJson, sha256Hex } from "../orchestration/operation-key";
import {
  OperationController,
  type CommandIntent,
  type OperationPointer,
  type PendingPointerStore,
} from "../orchestration/operation-controller";
import {
  createPlanAdoptionPort,
  bindPlanAdoptionOwner,
  preparePlanAdoption,
  type PreparedPlanAdoption,
  type PlanAdoptionTransport,
} from "./plan-adoption-port";

const request = fixture.cases[0].request;
const scope = "1".repeat(64),
  fp = "2".repeat(64),
  digest = "3".repeat(64);
const pointer: OperationPointer = {
  operationKey: request.request_id,
  kind: "project_adopt",
  targetKey: request.work_ref,
};
const intent: CommandIntent = {
  kind: "project_adopt",
  targetKey: request.work_ref,
  payload: { action: "ADOPT_PLAN", request },
};
const signal = () => new AbortController().signal;
function preview() {
  return {
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
        input_ref: `terminal-input:${"4".repeat(64)}`,
        artifact_sha256: "5".repeat(64),
        payload_sha256: "6".repeat(64),
      },
      recipe_fingerprint_sha256: fp,
    },
    preview: {
      schema: "mastermind.project_plan_adoption_preview.v1",
      work_ref: request.work_ref,
      expected_commit: request.expected_commit,
      expected_adoption: request.expected_adoption,
      candidate_sha256: request.candidate_sha256,
      changed_frontmatter_fields: ["objective", "waves"],
      record_body_changed: true,
    },
  };
}
function status(kind: "none" | "ready" | "accepted" = "none") {
  return {
    schema: "mastermind.workspace_source_operation_status.v1",
    selection: {
      action: "ADOPT_PLAN",
      request_id: request.request_id,
      work_ref: request.work_ref,
    },
    owner_context: { principal_scope: scope },
    disposition: kind === "accepted" ? "accepted" : "unknown",
    reason:
      kind === "none"
        ? "ORIGINAL_OPERATION_NOT_OBSERVED"
        : kind === "ready"
          ? "READY_FOR_ADVANCE"
          : null,
    request_sha256: kind === "none" ? null : sha256Hex(canonicalJson(request)),
    recipe_fingerprint_sha256: kind === "none" ? null : fp,
    phase: kind === "none" ? null : kind === "ready" ? "CANDIDATE" : "ADOPTION",
    receipt:
      kind === "none"
        ? null
        : {
            kind: "SOURCE_OBSERVED",
            event_id: 1,
            recorded_at_ms: 100,
            receipt_sha256: digest,
            sources: [
              {
                repository: "macro",
                commit: "a".repeat(40),
                path: "agentos/decisions/DEC-PLAN-NEXT.md",
                content_sha256: "b".repeat(64),
              },
            ],
            proposal: null,
          },
    advance: kind === "ready" ? { phase_receipt_digest: digest } : null,
  };
}
function harness() {
  let epoch = "one",
    adopt = true,
    inspect = true,
    current = true,
    prepared: PreparedPlanAdoption | null = null;
  const transport: PlanAdoptionTransport = {
    prepareSourceOperation: vi.fn(async () => preview()),
    readSourceOperation: vi.fn(async () => status()),
    submitSourceOperation: vi.fn(async () => status()),
    reconcileSourceOperation: vi.fn(async () => status("ready")),
    advanceSourceOperation: vi.fn(async () => status("accepted")),
  };
  const owner = {
    context: () => ({ principalScope: scope, generation: epoch }),
    canAdopt: () => adopt,
    canInspect: () => inspect,
  };
  const port = createPlanAdoptionPort({
    workRef: request.work_ref,
    transport,
    owner,
    prepared: () => prepared,
    isPreparedCurrent: () => current,
  });
  return {
    transport,
    owner,
    port,
    setEpoch: (value: string) => {
      epoch = value;
    },
    setAdopt: (value: boolean) => {
      adopt = value;
    },
    setInspect: (value: boolean) => {
      inspect = value;
    },
    setCurrent: (value: boolean) => {
      current = value;
    },
    dropPrepared: () => {
      prepared = null;
    },
    prepare: async () => {
      prepared = await preparePlanAdoption(
        {
          workRef: request.work_ref,
          request,
          transport,
          owner,
          isCurrent: () => current,
        },
        signal(),
      );
      return prepared;
    },
  };
}
class Store implements PendingPointerStore {
  value: OperationPointer | null = null;
  clears = 0;
  read() {
    return this.value;
  }
  reserve(
    _scope: string,
    p: OperationPointer,
  ): { reserved: true } | { reserved: false; pointer: OperationPointer } {
    if (this.value) return { reserved: false, pointer: this.value };
    this.value = { ...p };
    return { reserved: true };
  }
  clearIfEqual(_scope: string, p: OperationPointer) {
    this.clears++;
    if (!this.value || canonicalJson(p) !== canonicalJson(this.value))
      return false;
    this.value = null;
    return true;
  }
}

describe("fixed owner-backed plan adoption port (inert transport, actual controller)", () => {
  it("binds actual fec4 context to host epoch while keeping preview and source-write readiness distinct", async () => {
    const h = harness();
    let current = true,
      ready = false;
    const raw = {
      schema: "mastermind.workspace_source_operation_context.v1",
      selection: { action: "ADOPT_PLAN", work_ref: request.work_ref },
      owner_context: { principal_scope: scope },
      can_inspect: true,
    };
    const owner = bindPlanAdoptionOwner({
      raw,
      workRef: request.work_ref,
      generation: "epoch1",
      isCurrent: () => current,
      sourceReady: () => ready,
    });
    raw.owner_context.principal_scope = "9".repeat(64);
    expect(owner.context()).toEqual({
      principalScope: scope,
      generation: "epoch1",
    });
    expect(owner.canInspect()).toBe(true);
    expect(owner.canAdopt()).toBe(false);
    const prepared = await preparePlanAdoption(
      {
        workRef: request.work_ref,
        request,
        transport: h.transport,
        owner,
        isCurrent: () => true,
      },
      signal(),
    );
    const port = createPlanAdoptionPort({
      workRef: request.work_ref,
      transport: h.transport,
      owner,
      prepared: () => prepared,
      isPreparedCurrent: () => true,
    });
    expect(() => port.prepare(intent)).toThrow();
    expect(h.transport.submitSourceOperation).not.toHaveBeenCalled();
    ready = true;
    expect(port.prepare(intent)).toEqual(pointer);
    current = false;
    expect(owner.context()).toBeNull();
    expect(owner.canInspect()).toBe(false);
    expect(owner.canAdopt()).toBe(false);
  });
  it.each(["work", "action", "scope", "extra"])(
    "rejects unqualified owner context %s without transport",
    (field) => {
      const raw: Record<string, unknown> = {
        schema: "mastermind.workspace_source_operation_context.v1",
        selection: { action: "ADOPT_PLAN", work_ref: request.work_ref },
        owner_context: { principal_scope: scope },
        can_inspect: true,
      };
      if (field === "work")
        raw.selection = { action: "ADOPT_PLAN", work_ref: "WS:OTHER" };
      if (field === "action")
        raw.selection = {
          action: "ACCEPT_DIRECTION",
          work_ref: request.work_ref,
        };
      if (field === "scope")
        raw.owner_context = { principal_scope: "unqualified-label" };
      if (field === "extra") raw.can_adopt = true;
      expect(() =>
        bindPlanAdoptionOwner({
          raw,
          workRef: request.work_ref,
          generation: "epoch1",
          isCurrent: () => true,
          sourceReady: () => true,
        }),
      ).toThrow("PLAN_ADOPTION_PORT_UNAVAILABLE");
    },
  );
  it("qualifies an exact real-schema preview and submits only the original private-input witness", async () => {
    const h = harness(),
      p = await h.prepare();
    expect(p.requestSha256).toBe(sha256Hex(canonicalJson(request)));
    // Independently computed Python json.dumps canonical INNER request, no LF.
    expect(p.requestSha256).toBe(
      "b1976b590175d0b4ea20599b6a87315c6919a02585768388f3b3f92478929926",
    );
    expect(p.preview.changed_frontmatter_fields).toEqual([
      "objective",
      "waves",
    ]);
    expect(Object.isFrozen(p.request.proposal_source)).toBe(true);
    expect(h.port.prepare(intent)).toEqual(pointer);
    await h.port.submit(pointer, intent, signal());
    expect(h.transport.submitSourceOperation).toHaveBeenCalledWith(
      {
        action: "ADOPT_PLAN",
        request_id: request.request_id,
        work_ref: request.work_ref,
        preview_witness: p.previewWitness,
      },
      expect.any(AbortSignal),
    );
    const submitted = vi.mocked(h.transport.submitSourceOperation).mock
      .calls[0][0];
    expect(Object.keys(submitted).sort()).toEqual([
      "action",
      "preview_witness",
      "request_id",
      "work_ref",
    ]);
  });
  it.each([
    "request_sha256",
    "recipe_fingerprint_sha256",
    "owner_context",
    "selection",
    "preview_witness",
  ])("rejects mismatched preview %s without submission", async (field) => {
    const h = harness();
    vi.mocked(h.transport.prepareSourceOperation).mockResolvedValue({
      ...preview(),
      [field]: null,
    });
    await expect(h.prepare()).rejects.toThrow("PLAN_ADOPTION_PORT_UNAVAILABLE");
    expect(h.transport.submitSourceOperation).not.toHaveBeenCalled();
  });
  it("rejects unknown public changed-field names, never treating arbitrary producer text as safe summary", async () => {
    const h = harness(),
      p = preview();
    p.preview.changed_frontmatter_fields = ["secret_payload"];
    vi.mocked(h.transport.prepareSourceOperation).mockResolvedValue(p);
    await expect(h.prepare()).rejects.toThrow("PLAN_ADOPTION_PORT_UNAVAILABLE");
  });
  it("does not invoke getters or forward a thrown private error", async () => {
    const h = harness(),
      getter = vi.fn(() => {
        throw Error("PRIVATE");
      }),
      p = preview();
    Object.defineProperty(p, "preview_witness", {
      enumerable: true,
      get: getter,
    });
    vi.mocked(h.transport.prepareSourceOperation).mockResolvedValue(p);
    await expect(h.prepare()).rejects.toThrow(
      /^PLAN_ADOPTION_PORT_UNAVAILABLE$/,
    );
    expect(getter).not.toHaveBeenCalled();
  });
  it("fences authentication ABA while prepare is awaiting the owner", async () => {
    const h = harness();
    vi.mocked(h.transport.prepareSourceOperation).mockImplementation(
      async () => {
        h.setEpoch("three");
        return preview();
      },
    );
    await expect(h.prepare()).rejects.toThrow("PLAN_ADOPTION_PORT_UNAVAILABLE");
  });
  it("refuses stale selected source before initial submit", async () => {
    const h = harness();
    await h.prepare();
    h.setCurrent(false);
    await expect(h.port.submit(pointer, intent, signal())).rejects.toThrow();
    expect(h.transport.submitSourceOperation).not.toHaveBeenCalled();
  });
  it("rejects same-ID replacement request fields before dispatch", async () => {
    const h = harness();
    await h.prepare();
    await expect(
      h.port.submit(
        pointer,
        {
          ...intent,
          payload: {
            action: "ADOPT_PLAN",
            request: { ...request, candidate_sha256: "8".repeat(64) },
          },
        },
        signal(),
      ),
    ).rejects.toThrow();
    expect(h.transport.submitSourceOperation).not.toHaveBeenCalled();
  });
  it.each(["foreign-kind", "foreign-work", "foreign-id"])(
    "rejects %s before any status transport",
    async (variant) => {
      const h = harness(),
        p = {
          ...pointer,
          ...(variant === "foreign-kind"
            ? { kind: "project_create" as const }
            : variant === "foreign-work"
              ? { targetKey: "WS:OTHER" }
              : { operationKey: "mmos-project-create-" + "1".repeat(40) }),
        };
      await expect(h.port.readOperation(p, signal())).rejects.toThrow();
      expect(h.transport.readSourceOperation).not.toHaveBeenCalled();
    },
  );
  it("keeps recovery independent of missing prepared data or refreshed/unavailable Macro source", async () => {
    const h = harness();
    h.setCurrent(false);
    h.setAdopt(false); // Source-write readiness absent; original status grant held.
    h.dropPrepared();
    const read = await h.port.readOperation(pointer, signal());
    expect(read.disposition).toBe("unknown");
    const reconciled = await h.port.reconcileOperation!(pointer, signal());
    expect(reconciled.advance?.phase_receipt_digest).toBe(digest);
    expect(h.transport.submitSourceOperation).not.toHaveBeenCalled();
    expect(h.transport.advanceSourceOperation).not.toHaveBeenCalled();
  });
  it("denies status and reconciliation when the distinct original-operation grant is revoked", async () => {
    const h = harness();
    h.setInspect(false);
    await expect(h.prepare()).rejects.toThrow();
    await expect(h.port.readOperation(pointer, signal())).rejects.toThrow();
    await expect(
      h.port.reconcileOperation!(pointer, signal()),
    ).rejects.toThrow();
    expect(h.transport.readSourceOperation).not.toHaveBeenCalled();
    expect(h.transport.reconcileSourceOperation).not.toHaveBeenCalled();
    expect(h.transport.prepareSourceOperation).not.toHaveBeenCalled();
  });
  it("automatic status reads remain GET-only; explicit observational recovery uses a separate transport", async () => {
    const h = harness();
    await h.port.readOperation(pointer, signal());
    expect(h.transport.reconcileSourceOperation).not.toHaveBeenCalled();
    await h.port.reconcileOperation!(pointer, signal());
    expect(h.transport.reconcileSourceOperation).toHaveBeenCalledTimes(1);
  });
  it("advances only the same original ID and digest, without replacement request or preview payload", async () => {
    const h = harness();
    h.setCurrent(false);
    await h.port.advanceOperation!(pointer, digest, signal());
    expect(h.transport.advanceSourceOperation).toHaveBeenCalledWith(
      {
        schema: "mastermind.workspace_source_operation_advance.v1",
        action: "ADOPT_PLAN",
        request_id: request.request_id,
        work_ref: request.work_ref,
        phase_receipt_digest: digest,
      },
      expect.any(AbortSignal),
    );
  });
  it("retains the controller's partial hint when authorization disappears between status and advance", async () => {
    const h = harness(),
      store = new Store();
    store.value = pointer;
    vi.mocked(h.transport.readSourceOperation).mockResolvedValue(
      status("ready"),
    );
    const controller = new OperationController(h.port, store);
    await controller.recover();
    h.setAdopt(false);
    await controller.advance();
    expect(store.value).toEqual(pointer);
    expect(store.clears).toBe(0);
    expect(h.transport.advanceSourceOperation).not.toHaveBeenCalled();
  });
  it("retains a submitted unknown operation across auth loss and never reports no dispatch", async () => {
    const h = harness(),
      store = new Store();
    await h.prepare();
    vi.mocked(h.transport.submitSourceOperation).mockImplementation(
      async () => {
        h.setEpoch("new");
        return status("accepted");
      },
    );
    const controller = new OperationController(h.port, store);
    await controller.begin(intent);
    expect(store.value).toEqual(pointer);
    expect(store.clears).toBe(0);
  });
  it("does not invalidate an authentic submitted result merely because publication refreshed the source", async () => {
    const h = harness();
    await h.prepare();
    vi.mocked(h.transport.submitSourceOperation).mockImplementation(
      async () => {
        h.setCurrent(false);
        return status("accepted");
      },
    );
    expect((await h.port.submit(pointer, intent, signal())).disposition).toBe(
      "accepted",
    );
  });
  it("rejects another principal's final receipt without clearing the retained original hint", async () => {
    const h = harness(),
      store = new Store();
    store.value = pointer;
    const foreign = status("accepted");
    foreign.owner_context.principal_scope = "9".repeat(64);
    vi.mocked(h.transport.readSourceOperation).mockResolvedValue(foreign);
    const controller = new OperationController(h.port, store);
    await controller.recover();
    expect(store.value).toEqual(pointer);
    expect(store.clears).toBe(0);
  });
  it("rejects partial publication mislabeled refused instead of erasing original custody", async () => {
    const h = harness(),
      store = new Store();
    store.value = pointer;
    vi.mocked(h.transport.readSourceOperation).mockResolvedValue({
      ...status("ready"),
      disposition: "refused",
      reason: "REFUSED",
    });
    const controller = new OperationController(h.port, store);
    await controller.recover();
    expect(store.value).toEqual(pointer);
    expect(store.clears).toBe(0);
  });
});
