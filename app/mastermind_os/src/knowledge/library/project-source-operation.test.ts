import { describe, expect, it } from "vitest";
import fixture from "./project-source-operation-contract-cases.json";
import {
  PROJECT_SOURCE_ACTION_ADD_FILE,
  PROJECT_SOURCE_ACTION_SET_PREFERENCE,
  PROJECT_SOURCE_ACTIONS,
  PROJECT_SOURCE_CONTEXT_SCHEMA,
  PROJECT_SOURCE_OPERATION_INVALID,
  PROJECT_SOURCE_STATUS_SCHEMA,
  decodeProjectSourceOperationContext,
  decodeProjectSourceOperationStatus,
  type ProjectSourceContext,
  type ProjectSourceContextExpectation,
  type ProjectSourceStatus,
  type ProjectSourceStatusExpectation,
} from "./project-source-operation";

interface FixtureContextCase {
  readonly name: string;
  readonly raw: Record<string, unknown>;
  readonly expected: ProjectSourceContextExpectation;
  readonly decode: "valid" | "invalid";
  readonly decode_reject_reason?: string;
  readonly python_grammar_probe?: string;
}
interface FixtureStatusCase {
  readonly name: string;
  readonly raw: Record<string, unknown>;
  readonly expected: ProjectSourceStatusExpectation;
  readonly decode: "valid" | "invalid";
  readonly disposition: string;
  readonly decode_reject_reason?: string;
  readonly python_validate_status?: "accept" | "reject";
}
interface FixtureProvenance {
  readonly kind: string;
  readonly python_status_results: { readonly accepted: number; readonly rejected: number };
  readonly python_context_grammar_probe: { readonly accepted: number; readonly rejected: number };
  readonly [key: string]: unknown;
}
interface Fixture {
  readonly provenance: FixtureProvenance;
  readonly context_expectations: Record<
    string,
    ProjectSourceContextExpectation
  >;
  readonly status_expectations: Record<string, ProjectSourceStatusExpectation>;
  readonly context_cases: readonly FixtureContextCase[];
  readonly status_cases: readonly FixtureStatusCase[];
}

const CONTRACT = fixture as unknown as Fixture;
const clone = (value: unknown): Record<string, unknown> =>
  structuredClone(value) as Record<string, unknown>;
const caseByName = (cases: readonly { name: string }[], name: string): number => {
  const index = cases.findIndex((entry) => entry.name === name);
  expect(index, `fixture case ${name}`).toBeGreaterThanOrEqual(0);
  return index;
};
const contextCase = (name: string): FixtureContextCase =>
  CONTRACT.context_cases[caseByName(CONTRACT.context_cases, name)];
const statusCase = (name: string): FixtureStatusCase =>
  CONTRACT.status_cases[caseByName(CONTRACT.status_cases, name)];
const rawStatusCase = (name: string): Record<string, unknown> =>
  clone(statusCase(name).raw);
const contextExpectation = (
  expectation: ProjectSourceContextExpectation,
): ProjectSourceContextExpectation => structuredClone(expectation);
const statusExpectation = (
  expectation: ProjectSourceStatusExpectation,
): ProjectSourceStatusExpectation => structuredClone(expectation);
const at = (value: unknown, path: PropertyKey[]): Record<string, unknown> => {
  let current: unknown = value;
  for (const key of path) current = (current as Record<string, unknown>)[key as string];
  return current as Record<string, unknown>;
};
const set = (value: unknown, path: PropertyKey[], replacement: unknown): void => {
  at(value, path.slice(0, -1))[path[path.length - 1] as string] = replacement;
};
const omit = (value: unknown, path: PropertyKey[]): void => {
  delete at(value, path.slice(0, -1))[path[path.length - 1] as string];
};

const expectInvalid = (run: () => unknown): void => {
  let message: string | null = null;
  try {
    run();
  } catch (error) {
    message = (error as Error).message;
  }
  expect(message).toBe(PROJECT_SOURCE_OPERATION_INVALID);
};

const decodeContext = (
  raw: unknown,
  expected: ProjectSourceContextExpectation,
): ProjectSourceContext => decodeProjectSourceOperationContext(raw, expected);
const decodeStatus = (
  raw: unknown,
  expected: ProjectSourceStatusExpectation,
): ProjectSourceStatus => decodeProjectSourceOperationStatus(raw, expected);

