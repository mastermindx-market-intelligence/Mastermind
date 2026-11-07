/**
 * Vitest suite for the bounded saved-conversation search composer.
 *
 * These tests exercise the module purely through its exported surface and
 * stub owner objects: no real Session Bridge owner, no real port, no host
 * runtime. They verify the bounded read-composition contract: shape
 * validation, fencing, budgeting, literal matching, digest binding and
 * fail-closed behavior. Cryptographic qualification itself stays inside the
 * existing port and is NOT re-tested here; the parent repository's vitest
 * run and tsc remain the final gate.
 */

import { describe, expect, it } from "vitest";
import {
  decodeSavedConversationPage,
  readSavedConversationSource,
  searchSavedConversations,
} from "./saved-conversations";
import type {
  SavedConversationReference,
  SavedConversationSearchOwner,
  SavedConversationSearchResult,
} from "./saved-conversations";
import type { OperationPointer } from "../orchestration/operation-controller";

const WORK = "WS:DISCOVERY";
const OTHER_WORK = "WS:OTHERPROJECT";
const HEX = (n: number): string => n.toString(16).padStart(64, "0");

const TEXT_MATCH =
  "The scheduled migration completed and the deployment is green. Next step is to verify the rollback window.";
const TEXT_OTHER =
  "The deployment stayed red and the migration was rolled back before dawn.";
const TEXT_UNICODE =
  "Deploy完成 — café rollout 🌟 is green across all regions. 🌟 verify the rollback window next.";
const PRIVATE_NEXT_STEP = "PRIVATE nextStep must never surface";
const DIGEST_MATCH =
  "05d9fcdf98dea67b672c1897f5f78387c01591bdf1fe9ab9c51f28c8e0461a3f";
const DIGEST_UNICODE =
  "ba1163c973a57ba433e998e29ada8a184f02f6366335e1b46f60701edf8ab0cc";

/** One owner-shaped saved-reference row (10 snake_case fields). */
function row(
  index: number,
  overrides: Record<string, unknown> = {},
  workRef: string = WORK,
  rootJobId?: string,
): Record<string, unknown> {
  return {
    read_ref: "session-reply-" + HEX(index),
    operation_key: "session-continue-" + HEX(index + 100),
    request_ref: "request-" + index,
    request_event_id: 40 + index,
    request_revision: HEX(index + 200),
    requested_at: "2026-11-03T10:20:30.000Z",
    work_ref: workRef,
    root_job_id: rootJobId === undefined ? "JOB-" + (1000 + index) : rootJobId,
    target_ref: "fabric_attempt:" + HEX(index + 300),
    reference_only: true,
    ...overrides,
  };
}

interface PageOptions {
  status?: "COMPLETE" | "PARTIAL";
  nextCursor?: string | null;
  highWater?: number;
}

/** Exact existing OS envelope: 7 keys outside, 5 keys in data. */
function envelope(
  rows: Record<string, unknown>[],
  options: PageOptions = {},
): {
  schema: string;
  operation: string;
  ok: boolean;
  effect: string;
  operation_key: null;
  error: null;
  data: {
    schema: string;
    status: string;
    references: Record<string, unknown>[];
    next_cursor: string | null;
    high_water: number;
  };
} {
  const status = options.status ?? (rows.length > 0 ? "COMPLETE" : "PARTIAL");
  const nextCursor =
    options.nextCursor !== undefined
      ? options.nextCursor
      : status === "PARTIAL"
        ? "Y3Vyc29yLTA"
        : null;
  return {
    schema: "mastermind.os.executive.session_result.v1",
    operation: "references",
    ok: true,
    effect: "NONE",
    operation_key: null,
    error: null,
    data: {
      schema: "mastermind.session_reply_references.v1",
      status,
      references: rows,
      next_cursor: nextCursor,
      high_water: options.highWater ?? 100,
    },
  };
}

function qualifiedAnswer(
  reference: Record<string, unknown>,
  text: string,
): { receipt: Record<string, unknown>; answer: Record<string, unknown> } {
  return {
    receipt: {
      operationKey: reference.operation_key,
      kind: "message",
      targetKey: reference.target_ref,
      disposition: "accepted",
    },
    answer: {
      text,
      nextStep: PRIVATE_NEXT_STEP,
      readRef: reference.read_ref,
      parentConsumed: false,
    },
  };
}

interface OwnerTrace {
  referenceReads: Array<{ workRef: string; pageSize: number; cursor?: string }>;
  answerPointers: OperationPointer[];
}

function makeOwner(options: {
  page?: unknown;
  answers?: Map<string, unknown>;
  pageError?: Error;
  answerErrors?: Map<string, Error>;
  context?: () => { principalScope: string; generation: string } | null;
  authGeneration?: () => number;
  afterPage?: () => void;
  beforeAnswer?: (pointer: OperationPointer) => void;
}): SavedConversationSearchOwner & { trace: OwnerTrace } {
  const trace: OwnerTrace = { referenceReads: [], answerPointers: [] };
  const context =
    options.context ??
    (() => ({ principalScope: "principal://mastermind/discovery", generation: "gen-1" }));
  const authGeneration = options.authGeneration ?? (() => 7);
  const readReferences = async (request: {
    workRef: string;
    pageSize: number;
    cursor?: string;
    signal: AbortSignal;
  }): Promise<unknown> => {
    trace.referenceReads.push({
      workRef: request.workRef,
      pageSize: request.pageSize,
      ...(request.cursor === undefined ? {} : { cursor: request.cursor }),
    });
    if (options.pageError !== undefined) throw options.pageError;
    if (options.afterPage !== undefined) options.afterPage();
    return options.page;
  };
  const readAnswer = async (
    pointer: OperationPointer,
    _signal: AbortSignal,
  ): Promise<unknown> => {
    trace.answerPointers.push(pointer);
    if (options.beforeAnswer !== undefined) options.beforeAnswer(pointer);
    const key = pointer.operationKey + "|" + pointer.targetKey;
    const error = options.answerErrors?.get(key);
    if (error !== undefined) throw error;
    return options.answers?.get(key);
  };
  const owner = {
    context,
    authGeneration,
    readReferences,
    readAnswer,
    trace,
  } as SavedConversationSearchOwner & { trace: OwnerTrace };
  return owner;
}

