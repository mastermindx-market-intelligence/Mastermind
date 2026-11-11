import { describe, expect, it } from "vitest";

import {
  ORIGINAL_OPERATION_ID_PREFIXES,
  SOURCE_OPERATION_STATUS_INVALID,
  SOURCE_OPERATION_STATUS_SCHEMA,
  canonicalSourceOperationStatusJson,
  decodeSourceOperationStatus,
  unavailableSourceOperationStatus,
  type SourceOperationStatus,
} from "./plan-adoption-status";

describe("parent integration boundary against actual1e57 producer", () => {
  it("preserves owner UNKNOWN when a later phase conflicts or is not dispatched", () => {
    for (const reason of ["CONFLICT", "NOT_DISPATCHED"]) {
      const out = decode(candidateAdoptStatus({ reason }));
      expect(out.disposition).toBe("unknown");
      expect(out.receipt?.kind).toBe("SOURCE_OBSERVED");
    }
  });
  it("rejects C1 control characters in captured source paths", () => {
    for (const character of ["\u0080", "\u0085", "\u009f"])
      expectInvalid(
        acceptedAdoptStatus({
          receipt: receipt({
            sources: [sourceRef({ path: "docs/" + character + ".md" })],
          }),
        }),
      );
  });
  it("rejects a SOURCE_OBSERVED receipt mixed with PR-only evidence", () => {
    expectInvalid(
      acceptedAdoptStatus({ receipt: receipt({ proposal: pullRequest() }) }),
    );
  });
  it("rejects substituting the public request hash for the trusted fingerprint", () => {
    expectInvalid(
      acceptedAdoptStatus({ recipe_fingerprint_sha256: REQUEST_SHA }),
    );
  });
  it("rejects indexed source accessors without invoking them", () => {
    let calls = 0;
    const sources = [sourceRef()];
    Object.defineProperty(sources, "0", {
      get() {
        calls++;
        return sourceRef();
      },
      enumerable: true,
    });
    let error: unknown;
    try {
      decode(acceptedAdoptStatus({ receipt: receipt({ sources }) }));
    } catch (caught) {
      error = caught;
    }
    expect(calls).toBe(0);
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe(SOURCE_OPERATION_STATUS_INVALID);
  });
  it("does not leak a reflective exception from a hostile proxy", () => {
    const secret = Error("PRIVATE_REFLECTION_CANARY");
    const value = new Proxy(acceptedAdoptStatus(), {
      getPrototypeOf() {
        throw secret;
      },
    });
    let error: unknown;
    try {
      decode(value);
    } catch (caught) {
      error = caught;
    }
    expect(error).not.toBe(secret);
    expect((error as Error).message).toBe(SOURCE_OPERATION_STATUS_INVALID);
  });
});

/* ------------------------------------------------------------------ *
 * fixture material
 * ------------------------------------------------------------------ */

const COMMIT = "a1".repeat(20); // 40 lower hex
const CONTENT = "b2".repeat(32); // 64 lower hex
const RECEIPT_SHA = "c3".repeat(32); // 64 lower hex
const REQUEST_SHA = "d4".repeat(32); // 64 lower hex
const FINGERPRINT = "e5".repeat(32); // 64 lower hex
const SCOPE = "f0".repeat(32); // 64 lower hex
const FOREIGN_SCOPE = "0a".repeat(32); // 64 lower hex, another principal
const ADOPT_TAIL = "ab".repeat(20); // 40 lower hex

const ADOPT_ID = ORIGINAL_OPERATION_ID_PREFIXES.ADOPT_PLAN + ADOPT_TAIL;
const CREATE_ID =
  ORIGINAL_OPERATION_ID_PREFIXES.publish_project_proposal + "cd".repeat(20);
const DIRECTION_ID =
  ORIGINAL_OPERATION_ID_PREFIXES.ACCEPT_DIRECTION + "ef".repeat(20);
const FILE_ID =
  ORIGINAL_OPERATION_ID_PREFIXES.add_project_file + "12".repeat(20);
const PREFERENCE_ID =
  ORIGINAL_OPERATION_ID_PREFIXES.set_project_communication_preference +
  "34".repeat(20);

const WORK_REF = "WS:PLAN-ADOPT-ROOT";

type Obj = Record<string, unknown>;

function sourceRef(overrides: Obj = {}): Obj {
  return {
    repository: "macro",
    commit: COMMIT,
    path: "docs/plan/adoption.md",
    content_sha256: CONTENT,
    ...overrides,
  };
}

function pullRequest(overrides: Obj = {}): Obj {
  return {
    number: 417,
    url: "https://github.com/mastermindx-market-intelligence/macro/pull/417",
    head_commit: COMMIT,
    head_branch: "feature/plan-adopt",
    ...overrides,
  };
}

function receipt(overrides: Obj = {}): Obj {
  return {
    kind: "SOURCE_OBSERVED",
    event_id: 7,
    recorded_at_ms: 1712345678901,
    receipt_sha256: RECEIPT_SHA,
    sources: [sourceRef()],
    proposal: null,
    ...overrides,
  };
}

function selection(overrides: Obj = {}): Obj {
  return {
    action: "ADOPT_PLAN",
    request_id: ADOPT_ID,
    work_ref: WORK_REF,
    ...overrides,
  };
}

function status(
  parts: {
    selection?: unknown;
    principal_scope?: unknown;
    disposition?: unknown;
    reason?: unknown;
    request_sha256?: unknown;
    recipe_fingerprint_sha256?: unknown;
    phase?: unknown;
    receipt?: unknown;
    advance?: unknown;
    schema?: unknown;
    extra?: Obj;
  } = {},
): Obj {
  const body: Obj = {
    schema:
      parts.schema === undefined
        ? SOURCE_OPERATION_STATUS_SCHEMA
        : parts.schema,
    selection: parts.selection === undefined ? selection() : parts.selection,
    owner_context: {
      principal_scope:
        parts.principal_scope === undefined ? SCOPE : parts.principal_scope,
    },
    disposition:
      parts.disposition === undefined ? "unknown" : parts.disposition,
    reason:
      parts.reason === undefined
        ? "ORIGINAL_OPERATION_NOT_OBSERVED"
        : parts.reason,
    request_sha256:
      parts.request_sha256 === undefined ? null : parts.request_sha256,
    recipe_fingerprint_sha256:
      parts.recipe_fingerprint_sha256 === undefined
        ? null
        : parts.recipe_fingerprint_sha256,
    phase: parts.phase === undefined ? null : parts.phase,
    receipt: parts.receipt === undefined ? null : parts.receipt,
    advance: parts.advance === undefined ? null : parts.advance,
  };
  if (parts.extra !== undefined) Object.assign(body, parts.extra);
  return body;
}

/** Accepted final ADOPT source observation: ADOPTION phase. */
function acceptedAdoptStatus(overrides: Obj = {}): Obj {
  return {
    ...status({
      disposition: "accepted",
      reason: null,
      request_sha256: REQUEST_SHA,
      recipe_fingerprint_sha256: FINGERPRINT,
      phase: "ADOPTION",
      receipt: receipt({ kind: "SOURCE_OBSERVED" }),
    }),
    ...overrides,
  };
}

