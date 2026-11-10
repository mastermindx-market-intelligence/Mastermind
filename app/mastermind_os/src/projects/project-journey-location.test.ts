import { describe, expect, it } from "vitest";
import {
  CREATE_REQUEST_ID_HEX_CHARS,
  MAX_WORK_REF_KEY_CHARS,
  MIN_WORK_REF_KEY_CHARS,
  PLANNING_OPERATION_ID_HEX_CHARS,
  PLANNING_OPERATION_ID_PREFIX,
  PROJECT_JOURNEY_CREATE_REQUEST_KEY,
  PROJECT_JOURNEY_FLAG_KEY,
  PROJECT_JOURNEY_JOB_KEY,
  PROJECT_JOURNEY_KEYS,
  PROJECT_JOURNEY_PLANNING_OPERATION_KEY,
  PROJECT_JOURNEY_SELECTION_INVALID,
  PROJECT_JOURNEY_WORK_REF_KEY,
  commitProjectJourneySelection,
  projectJourneyUrl,
  readProjectJourneyLocation,
} from "./project-journey-location";
import { ORIGINAL_OPERATION_ID_PREFIXES } from "../planning/plan-adoption-status";
import type { ProjectJourneySelection } from "./ProjectPlanningJourney";

/** 40-char lowercase hex CREATE id built from the real producer prefix. */
const CREATE = `${ORIGINAL_OPERATION_ID_PREFIXES.publish_project_proposal}${"ab".repeat(CREATE_REQUEST_ID_HEX_CHARS / 2)}`;
const WORK_REF = "WS:AB-01";
/** Exact issued planning prefix +40 lowercase hex characters. */
const OP = PLANNING_OPERATION_ID_PREFIX+"cd".repeat(PLANNING_OPERATION_ID_HEX_CHARS / 2);
const JOB = "JOB-planning.001:alpha";
const FULL: ProjectJourneySelection = {
  createRequestId: CREATE,
  workRef: WORK_REF,
  planningOperationKey: OP,
  jobId: JOB,
};
const PARTIAL: ProjectJourneySelection = {
  createRequestId: CREATE,
  workRef: WORK_REF,
  planningOperationKey: null,
  jobId: null,
};
const ORIGIN_PATH = "https://os.example.com/os/";
const qs = (pairs: [string, string][]): string => new URLSearchParams(pairs).toString();
const queryOf = (selection: ProjectJourneySelection): string =>
  qs([
    [PROJECT_JOURNEY_FLAG_KEY, "1"],
    [PROJECT_JOURNEY_CREATE_REQUEST_KEY, selection.createRequestId],
    ...(selection.workRef !== null ? ([[PROJECT_JOURNEY_WORK_REF_KEY, selection.workRef]] as [string, string][]) : []),
    ...(selection.planningOperationKey !== null ? ([[PROJECT_JOURNEY_PLANNING_OPERATION_KEY, selection.planningOperationKey]] as [string, string][]) : []),
    ...(selection.jobId !== null ? ([[PROJECT_JOURNEY_JOB_KEY, selection.jobId]] as [string, string][]) : []),
  ]);

const INVALID: ProjectJourneyReadResultShape = { valid: false, open: false, selection: null };
type ProjectJourneyReadResultShape = ReturnType<typeof readProjectJourneyLocation>;

const asSelection = (value: unknown): ProjectJourneySelection => value as ProjectJourneySelection;