function freshSignal(): AbortSignal {
  return new AbortController().signal;
}

function searchRequest(
  extra: {
    workRef?: string;
    query?: string;
    cursor?: string;
    expectedHighWater?: number;
    signal?: AbortSignal;
  } = {},
): {
  workRef: string;
  query: string;
  expectedHighWater?: number;
  cursor?: string;
  signal: AbortSignal;
} {
  return {
    workRef: WORK,
    query: "green",
    signal: freshSignal(),
    ...extra,
  };
}

describe("decodeSavedConversationPage", () => {
  it("accepts a valid COMPLETE page and returns frozen detached copies", () => {
    const raw = envelope([row(1), row(2)]);
    const page = decodeSavedConversationPage(raw, WORK);
    expect(page).not.toBeNull();
    expect(page?.references).toHaveLength(2);
    expect(page?.nextCursor).toBeNull();
    expect(page?.highWater).toBe(100);
    expect(Object.isFrozen(page)).toBe(true);
    expect(Object.isFrozen(page?.references)).toBe(true);
    expect(Object.isFrozen(page?.references[0])).toBe(true);
    expect(page?.references[0]?.read_ref).toBe(row(1).read_ref);
  });

  it("accepts up to four rows and rejects five", () => {
    expect(
      decodeSavedConversationPage(envelope([row(1), row(2), row(3), row(4)]), WORK),
    ).not.toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1), row(2), row(3), row(4), row(5)]),
        WORK,
      ),
    ).toBeNull();
  });

  it("rejects wrong work_ref and foreign roots never leak partial data", () => {
    expect(decodeSavedConversationPage(envelope([row(1)]), OTHER_WORK)).toBeNull();
  });

  it("rejects envelope and data key-count drift", () => {
    const eightKeys = envelope([row(1)]);
    (eightKeys as Record<string, unknown>).surprise = 1;
    expect(decodeSavedConversationPage(eightKeys, WORK)).toBeNull();
    const sixDataKeys = envelope([row(1)]);
    (sixDataKeys.data as Record<string, unknown>).surprise = 1;
    expect(decodeSavedConversationPage(sixDataKeys, WORK)).toBeNull();
  });

  it("rejects header field drift", () => {
    const wrongSchema = envelope([row(1)]);
    wrongSchema.schema = "mastermind.os.executive.session_result.v2";
    expect(decodeSavedConversationPage(wrongSchema, WORK)).toBeNull();
    const wrongOperation = envelope([row(1)]);
    wrongOperation.operation = "history";
    expect(decodeSavedConversationPage(wrongOperation, WORK)).toBeNull();
    const notOk = envelope([row(1)]);
    notOk.ok = false;
    expect(decodeSavedConversationPage(notOk, WORK)).toBeNull();
    const wrongEffect = envelope([row(1)]);
    wrongEffect.effect = "READ";
    expect(decodeSavedConversationPage(wrongEffect, WORK)).toBeNull();
    const withKey = envelope([row(1)]);
    (withKey as Record<string, unknown>).operation_key = "session-continue-" + HEX(1);
    expect(decodeSavedConversationPage(withKey, WORK)).toBeNull();
    const withError = envelope([row(1)]);
    (withError as Record<string, unknown>).error = "boom";
    expect(decodeSavedConversationPage(withError, WORK)).toBeNull();
  });

  it("rejects a getter row and never invokes the getter", () => {
    let getterCalls = 0;
    const raw = envelope([row(1)]);
    const rawRow = raw.data.references[0];
    if (rawRow !== undefined) {
      Object.defineProperty(rawRow, "read_ref", {
        enumerable: true,
        configurable: true,
        get() {
          getterCalls += 1;
          return "session-reply-" + HEX(9);
        },
      });
    }
    expect(getterCalls).toBe(0);
    expect(decodeSavedConversationPage(raw, WORK)).toBeNull();
    expect(getterCalls).toBe(0);
  });

  it("rejects extra keys, symbol keys, toJSON slots and inherited rows", () => {
    const eleven = envelope([row(1)]);
    const elevenRow = eleven.data.references[0];
    if (elevenRow !== undefined) {
      (elevenRow as Record<string, unknown>).toJSON = () => "{}";
    }
    expect(decodeSavedConversationPage(eleven, WORK)).toBeNull();
    const symbolRow = envelope([row(1)]);
    const symbolTarget = symbolRow.data.references[0];
    const marker = Symbol("x");
    if (symbolTarget !== undefined) {
      Object.defineProperty(symbolTarget, marker, {
        value: 1,
        enumerable: false,
      });
    }
    expect(decodeSavedConversationPage(symbolRow, WORK)).toBeNull();
    const inherited = envelope([
      Object.create({ read_ref: "session-reply-" + HEX(1) }),
    ]);
    expect(decodeSavedConversationPage(inherited, WORK)).toBeNull();
    const extraIndex = envelope([row(1)]);
    const references = extraIndex.data.references;
    Object.defineProperty(references, "extra", {
      value: row(2),
      enumerable: false,
    });
    expect(decodeSavedConversationPage(extraIndex, WORK)).toBeNull();
  });

  it("rejects duplicate read_ref, operation and event identities", () => {
    expect(decodeSavedConversationPage(envelope([row(1), row(1)]), WORK)).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1), row(2, { request_event_id: 41 })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1), row(2, { read_ref: row(1).read_ref })]),
        WORK,
      ),
    ).toBeNull();
  });

  it("enforces the event-id watermark and expectedHighWater", () => {
    expect(decodeSavedConversationPage(envelope([row(1)], { highWater: 40 }), WORK)).toBeNull();
    expect(decodeSavedConversationPage(envelope([row(1)]), WORK, 99)).toBeNull();
    expect(decodeSavedConversationPage(envelope([row(1)]), WORK, 100)).not.toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1)], { status: "PARTIAL", nextCursor: "c1" }),
        WORK,
        100,
      ),
    ).not.toBeNull();
  });

  it("requires real-calendar UTC stamps with Z or +00:00 only", () => {
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { requested_at: "2026-02-30T00:00:00Z" })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { requested_at: "2026-13-01T00:00:00Z" })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { requested_at: "2026-11-03T24:00:00Z" })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { requested_at: "2026-11-03T10:20:60Z" })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { requested_at: "2026-11-03T10:20:30+02:00" })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { requested_at: "2026-11-03T10:20:30.000+05:30" })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { requested_at: "2024-02-29T23:59:59+00:00" })]),
        WORK,
      ),
    ).not.toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { requested_at: "2025-12-31T00:00:00.000000Z" })]),
        WORK,
      ),
    ).not.toBeNull();
  });

  it("enforces PARTIAL iff next_cursor is non-null, with canonical cursors", () => {
    expect(
      decodeSavedConversationPage(
        envelope([], { status: "PARTIAL", nextCursor: null }),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1)], { status: "COMPLETE", nextCursor: "abc" }),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1)], { status: "PARTIAL", nextCursor: "bad cursor!" }),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([], { status: "PARTIAL", nextCursor: "Y3Vyc29yLTE" }),
        WORK,
      ),
    ).not.toBeNull();
  });

  it("rejects row field drift: revision, ids, refs, flags", () => {
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { request_revision: "ZZ" + "a".repeat(62) })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { root_job_id: "JOB-abc" })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { target_ref: "fabric_attempt:short" })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { reference_only: false })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { request_ref: "" })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { request_ref: "x".repeat(257) })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { request_event_id: 0 })]),
        WORK,
      ),
    ).toBeNull();
    expect(
      decodeSavedConversationPage(
        envelope([row(1, { request_event_id: 1.5 })]),
        WORK,
      ),
    ).toBeNull();
  });

  it("is shape and selection only: nothing here authenticates a row", () => {
    // A syntactically valid page decodes without any cryptographic or owner
    // check: authentication stays with the signed Session Bridge owner and
    // the port's answer validator, never in this module.
    const unverified = envelope([row(1)]);
    expect(decodeSavedConversationPage(unverified, WORK)).not.toBeNull();
  });
});

