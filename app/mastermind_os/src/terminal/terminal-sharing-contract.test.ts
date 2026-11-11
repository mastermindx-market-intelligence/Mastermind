import actualSqlFixture from "../inbox/fixtures/terminal-sharing-request-feed.json";
import { describe, expect, it } from "vitest";
import {
  FEED_BYTE_BUDGET,
  FEED_REQUEST_LIMIT,
  decodeTerminalSessionStatus,
  decodeTerminalSharingFeed,
  TERMINAL_SHARING_UNAVAILABLE,
} from "./terminal-sharing-contract";

const PRINCIPAL = "1a".repeat(32);
const SESSION = "2b".repeat(32);
const OTHER_PRINCIPAL = "55".repeat(32);
const CONTENT = "3a".repeat(32);
const REQUEST_REF = "0193f2c4-7a1b-7c2d-8e3f-4a5b6c7d8e9f";
const OTHER_REQUEST_REF = "0193f2c4-7a1b-7c2d-8e3f-4a5b6c7d8e90";
const DELIVERY_ID = "0f8e7d6c-5b4a-6c3d-9e2f-1a2b3c4d5e6f";
const TEAM_ID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d";
const ISSUED_AT = "2026-11-04T10:15:30.123456Z";
const OBSERVED_AT = "2026-11-04T10:15:30.654321Z";
const SLOT = "2026-11-04";

const EXPECTED = { principalScope: PRINCIPAL, sessionScope: SESSION };

function request(): Record<string, any> {
  return {
    request_ref: REQUEST_REF,
    revision: 1,
    issued_at: ISSUED_AT,
    delivery: {
      delivery_id: DELIVERY_ID,
      content_sha256: CONTENT,
      title: "Boundary review brief",
      slot_asof: SLOT,
      artifact_asof: null,
    },
    audience: {
      team_id: TEAM_ID,
      name: "Boundary owners",
      member_count: 3,
      membership_policy: "DYNAMIC_TEAM_MEMBERSHIP",
    },
    review: {
      request_ref: REQUEST_REF,
      revision: 1,
      delivery_id: DELIVERY_ID,
    },
  };
}

function validFeed(): Record<string, any> {
  return {
    schema: "mastermind.terminal_sharing_request_feed.v1",
    viewer: { principal_scope: PRINCIPAL, session_scope: SESSION },
    source: {
      owner: "TERMINAL_BRIEF_DELIVERY",
      scope: "OWNED_EXPLICIT_SHARING_REQUESTS",
      observed_at: OBSERVED_AT,
    },
    coverage: { state: "COMPLETE_WITHIN_SCOPE", reason_codes: [] },
    requests: [request()],
  };
}

function decodeFeed(value: unknown) {
  return decodeTerminalSharingFeed(value, EXPECTED);
}

function closed(fn: () => unknown): void {
  expect(fn).toThrowError(new RegExp(`^${TERMINAL_SHARING_UNAVAILABLE}$`));
}

async function closedAsync(fn: () => Promise<unknown>): Promise<void> {
  await expect(fn).rejects.toThrowError(new RegExp(`^${TERMINAL_SHARING_UNAVAILABLE}$`));
}