describe("readProjectJourneyLocation", () => {
  it("closes malformed locations without throwing or leaking input", () => {
    expect(readProjectJourneyLocation("INVALID_LOCATION_ONLY")).toEqual(INVALID);
  });
  it("gives a fixed writer refusal for malformed locations", () => {
    expect(() => projectJourneyUrl("INVALID_LOCATION_ONLY", FULL)).toThrow(PROJECT_JOURNEY_SELECTION_INVALID);
  });

  it("reads absence as valid closed with no selection, ignoring unrelated keys", () => {
    expect(readProjectJourneyLocation(`${ORIGIN_PATH}`)).toEqual({
      valid: true,
      open: false,
      selection: null,
    });
    expect(
      readProjectJourneyLocation(
        `${ORIGIN_PATH}?work_ref=WS%3AALPHA&root_job_id=JOB-A&goal=classified&profile=internal&prompt=leak-me`,
      ),
    ).toEqual({ valid: true, open: false, selection: null });
  });

  it("reads flag-only state as valid open blank", () => {
    expect(readProjectJourneyLocation(`${ORIGIN_PATH}?${PROJECT_JOURNEY_FLAG_KEY}=1`)).toEqual({
      valid: true,
      open: true,
      selection: null,
    });
  });

  it("accepts a bare query string as a read-only location", () => {
    expect(readProjectJourneyLocation(`?${PROJECT_JOURNEY_FLAG_KEY}=1`)).toEqual({
      valid: true,
      open: true,
      selection: null,
    });
  });

  it("reopens a selection from ids even when the flag key is absent", () => {
    const url = `${ORIGIN_PATH}?${qs([[PROJECT_JOURNEY_CREATE_REQUEST_KEY, CREATE]])}`;
    expect(readProjectJourneyLocation(url)).toEqual({
      valid: true,
      open: true,
      selection: { createRequestId: CREATE, workRef: null, planningOperationKey: null, jobId: null },
    });
  });

  it("roundtrips a committed selection, including partials", () => {
    for (const selection of [FULL, PARTIAL, { ...FULL, workRef: null, planningOperationKey: null, jobId: null } as ProjectJourneySelection]) {
      const url = projectJourneyUrl(ORIGIN_PATH, selection);
      const read = readProjectJourneyLocation(url);
      expect(read.valid).toBe(true);
      expect(read.open).toBe(true);
      expect(read.selection).toEqual(selection);
    }
  });

  it("accepts a URL object input", () => {
    expect(readProjectJourneyLocation(new URL(`${ORIGIN_PATH}?${PROJECT_JOURNEY_FLAG_KEY}=1`))).toEqual({
      valid: true,
      open: true,
      selection: null,
    });
  });

  it("rejects a bad flag value", () => {
    for (const value of ["0", "", "true", " 1", "1 ", "01"]) {
      const url = `${ORIGIN_PATH}?${qs([[PROJECT_JOURNEY_FLAG_KEY, value]])}`;
      expect(readProjectJourneyLocation(url)).toEqual(INVALID);
    }
  });

  it("rejects duplicate owned keys", () => {
    for (const key of PROJECT_JOURNEY_KEYS) {
      const url = `${ORIGIN_PATH}?${qs([
        [PROJECT_JOURNEY_FLAG_KEY, "1"],
        [PROJECT_JOURNEY_CREATE_REQUEST_KEY, CREATE],
        [key, "x"],
        [key, "x"],
      ])}`;
      expect(readProjectJourneyLocation(url)).toEqual(INVALID);
    }
  });

  it("rejects invalid CREATE ids", () => {
    for (const value of [
      `nope-${"ab".repeat(20)}`,
      CREATE.slice(0, -1),
      `${CREATE}a`,
      CREATE.toUpperCase(),
      `${ORIGINAL_OPERATION_ID_PREFIXES.publish_project_proposal}${"g0".repeat(20)}`,
    ]) {
      const url = `${ORIGIN_PATH}?${qs([[PROJECT_JOURNEY_CREATE_REQUEST_KEY, value]])}`;
      expect(readProjectJourneyLocation(url)).toEqual(INVALID);
    }
  });

  it("rejects invalid work refs at both bounds and in shape", () => {
    for (const value of [
      "AB-01",
      "ws:AB-01",
      "WS:A",
      `WS:${"A".repeat(MAX_WORK_REF_KEY_CHARS + 1)}`,
      "WS:-AB",
      "WS:AB-",
      "WS:AB--CD",
      "WS:AB CD",
      "WS:ab-01",
    ]) {
      const url = `${ORIGIN_PATH}?${qs([[PROJECT_JOURNEY_WORK_REF_KEY, value]])}`;
      expect(readProjectJourneyLocation(url)).toEqual(INVALID);
    }
  });

  it("accepts work refs at both suffix bounds next to their CREATE id", () => {
    for (const value of [`WS:${"A".repeat(MIN_WORK_REF_KEY_CHARS)}`, `WS:${"A".repeat(MAX_WORK_REF_KEY_CHARS)}`]) {
      const url = `${ORIGIN_PATH}?${qs([
        [PROJECT_JOURNEY_CREATE_REQUEST_KEY, CREATE],
        [PROJECT_JOURNEY_WORK_REF_KEY, value],
      ])}`;
      expect(readProjectJourneyLocation(url)).toEqual({
        valid: true,
        open: true,
        selection: { createRequestId: CREATE, workRef: value, planningOperationKey: null, jobId: null },
      });
    }
  });

  it("rejects invalid planning operation ids", () => {
    for (const value of [OP.slice(0, -1), `${OP}a`, OP.toUpperCase()]) {
      const url = `${ORIGIN_PATH}?${qs([[PROJECT_JOURNEY_PLANNING_OPERATION_KEY, value]])}`;
      expect(readProjectJourneyLocation(url)).toEqual(INVALID);
    }
  });

  it("rejects invalid planning job ids", () => {
    for (const value of [".JOB-1", "-JOB-1", `${"A".repeat(129)}`, "JOB 1", "JOB$1", ""]) {
      const url = `${ORIGIN_PATH}?${qs([[PROJECT_JOURNEY_JOB_KEY, value]])}`;
      expect(readProjectJourneyLocation(url)).toEqual(INVALID);
    }
  });

  it("rejects ids without the anchoring CREATE id", () => {
    for (const [key, value] of [
      [PROJECT_JOURNEY_WORK_REF_KEY, WORK_REF],
      [PROJECT_JOURNEY_PLANNING_OPERATION_KEY, OP],
      [PROJECT_JOURNEY_JOB_KEY, JOB],
    ] as [string, string][]) {
      const url = `${ORIGIN_PATH}?${qs([[key, value]])}`;
      expect(readProjectJourneyLocation(url)).toEqual(INVALID);
    }
  });

  it("rejects mixed dependencies", () => {
    const withOpNoWorkRef = `${ORIGIN_PATH}?${qs([
      [PROJECT_JOURNEY_CREATE_REQUEST_KEY, CREATE],
      [PROJECT_JOURNEY_PLANNING_OPERATION_KEY, OP],
    ])}`;
    expect(readProjectJourneyLocation(withOpNoWorkRef)).toEqual(INVALID);
    const withJobNoOp = `${ORIGIN_PATH}?${qs([
      [PROJECT_JOURNEY_CREATE_REQUEST_KEY, CREATE],
      [PROJECT_JOURNEY_WORK_REF_KEY, WORK_REF],
      [PROJECT_JOURNEY_JOB_KEY, JOB],
    ])}`;
    expect(readProjectJourneyLocation(withJobNoOp)).toEqual(INVALID);
  });

  it("never reads journey state out of the hash", () => {
    expect(readProjectJourneyLocation(`${ORIGIN_PATH}#?${PROJECT_JOURNEY_FLAG_KEY}=1`)).toEqual({
      valid: true,
      open: false,
      selection: null,
    });
  });

  it("rejects empty owned values", () => {
    const url = `${ORIGIN_PATH}?${PROJECT_JOURNEY_CREATE_REQUEST_KEY}=`;
    expect(readProjectJourneyLocation(url)).toEqual(INVALID);
  });
});