describe("searchSavedConversations", () => {
  it("matches qualified saved answers across rootless same-project rows", async () => {
    const a = row(1, {}, WORK, "JOB-11");
    const b = row(2, {}, WORK, "JOB-22");
    const answers = new Map<string, unknown>([
      [a.operation_key + "|" + a.target_ref, qualifiedAnswer(a, TEXT_MATCH)],
      [b.operation_key + "|" + b.target_ref, qualifiedAnswer(b, TEXT_OTHER)],
    ]);
    const owner = makeOwner({ page: envelope([a, b]), answers });
    const result: SavedConversationSearchResult = await searchSavedConversations(
      searchRequest(),
      owner,
    );
    expect(result.state).toBe("AVAILABLE");
    expect(result.reason).toBeNull();
    expect(result.scope).toBe("SAVED_CONVERSATIONS_IN_PROJECT");
    expect(result.workRef).toBe(WORK);
    expect(result.query).toBe("green");
    expect(result.items).toHaveLength(1);
    expect(result.coverage.status).toBe("COMPLETE");
    // Counts reflect the rows actually scanned by this one query, never a
    // total company conversation count.
    expect(result.coverage.scanned).toBe(2);
    expect(result.coverage.matched).toBe(1);
    expect(result.coverage.unavailable).toBe(0);
    expect(result.coverage.nextCursor).toBeNull();
    expect(result.coverage.highWater).toBe(100);
    const item = result.items[0];
    const matchedReference: SavedConversationReference | undefined = item?.reference;
    expect(matchedReference?.work_ref).toBe(WORK);
    expect(item?.reference.root_job_id).toBe("JOB-11");
    expect(item?.reference.read_ref).toBe(a.read_ref);
    expect(item?.sourceTextSha256).toBe(DIGEST_MATCH);
    // No generated summary, no nextStep, no private envelope in the result.
    expect(item?.excerpt).toBe(TEXT_MATCH);
    expect(JSON.stringify(result).includes(PRIVATE_NEXT_STEP)).toBe(false);
    expect(JSON.stringify(result).includes("parentConsumed")).toBe(false);
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(result.items)).toBe(true);
    expect(Object.isFrozen(item)).toBe(true);
    expect(Object.isFrozen(item?.reference)).toBe(true);
  });

  it("reads exactly one pageSize=4 page and at most four answers in order", async () => {
    const rows = [row(1), row(2), row(3), row(4)];
    const answers = new Map<string, unknown>(
      rows.map((r) => [r.operation_key + "|" + r.target_ref, qualifiedAnswer(r, TEXT_OTHER)]),
    );
    const owner = makeOwner({ page: envelope(rows), answers });
    const result = await searchSavedConversations(searchRequest(), owner);
    expect(result.coverage.scanned).toBe(4);
    expect(result.coverage.matched).toBe(0);
    expect(owner.trace.referenceReads).toHaveLength(1);
    expect(owner.trace.referenceReads[0]?.pageSize).toBe(4);
    expect(owner.trace.referenceReads[0]?.workRef).toBe(WORK);
    expect(owner.trace.answerPointers).toHaveLength(4);
    expect(owner.trace.answerPointers[0]).toEqual({
      operationKey: rows[0]?.operation_key,
      targetKey: rows[0]?.target_ref,
      kind: "message",
    });
  });

  it("binds the SHA-256 of the exact full source text via WebCrypto", async () => {
    const a = row(1);
    const answers = new Map<string, unknown>([
      [a.operation_key + "|" + a.target_ref, qualifiedAnswer(a, TEXT_UNICODE)],
    ]);
    const owner = makeOwner({ page: envelope([a]), answers });
    const result = await searchSavedConversations(
      searchRequest({ query: "GREEN" }),
      owner,
    );
    expect(result.items).toHaveLength(1);
    expect(result.items[0]?.sourceTextSha256).toBe(DIGEST_UNICODE);
    expect(result.items[0]?.sourceTextSha256).toMatch(/^[0-9a-f]{64}$/);
  });

  it("produces an exact bounded excerpt around the first match", async () => {
    const a = row(1);
    const text = "prefix green suffix";
    const answers = new Map<string, unknown>([
      [a.operation_key + "|" + a.target_ref, qualifiedAnswer(a, text)],
    ]);
    const owner = makeOwner({ page: envelope([a]), answers });
    const result = await searchSavedConversations(searchRequest(), owner);
    expect(result.items[0]?.excerpt).toBe(text);
  });

  it("keeps unicode excerpts inside 480 UTF-8 bytes without splitting codepoints", async () => {
    const utf8Bytes = (value: string): number => new TextEncoder().encode(value).length;
    const a = row(1);
    const answers = new Map<string, unknown>([
      [a.operation_key + "|" + a.target_ref, qualifiedAnswer(a, TEXT_UNICODE)],
    ]);
    const owner = makeOwner({ page: envelope([a]), answers });
    const result = await searchSavedConversations(
      searchRequest({ query: "GREEN" }),
      owner,
    );
    const excerpt = result.items[0]?.excerpt ?? "";
    expect(utf8Bytes(excerpt)).toBeLessThanOrEqual(480);
    expect(TEXT_UNICODE.includes(excerpt)).toBe(true);
    expect(excerpt.toLowerCase().includes("green")).toBe(true);
    for (const ch of Array.from(excerpt)) {
      const code = ch.codePointAt(0) ?? 0;
      expect(code >= 0xd800 && code <= 0xdfff).toBe(false);
    }

    const b = row(2);
    const longText = "x".repeat(5) + "🌟".repeat(200) + " tail";
    const answers2 = new Map<string, unknown>([
      [b.operation_key + "|" + b.target_ref, qualifiedAnswer(b, longText)],
    ]);
    const owner2 = makeOwner({ page: envelope([b]), answers: answers2 });
    const result2 = await searchSavedConversations(
      searchRequest({ query: "🌟".repeat(30) }),
      owner2,
    );
    const excerpt2 = result2.items[0]?.excerpt ?? "";
    expect(utf8Bytes(excerpt2)).toBeLessThanOrEqual(480);
    expect(longText.startsWith(excerpt2)).toBe(true);
  });

  it("matches the query only literally, never as a regex", async () => {
    const a = row(1);
    const answers = new Map<string, unknown>([
      [a.operation_key + "|" + a.target_ref, qualifiedAnswer(a, "has axxxb inside")],
    ]);
    const owner = makeOwner({ page: envelope([a]), answers });
    const noMatch = await searchSavedConversations(
      searchRequest({ query: "a.*b" }),
      owner,
    );
    expect(noMatch.items).toHaveLength(0);
    expect(noMatch.coverage.matched).toBe(0);
    expect(noMatch.coverage.unavailable).toBe(0);

    const b = row(2);
    const literal = "literal a.*b present";
    const answers2 = new Map<string, unknown>([
      [b.operation_key + "|" + b.target_ref, qualifiedAnswer(b, literal)],
    ]);
    const owner2 = makeOwner({ page: envelope([b]), answers: answers2 });
    const literalMatch = await searchSavedConversations(
      searchRequest({ query: "a.*b" }),
      owner2,
    );
    expect(literalMatch.items).toHaveLength(1);
    expect(literal.includes(literalMatch.items[0]?.excerpt ?? "")).toBe(true);
  });

  it("accepts boundary queries of 2 and 128 scalar chars", async () => {
    const a = row(1);
    const text = "ok fine";
    const answers = new Map<string, unknown>([
      [a.operation_key + "|" + a.target_ref, qualifiedAnswer(a, text)],
    ]);
    const owner = makeOwner({ page: envelope([a]), answers });
    const two = await searchSavedConversations(searchRequest({ query: "ok" }), owner);
    expect(two.items).toHaveLength(1);
    const long = "e".repeat(128);
    const text2 = long + " tail";
    const b = row(2);
    const answers2 = new Map<string, unknown>([
      [b.operation_key + "|" + b.target_ref, qualifiedAnswer(b, text2)],
    ]);
    const owner2 = makeOwner({ page: envelope([b]), answers: answers2 });
    const boundary = await searchSavedConversations(
      searchRequest({ query: long }),
      owner2,
    );
    expect(boundary.items).toHaveLength(1);
  });

  it("performs no read for invalid queries, work refs, cursors or watermarks", async () => {
    const cases = [
      searchRequest({ query: "a" }),
      searchRequest({ query: "x".repeat(129) }),
      searchRequest({ query: "ok\u0007now" }),
      searchRequest({ query: "\ud800lone" }),
      searchRequest({ workRef: "project-x" }),
      searchRequest({ workRef: "WS:a" }),
      searchRequest({ workRef: "ws:DISCOVERY" }),
      searchRequest({ cursor: "bad cursor!" }),
      searchRequest({ expectedHighWater: -1 }),
      searchRequest({ expectedHighWater: 1.5 }),
    ];
    for (const req of cases) {
      const owner = makeOwner({ page: envelope([row(1)]) });
      const result = await searchSavedConversations(req, owner);
      expect(result.state).toBe("UNAVAILABLE");
      expect(result.reason).toBe("INVALID_INPUT");
      expect(result.items).toHaveLength(0);
      expect(owner.trace.referenceReads).toHaveLength(0);
      expect(owner.trace.answerPointers).toHaveLength(0);
    }
  });

  it("performs no read when the owner cannot serve or has no context", async () => {
    const noContext = makeOwner({
      page: envelope([row(1)]),
      context: () => null,
    });
    const result = await searchSavedConversations(searchRequest(), noContext);
    expect(result.reason).toBe("OWNER_UNAVAILABLE");
    expect(noContext.trace.referenceReads).toHaveLength(0);

    const nanAuth = makeOwner({
      page: envelope([row(1)]),
      authGeneration: () => Number.NaN,
    });
    const result2 = await searchSavedConversations(searchRequest(), nanAuth);
    expect(result2.reason).toBe("OWNER_UNAVAILABLE");
    expect(nanAuth.trace.referenceReads).toHaveLength(0);

    const emptyScope = makeOwner({
      page: envelope([row(1)]),
      context: () => ({ principalScope: "", generation: "gen-1" }),
    });
    const result3 = await searchSavedConversations(searchRequest(), emptyScope);
    expect(result3.reason).toBe("OWNER_UNAVAILABLE");
    expect(emptyScope.trace.referenceReads).toHaveLength(0);

    const incomplete = {
      context: () => ({ principalScope: "p", generation: "g" }),
      authGeneration: () => 1,
    };
    const result4 = await searchSavedConversations(
      searchRequest(),
      incomplete as unknown as SavedConversationSearchOwner,
    );
    expect(result4.reason).toBe("OWNER_UNAVAILABLE");
  });

  it("fails closed on auth generation drift after the page read", async () => {
    let generation = 7;
    const owner = makeOwner({
      page: envelope([row(1)]),
      answers: new Map<string, unknown>(),
      authGeneration: () => generation,
      afterPage: () => {
        generation = 8;
      },
    });
    const result = await searchSavedConversations(searchRequest(), owner);
    expect(result.state).toBe("UNAVAILABLE");
    expect(result.reason).toBe("SOURCE_CHANGED");
    expect(result.items).toHaveLength(0);
    expect(result.coverage.nextCursor).toBeNull();
    expect(result.coverage.highWater).toBeNull();
    expect(owner.trace.answerPointers).toHaveLength(0);
  });

  it("fails closed on owner context drift after the page read", async () => {
    let generation = "gen-1";
    const owner = makeOwner({
      page: envelope([row(1)]),
      context: () => ({ principalScope: "principal://p", generation }),
      afterPage: () => {
        generation = "gen-2";
      },
    });
    const result = await searchSavedConversations(searchRequest(), owner);
    expect(result.reason).toBe("SOURCE_CHANGED");
    expect(owner.trace.answerPointers).toHaveLength(0);
  });

  it("fails closed when a read method is replaced between awaits", async () => {
    let owner: SavedConversationSearchOwner & { trace: OwnerTrace };
    owner = makeOwner({
      page: envelope([row(1)]),
      answers: new Map<string, unknown>(),
      afterPage: () => {
        const replacement = async (pointer: OperationPointer) => ({
          receipt: {...pointer, disposition: "unknown" as const}, answer: null,
        });
        owner.readAnswer = replacement;
      },
    });
    const result = await searchSavedConversations(searchRequest(), owner);
    expect(result.reason).toBe("SOURCE_CHANGED");
    expect(result.items).toHaveLength(0);
  });

  it("discards content on abort before and during the search", async () => {
    const pre = new AbortController();
    pre.abort();
    const preOwner = makeOwner({ page: envelope([row(1)]) });
    const result = await searchSavedConversations(
      searchRequest({ signal: pre.signal }),
      preOwner,
    );
    expect(result.reason).toBe("SOURCE_CHANGED");
    expect(result.items).toHaveLength(0);
    expect(preOwner.trace.referenceReads).toHaveLength(0);

    const mid = new AbortController();
    const a = row(1);
    const midOwner = makeOwner({
      page: envelope([a]),
      answers: new Map<string, unknown>([
        [a.operation_key + "|" + a.target_ref, qualifiedAnswer(a, TEXT_MATCH)],
      ]),
      beforeAnswer: () => {
        mid.abort();
        throw new Error("late completion");
      },
    });
    const aborted = await searchSavedConversations(
      searchRequest({ signal: mid.signal }),
      midOwner,
    );
    expect(aborted.state).toBe("UNAVAILABLE");
    expect(aborted.reason).toBe("SOURCE_CHANGED");
    expect(aborted.items).toHaveLength(0);
    expect(aborted.coverage.nextCursor).toBeNull();
    expect(aborted.coverage.highWater).toBeNull();
    // No qualified-answer content survives an abort; the echoed query string
    // is not answer content.
    expect(JSON.stringify(aborted).includes("rollback window")).toBe(false);

    // A follow-up search on a fresh owner completes normally: the aborted
    // search left no module-level state behind.
    const ownerB = makeOwner({
      page: envelope([a]),
      answers: new Map<string, unknown>([
        [a.operation_key + "|" + a.target_ref, qualifiedAnswer(a, TEXT_MATCH)],
      ]),
    });
    const completed = await searchSavedConversations(searchRequest(), ownerB);
    expect(completed.state).toBe("AVAILABLE");
    expect(completed.items).toHaveLength(1);
  });

  it("treats unknown, refused, mismatched and oversize answers as unavailable", async () => {
    const a = row(1);
    const refused = {
      receipt: {
        operationKey: a.operation_key,
        kind: "message",
        targetKey: a.target_ref,
        disposition: "refused",
      },
      answer: null,
    };
    const unknownRow = row(2);
    const unknown = {
      receipt: {
        operationKey: unknownRow.operation_key,
        kind: "message",
        targetKey: unknownRow.target_ref,
        disposition: "unknown",
      },
      answer: null,
    };
    const b = row(3);
    const wrongKey = qualifiedAnswer(b, TEXT_MATCH);
    wrongKey.receipt.operationKey = "session-continue-" + HEX(999);
    const c = row(4);
    const wrongRef = qualifiedAnswer(c, TEXT_MATCH);
    wrongRef.answer.readRef = "session-reply-" + HEX(999);
    const oversizeRow = row(5, {}, WORK, undefined);
    const answers = new Map<string, unknown>([
      [a.operation_key + "|" + a.target_ref, refused],
      [unknownRow.operation_key + "|" + unknownRow.target_ref, unknown],
      [b.operation_key + "|" + b.target_ref, wrongKey],
      [c.operation_key + "|" + c.target_ref, wrongRef],
      [oversizeRow.operation_key + "|" + oversizeRow.target_ref, qualifiedAnswer(oversizeRow, "y".repeat(20000))],
    ]);
    // Five rows would be rejected by the decoder, so the unavailable budget
    // is exercised with a mixed page of four: refusal, unknown, receipt
    // mismatch, read-ref mismatch.
    const page = envelope([a, unknownRow, b, c]);
    const owner = makeOwner({
      page,
      answers,
    });
    const result = await searchSavedConversations(searchRequest(), owner);
    expect(result.state).toBe("AVAILABLE");
    expect(result.reason).toBeNull();
    expect(result.coverage.status).toBe("PARTIAL");
    expect(result.coverage.scanned).toBe(4);
    expect(result.coverage.matched).toBe(0);
    expect(result.coverage.unavailable).toBe(4);
    expect(JSON.stringify(result).includes(PRIVATE_NEXT_STEP)).toBe(false);
    expect(JSON.stringify(result).includes("rollback window")).toBe(false);

    // An oversize body counts unavailable, and is not an owner denial.
    const single = row(9, {}, WORK, undefined);
    const owner2 = makeOwner({
      page: envelope([single]),
      answers: new Map<string, unknown>([
        [single.operation_key + "|" + single.target_ref, qualifiedAnswer(single, "y".repeat(20000))],
      ]),
    });
    const result2 = await searchSavedConversations(searchRequest(), owner2);
    expect(result2.state).toBe("AVAILABLE");
    expect(result2.reason).toBeNull();
    expect(result2.coverage.unavailable).toBe(1);
    expect(result2.coverage.matched).toBe(0);
  });

  it("keeps an empty PARTIAL page partial with an honest cursor", async () => {
    const owner = makeOwner({
      page: envelope([], { status: "PARTIAL", nextCursor: "Y3Vyc29yLTE" }),
    });
    const result = await searchSavedConversations(searchRequest(), owner);
    expect(result.state).toBe("AVAILABLE");
    expect(result.coverage.status).toBe("PARTIAL");
    expect(result.coverage.scanned).toBe(0);
    expect(result.coverage.matched).toBe(0);
    expect(result.coverage.unavailable).toBe(0);
    expect(result.coverage.nextCursor).toBe("Y3Vyc29yLTE");
    expect(result.coverage.highWater).toBe(100);
    expect(owner.trace.answerPointers).toHaveLength(0);
  });

  it("keeps the page cursor when a PARTIAL page produced matches", async () => {
    const a = row(1);
    const owner = makeOwner({
      page: envelope([a], { status: "PARTIAL", nextCursor: "Y3Vyc29yLTI" }),
      answers: new Map<string, unknown>([
        [a.operation_key + "|" + a.target_ref, qualifiedAnswer(a, TEXT_MATCH)],
      ]),
    });
    const result = await searchSavedConversations(searchRequest(), owner);
    expect(result.coverage.status).toBe("PARTIAL");
    expect(result.coverage.matched).toBe(1);
    expect(result.coverage.nextCursor).toBe("Y3Vyc29yLTI");
  });

  it("rejects a non-advancing cursor without any answer read", async () => {
    const owner = makeOwner({
      page: envelope([row(1)], { status: "PARTIAL", nextCursor: "same" }),
      answers: new Map<string, unknown>(),
    });
    const result = await searchSavedConversations(
      searchRequest({ cursor: "same" }),
      owner,
    );
    expect(result.reason).toBe("INVALID_SOURCE");
    expect(result.items).toHaveLength(0);
    expect(owner.trace.answerPointers).toHaveLength(0);
  });

  it("fails closed on watermark movement and work_ref drift", async () => {
    const a = row(1);
    const watermarkOwner = makeOwner({
      page: envelope([a]),
      answers: new Map<string, unknown>([
        [a.operation_key + "|" + a.target_ref, qualifiedAnswer(a, TEXT_MATCH)],
      ]),
    });
    const moved = await searchSavedConversations(
      searchRequest({ expectedHighWater: 99 }),
      watermarkOwner,
    );
    expect(moved.state).toBe("UNAVAILABLE");
    expect(moved.reason).toBe("SOURCE_CHANGED");
    expect(moved.items).toHaveLength(0);
    expect(watermarkOwner.trace.answerPointers).toHaveLength(0);

    const driftedPage = envelope([row(1, {}, OTHER_WORK)]);
    const driftOwner = makeOwner({ page: driftedPage });
    const drifted = await searchSavedConversations(searchRequest(), driftOwner);
    expect(drifted.reason).toBe("SOURCE_CHANGED");
    expect(drifted.items).toHaveLength(0);
    expect(driftOwner.trace.answerPointers).toHaveLength(0);
  });

  it("never surfaces owner exception text", async () => {
    const owner = makeOwner({ pageError: new Error("SECRET-INTERNAL-STACK") });
    const result = await searchSavedConversations(searchRequest(), owner);
    expect(result.state).toBe("UNAVAILABLE");
    expect(result.reason).toBe("OWNER_UNAVAILABLE");
    expect(JSON.stringify(result).includes("SECRET")).toBe(false);

    const a = row(1);
    const owner2 = makeOwner({
      page: envelope([a]),
      answerErrors: new Map<string, Error>([
        [a.operation_key + "|" + a.target_ref, new Error("SECRET-ANSWER")],
      ]),
    });
    const result2 = await searchSavedConversations(searchRequest(), owner2);
    expect(result2.state).toBe("AVAILABLE");
    expect(result2.coverage.unavailable).toBe(1);
    expect(JSON.stringify(result2).includes("SECRET")).toBe(false);
  });

  it("cannot be retargeted by mutation of the raw page after decode", async () => {
    const a = row(1);
    const b = row(2);
    const raw = envelope([{ ...a }, { ...b }]);
    const answers = new Map<string, unknown>([
      [a.operation_key + "|" + a.target_ref, qualifiedAnswer(a, TEXT_MATCH)],
      [b.operation_key + "|" + b.target_ref, qualifiedAnswer(b, TEXT_OTHER)],
    ]);
    const owner = makeOwner({
      page: raw,
      answers,
      beforeAnswer: () => {
        const rawRow = raw.data.references[0];
        if (rawRow !== undefined) {
          rawRow.read_ref = "session-reply-" + HEX(777);
          rawRow.operation_key = "session-continue-" + HEX(777);
          rawRow.target_ref = "fabric_attempt:" + HEX(777);
        }
      },
    });
    const result = await searchSavedConversations(searchRequest(), owner);
    expect(result.state).toBe("AVAILABLE");
    expect(result.items).toHaveLength(1);
    expect(owner.trace.answerPointers).toEqual([
      { operationKey: a.operation_key, targetKey: a.target_ref, kind: "message" },
      { operationKey: b.operation_key, targetKey: b.target_ref, kind: "message" },
    ]);
    expect(result.items[0]?.reference.read_ref).toBe(a.read_ref);
  });

  it("leaves original clocks and the network untouched", async () => {
    let clockCalls = 0;
    const realNow = Date.now;
    Date.now = () => {
      clockCalls += 1;
      return realNow();
    };
    try {
      const a = row(1);
      const owner = makeOwner({
        page: envelope([a]),
        answers: new Map<string, unknown>([
          [a.operation_key + "|" + a.target_ref, qualifiedAnswer(a, TEXT_MATCH)],
        ]),
      });
      const result = await searchSavedConversations(searchRequest(), owner);
      expect(result.items).toHaveLength(1);
      expect(clockCalls).toBe(0);
      expect(owner.trace.referenceReads).toHaveLength(1);
    } finally {
      Date.now = realNow;
    }
  });
});