const expectFrozenDeep = (value: unknown): void => {
  expect(Object.isFrozen(value)).toBe(true);
  if (value !== null && typeof value === "object") {
    for (const property of Object.values(value as Record<string, unknown>)) {
      expectFrozenDeep(property);
    }
  }
};

const expectPlainData = (value: unknown): void => {
  for (const property of Object.values(value as Record<string, unknown>)) {
    expect(typeof property).not.toBe("function");
    if (property !== null && typeof property === "object") {
      expectPlainData(property);
    }
  }
};

describe("project source operation contract fixture", () => {
  it("is a synthetic closed-shape fixture, not live receipts or Runtime events", () => {
    expect(CONTRACT.provenance.kind).toBe("synthetic_cross_language_contract_cases");
    expect(CONTRACT.provenance.python_status_results.accepted).toBe(13);
    expect(CONTRACT.provenance.python_status_results.rejected).toBe(33);
  });

  it("carries the two closed actions and their paired expectation tuples", () => {
    expect([...PROJECT_SOURCE_ACTIONS]).toEqual([
      PROJECT_SOURCE_ACTION_ADD_FILE,
      PROJECT_SOURCE_ACTION_SET_PREFERENCE,
    ]);
    expect(Object.keys(CONTRACT.status_expectations)).toEqual([
      "add_project_file",
      "set_project_communication_preference",
    ]);
    const file = CONTRACT.status_expectations.add_project_file;
    expect(file.requestId.startsWith("mmos-project-file-add-")).toBe(true);
    const preference = CONTRACT.status_expectations.set_project_communication_preference;
    expect(preference.requestId.startsWith("mmos-project-preference-set-")).toBe(true);
  });

  it("decodes every valid fixture context case and refuses every invalid one", () => {
    for (const entry of CONTRACT.context_cases) {
      if (entry.decode === "valid") {
        const decoded = decodeContext(entry.raw, entry.expected);
        expect(decoded.schema).toBe(PROJECT_SOURCE_CONTEXT_SCHEMA);
        expect(decoded.selection.action).toBe(entry.expected.action);
        expect(decoded.selection.work_ref).toBe(entry.expected.workRef);
        expect(decoded.can_inspect).toBe(true);
      } else {
        expectInvalid(() => decodeContext(entry.raw, entry.expected));
      }
    }
  });

  it("decodes every valid fixture status case and refuses every invalid one", () => {
    for (const entry of CONTRACT.status_cases) {
      if (entry.decode === "valid") {
        const decoded = decodeStatus(entry.raw, entry.expected);
        expect(decoded.disposition).toBe(entry.disposition);
        expect(decoded.schema).toBe(PROJECT_SOURCE_STATUS_SCHEMA);
        expect(decoded.selection.request_id).toBe(entry.expected.requestId);
        // Every wire value the decoder accepted was also accepted by the
        // actual supplied Python validate_status when the fixture was built.
        expect(entry.python_validate_status).toBe("accept");
      } else {
        expectInvalid(() => decodeStatus(entry.raw, entry.expected));
      }
    }
  });

  it("keeps Python-rejected raw values rejected by the decoder too", () => {
    for (const entry of CONTRACT.status_cases) {
      if (entry.python_validate_status === "reject") {
        expect(entry.decode).toBe("invalid");
      }
    }
  });
});

