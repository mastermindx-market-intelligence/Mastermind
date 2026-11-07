import { describe, expect, it } from "vitest";

import {
  decodePlanAdoptionRequest,
  type PlanAdoptionRequest,
} from "./plan-adoption-request";

const WORK_REF = "WS:PLAN-DOC";
const WORK_REF_KEY = "PLAN-DOC";
const COMMIT = "a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e";
const SHA =
  "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
const REQUEST_ID = "mmos-project-adopt-" + COMMIT;
const DEC_REF = "DEC:PLAN-ADOPTION-AB";
const SCHEMA = "agentos.plan_adoption_request.v1";
const MACRO = "mastermindx-market-intelligence/macro";
const MASTERMIND = "mastermindx-market-intelligence/Mastermind";
const PROPOSAL_PATH = "agentos/proposals/PLAN-DOC-PROPOSAL-AB.md";
const BASE_PATH = "docs/plans/PLAN-DOC-BASE-CD.md";
const INVALID = "PLAN_ADOPTION_REQUEST_INVALID";

function proposalSource(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    repository: MACRO,
    path: PROPOSAL_PATH,
    commit: COMMIT,
    content_sha256: SHA,
    ...overrides,
  };
}

function baseSource(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    repository: MASTERMIND,
    path: BASE_PATH,
    commit: COMMIT,
    content_sha256: SHA,
    ...overrides,
  };
}

function rawRequest(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema: SCHEMA,
    request_id: REQUEST_ID,
    work_ref: WORK_REF,
    expected_commit: COMMIT,
    expected_adoption: DEC_REF,
    proposal_source: proposalSource(),
    base_source: baseSource(),
    candidate_sha256: SHA,
    ...overrides,
  };
}

/** Decode and assert the single value-free rejection for invalid inputs. */
function expectInvalid(value: unknown, expectedWorkRef: unknown = WORK_REF): Error {
  let error: unknown;
  try {
    // The static decoder signature says `string`, but a hostile caller can lie.
    decodePlanAdoptionRequest(value, expectedWorkRef as string);
  } catch (caught) {
    error = caught;
  }
  expect(error).toBeInstanceOf(Error);
  const failure = error as Error;
  expect(failure.message).toBe(INVALID);
  return failure;
}

function expectValid(value: unknown, expectedWorkRef: unknown = WORK_REF): PlanAdoptionRequest {
  const decoded = decodePlanAdoptionRequest(value, expectedWorkRef as string);
  expect(decoded).not.toBe(value);
  return decoded;
}