/** Same evidence, still CANDIDATE: must stay unknown, never accepted. */
function candidateAdoptStatus(overrides: Obj = {}): Obj {
  return {
    ...status({
      disposition: "unknown",
      reason: "SOURCE_UNAVAILABLE",
      request_sha256: REQUEST_SHA,
      recipe_fingerprint_sha256: FINGERPRINT,
      phase: "CANDIDATE",
      receipt: receipt({ kind: "SOURCE_OBSERVED" }),
    }),
    ...overrides,
  };
}

function readyForAdvanceAdoptStatus(): Obj {
  return status({
    disposition: "unknown",
    reason: "READY_FOR_ADVANCE",
    request_sha256: REQUEST_SHA,
    recipe_fingerprint_sha256: FINGERPRINT,
    phase: "CANDIDATE",
    receipt: receipt({ kind: "SOURCE_OBSERVED", receipt_sha256: RECEIPT_SHA }),
    advance: { phase_receipt_digest: RECEIPT_SHA },
  });
}

function decode(value: unknown): SourceOperationStatus {
  return decodeSourceOperationStatus(value);
}

/** Asserts one constant rejection, with no untrusted text in the message. */
function expectInvalid(value: unknown): void {
  let thrown: unknown = undefined;
  try {
    decodeSourceOperationStatus(value);
  } catch (error) {
    thrown = error;
  }
  expect(thrown, "expected SOURCE_OPERATION_STATUS_INVALID").toBeInstanceOf(
    Error,
  );
  expect((thrown as Error).message).toBe(SOURCE_OPERATION_STATUS_INVALID);
}

function utf8Bytes(s: string): number {
  return new TextEncoder().encode(s).length;
}

/* ------------------------------------------------------------------ *
 * accepted final vs candidate
 * ------------------------------------------------------------------ */

describe("accepted final source observation versus candidate", () => {
  it("accepts a genuine-shaped final ADOPTION source observation", () => {
    const out = decode(acceptedAdoptStatus());
    expect(out.disposition).toBe("accepted");
    expect(out.reason).toBeNull();
    expect(out.phase).toBe("ADOPTION");
    expect(out.receipt?.kind).toBe("SOURCE_OBSERVED");
    expect(out.receipt?.sources).toHaveLength(1);
    expect(out.advance).toBeNull();
    expect(out.schema).toBe(SOURCE_OPERATION_STATUS_SCHEMA);
    expect(out.selection.action).toBe("ADOPT_PLAN");
  });

  it("keeps the identical evidence as CANDIDATE unknown, never accepted", () => {
    const out = decode(candidateAdoptStatus());
    expect(out.disposition).toBe("unknown");
    expect(out.phase).toBe("CANDIDATE");
    expect(out.reason).toBe("SOURCE_UNAVAILABLE");
    expect(out.receipt?.kind).toBe("SOURCE_OBSERVED");
    expect(out.advance).toBeNull();
  });

  it("rejects a candidate phase claimed as accepted", () => {
    expectInvalid(acceptedAdoptStatus({ phase: "CANDIDATE", reason: null }));
  });

  it("rejects accepted with a non-null reason", () => {
    expectInvalid(acceptedAdoptStatus({ reason: "SOURCE_UNAVAILABLE" }));
  });

  it("accepts a final non-ADOPT PUBLICATION observation", () => {
    const out = decode(
      status({
        selection: selection({
          action: "publish_project_proposal",
          request_id: CREATE_ID,
        }),
        disposition: "accepted",
        reason: null,
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "PUBLICATION",
        receipt: receipt({ kind: "SOURCE_OBSERVED" }),
      }),
    );
    expect(out.disposition).toBe("accepted");
    expect(out.selection.action).toBe("publish_project_proposal");
    expect(out.selection.request_id).toBe(CREATE_ID);
    expect(out.phase).toBe("PUBLICATION");
  });

  it("rejects a CANDIDATE phase on a non-ADOPT action", () => {
    expectInvalid(
      status({
        selection: selection({
          action: "publish_project_proposal",
          request_id: CREATE_ID,
        }),
        disposition: "unknown",
        reason: "SOURCE_UNAVAILABLE",
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "CANDIDATE",
        receipt: receipt({ kind: "SOURCE_OBSERVED" }),
      }),
    );
  });

  it("rejects an ADOPTION phase on a non-ADOPT action", () => {
    expectInvalid(
      status({
        selection: selection({
          action: "publish_project_proposal",
          request_id: CREATE_ID,
        }),
        disposition: "accepted",
        reason: null,
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "ADOPTION",
        receipt: receipt({ kind: "SOURCE_OBSERVED" }),
      }),
    );
  });

  it("rejects an accepted claim with no receipt at all", () => {
    expectInvalid(
      status({ disposition: "accepted", reason: null, phase: "ADOPTION" }),
    );
  });
});

/* ------------------------------------------------------------------ *
 * advance witness pairing
 * ------------------------------------------------------------------ */

describe("advance witness and action/key pairing", () => {
  it("accepts READY_FOR_ADVANCE only with the exact receipt digest", () => {
    const out = decode(readyForAdvanceAdoptStatus());
    expect(out.reason).toBe("READY_FOR_ADVANCE");
    expect(out.advance?.phase_receipt_digest).toBe(RECEIPT_SHA);
    expect(out.receipt?.receipt_sha256).toBe(RECEIPT_SHA);
    expect(out.phase).toBe("CANDIDATE");
    expect(out.disposition).toBe("unknown");
  });

  it("rejects an advance digest that is not the receipt digest", () => {
    expectInvalid({
      ...readyForAdvanceAdoptStatus(),
      advance: { phase_receipt_digest: FINGERPRINT },
    });
  });

  it("rejects READY_FOR_ADVANCE on a non-ADOPT action", () => {
    expectInvalid({
      ...readyForAdvanceAdoptStatus(),
      selection: selection({
        action: "publish_project_proposal",
        request_id: CREATE_ID,
      }),
    });
  });

  it("rejects READY_FOR_ADVANCE in the final ADOPTION phase", () => {
    expectInvalid({
      ...readyForAdvanceAdoptStatus(),
      phase: "ADOPTION",
    });
  });

  it("rejects READY_FOR_ADVANCE without an advance witness", () => {
    expectInvalid({ ...readyForAdvanceAdoptStatus(), advance: null });
  });

  it("rejects an advance witness attached to any other state", () => {
    expectInvalid({
      ...candidateAdoptStatus(),
      advance: { phase_receipt_digest: RECEIPT_SHA },
    });
    expectInvalid({
      ...acceptedAdoptStatus(),
      advance: { phase_receipt_digest: RECEIPT_SHA },
    });
    expectInvalid({
      ...status({ disposition: "unknown", reason: "IN_PROGRESS" }),
      advance: { phase_receipt_digest: RECEIPT_SHA },
    });
  });

  it("rejects READY_FOR_ADVANCE without a source observation", () => {
    expectInvalid({
      ...readyForAdvanceAdoptStatus(),
      receipt: receipt({ kind: "INTENT", sources: [] }),
    });
  });
});