describe("context shape", () => {
  const base = () => clone(contextCase("context_add_file_valid").raw);
  const expectation = () =>
    contextExpectation(contextCase("context_add_file_valid").expected);

  it("decodes the signed-owner inspection context into a frozen detached value", () => {
    const decoded = decodeContext(base(), expectation());
    expect(decoded).toEqual({
      schema: "mastermind.workspace_source_operation_context.v1",
      selection: {
        action: PROJECT_SOURCE_ACTION_ADD_FILE,
        work_ref: "WS:PROJ-7",
      },
      owner_context: { principal_scope: expect.any(String) },
      can_inspect: true,
    });
    expect(decoded.owner_context.principal_scope).toMatch(/^[0-9a-f]{64}$/);
    expectFrozenDeep(decoded);
    expectPlainData(decoded);
    expect(Object.getPrototypeOf(decoded)).toBe(Object.prototype);
  });

  it("rejects any selected action or work ref other than the expected tuple", () => {
    const raw = base();
    set(raw, ["selection", "action"], "set_project_communication_preference");
    expectInvalid(() => decodeContext(raw, expectation()));
    const otherWorkRef = base();
    set(otherWorkRef, ["selection", "work_ref"], "WS:OTHER-1");
    expectInvalid(() => decodeContext(otherWorkRef, expectation()));
  });

  it("rejects a context whose action is outside the two decoded actions", () => {
    const raw = base();
    set(raw, ["selection", "action"], "ADOPT_PLAN");
    expectInvalid(() => decodeContext(raw, expectation()));
    const rawPublish = base();
    set(rawPublish, ["selection", "action"], "publish_project_proposal");
    expectInvalid(() => decodeContext(rawPublish, expectation()));
  });

  it("requires can_inspect to be exactly true", () => {
    const raw = base();
    set(raw, ["can_inspect"], false);
    expectInvalid(() => decodeContext(raw, expectation()));
    const rawText = base();
    set(rawText, ["can_inspect"], "true");
    expectInvalid(() => decodeContext(rawText, expectation()));
    const rawMissing = base();
    omit(rawMissing, ["can_inspect"]);
    expectInvalid(() => decodeContext(rawMissing, expectation()));
  });

  it("rejects unknown schemas, extra fields and missing fields", () => {
    const wrongSchema = base();
    set(wrongSchema, ["schema"], "mastermind.workspace_source_operation_context.v2");
    expectInvalid(() => decodeContext(wrongSchema, expectation()));
    const extra = base();
    set(extra, ["issued_by"], "someone");
    expectInvalid(() => decodeContext(extra, expectation()));
    const missing = base();
    omit(missing, ["owner_context"]);
    expectInvalid(() => decodeContext(missing, expectation()));
  });

  it("enforces the strict 2..64 uppercase kebab WS:KEY work-ref grammar", () => {
    for (const workRef of ["WS:proj-7", "PROJ-7", "WS:", "WS:A", "WS:" + "A".repeat(65),
      "WS:PROJ-7\n", "WS:PROJ--7", " WS:PROJ-7", "WS:PROJ-7 ", "WS:PRÓJ-7"]) {
      const raw = base();
      set(raw, ["selection", "work_ref"], workRef);
      expectInvalid(() => decodeContext(raw, expectation()));
    }
    const shortExpected = contextExpectation({ ...expectation(), workRef: "WS:A" });
    expectInvalid(() => decodeContext(base(), shortExpected));
  });

  it("requires the owner principal scope to be exact lowercase hex64", () => {
    for (const scope of ["", "Z".repeat(64), "a".repeat(63), "a".repeat(65),
      "A".repeat(64), null, 42]) {
      const raw = base();
      set(raw, ["owner_context", "principal_scope"], scope);
      expectInvalid(() => decodeContext(raw, expectation()));
    }
  });

  it("rejects non-plain-data context inputs without ever calling getters", () => {
    let getterCalls = 0;
    const raw = base();
    Object.defineProperty(raw, "schema", {
      enumerable: true,
      get() {
        getterCalls += 1;
        return "mastermind.workspace_source_operation_context.v1";
      },
    });
    expectInvalid(() => decodeContext(raw, expectation()));
    expect(getterCalls).toBe(0);

    const hidden = base();
    Object.defineProperty(hidden, "can_inspect", { enumerable: false, value: true });
    expectInvalid(() => decodeContext(hidden, expectation()));

    const symbolKey = base();
    const marker = Symbol("marker");
    (symbolKey as Record<symbol, unknown>)[marker] = true;
    expectInvalid(() => decodeContext(symbolKey, expectation()));

    const foreign = Object.create({ schema: "mastermind.workspace_source_operation_context.v1" }) as Record<string, unknown>;
    Object.assign(foreign, base());
    expectInvalid(() => decodeContext(foreign, expectation()));

    const withToJSON = base();
    set(withToJSON, ["toJSON"], () => ({}));
    expectInvalid(() => decodeContext(withToJSON, expectation()));

    const selectionWithGetter = base();
    Object.defineProperty(selectionWithGetter.selection, "action", {
      enumerable: true,
      get() {
        getterCalls += 1;
        return PROJECT_SOURCE_ACTION_ADD_FILE;
      },
    });
    expectInvalid(() => decodeContext(selectionWithGetter, expectation()));
    expect(getterCalls).toBe(0);

    for (const bad of [null, undefined, 7, "ctx", [], true]) {
      expectInvalid(() => decodeContext(bad, expectation()));
    }
    expectInvalid(() => decodeContext(base(), null as unknown as ProjectSourceContextExpectation));
    const wrongExpectedAction = contextExpectation({
      ...expectation(),
      action: "publish_project_proposal" as unknown as ProjectSourceContextExpectation["action"],
    });
    expectInvalid(() => decodeContext(base(), wrongExpectedAction));
  });

  it("rejects cyclic context values", () => {
    const raw = base();
    at(raw, ["selection"])["self"] = raw;
    expectInvalid(() => decodeContext(raw, expectation()));
    const ownerCycle = base();
    (ownerCycle.owner_context as Record<string, unknown>)["loop"] = ownerCycle;
    expectInvalid(() => decodeContext(ownerCycle, expectation()));
  });
});