describe("terminal sharing feed codec", () => {
  it("decodes a valid feed into deeply frozen plain records", () => {
    const feed = decodeFeed(validFeed());
    expect(feed.viewer).toEqual({ principal_scope: PRINCIPAL, session_scope: SESSION });
    expect(feed.source).toEqual({
      owner: "TERMINAL_BRIEF_DELIVERY",
      scope: "OWNED_EXPLICIT_SHARING_REQUESTS",
      observed_at: OBSERVED_AT,
    });
    expect(feed.coverage).toEqual({ state: "COMPLETE_WITHIN_SCOPE", reason_codes: [] });
    expect(feed.requests).toHaveLength(1);
    const issued = feed.requests[0];
    expect(issued).toEqual({
      request_ref: REQUEST_REF,
      revision: 1,
      issued_at: ISSUED_AT,
      delivery: {
        delivery_id: DELIVERY_ID,
        content_sha256: CONTENT,
        title: "Boundary review brief",
        slot_asof: SLOT,
        artifact_asof: null,
      },
      audience: {
        team_id: TEAM_ID,
        name: "Boundary owners",
        member_count: 3,
        membership_policy: "DYNAMIC_TEAM_MEMBERSHIP",
      },
      review: { request_ref: REQUEST_REF, revision: 1, delivery_id: DELIVERY_ID },
    });
    expect(Object.isFrozen(feed)).toBe(true);
    expect(Object.isFrozen(feed.viewer)).toBe(true);
    expect(Object.isFrozen(feed.source)).toBe(true);
    expect(Object.isFrozen(feed.coverage)).toBe(true);
    expect(Object.isFrozen(feed.coverage.reason_codes)).toBe(true);
    expect(Object.isFrozen(feed.requests)).toBe(true);
    expect(Object.isFrozen(issued)).toBe(true);
    expect(Object.isFrozen(issued.delivery)).toBe(true);
    expect(Object.isFrozen(issued.audience)).toBe(true);
    expect(Object.isFrozen(issued.review)).toBe(true);
  });

  it("refuses array accessors and custom iteration without invoking them", () => {
    let invoked = 0;
    for (const field of ["requests", "reason_codes"] as const) {
      const feed = validFeed();
      const array: unknown[] = [field === "requests" ? request() : "LIMIT_REACHED"];
      Object.defineProperty(array, "0", { enumerable: true, get() { invoked++; throw new Error("private"); } });
      if (field === "requests") feed.requests = array;
      else { feed.coverage.state = "PARTIAL"; feed.coverage.reason_codes = array; }
      closed(() => decodeFeed(feed));
    }
    const feed = validFeed();
    Object.defineProperty(feed.requests, Symbol.iterator, { value() { invoked++; throw new Error("private"); } });
    closed(() => decodeFeed(feed));
    expect(invoked).toBe(0);
  });

  it("keeps decoded records immutable against mutation attempts", () => {
    const feed = decodeFeed(validFeed());
    const issued = feed.requests[0];
    expect(() => {
      (issued.delivery as { title: string }).title = "replaced";
    }).toThrow();
    expect(issued.delivery.title).toBe("Boundary review brief");
    expect(() => {
      (feed.requests as unknown[]).push({});
    }).toThrow();
    expect(feed.requests).toHaveLength(1);
    expect(() => {
      (feed.coverage.reason_codes as string[]).push("LIMIT_REACHED");
    }).toThrow();
  });

  it("accepts the feed only for the exact expected viewer scopes", () => {
    expect(decodeFeed(validFeed()).viewer.principal_scope).toBe(PRINCIPAL);
    closed(() => decodeTerminalSharingFeed(validFeed(), {
      principalScope: OTHER_PRINCIPAL,
      sessionScope: SESSION,
    }));
    closed(() => decodeTerminalSharingFeed(validFeed(), {
      principalScope: PRINCIPAL,
      sessionScope: "33".repeat(32),
    }));
    const otherViewer = validFeed();
    (otherViewer.viewer as Record<string, unknown>).principal_scope = OTHER_PRINCIPAL;
    closed(() => decodeFeed(otherViewer));
  });

  it("rejects malformed digests, refs and revisions", () => {
    const cases: Array<(feed: Record<string, any>) => void> = [
      (feed) => {
        (feed.requests[0].delivery as Record<string, unknown>).content_sha256 = CONTENT.slice(1);
      },
      (feed) => {
        (feed.requests[0].delivery as Record<string, unknown>).content_sha256 = CONTENT.toUpperCase();
      },
      (feed) => {
        (feed.requests[0].delivery as Record<string, unknown>).content_sha256 = `x${CONTENT.slice(1)}`;
      },
      (feed) => {
        (feed.requests[0].delivery as Record<string, unknown>).content_sha256 = 7;
      },
      (feed) => {
        feed.request_ref = REQUEST_REF.toUpperCase();
      },
      (feed) => {
        feed.request_ref = `{${REQUEST_REF}}`;
      },
      (feed) => {
        feed.request_ref = REQUEST_REF.replaceAll("-", "");
      },
      (feed) => {
        feed.request_ref = "00000000-0000-0000-0000-000000000000";
      },
      (feed) => {
        feed.request_ref = "0193f2c4-7a1b-9c2d-8e3f-4a5b6c7d8e9f";
      },
      (feed) => {
        (feed.requests[0].review as Record<string, unknown>).request_ref = OTHER_REQUEST_REF;
      },
      (feed) => {
        (feed.requests[0].review as Record<string, unknown>).delivery_id = TEAM_ID;
      },
      (feed) => {
        (feed.requests[0].review as Record<string, unknown>).revision = 2;
      },
      (feed) => {
        feed.revision = 2;
      },
      (feed) => {
        feed.revision = "1";
      },
      (feed) => {
        feed.revision = 1.5;
      },
      (feed) => {
        feed.revision = true;
      },
      (feed) => {
        (feed.requests[0] as Record<string, unknown>).delivery_id = DELIVERY_ID;
      },
    ];
    for (const breakFeed of cases) {
      const feed = validFeed();
      breakFeed(feed);
      closed(() => decodeFeed(feed));
    }
  });

  it("rejects non-UTC or non-calendar timestamps and slots", () => {
    const stamps = [
      "2026-11-04T10:15:30.12345Z",
      "2026-11-04T10:15:30.1234567Z",
      "2026-11-04T10:15:30Z",
      "2026-11-04 10:15:30.123456Z",
      "2026-11-04T10:15:30.123456+00:00",
      "2026-11-04T10:15:30.123456z",
      "2026-13-01T00:00:00.000000Z",
      "2026-00-01T00:00:00.000000Z",
      "2026-02-30T00:00:00.000000Z",
      "2026-02-29T00:00:00.000000Z",
      "2026-11-04T24:00:00.000000Z",
      "2026-11-04T10:60:00.000000Z",
      "2026-11-04T10:15:60.000000Z",
      "0000-01-01T00:00:00.000000Z",
      ISSUED_AT.replace("T", "t"),
    ];
    for (const stamp of stamps) {
      const feed = validFeed();
      (feed.requests[0] as Record<string, unknown>).issued_at = stamp;
      closed(() => decodeFeed(feed));
      const observed = validFeed();
      (observed.source as Record<string, unknown>).observed_at = stamp;
      closed(() => decodeFeed(observed));
    }
    for (const slot of ["2026-02-30", "2026-13-01", "20261104", "2026-2-4", "0000-01-01", "2026-11-04T10:15:30.123456Z"]) {
      const feed = validFeed();
      (feed.requests[0].delivery as Record<string, unknown>).slot_asof = slot;
      closed(() => decodeFeed(feed));
    }
    const leap = validFeed();
    (leap.requests[0] as Record<string, unknown>).issued_at = "2024-02-29T00:00:00.000000Z";
    expect(decodeFeed(leap).requests[0].issued_at).toBe("2024-02-29T00:00:00.000000Z");
    const leapSlot = validFeed();
    (leapSlot.requests[0].delivery as Record<string, unknown>).slot_asof = "2028-02-29";
    expect(decodeFeed(leapSlot).requests[0].delivery.slot_asof).toBe("2028-02-29");
  });

  it("enforces the total UTF-8 JSON budget and the request limit", () => {
    const hex = "0123456789abcdef";
    const uniqueRequest = (index: number, title: string): Record<string, any> => {
      const entry = request();
      entry.request_ref = `${REQUEST_REF.slice(0, -2)}${hex[Math.floor(index / 16)]}${hex[index % 16]}`;
      const delivery = entry.delivery as Record<string, any>;
      delivery.delivery_id = `${DELIVERY_ID.slice(0, -2)}${hex[Math.floor(index / 16)]}${hex[index % 16]}`;
      delivery.title = title;
      entry.review = {
        request_ref: entry.request_ref,
        revision: 1,
        delivery_id: delivery.delivery_id,
      };
      return entry;
    };
    const requests = Array.from({ length: FEED_REQUEST_LIMIT }, (_unused, index) =>
      uniqueRequest(index, "t".repeat(3400)),
    );

    const budget = validFeed();
    budget.requests = requests;
    expect(JSON.stringify(budget).length).toBeGreaterThan(FEED_BYTE_BUDGET / 2);
    closed(() => decodeFeed(budget));

    const full = validFeed();
    full.requests = Array.from({ length: FEED_REQUEST_LIMIT }, (_unused, index) =>
      uniqueRequest(index, "Compact"),
    );
    expect(decodeFeed(full).requests).toHaveLength(FEED_REQUEST_LIMIT);

    const over = validFeed();
    over.requests = [...full.requests, uniqueRequest(20, "One past the limit")];
    closed(() => decodeFeed(over));
  });

  it("refuses getters, symbols, extras and hostile shapes without invoking them", () => {
    const getterFeed = validFeed();
    let invocations = 0;
    Object.defineProperty(getterFeed, "coverage", {
      enumerable: true,
      get() {
        invocations += 1;
        return { state: "COMPLETE_WITHIN_SCOPE", reason_codes: [] };
      },
    });
    closed(() => decodeFeed(getterFeed));
    expect(invocations).toBe(0);

    const deepGetter = validFeed();
    let deepInvocations = 0;
    Object.defineProperty(deepGetter.requests[0].delivery, "title", {
      enumerable: true,
      get() {
        deepInvocations += 1;
        return "Hostile title";
      },
    });
    closed(() => decodeFeed(deepGetter));
    expect(deepInvocations).toBe(0);

    const symbolExtra = validFeed();
    (symbolExtra as Record<symbol, unknown>)[Symbol("extra")] = 1;
    closed(() => decodeFeed(symbolExtra));

    const unknownExtra = validFeed();
    unknownExtra.extra = "value";
    closed(() => decodeFeed(unknownExtra));

    const missing = validFeed();
    delete missing.source;
    closed(() => decodeFeed(missing));

    const nestedExtra = validFeed();
    (nestedExtra.requests[0].audience as Record<string, unknown>).actor_uuid = TEAM_ID;
    closed(() => decodeFeed(nestedExtra));

    for (const shape of [null, undefined, 7, "feed", [], true, new Date()]) {
      closed(() => decodeFeed(shape));
    }
    class Carried {}
    closed(() => decodeFeed(new Carried()));

    const { proxy, revoke } = Proxy.revocable(validFeed(), {});
    revoke();
    closed(() => decodeFeed(proxy));

    const nonEnumerable = validFeed();
    Object.defineProperty(nonEnumerable, "requests", { enumerable: false, value: [request()] });
    closed(() => decodeFeed(nonEnumerable));
  });

  it("refuses duplicate refs, delivery reuse and broken review tuples", () => {
    const duplicateRequest = validFeed();
    duplicateRequest.requests = [request(), request()];
    closed(() => decodeFeed(duplicateRequest));

    const sharedDelivery = validFeed();
    const second = request();
    second.request_ref = OTHER_REQUEST_REF;
    second.review = { ...(second.review as Record<string, unknown>), request_ref: OTHER_REQUEST_REF };
    sharedDelivery.requests = [request(), second];
    closed(() => decodeFeed(sharedDelivery));

    const brokenTuple = validFeed();
    (brokenTuple.requests[0].review as Record<string, unknown>).delivery_id = TEAM_ID;
    closed(() => decodeFeed(brokenTuple));
  });

  it("enforces closed coverage semantics", () => {
    const partial = validFeed();
    partial.coverage = {
      state: "PARTIAL",
      reason_codes: ["LIMIT_REACHED", "REQUEST_SOURCE_CHANGED", "REQUEST_AUTHORITY_CHANGED"],
    };
    expect(decodeFeed(partial).coverage).toEqual({
      state: "PARTIAL",
      reason_codes: ["LIMIT_REACHED", "REQUEST_SOURCE_CHANGED", "REQUEST_AUTHORITY_CHANGED"],
    });
    const cases: Array<Record<string, unknown>> = [
      { state: "COMPLETE_WITHIN_SCOPE", reason_codes: ["LIMIT_REACHED"] },
      { state: "PARTIAL", reason_codes: [] },
      { state: "PARTIAL", reason_codes: ["SOMETHING_ELSE"] },
      { state: "PARTIAL", reason_codes: ["LIMIT_REACHED", "LIMIT_REACHED"] },
      { state: "PARTIAL", reason_codes: "LIMIT_REACHED" },
      { state: "EMPTY", reason_codes: [] },
      { state: "PARTIAL", reason_codes: [7] },
    ];
    for (const coverage of cases) {
      const feed = validFeed();
      feed.coverage = coverage;
      closed(() => decodeFeed(feed));
    }
  });

  it("pins source owner, scope and free-text field rules", () => {
    const feed = validFeed();
    (feed.source as Record<string, unknown>).owner = "OTHER_SOURCE";
    closed(() => decodeFeed(feed));
    const scope = validFeed();
    (scope.source as Record<string, unknown>).scope = "ALL_SHARING_REQUESTS";
    closed(() => decodeFeed(scope));

    const titles: string[] = [
      "",
      "a\u0000b",
      "line\nbreak",
      `${"t".repeat(16385)}`,
    ];
    for (const title of titles) {
      const entry = validFeed();
      (entry.requests[0].delivery as Record<string, unknown>).title = title;
      closed(() => decodeFeed(entry));
    }
    const bounded = validFeed();
    (bounded.requests[0].delivery as Record<string, unknown>).title = "t".repeat(240);
    expect(decodeFeed(bounded).requests[0].delivery.title).toHaveLength(240);
    const names = validFeed();
    (names.requests[0].audience as Record<string, unknown>).name = "";
    closed(() => decodeFeed(names));

    const counts: unknown[] = [-1, 1.5, "3", Number.MAX_SAFE_INTEGER + 1];
    for (const memberCount of counts) {
      const entry = validFeed();
      (entry.requests[0].audience as Record<string, unknown>).member_count = memberCount;
      closed(() => decodeFeed(entry));
    }
    const absentCount = validFeed();
    (absentCount.requests[0].audience as Record<string, unknown>).member_count = null;
    closed(() => decodeFeed(absentCount));

    const policy = validFeed();
    (policy.requests[0].audience as Record<string, unknown>).membership_policy = "STATIC";
    closed(() => decodeFeed(policy));
    const artifact = validFeed();
    (artifact.requests[0].delivery as Record<string, unknown>).artifact_asof = "not-a-time";
    closed(() => decodeFeed(artifact));
    const withArtifact = validFeed();
    (withArtifact.requests[0].delivery as Record<string, unknown>).artifact_asof = "2026-11-03T22:05:00.000000Z";
    expect(decodeFeed(withArtifact).requests[0].delivery.artifact_asof).toBe(
      "2026-11-03T22:05:00.000000Z",
    );
  });
});