describe("parent source-boundary repairs", () => {
  it.each(["read_ref", "operation_key", "request_revision", "root_job_id", "target_ref"])("rejects a trailing LF on exact %s identity", field => {
    const original=row(1); original[field]=String(original[field])+"\n";
    expect(decodeSavedConversationPage(envelope([original]),WORK)).toBeNull();
  });
  it("rejects control or surrogate request provenance and cursor trailing LF",()=>{
    for(const request_ref of ["private\u0000ref","private\u0085ref","x\ud800"])
      expect(decodeSavedConversationPage(envelope([row(1,{request_ref})]),WORK)).toBeNull();
    expect(decodeSavedConversationPage(envelope([],{status:"PARTIAL",nextCursor:"YQ==\n"}),WORK)).toBeNull();
  });
  it("rejects request accessors without invoking them or reading private sources", async()=>{
    let called=0;const owner=makeOwner({page:envelope([row(1)])});
    const request=Object.defineProperty(searchRequest(),"query",{get(){called++;throw new Error("private");}});
    const result=await searchSavedConversations(request,owner);
    expect(result.reason).toBe("INVALID_INPUT");expect(result.items).toEqual([]);expect(called).toBe(0);
    expect(owner.trace.answerPointers).toEqual([]);
  });
  it("does not echo an unbounded invalid query or accept extra request selectors", async()=>{
    const owner=makeOwner({page:envelope([row(1)])});
    const result=await searchSavedConversations({...searchRequest(),query:"private".repeat(100000)},owner);
    expect(result.query).toBe("");expect(result.reason).toBe("INVALID_INPUT");
    const extra=await searchSavedConversations({...searchRequest(),rootJobId:"JOB-1"} as never,owner);
    expect(extra.reason).toBe("INVALID_INPUT");expect(owner.trace.answerPointers).toEqual([]);
  });
});