/* ------------------------------------------------------------------ *
 * unknown with no evidence is not a no-effect claim
 * ------------------------------------------------------------------ */

describe("no-owner unknown versus no-effect", () => {
  it("accepts an unknown with null evidence and keeps it unknown", () => {
    const out = decode(
      status({ disposition: "unknown", reason: "IN_PROGRESS" }),
    );
    expect(out.disposition).toBe("unknown");
    expect(out.reason).toBe("IN_PROGRESS");
    expect(out.receipt).toBeNull();
    expect(out.request_sha256).toBeNull();
    expect(out.recipe_fingerprint_sha256).toBeNull();
    expect(out.phase).toBeNull();
    expect(out.advance).toBeNull();
  });

  it("builds the exact null-evidence unavailable body", () => {
    const out = unavailableSourceOperationStatus(
      "ADOPT_PLAN",
      ADOPT_ID,
      WORK_REF,
      SCOPE,
    );
    expect(out).toEqual({
      schema: SOURCE_OPERATION_STATUS_SCHEMA,
      selection: {
        action: "ADOPT_PLAN",
        request_id: ADOPT_ID,
        work_ref: WORK_REF,
      },
      owner_context: { principal_scope: SCOPE },
      disposition: "unknown",
      reason: "ORIGINAL_OPERATION_NOT_OBSERVED",
      request_sha256: null,
      recipe_fingerprint_sha256: null,
      phase: null,
      receipt: null,
      advance: null,
    });
    expect(out.selection).not.toBe(
      unavailableSourceOperationStatus("ADOPT_PLAN", ADOPT_ID, WORK_REF, SCOPE)
        .selection,
    );
    expect(out.owner_context.principal_scope).toBe(SCOPE);
  });

  it("validates the unavailable selection with the same grammar", () => {
    expect(() =>
      unavailableSourceOperationStatus(
        "ADOPT_PLAN",
        CREATE_ID,
        WORK_REF,
        SCOPE,
      ),
    ).toThrow(SOURCE_OPERATION_STATUS_INVALID);
    expect(() =>
      unavailableSourceOperationStatus(
        "ADOPT_PLAN",
        ADOPT_ID,
        "ws:lower",
        SCOPE,
      ),
    ).toThrow(SOURCE_OPERATION_STATUS_INVALID);
    expect(() =>
      unavailableSourceOperationStatus(
        "ADOPT_PLAN",
        ADOPT_ID,
        WORK_REF,
        "not-hex",
      ),
    ).toThrow(SOURCE_OPERATION_STATUS_INVALID);
  });

  it("rejects ORIGINAL_OPERATION_NOT_OBSERVED carrying any evidence", () => {
    expectInvalid(
      status({
        disposition: "unknown",
        reason: "ORIGINAL_OPERATION_NOT_OBSERVED",
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "CANDIDATE",
        receipt: receipt({ kind: "SOURCE_OBSERVED" }),
      }),
    );
    expectInvalid({
      ...status({
        disposition: "unknown",
        reason: "ORIGINAL_OPERATION_NOT_OBSERVED",
      }),
      advance: { phase_receipt_digest: RECEIPT_SHA },
    });
  });

  it("never lets a null receipt claim a phase or either fingerprint", () => {
    expectInvalid(
      status({
        disposition: "unknown",
        reason: "IN_PROGRESS",
        phase: "CANDIDATE",
      }),
    );
    expectInvalid(
      status({
        disposition: "unknown",
        reason: "IN_PROGRESS",
        request_sha256: REQUEST_SHA,
      }),
    );
    expectInvalid(
      status({
        disposition: "unknown",
        reason: "IN_PROGRESS",
        recipe_fingerprint_sha256: FINGERPRINT,
      }),
    );
  });

  it("never infers accepted from a null receipt", () => {
    expectInvalid(status({ disposition: "accepted", reason: null }));
    expectInvalid(
      status({ disposition: "accepted", reason: null, phase: "ADOPTION" }),
    );
  });
});

/* ------------------------------------------------------------------ *
 * refusal and partial publication
 * ------------------------------------------------------------------ */

describe("refusal and partial publication", () => {
  it("accepts each closed refusal reason with no evidence at all", () => {
    for (const reason of ["NOT_DISPATCHED", "REFUSED", "CONFLICT"] as const) {
      const out = decode(status({ disposition: "refused", reason }));
      expect(out.disposition).toBe("refused");
      expect(out.reason).toBe(reason);
      expect(out.receipt).toBeNull();
      expect(out.phase).toBeNull();
      expect(out.advance).toBeNull();
    }
  });

  it("rejects a refusal carrying a receipt or any fingerprint", () => {
    for (const reason of ["NOT_DISPATCHED", "REFUSED", "CONFLICT"] as const) {
      expectInvalid(
        status({
          disposition: "refused",
          reason,
          receipt: receipt({ kind: "INTENT", sources: [] }),
          request_sha256: REQUEST_SHA,
          recipe_fingerprint_sha256: FINGERPRINT,
          phase: "PUBLICATION",
        }),
      );
    }
  });

  it("never reports a partially published operation as refused", () => {
    expectInvalid(
      status({
        disposition: "refused",
        reason: "NOT_DISPATCHED",
        request_sha256: REQUEST_SHA,
      }),
    );
    expectInvalid(
      status({
        disposition: "refused",
        reason: "CONFLICT",
        phase: "PUBLICATION",
      }),
    );
    expectInvalid(
      status({
        disposition: "refused",
        reason: "REFUSED",
        receipt: receipt({ kind: "SOURCE_OBSERVED", sources: [sourceRef()] }),
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "CANDIDATE",
      }),
    );
  });

  it("keeps REFUSED out of unknown dispositions without suppressing partial-phase conflict", () => {
    expectInvalid(status({ disposition: "unknown", reason: "REFUSED" }));
  });

  it("keeps non-refusal reasons out of the refused disposition", () => {
    expectInvalid(status({ disposition: "refused", reason: "IN_PROGRESS" }));
    expectInvalid(
      status({ disposition: "refused", reason: "SOURCE_UNAVAILABLE" }),
    );
  });

  it("lets unknown retain an actual receipt with a closed reason", () => {
    for (const reason of [
      "IN_PROGRESS",
      "PHASE_ATTEMPT_UNRESOLVED",
      "PRECONDITION_UNAVAILABLE",
      "PRIVATE_INPUT_UNAVAILABLE",
      "SOURCE_UNAVAILABLE",
    ] as const) {
      const out = decode(candidateAdoptStatus({ reason }));
      expect(out.disposition).toBe("unknown");
      expect(out.reason).toBe(reason);
      expect(out.receipt?.kind).toBe("SOURCE_OBSERVED");
    }
  });
});

/* ------------------------------------------------------------------ *
 * receipt kind pairing
 * ------------------------------------------------------------------ */