describe("status shape and identity", () => {
  const validAccepted = () => clone(statusCase("accepted_publication_add_file").raw);
  const acceptedExpectation = () =>
    statusExpectation(statusCase("accepted_publication_add_file").expected);

  it("decodes an accepted publication status with full provenance retained", () => {
    const decoded = decodeStatus(validAccepted(), acceptedExpectation());
    expect(decoded.disposition).toBe("accepted");
    expect(decoded.reason).toBeNull();
    expect(decoded.phase).toBe("PUBLICATION");
    expect(decoded.request_sha256).not.toBeNull();
    expect(decoded.recipe_fingerprint_sha256).not.toBeNull();
    expect(decoded.request_sha256).not.toBe(decoded.recipe_fingerprint_sha256);
    expect(decoded.receipt?.kind).toBe("SOURCE_OBSERVED");
    expect(decoded.receipt?.sources.length).toBe(1);
    expect(decoded.receipt?.sources[0]?.repository).toBe("macro");
    expect(decoded.receipt?.proposal).toBeNull();
    expect(decoded.advance).toBeNull();
    expect(typeof decoded.receipt?.event_id).toBe("number");
    expect(typeof decoded.receipt?.recorded_at_ms).toBe("number");
    expectFrozenDeep(decoded);
    expectPlainData(decoded);
  });

  it("never reports digests or phase without a receipt", () => {
    const unavailable = decodeStatus(
      rawStatusCase("unavailable_null_evidence"),
      statusExpectation(statusCase("unavailable_null_evidence").expected),
    );
    expect(unavailable.disposition).toBe("unknown");
    expect(unavailable.reason).toBe("ORIGINAL_OPERATION_NOT_OBSERVED");
    expect(unavailable.request_sha256).toBeNull();
    expect(unavailable.recipe_fingerprint_sha256).toBeNull();
    expect(unavailable.phase).toBeNull();
    expect(unavailable.receipt).toBeNull();
    expect(unavailable.advance).toBeNull();
    // Absence of a receipt is never read as proof that no effect happened.
    expect(unavailable.disposition).not.toBe("accepted");
  });

  it("retains unknown partial provenance after the source becomes unavailable", () => {
    const decoded = decodeStatus(
      rawStatusCase("unknown_partial_phase_attempted_retained"),
      statusExpectation(statusCase("unknown_partial_phase_attempted_retained").expected),
    );
    expect(decoded.disposition).toBe("unknown");
    expect(decoded.reason).toBe("PHASE_ATTEMPT_UNRESOLVED");
    expect(decoded.receipt?.kind).toBe("PHASE_ATTEMPTED");
    expect(decoded.receipt?.sources).toEqual([]);
    expect(decoded.receipt?.proposal).toBeNull();
    expect(decoded.request_sha256).toBe(
      statusCase("unknown_partial_phase_attempted_retained").expected.requestSha256,
    );
    expect(decoded.phase).toBe("PUBLICATION");
  });

  it("decodes refused statuses and proposal-observed provenance", () => {
    const refused = decodeStatus(
      rawStatusCase("refused_not_dispatched"),
      statusExpectation(statusCase("refused_not_dispatched").expected),
    );
    expect(refused.disposition).toBe("refused");
    expect(refused.reason).toBe("NOT_DISPATCHED");
    expect(refused.receipt).toBeNull();
    expect(refused.request_sha256).toBeNull();

    const proposed = decodeStatus(
      rawStatusCase("unknown_proposal_observed"),
      statusExpectation(statusCase("unknown_proposal_observed").expected),
    );
    expect(proposed.disposition).toBe("unknown");
    expect(proposed.receipt?.kind).toBe("PROPOSAL_OBSERVED");
    expect(proposed.receipt?.proposal?.url).toBe(
      "https://github.com/mastermindx-market-intelligence/macro/pull/" +
        String(proposed.receipt?.proposal?.number),
    );
    expect(proposed.receipt?.sources).toEqual([]);
  });

  it("returns frozen detached copies on every decode", () => {
    const first = decodeStatus(validAccepted(), acceptedExpectation());
    const second = decodeStatus(validAccepted(), acceptedExpectation());
    expect(first).not.toBe(second);
    expect(first.receipt).not.toBe(second.receipt);
    expect(first).toEqual(second);
    expectFrozenDeep(first);
    const raw = validAccepted();
    const decoded = decodeStatus(raw, acceptedExpectation());
    set(raw, ["receipt", "receipt_sha256"], "f".repeat(64));
    (at(raw, ["receipt", "sources"]) as unknown as unknown[]).push({
      repository: "macro", commit: "a".repeat(40), path: "project/late.md",
      content_sha256: "c".repeat(64),
    });
    expect(decoded).toEqual(first);
  });

  it("matches the expected operation tuple exactly", () => {
    const file = statusCase("accepted_publication_add_file");
    const raw = clone(file.raw);
    set(raw, ["selection", "request_id"],
      CONTRACT.status_expectations.set_project_communication_preference.requestId);
    expectInvalid(() => decodeStatus(raw, statusExpectation(file.expected)));
    const mismatchedExpectation = statusExpectation({
      ...file.expected,
      requestId: CONTRACT.status_expectations.set_project_communication_preference.requestId,
    });
    expectInvalid(() => decodeStatus(clone(file.raw), mismatchedExpectation));
    const wrongWorkRef = statusExpectation({ ...file.expected, workRef: "WS:OTHER-1" });
    expectInvalid(() => decodeStatus(clone(file.raw), wrongWorkRef));
    const wrongScope = statusExpectation({
      ...file.expected,
      principalScope: "a".repeat(64),
    });
    expectInvalid(() => decodeStatus(clone(file.raw), wrongScope));
    const wrongPublicSha = statusExpectation({
      ...file.expected,
      requestSha256: "b".repeat(64),
    });
    expectInvalid(() => decodeStatus(clone(file.raw), wrongPublicSha));
  });

  it("validates the expected tuple itself before reading any wire body", () => {
    const notClosed = {
      ...acceptedExpectation(),
      action: "ADOPT_PLAN" as unknown as ProjectSourceStatusExpectation["action"],
    };
    expectInvalid(() => decodeStatus(validAccepted(), notClosed));
    const badWorkRef = { ...acceptedExpectation(), workRef: "WS:" };
    expectInvalid(() => decodeStatus(validAccepted(), badWorkRef));
    const badRequestId = { ...acceptedExpectation(), requestId: "mmos-project-file-add-short" };
    expectInvalid(() => decodeStatus(validAccepted(), badRequestId));
    const badSha = { ...acceptedExpectation(), requestSha256: "A".repeat(64) };
    expectInvalid(() => decodeStatus(validAccepted(), badSha));
    const badScope = { ...acceptedExpectation(), principalScope: "zz" };
    expectInvalid(() => decodeStatus(validAccepted(), badScope));
    expectInvalid(() =>
      decodeStatus(validAccepted(), null as unknown as ProjectSourceStatusExpectation));
    expectInvalid(() =>
      decodeStatus(null, acceptedExpectation()));
  });

  it("restricts plain actions to the PUBLICATION phase and refuses adopt machinery", () => {
    const raw = validAccepted();
    set(raw, ["phase"], "ADOPTION");
    expectInvalid(() => decodeStatus(raw, acceptedExpectation()));
    const candidate = validAccepted();
    set(candidate, ["phase"], "CANDIDATE");
    expectInvalid(() => decodeStatus(candidate, acceptedExpectation()));
    expectInvalid(() =>
      decodeStatus(
        rawStatusCase("invalid_ready_for_advance_on_plain_action"),
        statusExpectation(statusCase("invalid_ready_for_advance_on_plain_action").expected),
      ));
    expectInvalid(() =>
      decodeStatus(
        rawStatusCase("invalid_advance_on_accepted"),
        statusExpectation(statusCase("invalid_advance_on_accepted").expected),
      ));
  });
});