describe("explicit saved-source Open",()=>{
  function original() {
    const reference=row(1);
    const page=envelope([reference]);
    const answers=new Map<string,unknown>([[reference.operation_key+"|"+reference.target_ref,qualifiedAnswer(reference,TEXT_MATCH)]]);
    const owner=makeOwner({page,answers});
    const decoded=decodeSavedConversationPage(page,WORK)!;
    const match={reference:decoded.references[0],excerpt:"migration completed",sourceTextSha256:DIGEST_MATCH};
    return {reference,page,answers,owner,match,request:{workRef:WORK,match,expectedHighWater:100,signal:freshSignal()}};
  }
  it("re-reads exact current page membership and original qualified text before exposing content",async()=>{
    const f=original();const result=await readSavedConversationSource(f.request,f.owner);
    expect(result).toMatchObject({state:"AVAILABLE",reason:null,text:TEXT_MATCH,sourceTextSha256:DIGEST_MATCH});
    expect(result.reference).toEqual(f.match.reference);
    expect(f.owner.trace.referenceReads).toEqual([{workRef:WORK,pageSize:4}]);
    expect(f.owner.trace.answerPointers).toEqual([{operationKey:f.reference.operation_key,kind:"message",targetKey:f.reference.target_ref}]);
    expect(JSON.stringify(result)).not.toContain(PRIVATE_NEXT_STEP);
  });
  it.each(["missing", "revision", "watermark"])("does not read an answer after original index %s changes",async mode=>{
    const f=original();
    if(mode==="missing")f.page.data.references=[];
    if(mode==="revision")f.reference.request_revision=HEX(999);
    if(mode==="watermark")f.page.data.high_water=101;
    const result=await readSavedConversationSource(f.request,f.owner);
    expect(result.state).toBe("UNAVAILABLE");expect(result.reason).toBe("SOURCE_CHANGED");
    expect(result.text).toBeNull();expect(f.owner.trace.answerPointers).toEqual([]);
  });
  it.each(["text", "readref", "digest", "excerpt"])("rejects changed %s without displaying source",async mode=>{
    const f=original();
    if(mode==="text")f.answers.set(f.reference.operation_key+"|"+f.reference.target_ref,qualifiedAnswer(f.reference,"private changed body"));
    if(mode==="readref"){
      const answer=qualifiedAnswer(f.reference,TEXT_MATCH);answer.answer.readRef="session-reply-"+HEX(987);
      f.answers.set(f.reference.operation_key+"|"+f.reference.target_ref,answer);
    }
    if(mode==="digest")f.match.sourceTextSha256=HEX(987);
    if(mode==="excerpt")f.match.excerpt="invented excerpt";
    const result=await readSavedConversationSource(f.request,f.owner);
    expect(result.state).toBe("UNAVAILABLE");expect(result.text).toBeNull();
  });
  it("retains explicit original page cursor and rejects late principal/source revocation",async()=>{
    const f=original(); let current=true;
    const owner=makeOwner({page:f.page,answers:f.answers,
      context:()=>current?{principalScope:"scope",generation:"1"}:null,
      beforeAnswer:()=>{current=false;}});
    const result=await readSavedConversationSource({...f.request,pageCursor:"YQ=="},owner);
    expect(owner.trace.referenceReads).toEqual([{workRef:WORK,pageSize:4,cursor:"YQ=="}]);
    expect(result.reason).toBe("SOURCE_CHANGED");expect(result.text).toBeNull();
  });
  it("malformed or foreign Open request makes no owner read",async()=>{
    const f=original();
    const invalid=await readSavedConversationSource({...f.request,workRef:"WS:FOREIGN"},f.owner);
    expect(invalid.reason).toBe("INVALID_INPUT");expect(f.owner.trace.referenceReads).toEqual([]);
    let called=0;const request=Object.defineProperty({...f.request},"match",{get(){called++;throw new Error("private");}});
    expect((await readSavedConversationSource(request,f.owner)).reason).toBe("INVALID_INPUT");expect(called).toBe(0);
  });
});