describe("receipt kind pairing", () => {
  it("keeps INTENT evidence-only, empty sources, no proposal, unknown", () => {
    const out = decode(
      status({
        disposition: "unknown",
        reason: "IN_PROGRESS",
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "PUBLICATION",
        receipt: receipt({ kind: "INTENT", sources: [], proposal: null }),
        selection: selection({
          action: "publish_project_proposal",
          request_id: CREATE_ID,
        }),
      }),
    );
    expect(out.receipt?.kind).toBe("INTENT");
    expect(out.receipt?.sources).toEqual([]);
    expect(out.receipt?.proposal).toBeNull();
  });

  it("rejects INTENT with sources, a proposal, or a decided disposition", () => {
    expectInvalid(
      status({
        disposition: "unknown",
        reason: "IN_PROGRESS",
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "PUBLICATION",
        receipt: receipt({ kind: "INTENT", proposal: pullRequest() }),
        selection: selection({
          action: "publish_project_proposal",
          request_id: CREATE_ID,
        }),
      }),
    );
    expectInvalid(
      status({
        disposition: "unknown",
        reason: "IN_PROGRESS",
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "PUBLICATION",
        receipt: receipt({ kind: "INTENT", sources: [sourceRef()] }),
        selection: selection({
          action: "publish_project_proposal",
          request_id: CREATE_ID,
        }),
      }),
    );
    expectInvalid(
      status({
        disposition: "accepted",
        reason: null,
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "PUBLICATION",
        receipt: receipt({ kind: "INTENT", sources: [] }),
        selection: selection({
          action: "publish_project_proposal",
          request_id: CREATE_ID,
        }),
      }),
    );
    expectInvalid(
      status({
        disposition: "refused",
        reason: "REFUSED",
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "PUBLICATION",
        receipt: receipt({ kind: "PHASE_ATTEMPTED", sources: [] }),
        selection: selection({
          action: "publish_project_proposal",
          request_id: CREATE_ID,
        }),
      }),
    );
  });

  it("requires PROPOSAL_OBSERVED to carry the proposal and no sources", () => {
    const out = decode(
      status({
        disposition: "unknown",
        reason: "IN_PROGRESS",
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "PUBLICATION",
        receipt: receipt({
          kind: "PROPOSAL_OBSERVED",
          sources: [],
          proposal: pullRequest(),
        }),
        selection: selection({
          action: "publish_project_proposal",
          request_id: CREATE_ID,
        }),
      }),
    );
    expect(out.receipt?.proposal?.number).toBe(417);
  });

  it("rejects PROPOSAL_OBSERVED without a proposal or with sources", () => {
    expectInvalid(
      status({
        disposition: "unknown",
        reason: "IN_PROGRESS",
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "PUBLICATION",
        receipt: receipt({
          kind: "PROPOSAL_OBSERVED",
          sources: [],
          proposal: null,
        }),
        selection: selection({
          action: "publish_project_proposal",
          request_id: CREATE_ID,
        }),
      }),
    );
    expectInvalid(
      status({
        disposition: "unknown",
        reason: "IN_PROGRESS",
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "PUBLICATION",
        receipt: receipt({
          kind: "PROPOSAL_OBSERVED",
          sources: [sourceRef()],
          proposal: pullRequest(),
        }),
        selection: selection({
          action: "publish_project_proposal",
          request_id: CREATE_ID,
        }),
      }),
    );
  });

  it("requires SOURCE_OBSERVED to carry one to three sources", () => {
    expectInvalid(candidateAdoptStatus({ receipt: receipt({ sources: [] }) }));
    expectInvalid(
      candidateAdoptStatus({
        receipt: receipt({
          sources: [sourceRef(), sourceRef(), sourceRef(), sourceRef()],
        }),
      }),
    );
    const three = decode(
      candidateAdoptStatus({
        receipt: receipt({ sources: [sourceRef(), sourceRef(), sourceRef()] }),
      }),
    );
    expect(three.receipt?.sources).toHaveLength(3);
  });

  it("rejects a receipt without both hashes or without a phase", () => {
    const base = {
      disposition: "unknown",
      reason: "SOURCE_UNAVAILABLE",
      phase: "CANDIDATE",
      receipt: receipt({ kind: "SOURCE_OBSERVED" }),
    };
    expectInvalid(
      status({
        ...base,
        request_sha256: null,
        recipe_fingerprint_sha256: FINGERPRINT,
      }),
    );
    expectInvalid(
      status({
        ...base,
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: null,
      }),
    );
    expectInvalid(status({ ...base, phase: null }));
  });

  it("keeps the public request hash and the trusted fingerprint distinct fields", () => {
    const out = decode(acceptedAdoptStatus());
    expect(out.request_sha256).toBe(REQUEST_SHA);
    expect(out.recipe_fingerprint_sha256).toBe(FINGERPRINT);
    expect(out.request_sha256).not.toBe(out.receipt?.receipt_sha256);
  });
});

/* ------------------------------------------------------------------ *
 * action, original-id and work-ref grammar
 * ------------------------------------------------------------------ */