describe("terminal session status codec", () => {
  function signedIn(): Record<string, unknown> {
    return {
      state: "SIGNED_IN",
      generation: 7,
      reason: null,
      available: true,
      principal_scope: PRINCIPAL,
      session_scope: SESSION,
    };
  }

  it("decodes the available signed-in shape as frozen plain data", () => {
    const status = decodeTerminalSessionStatus(signedIn());
    expect(status).toEqual({
      state: "SIGNED_IN",
      generation: 7,
      reason: null,
      available: true,
      principal_scope: PRINCIPAL,
      session_scope: SESSION,
    });
    expect(Object.isFrozen(status)).toBe(true);
  });

  it("keeps signed-in-without-verified-session unavailable and scope-free", () => {
    const status = decodeTerminalSessionStatus({
      state: "SIGNED_IN",
      generation: 7,
      reason: null,
      available: false,
      principal_scope: null,
      session_scope: null,
    });
    expect(status.available).toBe(false);
    expect(status.principal_scope).toBeNull();
    expect(status.session_scope).toBeNull();
  });

  it("refuses shapes that break the availability invariants", () => {
    const cases: Array<Record<string, unknown>> = [
      { ...signedIn(), available: true, session_scope: null },
      { ...signedIn(), available: true, principal_scope: null },
      { ...signedIn(), state: "SIGNED_OUT" },
      { ...signedIn(), state: "SIGNED_OUT", available: false },
      { ...signedIn(), state: "ERROR" },
      { ...signedIn(), state: "SIGNED_OUT", available: false, principal_scope: PRINCIPAL, session_scope: SESSION },
      { ...signedIn(), generation: -1 },
      { ...signedIn(), generation: 1.5 },
      { ...signedIn(), generation: Number.MAX_SAFE_INTEGER + 1 },
      { ...signedIn(), generation: "7" },
      { ...signedIn(), available: "true" },
      { ...signedIn(), reason: "SOMETHING_ELSE" },
      { ...signedIn(), reason: 7 },
      { ...signedIn(), principal_scope: "not-a-digest" },
      { ...signedIn(), session_scope: PRINCIPAL.toUpperCase() },
    ];
    for (const shape of cases) {
      closed(() => decodeTerminalSessionStatus(shape));
    }
    const unconfigured = {
      state: "UNCONFIGURED",
      generation: 0,
      reason: "NOT_CONFIGURED",
      available: false,
      principal_scope: null,
      session_scope: null,
    };
    expect(decodeTerminalSessionStatus(unconfigured).state).toBe("UNCONFIGURED");
    const error = { ...unconfigured, state: "ERROR", reason: "SESSION_CHANGED" };
    expect(decodeTerminalSessionStatus(error).reason).toBe("SESSION_CHANGED");

    for (const shape of [null, [], "status", () => undefined]) {
      closed(() => decodeTerminalSessionStatus(shape));
    }
    const extra = signedIn();
    extra.grant = "borrowed";
    closed(() => decodeTerminalSessionStatus(extra));
    const symbolExtra = signedIn();
    (symbolExtra as Record<symbol, unknown>)[Symbol("extra")] = 1;
    closed(() => decodeTerminalSessionStatus(symbolExtra));
    const getter = signedIn();
    let invocations = 0;
    Object.defineProperty(getter, "available", {
      enumerable: true,
      get() {
        invocations += 1;
        return true;
      },
    });
    closed(() => decodeTerminalSessionStatus(getter));
    expect(invocations).toBe(0);
  });
});