describe("projectJourneyUrl", () => {
  it("writes exactly the owned keys in fixed order and preserves origin/path", () => {
    const out = projectJourneyUrl(ORIGIN_PATH, FULL);
    expect(out.startsWith(`${ORIGIN_PATH}?${PROJECT_JOURNEY_FLAG_KEY}=1&`)).toBe(true);
    expect(out.endsWith(`?${queryOf(FULL)}`)).toBe(true);
    expect(new URL(out).hash).toBe("");
  });

  it("strips private canaries, legacy Mission identity and hash", () => {
    const dirty = `${ORIGIN_PATH}?work_ref=WS%3ASECRET&root_job_id=JOB-SECRET&goal=classified&profile=internal&prompt=leak-me&x=1#legacy-anchor`;
    const out = projectJourneyUrl(dirty, FULL);
    expect(out).not.toContain("SECRET");
    expect(out).not.toContain("classified");
    expect(out).not.toContain("leak-me");
    expect(out).not.toContain("legacy-anchor");
    expect(new URL(out).search).toBe(`?${queryOf(FULL)}`);
    expect(out.startsWith(ORIGIN_PATH)).toBe(true);
  });

  it("commits null as the clean closed URL", () => {
    const dirty = `${ORIGIN_PATH}?${queryOf(FULL)}&work_ref=WS%3AOLD`;
    const out = projectJourneyUrl(dirty, null);
    expect(out).toBe(ORIGIN_PATH);
    expect(readProjectJourneyLocation(out)).toEqual({ valid: true, open: false, selection: null });
  });

  it("preserves origin and path for ports, subpaths and the native tauri origin", () => {
    expect(projectJourneyUrl("https://os.example.com:8443/os/index.html", FULL).startsWith("https://os.example.com:8443/os/index.html")).toBe(true);
    expect(projectJourneyUrl("tauri://localhost/os/index.html", FULL).startsWith("tauri://localhost/os/index.html")).toBe(true);
    const tauriOut = projectJourneyUrl("tauri://localhost/os/index.html?x=1#h", PARTIAL);
    expect(tauriOut).toBe(`tauri://localhost/os/index.html?${queryOf(PARTIAL)}`);
  });

  it("never propagates URL credentials", () => {
    const out = projectJourneyUrl("https://user:pass@os.example.com/os/", PARTIAL);
    expect(out.startsWith(`${ORIGIN_PATH}?`)).toBe(true);
    expect(out).not.toContain("user:pass");
  });

  it("accepts URL object input", () => {
    expect(projectJourneyUrl(new URL(ORIGIN_PATH), PARTIAL)).toBe(`${ORIGIN_PATH}?${queryOf(PARTIAL)}`);
  });

  it("never writes nullable fields as the string 'null'", () => {
    const out = projectJourneyUrl(ORIGIN_PATH, { ...FULL, workRef: null, planningOperationKey: null, jobId: null });
    expect(out).not.toContain("null");
    expect(new URL(out).searchParams.get(PROJECT_JOURNEY_WORK_REF_KEY)).toBeNull();
    expect(new URL(out).searchParams.get(PROJECT_JOURNEY_PLANNING_OPERATION_KEY)).toBeNull();
    expect(new URL(out).searchParams.get(PROJECT_JOURNEY_JOB_KEY)).toBeNull();
  });

  it("refuses non-plain selections, accessors, extras and symbol keys without echoing values", () => {
    const cases: unknown[] = [
      undefined,
      "text",
      42,
      [],
      new Date(),
      Object.assign(Object.create({ evil: true }), FULL),
      { ...FULL, extra: "x" },
      { createRequestId: CREATE, workRef: WORK_REF },
      { ...FULL, [Symbol("s")]: 1 },
      { ...FULL, workRef: "WS:EVIL!!CANARY" },
      { ...FULL, workRef: "null" },
      { ...FULL, planningOperationKey: "null" },
      { ...FULL, jobId: 123 },
      { ...FULL, createRequestId: null },
      { ...FULL, createRequestId: `nope-${"ab".repeat(20)}` },
      { ...FULL, workRef: null },
      { createRequestId: CREATE, workRef: WORK_REF, planningOperationKey: OP, jobId: null, planningOperationKey2: OP },
    ];
    for (const selection of cases) {
      expect(() => projectJourneyUrl(ORIGIN_PATH, asSelection(selection))).toThrowError(
        PROJECT_JOURNEY_SELECTION_INVALID,
      );
    }
  });

  it("refuses accessor properties without ever invoking the getter", () => {
    const accessor = { ...FULL };
    Object.defineProperty(accessor, "workRef", {
      enumerable: true,
      get: () => {
        throw new Error("GETTER_INVOKED WS:SECRET");
      },
    });
    let message = "";
    try {
      projectJourneyUrl(ORIGIN_PATH, asSelection(accessor));
    } catch (error) {
      message = error instanceof Error ? error.message : "";
    }
    expect(message).toBe(PROJECT_JOURNEY_SELECTION_INVALID);
    expect(message).not.toContain("SECRET");
  });

  it("refuses a non-enumerable extra own key", () => {
    const extra = { ...FULL };
    Object.defineProperty(extra, "shadow", { value: "x", enumerable: false });
    expect(() => projectJourneyUrl(ORIGIN_PATH, asSelection(extra))).toThrowError(
      PROJECT_JOURNEY_SELECTION_INVALID,
    );
  });

  it("accepts a null-prototype plain selection", () => {
    const bare = Object.assign(Object.create(null), FULL);
    const out = projectJourneyUrl(ORIGIN_PATH, asSelection(bare));
    expect(out).toBe(`${ORIGIN_PATH}?${queryOf(FULL)}`);
  });

  it("throws TypeError for writer input without an absolute URL", () => {
    expect(() => projectJourneyUrl(`?${PROJECT_JOURNEY_FLAG_KEY}=1`, FULL)).toThrow(TypeError);
    expect(() => projectJourneyUrl("not-a-url", FULL)).toThrow(TypeError);
  });
});