describe("action, original-id and work-ref grammar", () => {
  it("round-trips every action with its own strict original id", () => {
    const pairs: Array<[string, string]> = [
      ["publish_project_proposal", CREATE_ID],
      ["ADOPT_PLAN", ADOPT_ID],
      ["ACCEPT_DIRECTION", DIRECTION_ID],
      ["add_project_file", FILE_ID],
      ["set_project_communication_preference", PREFERENCE_ID],
    ];
    for (const [action, id] of pairs) {
      const out = decode(
        status({ selection: selection({ action, request_id: id }) }),
      );
      expect(out.selection.action).toBe(action);
      expect(out.selection.request_id).toBe(id);
    }
  });

  it("rejects an id bound to the wrong action", () => {
    for (const [action, id] of [
      ["ADOPT_PLAN", CREATE_ID],
      ["publish_project_proposal", ADOPT_ID],
      ["ACCEPT_DIRECTION", FILE_ID],
      ["add_project_file", DIRECTION_ID],
      ["set_project_communication_preference", ADOPT_ID],
      ["ADOPT_PLAN", DIRECTION_ID],
    ] as Array<[string, string]>) {
      expectInvalid(
        status({ selection: selection({ action, request_id: id }) }),
      );
    }
  });

  it("rejects unknown actions", () => {
    expectInvalid(status({ selection: selection({ action: "ADOPT" }) }));
    expectInvalid(status({ selection: selection({ action: "adopt_plan" }) }));
    expectInvalid(status({ selection: selection({ action: "" }) }));
    expectInvalid(status({ selection: selection({ action: "ADOPT_PLAN " }) }));
  });

  it("rejects malformed original-id grammar", () => {
    const bad = [
      "mmos-project-adopt-",
      "mmos-project-adopt-" + "AB".repeat(20),
      "mmos-project-adopt-" + "ab".repeat(19),
      "mmos-project-adopt-" + "ab".repeat(21),
      "mmos-project-adopt-" + "g0".repeat(20),
      ADOPT_ID + "ab",
      ADOPT_ID.slice(0, -1),
      "",
    ];
    for (const id of bad) {
      expectInvalid(status({ selection: selection({ request_id: id }) }));
    }
  });

  it("rejects a boolean or non-string id", () => {
    expectInvalid(status({ selection: selection({ request_id: true }) }));
    expectInvalid(status({ selection: selection({ request_id: 123 }) }));
    expectInvalid(status({ selection: selection({ request_id: null }) }));
    expectInvalid(status({ selection: selection({ action: true }) }));
  });

  it("accepts the work-ref kebab bounds and rejects injection", () => {
    expect(decode(status()).selection.work_ref).toBe(WORK_REF);
    expect(
      decode(status({ selection: selection({ work_ref: "WS:AB" }) })).selection
        .work_ref,
    ).toBe("WS:AB");
    expect(
      decode(
        status({ selection: selection({ work_ref: "WS:" + "A".repeat(64) }) }),
      ).selection.work_ref,
    ).toBe("WS:" + "A".repeat(64));
    const badRefs = [
      "WS:A",
      "WS:" + "A".repeat(65),
      "WS:lower",
      "WS:AB--CD",
      "WS:-AB",
      "WS:AB-",
      "WS:AB CD",
      "WS:",
      "WS",
      "AB-CD",
      "WS:AB_CD",
      "WS:AB/CD",
      "WS:AB\nCD",
      "WS:AB-CD-",
    ];
    for (const ref of badRefs) {
      expectInvalid(status({ selection: selection({ work_ref: ref }) }));
    }
  });

  it("accepts duplicate and foreign principal scopes at the grammar level", () => {
    const first = decode(status());
    const duplicate = decode(status());
    const foreign = decode(status({ principal_scope: FOREIGN_SCOPE }));
    expect(duplicate.owner_context.principal_scope).toBe(SCOPE);
    expect(first.owner_context.principal_scope).toBe(
      duplicate.owner_context.principal_scope,
    );
    expect(foreign.owner_context.principal_scope).toBe(FOREIGN_SCOPE);
    expect(() =>
      unavailableSourceOperationStatus(
        "ADOPT_PLAN",
        ADOPT_ID,
        WORK_REF,
        FOREIGN_SCOPE,
      ),
    ).not.toThrow();
  });

  it("rejects malformed principal scopes", () => {
    for (const scope of [
      "nothex",
      SCOPE.slice(1),
      SCOPE + "aa",
      SCOPE.toUpperCase(),
      true,
      0,
      null,
    ]) {
      expectInvalid(status({ principal_scope: scope }));
    }
  });

  it("rejects a wrong schema discriminator", () => {
    expectInvalid(
      status({ schema: "mastermind.workspace_source_operation_status.v2" }),
    );
    expectInvalid(status({ schema: null }));
    expectInvalid(status({ schema: 1 }));
  });
});

/* ------------------------------------------------------------------ *
 * scalar typing
 * ------------------------------------------------------------------ */

describe("scalar typing", () => {
  it("bounds event_id and recorded_at_ms as safe integers", () => {
    const max = 9007199254740991; // 2^53 - 1
    expect(
      decode(candidateAdoptStatus({ receipt: receipt({ event_id: max }) }))
        .receipt?.event_id,
    ).toBe(max);
    expect(
      decode(candidateAdoptStatus({ receipt: receipt({ recorded_at_ms: 0 }) }))
        .receipt?.recorded_at_ms,
    ).toBe(0);
    expect(
      decode(
        candidateAdoptStatus({ receipt: receipt({ recorded_at_ms: max }) }),
      ).receipt?.recorded_at_ms,
    ).toBe(max);
    for (const bad of [
      0,
      -1,
      1.5,
      max + 1,
      Number.NaN,
      Number.POSITIVE_INFINITY,
    ]) {
      expectInvalid(
        candidateAdoptStatus({ receipt: receipt({ event_id: bad }) }),
      );
    }
    for (const bad of [-1, 1.5, max + 1, Number.NaN]) {
      expectInvalid(
        candidateAdoptStatus({ receipt: receipt({ recorded_at_ms: bad }) }),
      );
    }
  });

  it("rejects booleans in integer positions", () => {
    expectInvalid(
      candidateAdoptStatus({ receipt: receipt({ event_id: true }) }),
    );
    expectInvalid(
      candidateAdoptStatus({ receipt: receipt({ event_id: false }) }),
    );
    expectInvalid(
      candidateAdoptStatus({ receipt: receipt({ recorded_at_ms: true }) }),
    );
    expectInvalid(pullRequestNumber(true));
  });

  it("rejects number wrappers, bigint and other exotic scalars", () => {
    // eslint-disable-next-line no-new-wrappers
    expectInvalid(
      candidateAdoptStatus({ receipt: receipt({ event_id: new Number(7) }) }),
    );
    expectInvalid(status({ principal_scope: SCOPE, reason: ["IN_PROGRESS"] }));
    expectInvalid(status({ disposition: ["unknown"] }));
    expectInvalid(status({ phase: { toString: "PUBLICATION" } }));
  });

  it("rejects malformed hash digests everywhere", () => {
    expectInvalid(
      candidateAdoptStatus({
        receipt: receipt({ receipt_sha256: RECEIPT_SHA.toUpperCase() }),
      }),
    );
    expectInvalid(
      candidateAdoptStatus({
        receipt: receipt({ receipt_sha256: RECEIPT_SHA.slice(1) }),
      }),
    );
    expectInvalid(acceptedAdoptStatus({ request_sha256: REQUEST_SHA + "zz" }));
    expectInvalid(acceptedAdoptStatus({ recipe_fingerprint_sha256: null }));
    expectInvalid(
      candidateAdoptStatus({
        receipt: receipt({
          sources: [sourceRef({ commit: COMMIT.toUpperCase() })],
        }),
      }),
    );
    expectInvalid(
      candidateAdoptStatus({
        receipt: receipt({
          sources: [sourceRef({ content_sha256: "z".repeat(64) })],
        }),
      }),
    );
    expectInvalid({
      ...readyForAdvanceAdoptStatus(),
      advance: { phase_receipt_digest: RECEIPT_SHA + " " },
    });
  });
});

/** A otherwise-valid PROPOSAL_OBSERVED status whose only varied field is the PR number. */
function pullRequestNumber(value: unknown): Obj {
  return status({
    disposition: "unknown",
    reason: "IN_PROGRESS",
    request_sha256: REQUEST_SHA,
    recipe_fingerprint_sha256: FINGERPRINT,
    phase: "PUBLICATION",
    selection: selection({
      action: "publish_project_proposal",
      request_id: CREATE_ID,
    }),
    receipt: receipt({
      kind: "PROPOSAL_OBSERVED",
      sources: [],
      proposal: pullRequest({ number: value }),
    }),
  });
}

/* ------------------------------------------------------------------ *
 * source ref and pull-request injection
 * ------------------------------------------------------------------ */