describe("closed error surface", () => {
  it("reports only the closed code and never inner exception text", async () => {
    expect(decodeFeed(validFeed()).requests).toHaveLength(1);
    await closedAsync(async () => decodeFeed(null));
    let observed: Error | null = null;
    try {
      decodeFeed({ viewer: { principal_scope: { toString() { throw new Error("secret"); } } } });
    } catch (error) {
      observed = error as Error;
    }
    expect(observed).not.toBeNull();
    expect(observed?.message).toBe(TERMINAL_SHARING_UNAVAILABLE);
    expect(observed?.message.includes("secret")).toBe(false);
  });
});

it("decodes the frozen actual PostgreSQL explicit-issue fixture and refuses missing schema or a foreign session", () => {
  const expected={principalScope:actualSqlFixture.viewer.principal_scope,sessionScope:actualSqlFixture.viewer.session_scope};
  const decoded=decodeTerminalSharingFeed(structuredClone(actualSqlFixture),expected);
  expect(decoded.schema).toBe("mastermind.terminal_sharing_request_feed.v1");
  expect(decoded.requests[0].audience.member_count).toBe(3);
  expect(decoded.requests[0].delivery.content_sha256).toBe(actualSqlFixture.requests[0].delivery.content_sha256);
  const missing=structuredClone(actualSqlFixture) as Record<string,unknown>;delete missing.schema;
  expect(()=>decodeTerminalSharingFeed(missing,expected)).toThrow(TERMINAL_SHARING_UNAVAILABLE);
  expect(()=>decodeTerminalSharingFeed(actualSqlFixture,{...expected,sessionScope:"f".repeat(64)})).toThrow(TERMINAL_SHARING_UNAVAILABLE);
});