describe("decodePlanAdoptionRequest", () => {
  it("rejects with exactly one value-free message and never echoes input", () => {
    const secret = "mmos-project-adopt-" + "b".repeat(40);
    const failure = expectInvalid(rawRequest({ request_id: secret + "\n" }));
    expect(failure.message).not.toContain(secret);
    expect(failure.message).not.toContain("\n");
    expect(Object.keys(failure as unknown as Record<string, unknown>)).toEqual([]);
  });

  describe("exact positive cases", () => {
    it("decodes the exact compiler request shape", () => {
      const decoded = expectValid(rawRequest());
      expect(decoded).toEqual({
        schema: SCHEMA,
        request_id: REQUEST_ID,
        work_ref: WORK_REF,
        expected_commit: COMMIT,
        expected_adoption: DEC_REF,
        proposal_source: proposalSource(),
        base_source: baseSource(),
        candidate_sha256: SHA,
      });
    });

    it("accepts a null expected_adoption (initial baseline)", () => {
      const decoded = expectValid(rawRequest({ expected_adoption: null }));
      expect(decoded.expected_adoption).toBeNull();
    });

    it("preserves exact supplied strings without normalization", () => {
      const path = "docs/plans/PLAN-DOC-base .md";
      const decoded = expectValid(
        rawRequest({ base_source: baseSource({ path: path }) }),
      );
      expect(decoded.base_source.path).toBe(path);
    });

    it("accepts a null-prototype input object", () => {
      const value = Object.create(null) as Record<string, unknown>;
      Object.assign(value, rawRequest());
      const decoded = expectValid(value);
      expect(decoded.work_ref).toBe(WORK_REF);
    });

    it("accepts boundary-length work ref key (2 and 64 chars)", () => {
      expectValid(rawRequest({ work_ref: "WS:AB" }), "WS:AB");
      const long = "WS:" + "A".repeat(64);
      expectValid(rawRequest({ work_ref: long, expected_adoption: null }), long);
    });

    it("accepts boundary-length DEC ref key (128 chars)", () => {
      const dec = "DEC:" + "A".repeat(128);
      const decoded = expectValid(rawRequest({ expected_adoption: dec }));
      expect(decoded.expected_adoption).toBe(dec);
      expectInvalid(rawRequest({ expected_adoption: "DEC:" + "A".repeat(129) }));
    });

    it("accepts a macro base whose path is the exact selected WS record path", () => {
      const decoded = expectValid(
        rawRequest({ base_source: baseSource({ repository: MACRO, path: "agentos/workstreams/WS-" + WORK_REF_KEY + ".md" }) }),
      );
      expect(decoded.base_source.repository).toBe(MACRO);
    });

    it("accepts a Mastermind base path inside a workstreams-looking directory", () => {
      // The closed macro WS-path rule is scoped to the macro repository only.
      const decoded = expectValid(
        rawRequest({ base_source: baseSource({ path: "agentos/workstreams/notes.md" }) }),
      );
      expect(decoded.base_source.path).toBe("agentos/workstreams/notes.md");
    });
  });

  describe("cross-repository base closure", () => {
    it("accepts a macro base source", () => {
      const decoded = expectValid(rawRequest({ base_source: baseSource({ repository: MACRO }) }));
      expect(decoded.base_source.repository).toBe(MACRO);
    });

    it("accepts a Mastermind base source", () => {
      const decoded = expectValid(rawRequest());
      expect(decoded.base_source.repository).toBe(MASTERMIND);
    });

    it("rejects a Mastermind proposal source (compiler supports captured macro proposals only)", () => {
      expectInvalid(
        rawRequest({ proposal_source: proposalSource({ repository: MASTERMIND }) }),
      );
    });

    it("rejects unknown repositories for both roles", () => {
      expectInvalid(rawRequest({ proposal_source: proposalSource({ repository: "acme/other" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ repository: "acme/other" }) }));
      expectInvalid(rawRequest({ proposal_source: proposalSource({ repository: MACRO + "-evil" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ repository: "mastermindx-market-intelligence/mastermind" }) }));
    });
  });

  describe("malformed input types", () => {
    it("rejects non-object and non-plain-class inputs", () => {
      expectInvalid(null);
      expectInvalid(undefined);
      expectInvalid(42);
      expectInvalid(true);
      expectInvalid("agentos.plan_adoption_request.v1");
      expectInvalid([]);
      expectInvalid([rawRequest()]);
      expectInvalid(new Date());
      expectInvalid(new Map<string, unknown>());
      expectInvalid(new Set<string>());
      expectInvalid(/x/);
      expectInvalid(Symbol("x"));
      expectInvalid(() => 1);
    });

    it("rejects non-JSON-class instances carrying the exact fields", () => {
      class Request {}
      const value = Object.assign(new Request(), rawRequest());
      expectInvalid(value);
    });

    it("rejects wrong field types", () => {
      expectInvalid(rawRequest({ schema: 7 }));
      expectInvalid(rawRequest({ schema: null }));
      expectInvalid(rawRequest({ request_id: 123 }));
      expectInvalid(rawRequest({ work_ref: null }));
      expectInvalid(rawRequest({ work_ref: ["WS:AB"] }));
      expectInvalid(rawRequest({ expected_commit: { length: 40 } }));
      expectInvalid(rawRequest({ expected_adoption: 0 }));
      expectInvalid(rawRequest({ expected_adoption: false }));
      expectInvalid(rawRequest({ candidate_sha256: {} }));
      expectInvalid(rawRequest({ proposal_source: null }));
      expectInvalid(rawRequest({ proposal_source: "macro" }));
      expectInvalid(rawRequest({ proposal_source: [] }));
      expectInvalid(rawRequest({ base_source: undefined }));
      expectInvalid(rawRequest({ base_source: 0 }));
    });

    it("rejects wrong source-ref field types", () => {
      expectInvalid(rawRequest({ proposal_source: proposalSource({ repository: 5 }) }));
      expectInvalid(rawRequest({ proposal_source: proposalSource({ path: ["a.md"] }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ commit: null }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ content_sha256: true }) }));
    });
  });

  describe("closed key set", () => {
    it("rejects a missing each of the eight exact keys", () => {
      for (const key of Object.keys(rawRequest())) {
        const value = rawRequest();
        delete value[key];
        expectInvalid(value);
      }
    });

    it("rejects unknown extra fields, including authority-shaped ones", () => {
      expectInvalid(rawRequest({ grant: "ADOPT_PLAN" }));
      expectInvalid(rawRequest({ status: "approved" }));
      expectInvalid(rawRequest({ accepted: true }));
      expectInvalid(rawRequest({ actor: { principal_id: "p1" } }));
      expectInvalid(rawRequest({ snapshot: {} }));
      expectInvalid(rawRequest({ expected_snapshot_commit: COMMIT }));
      expectInvalid(rawRequest({ schema_version: 1 }));
    });

    it("rejects extra fields nested inside source refs", () => {
      expectInvalid(
        rawRequest({ proposal_source: proposalSource({ qualified: true }) }),
      );
      expectInvalid(
        rawRequest({ base_source: baseSource({ url: "https://evil/x.md" }) }),
      );
    });

    it("rejects symbol-keyed and non-enumerable extra properties", () => {
      const symbolic = rawRequest();
      (symbolic as Record<PropertyKey, unknown>)[Symbol("extra")] = 1;
      expectInvalid(symbolic);
      const hidden = rawRequest();
      Object.defineProperty(hidden, "grant", {
        value: "ADOPT_PLAN",
        enumerable: false,
        writable: true,
        configurable: true,
      });
      expectInvalid(hidden);
    });

    it("rejects a hostile throwing getter as one value-free invalid input", () => {
      const value = rawRequest();
      Object.defineProperty(value, "schema", {
        enumerable: true,
        get() {
          throw new RangeError("leak");
        },
      });
      const failure = expectInvalid(value);
      expect(failure.message).not.toContain("leak");
    });
  });

  describe("suffix newlines, whitespace and case games", () => {
    it("rejects trailing newline variants on scalar fields", () => {
      expectInvalid(rawRequest({ schema: SCHEMA + "\n" }));
      expectInvalid(rawRequest({ request_id: REQUEST_ID + "\n" }));
      expectInvalid(rawRequest({ work_ref: WORK_REF + "\r\n" }));
      expectInvalid(rawRequest({ expected_commit: COMMIT + "\n" }));
      expectInvalid(rawRequest({ candidate_sha256: SHA + "\r" }));
      expectInvalid(rawRequest({ expected_adoption: DEC_REF + "\n" }));
    });

    it("rejects leading/trailing whitespace and blank scalars", () => {
      expectInvalid(rawRequest({ request_id: " " + REQUEST_ID }));
      expectInvalid(rawRequest({ work_ref: "WS:PLAN-DOC " }));
      expectInvalid(rawRequest({ schema: " " + SCHEMA }));
    });

    it("rejects lowercased and mixed-case ref spellings", () => {
      expectInvalid(rawRequest({ work_ref: "ws:plan-doc" }), "ws:plan-doc");
      expectInvalid(rawRequest({ work_ref: "WS:plan-doc" }));
      expectInvalid(rawRequest({ expected_adoption: "dec:plan-adoption-ab" }));
      expectInvalid(
        rawRequest({ request_id: "mmos-project-adopt-" + COMMIT.toUpperCase() }),
      );
    });

    it("rejects lowercased schema string", () => {
      expectInvalid(rawRequest({ schema: SCHEMA.toUpperCase() }));
    });

    it("rejects whitespace inside kebab keys", () => {
      expectInvalid(rawRequest({ work_ref: "WS:PLAN DOC" }));
      expectInvalid(rawRequest({ expected_adoption: "DEC:PLAN ADOPTION" }));
    });
  });

  describe("work ref selection (foreign and malformed)", () => {
    it("rejects a well-formed foreign work ref", () => {
      expectInvalid(rawRequest({ work_ref: "WS:OTHER-DOC" }));
      expectInvalid(rawRequest({ work_ref: "WS:PLAN-DOCS" }));
    });

    it("rejects malformed work refs", () => {
      expectInvalid(rawRequest({ work_ref: "WS:A" }));
      expectInvalid(rawRequest({ work_ref: "WS:" }));
      expectInvalid(rawRequest({ work_ref: "PLAN-DOC" }));
      expectInvalid(rawRequest({ work_ref: "WS:PLAN--DOC" }));
      expectInvalid(rawRequest({ work_ref: "WS:-PLAN-DOC" }));
      expectInvalid(rawRequest({ work_ref: "WS:PLAN-DOC-" }));
      expectInvalid(rawRequest({ work_ref: "WS:" + "A".repeat(65) }));
      expectInvalid(rawRequest({ work_ref: "WS:PLAN\uD800DOC" }));
    });

    it("rejects an invalid expectedWorkRef even with a valid request", () => {
      expectInvalid(rawRequest(), "WS:A");
      expectInvalid(rawRequest(), "WS:");
      expectInvalid(rawRequest(), "plan-doc");
      expectInvalid(rawRequest(), "WS:PLAN-DOC-");
      expectInvalid(rawRequest(), "WS:\u0130PLAN");
      // A browser caller can lie about static types; hostile values still reject.
      expectInvalid(rawRequest(), 42 as unknown as string);
      expectInvalid(rawRequest(), null as unknown as string);
      // `undefined` would trip the helper's default parameter, so call directly.
      let caught: unknown;
      try {
        decodePlanAdoptionRequest(rawRequest(), undefined as unknown as string);
      } catch (error) {
        caught = error;
      }
      expect(caught).toBeInstanceOf(Error);
      expect((caught as Error).message).toBe(INVALID);
      expectInvalid(rawRequest(), ["WS:PLAN-DOC"] as unknown as string);
    });

    it("rejects a work_ref that disagrees with a valid expectedWorkRef", () => {
      expectInvalid(rawRequest({ work_ref: "WS:ZZZZ" }), "WS:ZZZ");
    });
  });

  describe("identifier and digest formats", () => {
    it("rejects malformed request ids", () => {
      expectInvalid(rawRequest({ request_id: "" }));
      expectInvalid(rawRequest({ request_id: "mmos-project-adoption-" + COMMIT }));
      expectInvalid(rawRequest({ request_id: "mmos-project-adopt-" + "g" + "0".repeat(39) }));
      expectInvalid(rawRequest({ request_id: "mmos-project-adopt-" + COMMIT.slice(0, 39) }));
      expectInvalid(rawRequest({ request_id: "mmos-project-adopt-" + COMMIT + "a" }));
      expectInvalid(rawRequest({ request_id: "mmos-project-adopt-" + COMMIT + "-extra" }));
      expectInvalid(rawRequest({ request_id: "MMOS-PROJECT-ADOPT-" + COMMIT }));
    });

    it("rejects branch labels and non-hex expected_commit values", () => {
      expectInvalid(rawRequest({ expected_commit: "" }));
      expectInvalid(rawRequest({ expected_commit: "main" }));
      expectInvalid(rawRequest({ expected_commit: "refs/heads/main" }));
      expectInvalid(rawRequest({ expected_commit: COMMIT.slice(0, 39) }));
      expectInvalid(rawRequest({ expected_commit: COMMIT + "a" }));
      expectInvalid(rawRequest({ expected_commit: COMMIT.toUpperCase() }));
      expectInvalid(rawRequest({ expected_commit: "0".repeat(40).replace("0", "z") }));
    });

    it("rejects malformed candidate_sha256 values", () => {
      expectInvalid(rawRequest({ candidate_sha256: "" }));
      expectInvalid(rawRequest({ candidate_sha256: SHA.slice(0, 63) }));
      expectInvalid(rawRequest({ candidate_sha256: SHA + "a" }));
      expectInvalid(rawRequest({ candidate_sha256: SHA.toUpperCase() }));
      expectInvalid(rawRequest({ candidate_sha256: "0".repeat(64).replace("0", "Z") }));
    });

    it("rejects malformed DEC refs for expected_adoption", () => {
      expectInvalid(rawRequest({ expected_adoption: "" }));
      expectInvalid(rawRequest({ expected_adoption: "DEC:" }));
      expectInvalid(rawRequest({ expected_adoption: "DEC:A" }));
      expectInvalid(rawRequest({ expected_adoption: "DEC:" + "A".repeat(129) }));
      expectInvalid(rawRequest({ expected_adoption: "DEC:PLAN-" }));
      expectInvalid(rawRequest({ expected_adoption: "DEC:-PLAN" }));
      expectInvalid(rawRequest({ expected_adoption: "WS:" + WORK_REF_KEY }));
      expectInvalid(rawRequest({ expected_adoption: DEC_REF + "-EXTRA/SLASH" }));
    });
  });

  describe("source reference path laws", () => {
    it("rejects URLs and absolute paths", () => {
      expectInvalid(rawRequest({ proposal_source: proposalSource({ path: "https://evil/x.md" }) }));
      expectInvalid(rawRequest({ proposal_source: proposalSource({ path: "http://evil/x.md" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ path: "file:///etc/passwd.md" }) }));
      expectInvalid(rawRequest({ proposal_source: proposalSource({ path: "/etc/plan.md" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ path: "/plan.md" }) }));
    });

    it("rejects traversal and dot segments", () => {
      expectInvalid(rawRequest({ base_source: baseSource({ path: "docs/../evil.md" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ path: "docs/./plan.md" }) }));
      expectInvalid(rawRequest({ proposal_source: proposalSource({ path: "../plan.md" }) }));
      expectInvalid(rawRequest({ proposal_source: proposalSource({ path: "a//b.md" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ path: "docs/" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ path: "." }) }));
      expectInvalid(rawRequest({ proposal_source: proposalSource({ path: ".." }) }));
    });

    it("rejects backslashes, control characters and surrogates", () => {
      expectInvalid(rawRequest({ proposal_source: proposalSource({ path: "docs\\plan.md" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ path: "C:\\temp\\plan.md" }) }));
      expectInvalid(rawRequest({ proposal_source: proposalSource({ path: "docs/\u0000plan.md" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ path: "docs/plan\n.md" }) }));
      expectInvalid(rawRequest({ proposal_source: proposalSource({ path: "docs/plan\r.md" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ path: "docs/plan\uD800.md" }) }));
    });

    it("rejects missing or wrong markdown suffix", () => {
      expectInvalid(rawRequest({ proposal_source: proposalSource({ path: "agentos/proposals/plan" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ path: "docs/plan.markdown" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ path: "docs/plan.MD" }) }));
      expectInvalid(rawRequest({ proposal_source: proposalSource({ path: "" }) }));
    });

    it("rejects over-long paths and accepts the 512-char boundary", () => {
      const prefix = "docs/plans/";
      const suffix = ".md";
      const exact = prefix + "x".repeat(512 - prefix.length - suffix.length) + suffix;
      expect(exact.length).toBe(512);
      expectValid(rawRequest({ base_source: baseSource({ path: exact }) }));
      expectInvalid(
        rawRequest({ base_source: baseSource({ path: prefix + "x".repeat(513) + suffix }) }),
      );
    });

    it("rejects malformed commit and digest fields inside source refs", () => {
      expectInvalid(rawRequest({ proposal_source: proposalSource({ commit: COMMIT.toUpperCase() }) }));
      expectInvalid(rawRequest({ proposal_source: proposalSource({ commit: "main" }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ commit: COMMIT.slice(1) }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ content_sha256: SHA.toUpperCase() }) }));
      expectInvalid(rawRequest({ base_source: baseSource({ content_sha256: "sha256:" + SHA }) }));
    });

    it("enforces the closed macro WS-record path rule (case-insensitive prefix, exact path)", () => {
      expectInvalid(
        rawRequest({ base_source: baseSource({ repository: MACRO, path: "agentos/workstreams/WS-OTHER.md" }) }),
      );
      expectInvalid(
        rawRequest({ proposal_source: proposalSource({ path: "agentos/workstreams/WS-OTHER.md" }) }),
      );
      expectInvalid(
        rawRequest({ base_source: baseSource({ repository: MACRO, path: "agentos/Workstreams/WS-" + WORK_REF_KEY + ".md" }) }),
      );
      expectInvalid(
        rawRequest({ proposal_source: proposalSource({ path: "AGENTOS/WORKSTREAMS/WS-" + WORK_REF_KEY + ".md" }) }),
      );
    });

    it("rejects non-string surrogate scalars anywhere in the request", () => {
      expectInvalid(rawRequest({ request_id: "mmos-project-adopt-\uD800" + "0".repeat(40 - 1) }));
      expectInvalid(rawRequest({ candidate_sha256: "\uDFFF" + SHA.slice(1) }));
    });
  });

  describe("detachment", () => {
    it("returns detached scalars: mutating input afterwards changes nothing", () => {
      const value = rawRequest();
      const source = value.proposal_source as Record<string, unknown>;
      const decoded = decodePlanAdoptionRequest(value, WORK_REF);
      value["request_id"] = "mmos-project-adopt-" + "f".repeat(40);
      source["path"] = "agentos/mutated.md";
      (value["base_source"] as Record<string, unknown>)["repository"] = "acme/mutated";
      expect(decoded.request_id).toBe(REQUEST_ID);
      expect(decoded.proposal_source.path).toBe(PROPOSAL_PATH);
      expect(decoded.base_source.repository).toBe(MASTERMIND);
    });

    it("returns detached objects: mutating output changes neither input nor a second decode", () => {
      const value = rawRequest();
      const decoded = decodePlanAdoptionRequest(value, WORK_REF);
      const mutation = decoded.proposal_source as { path: string };
      mutation.path = "agentos/mutated.md";
      (decoded as { work_ref: string }).work_ref = "WS:MUTATED";
      expect((value["proposal_source"] as Record<string, unknown>)["path"]).toBe(PROPOSAL_PATH);
      expect(value["work_ref"]).toBe(WORK_REF);
      const second = decodePlanAdoptionRequest(rawRequest(), WORK_REF);
      expect(second.proposal_source.path).toBe(PROPOSAL_PATH);
      expect(second.proposal_source).not.toBe(decoded.base_source);
      expect(second).not.toBe(decoded);
    });

    it("builds fresh nested references per decode call", () => {
      const value = rawRequest();
      const first = decodePlanAdoptionRequest(value, WORK_REF);
      const second = decodePlanAdoptionRequest(value, WORK_REF);
      expect(first.proposal_source).not.toBe(second.proposal_source);
      expect(first.base_source).not.toBe(first.proposal_source);
      expect(Object.keys(first)).toEqual(Object.keys(second));
    });
  });

  describe("prototype discipline", () => {
    it("accepts Object.prototype and null prototypes only", () => {
      const normal = rawRequest();
      expect(Object.getPrototypeOf(normal)).toBe(Object.prototype);
      expectValid(normal);
      const bare = Object.assign(Object.create(null), rawRequest());
      expectValid(bare);
    });

    it("rejects exotic prototypes carrying the exact fields", () => {
      const alien = Object.assign(Object.create({ evil: true }), rawRequest());
      expectInvalid(alien);
      const deeper = Object.assign(
        Object.create(Object.create(Object.prototype, {}), {}),
        rawRequest(),
      );
      expectInvalid(deeper);
    });

    it("rejects arrays even when they carry request-like members", () => {
      const array: unknown[] = [];
      Object.assign(array, rawRequest());
      expect(Object.keys(array)).toEqual(Object.keys(rawRequest()));
      expectInvalid(array);
    });
  });
});