describe("source path and pull-request injection", () => {
  it("rejects path traversal, absolute paths and backslashes", () => {
    const badPaths = [
      "../etc/passwd",
      "docs/../../etc/passwd",
      "a/../../b",
      "/etc/passwd",
      "//etc/passwd",
      "docs//plan.md",
      "docs/",
      "docs/./plan.md",
      "./plan.md",
      "..",
      ".",
      "",
      "docs\\plan.md",
      "docs\u0000plan.md",
      "docs\u001fplan.md",
      "docs\u007fplan.md",
    ];
    for (const path of badPaths) {
      expectInvalid(
        candidateAdoptStatus({
          receipt: receipt({ sources: [sourceRef({ path })] }),
        }),
      );
    }
  });

  it("bounds the source path at 512 UTF-8 bytes", () => {
    const exact = "d/" + "é".repeat(255); // 1 + 1 + 510 = 512 bytes
    expect(utf8Bytes(exact)).toBe(512);
    const out = decode(
      candidateAdoptStatus({
        receipt: receipt({ sources: [sourceRef({ path: exact })] }),
      }),
    );
    expect(out.receipt?.sources[0]?.path).toBe(exact);
    expectInvalid(
      candidateAdoptStatus({
        receipt: receipt({
          sources: [sourceRef({ path: "d/" + "é".repeat(256) })],
        }),
      }),
    );
    const ascii513 = "a".repeat(513);
    expectInvalid(
      candidateAdoptStatus({
        receipt: receipt({ sources: [sourceRef({ path: ascii513 })] }),
      }),
    );
  });

  it("rejects a repository that is not exactly macro", () => {
    for (const repo of ["Macro", "other", "", "macro/", null, 1]) {
      expectInvalid(
        candidateAdoptStatus({
          receipt: receipt({ sources: [sourceRef({ repository: repo })] }),
        }),
      );
    }
  });

  it("rejects a pull-request url that does not match its number", () => {
    const base = {
      disposition: "unknown",
      reason: "IN_PROGRESS",
      request_sha256: REQUEST_SHA,
      recipe_fingerprint_sha256: FINGERPRINT,
      phase: "PUBLICATION",
      selection: selection({
        action: "publish_project_proposal",
        request_id: CREATE_ID,
      }),
    };
    expectInvalid(
      status({
        ...base,
        receipt: receipt({
          kind: "PROPOSAL_OBSERVED",
          sources: [],
          proposal: pullRequest({
            url: "https://github.com/mastermindx-market-intelligence/macro/pull/418",
          }),
        }),
      }),
    );
    expectInvalid(
      status({
        ...base,
        receipt: receipt({
          kind: "PROPOSAL_OBSERVED",
          sources: [],
          proposal: pullRequest({
            url: "https://github.com/other/macro/pull/417",
          }),
        }),
      }),
    );
    expectInvalid(
      status({
        ...base,
        receipt: receipt({
          kind: "PROPOSAL_OBSERVED",
          sources: [],
          proposal: pullRequest({
            url: "http://github.com/mastermindx-market-intelligence/macro/pull/417",
          }),
        }),
      }),
    );
    expectInvalid(
      status({
        ...base,
        receipt: receipt({
          kind: "PROPOSAL_OBSERVED",
          sources: [],
          proposal: pullRequest({
            url: "https://github.com/mastermindx-market-intelligence/macro/pull/417/",
          }),
        }),
      }),
    );
    expectInvalid(
      status({
        ...base,
        receipt: receipt({
          kind: "PROPOSAL_OBSERVED",
          sources: [],
          proposal: pullRequest({ number: 0 }),
        }),
      }),
    );
    expectInvalid(
      status({
        ...base,
        receipt: receipt({
          kind: "PROPOSAL_OBSERVED",
          sources: [],
          proposal: pullRequest({ number: -3 }),
        }),
      }),
    );
  });

  it("rejects git-ref injection in head_branch", () => {
    const proposal = (head_branch: unknown): Obj =>
      status({
        disposition: "unknown",
        reason: "IN_PROGRESS",
        request_sha256: REQUEST_SHA,
        recipe_fingerprint_sha256: FINGERPRINT,
        phase: "PUBLICATION",
        selection: selection({
          action: "publish_project_proposal",
          request_id: CREATE_ID,
        }),
        receipt: receipt({
          kind: "PROPOSAL_OBSERVED",
          sources: [],
          proposal: pullRequest({ head_branch }),
        }),
      });
    const bad = [
      "-flag",
      "--draft",
      "refs/../../other",
      "main..other",
      "a@{b",
      "main\\other",
      "main other",
      "main\nother",
      "main\tother",
      "main~",
      "main^",
      "main:other",
      "main?x",
      "main*x",
      "main[x",
      "main//other",
      "/main",
      "main/",
      "main.",
      "release.lock",
      "release/.lock",
      "",
      "a".repeat(201),
      "branche-ünïcode",
      "main\u0000",
    ];
    for (const branch of bad) {
      expectInvalid(proposal(branch));
    }
    for (const branch of [
      "main",
      "feature/plan-adopt",
      "release-2026.11",
      "Hotfix_1.2",
      "a".repeat(200),
    ]) {
      const out = decode(proposal(branch));
      expect(out.receipt?.proposal?.head_branch).toBe(branch);
    }
  });
});

/* ------------------------------------------------------------------ *
 * closed shape, private fields, exotic objects
 * ------------------------------------------------------------------ */