describe("status plain-data and closed-grammar rejections", () => {
  const acceptedRaw = () => clone(statusCase("accepted_publication_add_file").raw);
  const expectation = () =>
    statusExpectation(statusCase("accepted_publication_add_file").expected);

  it("rejects broken receipt shapes and closed-value violations", () => {
    const badKind = acceptedRaw();
    set(badKind, ["receipt", "kind"], "RECEIPT_OBSERVED");
    expectInvalid(() => decodeStatus(badKind, expectation()));
    const badEvent = acceptedRaw();
    set(badEvent, ["receipt", "event_id"], 0);
    expectInvalid(() => decodeStatus(badEvent, expectation()));
    const floatEvent = acceptedRaw();
    set(floatEvent, ["receipt", "event_id"], 1.5);
    expectInvalid(() => decodeStatus(floatEvent, expectation()));
    const boolEvent = acceptedRaw();
    set(boolEvent, ["receipt", "event_id"], true);
    expectInvalid(() => decodeStatus(boolEvent, expectation()));
    const unsafeEvent = acceptedRaw();
    set(unsafeEvent, ["receipt", "event_id"], 9007199254740992);
    expectInvalid(() => decodeStatus(unsafeEvent, expectation()));
    const badTimestamp = acceptedRaw();
    set(badTimestamp, ["receipt", "recorded_at_ms"], "1762185000000");
    expectInvalid(() => decodeStatus(badTimestamp, expectation()));
    const negativeTimestamp = acceptedRaw();
    set(negativeTimestamp, ["receipt", "recorded_at_ms"], -1);
    expectInvalid(() => decodeStatus(negativeTimestamp, expectation()));
    const upperDigest = acceptedRaw();
    set(upperDigest, ["receipt", "receipt_sha256"], "F".repeat(64));
    expectInvalid(() => decodeStatus(upperDigest, expectation()));
    const wrongSelectionShape = acceptedRaw();
    set(wrongSelectionShape, ["selection", "extra"], 1);
    expectInvalid(() => decodeStatus(wrongSelectionShape, expectation()));
    const badDisposition = acceptedRaw();
    set(badDisposition, ["disposition"], "pending");
    expectInvalid(() => decodeStatus(badDisposition, expectation()));
    const badReason = acceptedRaw();
    set(badReason, ["reason"], "SOMEDAY");
    expectInvalid(() => decodeStatus(badReason, expectation()));
    const unknownRefused = clone(
      statusCase("invalid_reason_refused_on_unknown").raw,
    );
    expectInvalid(() =>
      decodeStatus(unknownRefused,
        statusExpectation(statusCase("invalid_reason_refused_on_unknown").expected)));
  });

  it("rejects sources over the fixed budget or off the canonical macro repo", () => {
    expectInvalid(() =>
      decodeStatus(
        rawStatusCase("invalid_sources_over_limit"),
        statusExpectation(statusCase("invalid_sources_over_limit").expected),
      ));
    const wrongRepo = acceptedRaw();
    set(wrongRepo, ["receipt", "sources", 0, "repository"], "Mastermind");
    expectInvalid(() => decodeStatus(wrongRepo, expectation()));
    const badCommit = acceptedRaw();
    set(badCommit, ["receipt", "sources", 0, "commit"], "a".repeat(41));
    expectInvalid(() => decodeStatus(badCommit, expectation()));
    const upperCommit = acceptedRaw();
    set(upperCommit, ["receipt", "sources", 0, "commit"], "A".repeat(40));
    expectInvalid(() => decodeStatus(upperCommit, expectation()));
    const sourcesObject = acceptedRaw();
    set(sourcesObject, ["receipt", "sources"], { 0: {} });
    expectInvalid(() => decodeStatus(sourcesObject, expectation()));
    const sparseSources = acceptedRaw();
    const sparse = [at(sparseSources, ["receipt", "sources", 0])] as unknown[];
    sparse.length = 2;
    delete sparse[0];
    set(sparseSources, ["receipt", "sources"], sparse);
    expectInvalid(() => decodeStatus(sparseSources, expectation()));
  });

  it("enforces the safe-path grammar on every source record", () => {
    const badPaths = [
      "",
      "project//preferences.json",
      "/absolute/preferences.json",
      "project/./preferences.json",
      "project/../preferences.json",
      "project/preferences.json/",
      "project\\preferences.json",
      "project/preferences.json\n",
      "project/pref\u0000erences.json",
      "project/pref\u007Ferences.json\u0085",
      "ü".repeat(300),
      `project/${"😀".repeat(130)}`,
    ];
    for (const path of badPaths) {
      const raw = acceptedRaw();
      set(raw, ["receipt", "sources", 0, "path"], path);
      expectInvalid(() => decodeStatus(raw, expectation()));
    }
    const unicodePath = acceptedRaw();
    set(unicodePath, ["receipt", "sources", 0, "path"], "project/notes/文件-😀.md");
    expect(decodeStatus(unicodePath, expectation()).receipt?.sources[0]?.path).toBe(
      "project/notes/文件-😀.md",
    );
  });

  it("enforces the exact safe Git branch grammar on proposals", () => {
    const withProposal = () => clone(statusCase("unknown_proposal_observed").raw);
    const proposalExpectation = () =>
      statusExpectation(statusCase("unknown_proposal_observed").expected);
    for (const branch of [
      "-work", "work/", "work.", "release.lock", "release~1", "feature//x",
      "feat..ure", "patch@{now}", "back\\slash", "has space", "brünch", "",
      "x".repeat(201),
    ]) {
      const raw = withProposal();
      set(raw, ["receipt", "proposal", "head_branch"], branch);
      expectInvalid(() => decodeStatus(raw, proposalExpectation()));
    }
    const goodBranch = withProposal();
    set(goodBranch, ["receipt", "proposal", "head_branch"], "agentos/project-file-7.v2");
    expect(
      decodeStatus(goodBranch, proposalExpectation()).receipt?.proposal?.head_branch,
    ).toBe("agentos/project-file-7.v2");
  });

  it("accepts only the fixed macro PR URL paired with the proposal number", () => {
    const withProposal = () => clone(statusCase("unknown_proposal_observed").raw);
    const proposalExpectation = () =>
      statusExpectation(statusCase("unknown_proposal_observed").expected);
    for (const url of [
      "https://gitlab.com/other/macro/pull/12",
      "https://github.com/mastermindx-market-intelligence/macro/pull/13",
      "https://github.com/mastermindx-market-intelligence/macro/pull/12/files",
      "not-a-url",
    ]) {
      const raw = withProposal();
      set(raw, ["receipt", "proposal", "url"], url);
      expectInvalid(() => decodeStatus(raw, proposalExpectation()));
    }
    const badNumber = withProposal();
    set(badNumber, ["receipt", "proposal", "number"], 0);
    expectInvalid(() => decodeStatus(badNumber, proposalExpectation()));
  });

  it("rejects accessor-backed and non-plain data without calling getters", () => {
    let getterCalls = 0;
    const getterSource = acceptedRaw();
    Object.defineProperty(at(getterSource, ["receipt", "sources"]), "0", {
      enumerable: true,
      get() {
        getterCalls += 1;
        return { repository: "macro", commit: "a".repeat(40), path: "p",
          content_sha256: "c".repeat(64) };
      },
    });
    expectInvalid(() => decodeStatus(getterSource, expectation()));
    expect(getterCalls).toBe(0);

    const hiddenField = acceptedRaw();
    Object.defineProperty(hiddenField, "phase", { enumerable: false, value: "PUBLICATION" });
    expectInvalid(() => decodeStatus(hiddenField, expectation()));

    const symbolReceipt = acceptedRaw();
    const marker = Symbol("receipt");
    (at(symbolReceipt, ["receipt"]) as Record<symbol, unknown>)[marker] = 1;
    expectInvalid(() => decodeStatus(symbolReceipt, expectation()));

    const subclassSources = acceptedRaw();
    class SourceList extends Array {}
    set(subclassSources, ["receipt", "sources"],
      SourceList.from([at(acceptedRaw(), ["receipt", "sources", 0])]));
    expectInvalid(() => decodeStatus(subclassSources, expectation()));

    const cyclic = acceptedRaw();
    (at(cyclic, ["receipt"]) as Record<string, unknown>)["loop"] =
      at(cyclic, ["receipt"]);
    expectInvalid(() => decodeStatus(cyclic, expectation()));

    for (const bad of [null, 1, "status", [], true, undefined]) {
      expectInvalid(() => decodeStatus(bad, expectation()));
    }
  });
});