describe("commitProjectJourneySelection", () => {
  const makeHistory = () => {
    const calls: unknown[][] = [];
    return {
      calls,
      history: {
        replaceState: (...args: unknown[]) => {
          calls.push(args);
          return undefined;
        },
      } as Pick<History, "replaceState">,
    };
  };

  it("writes the safe URL synchronously before invoking the callback, in exact order", () => {
    const { calls, history } = makeHistory();
    const seen: (ProjectJourneySelection | null)[] = [];
    commitProjectJourneySelection(ORIGIN_PATH, PARTIAL, history, (selection) => {
      seen.push(selection);
    });
    expect(calls.map((call) => call[0])).toEqual([null]);
    expect(calls[0][2]).toBe(`${ORIGIN_PATH}?${queryOf(PARTIAL)}`);
    expect(seen).toEqual([PARTIAL]);
    expect(seen[0]).not.toBe(PARTIAL);
    expect(readProjectJourneyLocation(calls[0][2] as string)).toEqual({
      valid: true,
      open: true,
      selection: PARTIAL,
    });
  });

  it("commits null and reports null after the clean URL is durable", () => {
    const { calls, history } = makeHistory();
    const seen: (ProjectJourneySelection | null)[] = [];
    commitProjectJourneySelection(`${ORIGIN_PATH}?${queryOf(FULL)}`, null, history, (selection) => {
      seen.push(selection);
    });
    expect(calls[0][2]).toBe(ORIGIN_PATH);
    expect(seen).toEqual([null]);
  });

  it("suppresses the callback when replaceState throws", () => {
    const failure = new Error("REPLACE_STATE_DENIED");
    const seen: (ProjectJourneySelection | null)[] = [];
    const history = {
      replaceState: () => {
        throw failure;
      },
    } as Pick<History, "replaceState">;
    expect(() => commitProjectJourneySelection(ORIGIN_PATH, FULL, history, (selection) => seen.push(selection))).toThrowError(failure);
    expect(seen).toEqual([]);
  });

  it("writes nothing and calls nothing when the selection is invalid", () => {
    const { calls, history } = makeHistory();
    const seen: (ProjectJourneySelection | null)[] = [];
    const bad = asSelection({ ...FULL, workRef: "WS:EVIL!!CANARY" });
    expect(() => commitProjectJourneySelection(ORIGIN_PATH, bad, history, (selection) => seen.push(selection))).toThrowError(
      PROJECT_JOURNEY_SELECTION_INVALID,
    );
    expect(calls).toEqual([]);
    expect(seen).toEqual([]);
  });
});