describe("closed shape, private fields and exotic objects", () => {
  it("rejects raw private or owner-side bodies anywhere", () => {
    const privates = [
      "actor",
      "account",
      "token",
      "rationale",
      "basis",
      "upload",
      "private_body",
    ];
    for (const key of privates) {
      expectInvalid(status({ extra: { [key]: "leak" } }));
    }
    const withPrivateReceipt = candidateAdoptStatus();
    (withPrivateReceipt.receipt as Obj).actor = "someone";
    expectInvalid(withPrivateReceipt);
    const withPrivateSource = candidateAdoptStatus();
    ((withPrivateSource.receipt as Obj).sources as Obj[])[0].account =
      "someone";
    expectInvalid(withPrivateSource);
    const withPrivateProposal = candidateAdoptStatus();
    (withPrivateProposal.receipt as Obj).proposal = {
      ...pullRequest(),
      upload: "x",
    };
    expectInvalid(withPrivateProposal);
    const withPrivateOwner = status();
    (withPrivateOwner.owner_context as Obj).basis = "why";
    expectInvalid(withPrivateOwner);
    const withPrivateAdvance = readyForAdvanceAdoptStatus();
    (withPrivateAdvance.advance as Obj).rationale = "why";
    expectInvalid(withPrivateAdvance);
  });

  it("rejects missing, extra and hidden keys", () => {
    const missing = status();
    delete missing.advance;
    expectInvalid(missing);
    const missingTwo = status();
    delete missingTwo.reason;
    delete missingTwo.receipt;
    expectInvalid(missingTwo);
    expectInvalid(status({ extra: { phase_receipt_digest: RECEIPT_SHA } }));
    const hidden = status();
    Object.defineProperty(hidden, "__hidden", {
      value: "x",
      writable: false,
      enumerable: false,
      configurable: true,
    });
    expectInvalid(hidden);
  });

  it("rejects symbol-keyed objects without reading them", () => {
    const sym = Symbol("hidden");
    const symKeyed = status();
    (symKeyed as unknown as { [k: symbol]: string })[sym] = "x";
    expectInvalid(symKeyed);
    const symOnly = Object.create(Object.prototype);
    symOnly[sym] = "x";
    expectInvalid(symOnly);
  });

  it("accepts null-prototype records and rejects class instances and collections", () => {
    const detached = JSON.parse(JSON.stringify(status())) as Obj;
    Object.setPrototypeOf(detached, null);
    const out = decode(detached as unknown);
    expect(out.selection.work_ref).toBe(WORK_REF);
    const nullProtoNested = JSON.parse(
      JSON.stringify(candidateAdoptStatus()),
    ) as Obj;
    Object.setPrototypeOf(nullProtoNested.receipt as object, null);
    Object.setPrototypeOf(
      (nullProtoNested.receipt as Obj).sources as object,
      null,
    );
    Object.setPrototypeOf(nullProtoNested.selection as object, null);
    expect(decode(nullProtoNested).disposition).toBe("unknown");
  });

  it("rejects class instances and collections in value positions", () => {
    class Hostile extends Object {}
    expectInvalid(new Hostile());
    expectInvalid(new Map());
    expectInvalid(new Set());
    expectInvalid(new Date());
    expectInvalid(new Error(SOURCE_OPERATION_STATUS_INVALID));
    const subclassed = status();
    Object.setPrototypeOf(subclassed, { inherited: true });
    expectInvalid(subclassed);
    expectInvalid([status()]);
    expectInvalid("mastermind.workspace_source_operation_status.v1");
    expectInvalid(null);
    expectInvalid(undefined);
    expectInvalid(0);
    expectInvalid(true);
    expectInvalid(() => status());
    expectInvalid(Symbol("status"));
  });

  it("rejects arrays and non-objects in nested value positions", () => {
    expectInvalid(status({ selection: [selection()] as unknown }));
    const arrayOwnerContext = status();
    arrayOwnerContext.owner_context = [SCOPE] as unknown;
    expectInvalid(arrayOwnerContext);
    const objectOwnerContext = status();
    objectOwnerContext.owner_context = {
      principal_scope: SCOPE,
      extra: SCOPE,
    } as unknown;
    expectInvalid(objectOwnerContext);
    expectInvalid(status({ receipt: [receipt()] as unknown }));
    expectInvalid(
      candidateAdoptStatus({
        receipt: receipt({ sources: sourceRef() as unknown as Obj }),
      }),
    );
    expectInvalid(
      candidateAdoptStatus({
        receipt: receipt({ sources: { 0: sourceRef() } }),
      }),
    );
    expectInvalid(status({ advance: [RECEIPT_SHA] }));
    expectInvalid(status({ advance: { phase_receipt_digest: [RECEIPT_SHA] } }));
    expectInvalid(
      status({
        reason: { toString: () => "IN_PROGRESS" } as unknown as string,
      }),
    );
  });

  it("rejects a custom list subclass element", () => {
    const hostileSources: unknown[] = [sourceRef()];
    Object.setPrototypeOf(hostileSources, {
      push: () => undefined,
    });
    expectInvalid(
      candidateAdoptStatus({
        receipt: receipt({ sources: hostileSources as unknown as Obj }),
      }),
    );
  });
});

/* ------------------------------------------------------------------ *
 * hostile getters are never invoked
 * ------------------------------------------------------------------ */

describe("hostile getters and no invocation", () => {
  it("never invokes a throwing getter on any field", () => {
    const probes: Array<[Obj, string]> = [];
    const top = status();
    probes.push([top, "schema"]);
    probes.push([top, "disposition"]);
    probes.push([top, "reason"]);
    probes.push([top.selection as Obj, "action"]);
    probes.push([top.selection as Obj, "request_id"]);
    probes.push([top.selection as Obj, "work_ref"]);
    probes.push([top.owner_context as Obj, "principal_scope"]);

    for (const [target, key] of probes) {
      let invocations = 0;
      const original = target[key];
      Object.defineProperty(target, key, {
        enumerable: true,
        configurable: true,
        get() {
          invocations += 1;
          throw new Error("GETTER MUST NEVER RUN");
        },
      });
      expectInvalid(top);
      expect(invocations, `getter on ${key} must not be invoked`).toBe(0);
      Object.defineProperty(target, key, {
        enumerable: true,
        configurable: true,
        writable: true,
        value: original,
      });
    }
  });

  it("never invokes a getter that returns the right value but counts reads", () => {
    const body = candidateAdoptStatus();
    let reads = 0;
    Object.defineProperty(body, "phase", {
      enumerable: true,
      configurable: true,
      get() {
        reads += 1;
        return "CANDIDATE";
      },
    });
    expectInvalid(body);
    expect(reads).toBe(0);
  });

  it("never invokes nested getters inside receipt, sources and proposal", () => {
    const body = acceptedAdoptStatus();
    const nested: Array<[object, string]> = [
      [body.receipt as Obj, "kind"],
      [body.receipt as Obj, "receipt_sha256"],
      [((body.receipt as Obj).sources as Obj[])[0], "path"],
      [((body.receipt as Obj).sources as Obj[])[0], "content_sha256"],
      [body.receipt as Obj, "sources"],
    ];
    for (const [target, key] of nested) {
      let invocations = 0;
      Object.defineProperty(target, key, {
        enumerable: true,
        configurable: true,
        get() {
          invocations += 1;
          throw new Error("GETTER MUST NEVER RUN");
        },
      });
      expectInvalid(body);
      expect(invocations, `nested getter on ${key}`).toBe(0);
    }
  });

  it("rejects an accessor-only value descriptor without reading it", () => {
    const body = status();
    Object.defineProperty(body, "advance", {
      enumerable: true,
      configurable: true,
      set() {
        throw new Error("SETTER MUST NEVER RUN");
      },
      get() {
        throw new Error("GETTER MUST NEVER RUN");
      },
    });
    expectInvalid(body);
  });

  it("rejects a poisoned or missing descriptor instead of throwing foreign errors", () => {
    const body = status();
    Object.defineProperty(body, "schema", {
      enumerable: true,
      configurable: false,
      writable: false,
      value: undefined,
    });
    expectInvalid(body);
  });
});

/* ------------------------------------------------------------------ *
 * deep malformed input stays bounded
 * ------------------------------------------------------------------ */

describe("deep malformed input and recursion safety", () => {
  it("rejects a very deep object immediately with the constant error", () => {
    let deep: Obj = { leaf: true };
    for (let i = 0; i < 200000; i += 1) {
      deep = { a: deep };
    }
    expectInvalid(deep);
  });

  it("rejects a very deep array inside a receipt", () => {
    let deep: unknown = ["x"];
    for (let i = 0; i < 100000; i += 1) {
      deep = [deep];
    }
    const body = candidateAdoptStatus();
    (body.receipt as Obj).sources = deep;
    expectInvalid(body);
  });

  it("rejects deep nesting at each closed value position", () => {
    let deep: Obj = { leaf: true };
    for (let i = 0; i < 50000; i += 1) {
      deep = { a: deep };
    }
    expectInvalid(status({ selection: deep }));
    const deepOwnerContext = status();
    deepOwnerContext.owner_context = deep;
    expectInvalid(deepOwnerContext);
    expectInvalid(status({ receipt: deep }));
    expectInvalid(status({ advance: deep }));
    expectInvalid(status({ reason: deep as unknown as string }));
    const body = candidateAdoptStatus();
    ((body.receipt as Obj).sources as Obj[])[0] = deep;
    expectInvalid(body);
  });

  it("keeps the canonical serializer away from hostile input", () => {
    // A rejected value is never serialised, so no deep canonical recursion.
    let deep: Obj = { leaf: true };
    for (let i = 0; i < 200000; i += 1) {
      deep = { a: deep };
    }
    let thrown: unknown = undefined;
    try {
      decodeSourceOperationStatus(deep);
    } catch (error) {
      thrown = error;
    }
    expect((thrown as Error).message).toBe(SOURCE_OPERATION_STATUS_INVALID);
    expect(thrown).not.toBeInstanceOf(RangeError);
  });
});

/* ------------------------------------------------------------------ *
 * canonical form and whole-status budget
 * ------------------------------------------------------------------ */

describe("canonical serialization and Unicode budget", () => {
  it("produces byte-exact sorted compact JSON without escaping non-ASCII", () => {
    const unavailable = unavailableSourceOperationStatus(
      "ADOPT_PLAN",
      ADOPT_ID,
      WORK_REF,
      SCOPE,
    );
    const expected =
      '{"advance":null,"disposition":"unknown","owner_context":{"principal_scope":"' +
      SCOPE +
      '"},"phase":null,"reason":"ORIGINAL_OPERATION_NOT_OBSERVED","receipt":null,' +
      '"recipe_fingerprint_sha256":null,"request_sha256":null,' +
      '"schema":"mastermind.workspace_source_operation_status.v1","selection":' +
      '{"action":"ADOPT_PLAN","request_id":"' +
      ADOPT_ID +
      '","work_ref":"WS:PLAN-ADOPT-ROOT"}}';
    expect(canonicalSourceOperationStatusJson(unavailable)).toBe(expected);
  });

  it("stays inside the whole-status UTF-8 budget with maximal Unicode paths", () => {
    const widePath = "d/" + "é".repeat(255); // 512 UTF-8 bytes
    const cjkPath = "p/" + "🌊".repeat(127); // 1 + 1 + 508 = 510 bytes
    expect(utf8Bytes(widePath)).toBe(512);
    expect(utf8Bytes(cjkPath)).toBeLessThanOrEqual(512);
    const out = decode(
      candidateAdoptStatus({
        receipt: receipt({
          sources: [
            sourceRef({ path: widePath }),
            sourceRef({ path: cjkPath }),
            sourceRef({ path: "docs/方案/adoption.md" }),
          ],
        }),
      }),
    );
    const canonical = canonicalSourceOperationStatusJson(out);
    expect(utf8Bytes(canonical) + 1).toBeLessThanOrEqual(32768);
    expect(canonical).toContain("é");
    expect(canonical).toContain("🌊");
    expect(canonical).not.toContain("\\u");
    expect(utf8Bytes(canonical)).toBeLessThan(4096);
  });

  it("serialises the same status identically twice", () => {
    const body = acceptedAdoptStatus();
    const first = canonicalSourceOperationStatusJson(decode(body));
    const second = canonicalSourceOperationStatusJson(decode(body));
    expect(first).toBe(second);
  });

  it("serialises a three-source status with sorted keys at every level", () => {
    const out = decode(
      candidateAdoptStatus({
        receipt: receipt({ sources: [sourceRef(), sourceRef(), sourceRef()] }),
      }),
    );
    const canonical = canonicalSourceOperationStatusJson(out);
    expect(canonical.startsWith('{"advance":')).toBe(true);
    expect(canonical.indexOf('"schema"')).toBeGreaterThan(
      canonical.indexOf('"receipt"'),
    );
    expect(canonical.indexOf('"selection"')).toBeGreaterThan(
      canonical.indexOf('"schema"'),
    );
    expect(canonical).not.toContain(", ");
    expect(canonical).not.toContain('": ');
  });
});

/* ------------------------------------------------------------------ *
 * detached output
 * ------------------------------------------------------------------ */

describe("deeply detached output", () => {
  it("returns an object graph sharing no reference with the input", () => {
    const input = acceptedAdoptStatus();
    const out = decode(input);
    expect(out).not.toBe(input);
    expect(out.selection).not.toBe(input.selection);
    expect(out.owner_context).not.toBe(input.owner_context);
    expect(out.receipt).not.toBe(input.receipt);
    expect(out.advance).toBeNull();
    const outSources = out.receipt?.sources as readonly unknown[];
    const inSources = (input.receipt as Obj).sources as Obj[];
    expect(outSources).not.toBe(inSources);
    expect(outSources[0]).not.toBe(inSources[0]);
  });

  it("keeps a valid output unchanged when the input is mutated afterwards", () => {
    const input = acceptedAdoptStatus();
    const out = decode(input);
    const before = canonicalSourceOperationStatusJson(out);
    (input.selection as Obj).work_ref = "WS:MUTATED-AFTER";
    (input.owner_context as Obj).principal_scope = FOREIGN_SCOPE;
    input.disposition = "unknown";
    input.phase = "CANDIDATE";
    input.reason = "IN_PROGRESS";
    (input.receipt as Obj).receipt_sha256 = RECEIPT_SHA.toUpperCase();
    const inSources = (input.receipt as Obj).sources as Obj[];
    inSources[0].path = "../../mutated";
    inSources[0].commit = "zz".repeat(20);
    expect(canonicalSourceOperationStatusJson(out)).toBe(before);
    expect(out.selection.work_ref).toBe(WORK_REF);
    expect(out.disposition).toBe("accepted");
    expect(out.phase).toBe("ADOPTION");
    expect(out.receipt?.receipt_sha256).toBe(RECEIPT_SHA);
    expect(out.receipt?.sources[0]?.path).toBe("docs/plan/adoption.md");
  });

  it("returns a fresh null-evidence body on every unavailable call", () => {
    const first = unavailableSourceOperationStatus(
      "ADOPT_PLAN",
      ADOPT_ID,
      WORK_REF,
      SCOPE,
    );
    const second = unavailableSourceOperationStatus(
      "ADOPT_PLAN",
      ADOPT_ID,
      WORK_REF,
      SCOPE,
    );
    expect(first).not.toBe(second);
    expect(first.selection).not.toBe(second.selection);
    expect(first).toEqual(second);
  });

  it("never leaks untrusted text into the rejection message", () => {
    const secret = "SECRET-TOKEN-XYZ";
    const probe = status({
      reason: `IN_PROGRESS ${secret}`,
      extra: { token: secret },
    });
    let message = "";
    try {
      decodeSourceOperationStatus(probe);
    } catch (error) {
      message = (error as Error).message;
    }
    expect(message).toBe(SOURCE_OPERATION_STATUS_INVALID);
    expect(message.includes(secret)).toBe(false);
    expect(message).not.toContain("IN_PROGRESS");
  });
});
