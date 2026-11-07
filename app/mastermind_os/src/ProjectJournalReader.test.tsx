// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { JOURNAL_BODY_SCHEMA, decodeProjectJournal, ProjectJournalDecodeError } from "./project-journal";
import { ProjectJournalReader, type JournalRead } from "./ProjectJournalReader";

afterEach(() => cleanup());

const WORK_REF = "WS:JOURNAL-CONSUMER";
const OTHER_REF = "WS:OTHER-PANEL";
const REPO = "mastermindx-market-intelligence/macro";
const COMMIT = "0123456789abcdef0123456789abcdef01234567";
const digest = (seed: number): string => `d${String(seed).padStart(3, "0")}${"e".repeat(60)}`;

const decision = () => ({
  id: "DEC:TLS-ALLOWLIST",
  kind: "DECISION",
  title: "Restrict outbound TLS to the release allowlist",
  why: "Outbound TLS beyond the allowlist leaked request metadata.",
  next_action: null,
  actor: "ops-agent",
  recorded_at: "2026-01-15",
  time_basis: "DECLARED_DECISION_DATE",
  source: {
    repository: REPO, commit: COMMIT,
    path: "agentos/decisions/DEC-TLS-ALLOWLIST.md", content_sha256: digest(1),
  },
});
const discovery = () => ({
  id: "DSC:R2-PUBLIC-READS",
  kind: "DISCOVERY",
  title: "Public R2 data-plane reads serve exact keys",
  why: "Use exact source keys in the reader.",
  next_action: null,
  actor: null,
  recorded_at: "2026-02-03",
  time_basis: "DECLARED_VERIFICATION_DATE",
  source: {
    repository: REPO, commit: COMMIT,
    path: "agentos/discoveries/DSC-R2-PUBLIC-READS.md", content_sha256: digest(2),
  },
});
const handoff = () => ({
  id: "HND:journal-consumer",
  kind: "HANDOFF",
  title: "Hand off the journal consumer wiring",
  why: null,
  next_action: null,
  actor: null,
  recorded_at: "2026-02-10T08:15:00Z",
  time_basis: "GIT_RECORD_COMMIT_TIME",
  source: {
    repository: REPO, commit: COMMIT,
    path: "agentos/handoffs/journal-consumer.md", content_sha256: digest(3),
  },
});
// Synthetic test raw body only; this is not production history.
const body = (workRef: string = WORK_REF) => ({
  schema: JOURNAL_BODY_SCHEMA,
  selection: { work_ref: workRef },
  availability: "AVAILABLE",
  source: { repository: REPO, commit: COMMIT },
  journal: {
    entries: [decision(), discovery(), handoff()],
    coverage: { state: "BOUNDED_RECORD_SAMPLE", scanned: 9, matched: 3, omitted: 6, invalid: 0 },
  },
  reason_codes: [],
});
const unavailableBody = (reason: string): Record<string, unknown> => ({
  schema: JOURNAL_BODY_SCHEMA,
  selection: { work_ref: WORK_REF },
  availability: "UNAVAILABLE",
  source: null,
  journal: null,
  reason_codes: [reason],
});
const clone = (): Record<string, unknown> => body() as unknown as Record<string, unknown>;
const firstEntry = (raw: Record<string, unknown>) =>
  (raw.journal as { entries: Array<Record<string, unknown>> }).entries[0];
const nthEntry = (raw: Record<string, unknown>, index: number) =>
  (raw.journal as { entries: Array<Record<string, unknown>> }).entries[index];
const coverage = (raw: Record<string, unknown>) =>
  (raw.journal as { coverage: Record<string, unknown> }).coverage;
const handoffEntry = (index: number) => ({
  id: `HND:seq-${index}`,
  kind: "HANDOFF",
  title: `Handoff ${index}`,
  why: null,
  next_action: null,
  actor: null,
  recorded_at: null,
  time_basis: "UNAVAILABLE",
  source: {
    repository: REPO, commit: COMMIT,
    path: `agentos/handoffs/seq-${index}.md`, content_sha256: digest(index + 10),
  },
});

describe("project journal strict decoder", () => {
  it("decodes a valid AVAILABLE body with all three kinds and returns a detached copy", () => {
    const raw = body();
    const decoded = decodeProjectJournal(raw, WORK_REF);
    expect(decoded.schema).toBe(JOURNAL_BODY_SCHEMA);
    expect(decoded.availability).toBe("AVAILABLE");
    expect(decoded.selection).toEqual({ work_ref: WORK_REF });
    expect(decoded.source).toEqual({ repository: REPO, commit: COMMIT });
    expect(decoded.reason_codes).toEqual([]);
    if (decoded.journal === null || decoded.source === null) throw new Error("expected an AVAILABLE journal");
    const { entries, coverage: sample } = decoded.journal;
    expect(entries.map(entry => entry.id)).toEqual(["DEC:TLS-ALLOWLIST", "DSC:R2-PUBLIC-READS", "HND:journal-consumer"]);
    expect(entries[0].time_basis).toBe("DECLARED_DECISION_DATE");
    expect(entries[1].why).toBe("Use exact source keys in the reader.");
    expect(entries[1].actor).toBeNull();
    expect(entries[2].recorded_at).toBe("2026-02-10T08:15:00Z");
    expect(entries[2].time_basis).toBe("GIT_RECORD_COMMIT_TIME");
    expect(entries[2].source.path).toBe("agentos/handoffs/journal-consumer.md");
    expect(sample).toEqual({ state: "BOUNDED_RECORD_SAMPLE", scanned: 9, matched: 3, omitted: 6, invalid: 0 });
    // Detached copy: raw mutations afterwards never leak into the decoded document.
    (raw.journal as { entries: unknown[] }).entries.push({ id: "HND:late" });
    expect(decoded.journal.entries).toHaveLength(3);
    entries[0].title = "mutated";
    expect(firstEntry(raw as unknown as Record<string, unknown>).title).toBe("Restrict outbound TLS to the release allowlist");
    // A JSON text body is accepted as the raw HTTP body as well.
    expect(decodeProjectJournal(JSON.stringify(body()), WORK_REF).availability).toBe("AVAILABLE");
  });

  it("rejects ok wrappers, extra keys, missing keys and non-object bodies", () => {
    expect(() => decodeProjectJournal({ ok: true, body: body() }, WORK_REF)).toThrow(ProjectJournalDecodeError);
    const extra = clone();
    extra.note = "extra";
    expect(() => decodeProjectJournal(extra, WORK_REF)).toThrow(/unexpected key/);
    const missing = clone();
    delete missing.availability;
    expect(() => decodeProjectJournal(missing, WORK_REF)).toThrow(/missing key/);
    const wrongSchema = clone();
    wrongSchema.schema = "mastermind.workspace_project_journal.v2";
    expect(() => decodeProjectJournal(wrongSchema, WORK_REF)).toThrow(/schema/);
    const nested = clone();
    (nested.selection as Record<string, unknown>).extra = 1;
    expect(() => decodeProjectJournal(nested, WORK_REF)).toThrow(/unexpected key/);
    expect(() => decodeProjectJournal("not json at all {", WORK_REF)).toThrow(ProjectJournalDecodeError);
    expect(() => decodeProjectJournal(42, WORK_REF)).toThrow(/JSON object/);
  });

  it("rejects selection mismatches and invalid work refs", () => {
    expect(() => decodeProjectJournal(body(), OTHER_REF)).toThrow(/match the requested workRef/);
    expect(() => decodeProjectJournal(body(OTHER_REF), WORK_REF)).toThrow(/match the requested workRef/);
    expect(() => decodeProjectJournal(body(), "WS:lower-key")).toThrow(/UPPER-KEBAB/);
    expect(() => decodeProjectJournal(body(), "WS:A")).toThrow(/UPPER-KEBAB/);
    expect(() => decodeProjectJournal(body(), "WS:TRAILING-")).toThrow(/UPPER-KEBAB/);
    expect(() => decodeProjectJournal(body(), "OTHER-REF")).toThrow(/UPPER-KEBAB/);
  });

  it("rejects boolean, unsafe, fractional and negative counts and bad coverage claims", () => {
    const booleanCount = clone();
    coverage(booleanCount).matched = true;
    expect(() => decodeProjectJournal(booleanCount, WORK_REF)).toThrow(/safe integer/);
    const unsafe = clone();
    coverage(unsafe).scanned = 2 ** 53;
    expect(() => decodeProjectJournal(unsafe, WORK_REF)).toThrow(/safe integer/);
    const fractional = clone();
    coverage(fractional).invalid = 1.5;
    expect(() => decodeProjectJournal(fractional, WORK_REF)).toThrow(/safe integer/);
    const negative = clone();
    coverage(negative).omitted = -1;
    expect(() => decodeProjectJournal(negative, WORK_REF)).toThrow(/safe integer/);
    const wrongState = clone();
    coverage(wrongState).state = "FULL_HISTORY";
    expect(() => decodeProjectJournal(wrongState, WORK_REF)).toThrow(/BOUNDED_RECORD_SAMPLE/);
    const underMatched = clone();
    coverage(underMatched).matched = 2;
    expect(() => decodeProjectJournal(underMatched, WORK_REF)).toThrow(/matched/);
    const underOmitted = clone();
    coverage(underOmitted).matched = 5;
    coverage(underOmitted).omitted = 1;
    expect(() => decodeProjectJournal(underOmitted, WORK_REF)).toThrow(/omitted/);
  });

  it("rejects duplicate ids, oversized entry lists and over-budget bodies", () => {
    const duplicate = clone();
    (duplicate.journal as { entries: unknown[] }).entries.push({ ...(firstEntry(duplicate) as object) });
    expect(() => decodeProjectJournal(duplicate, WORK_REF)).toThrow(/duplicate entry id/);
    const tooMany = clone();
    (tooMany.journal as { entries: unknown[] }).entries = Array.from({ length: 33 }, (_, index) => handoffEntry(index));
    expect(() => decodeProjectJournal(tooMany, WORK_REF)).toThrow(/32 entries/);
    const overBudget = clone();
    const entries = (overBudget.journal as { entries: Array<Record<string, unknown>> }).entries;
    entries.length = 0;
    entries.push(handoffEntry(0));
    entries[0].title = "x".repeat(140000);
    expect(() => decodeProjectJournal(overBudget, WORK_REF)).toThrow(/byte budget/);
  });

  it("rejects malformed record fields", () => {
    const badCommit = clone();
    (badCommit.source as Record<string, unknown>).commit = COMMIT.toUpperCase();
    expect(() => decodeProjectJournal(badCommit, WORK_REF)).toThrow(/40 lowercase hex/);
    const shortCommit = clone();
    (shortCommit.source as Record<string, unknown>).commit = COMMIT.slice(1);
    expect(() => decodeProjectJournal(shortCommit, WORK_REF)).toThrow(/40 lowercase hex/);
    const badDigest = clone();
    (firstEntry(badDigest).source as Record<string, unknown>).content_sha256 = "z".repeat(64);
    expect(() => decodeProjectJournal(badDigest, WORK_REF)).toThrow(/64 lowercase hex/);
    const badDay = clone();
    firstEntry(badDay).recorded_at = "2026-02-30";
    expect(() => decodeProjectJournal(badDay, WORK_REF)).toThrow(/calendar date/);
    const nonLeap = clone();
    firstEntry(nonLeap).recorded_at = "2025-02-29";
    expect(() => decodeProjectJournal(nonLeap, WORK_REF)).toThrow(/calendar date/);
    const looseDay = clone();
    firstEntry(looseDay).recorded_at = "2026-2-3";
    expect(() => decodeProjectJournal(looseDay, WORK_REF)).toThrow(/calendar date/);
    const badStamp = clone();
    nthEntry(badStamp, 2).recorded_at = "2026-02-10T08:15:00";
    expect(() => decodeProjectJournal(badStamp, WORK_REF)).toThrow(/timezone/);
    const noOffsetColon = clone();
    nthEntry(noOffsetColon, 2).recorded_at = "2026-02-10T08:15:00+0800";
    expect(() => decodeProjectJournal(noOffsetColon, WORK_REF)).toThrow(/timezone/);
    const handoffNullStamp = clone();
    nthEntry(handoffNullStamp, 2).recorded_at = null;
    expect(() => decodeProjectJournal(handoffNullStamp, WORK_REF)).toThrow(/time_basis/);
    const wrongBasis = clone();
    firstEntry(wrongBasis).time_basis = "DECLARED_VERIFICATION_DATE";
    expect(() => decodeProjectJournal(wrongBasis, WORK_REF)).toThrow(/time_basis/);
    const wrongPath = clone();
    (firstEntry(wrongPath).source as Record<string, unknown>).path = "agentos/decisions/DSC-TLS-ALLOWLIST.md";
    expect(() => decodeProjectJournal(wrongPath, WORK_REF)).toThrow(/path must be/);
    const foreignRepo = clone();
    (firstEntry(foreignRepo).source as Record<string, unknown>).repository = "other/repo";
    expect(() => decodeProjectJournal(foreignRepo, WORK_REF)).toThrow(/match the document source/);
    const foreignCommit = clone();
    (firstEntry(foreignCommit).source as Record<string, unknown>).commit = "f".repeat(40);
    expect(() => decodeProjectJournal(foreignCommit, WORK_REF)).toThrow(/match the document source/);
    const emptyTitle = clone();
    firstEntry(emptyTitle).title = "";
    expect(() => decodeProjectJournal(emptyTitle, WORK_REF)).toThrow(/title/);
    const longTitle = clone();
    firstEntry(longTitle).title = "x".repeat(4097);
    expect(() => decodeProjectJournal(longTitle, WORK_REF)).toThrow(/title/);
    const longActor = clone();
    firstEntry(longActor).actor = "a".repeat(257);
    expect(() => decodeProjectJournal(longActor, WORK_REF)).toThrow(/actor/);
    const badId = clone();
    firstEntry(badId).id = "DEC:lower-key";
    expect(() => decodeProjectJournal(badId, WORK_REF)).toThrow(/DEC:UPPER-KEBAB/);
    const badStem = clone();
    nthEntry(badStem, 2).id = "HND:has space";
    expect(() => decodeProjectJournal(badStem, WORK_REF)).toThrow(/HND:<stem>/);
    const unknownKind = clone();
    firstEntry(unknownKind).kind = "EVENT";
    expect(() => decodeProjectJournal(unknownKind, WORK_REF)).toThrow(/kind/);
  });

  it("decodes UNAVAILABLE bodies with exactly one reason and refuses contradictory envelopes", () => {
    const decoded = decodeProjectJournal(unavailableBody("RECORD_NOT_FOUND"), WORK_REF);
    expect(decoded.availability).toBe("UNAVAILABLE");
    expect(decoded.source).toBeNull();
    expect(decoded.journal).toBeNull();
    expect(decoded.reason_codes).toEqual(["RECORD_NOT_FOUND"]);
    const withReasons = clone();
    withReasons.reason_codes = ["SOURCE_UNAVAILABLE"];
    expect(() => decodeProjectJournal(withReasons, WORK_REF)).toThrow(/no reason codes/);
    const noReason = unavailableBody("RECORD_NOT_FOUND");
    noReason.reason_codes = [];
    expect(() => decodeProjectJournal(noReason, WORK_REF)).toThrow(/exactly one/);
    const twoReasons = unavailableBody("RECORD_NOT_FOUND");
    twoReasons.reason_codes = ["RECORD_NOT_FOUND", "RECORD_INVALID"];
    expect(() => decodeProjectJournal(twoReasons, WORK_REF)).toThrow(/exactly one/);
    const unknownReason = unavailableBody("WEATHER");
    expect(() => decodeProjectJournal(unknownReason, WORK_REF)).toThrow(/reason code/);
    const withSource = unavailableBody("SOURCE_UNAVAILABLE");
    withSource.source = { repository: REPO, commit: COMMIT };
    expect(() => decodeProjectJournal(withSource, WORK_REF)).toThrow(/source null/);
    const withJournal = unavailableBody("SOURCE_UNAVAILABLE");
    withJournal.journal = body().journal;
    expect(() => decodeProjectJournal(withJournal, WORK_REF)).toThrow(/journal null/);
    const nullSourceAvailable = clone();
    nullSourceAvailable.source = null;
    expect(() => decodeProjectJournal(nullSourceAvailable, WORK_REF)).toThrow(/source object/);
    const nullJournalAvailable = clone();
    nullJournalAvailable.journal = null;
    expect(() => decodeProjectJournal(nullJournalAvailable, WORK_REF)).toThrow(/journal object/);
    const badAvailability = clone();
    badAvailability.availability = "PARTIAL";
    expect(() => decodeProjectJournal(badAvailability, WORK_REF)).toThrow(/availability/);
  });
});

type DeferredRead = {
  workRef: string;
  signal: AbortSignal;
  resolve: (value: unknown) => void;
  reject: (cause: unknown) => void;
};
const deferredReads = (): { reads: DeferredRead[]; read: JournalRead } => {
  const reads: DeferredRead[] = [];
  const read: JournalRead = request =>
    new Promise((resolve, reject) => {
      reads.push({ workRef: request.workRef, signal: request.signal, resolve, reject });
    });
  return { reads, read };
};
const permitted = () => true;
const props = (overrides?: {
  workRef?: string;
  generation?: string | number;
  authGeneration?: string | number;
  locale?: "en" | "zh-CN";
}) => ({
  selection: { workRef: overrides?.workRef ?? WORK_REF, rootJobId: "JOB-7" },
  locale: overrides?.locale ?? ("en" as const),
  generation: overrides?.generation ?? 1,
  authGeneration: overrides?.authGeneration ?? 1,
  canRead: permitted,
});
const READ_BUTTON = "Read project journal";
const clickRead = (name: string = READ_BUTTON) => fireEvent.click(screen.getByRole("button", { name }));

describe("ProjectJournalReader explicit reads", () => {
  it("does not read on render and explains that records have not been read", () => {
    const { reads, read } = deferredReads();
    render(<ProjectJournalReader {...props()} read={read} />);
    expect(reads).toHaveLength(0);
    expect(screen.getByText(/has not been read/)).toBeTruthy();
    expect(screen.queryByText(/Records in this view/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Refresh" })).toBeNull();
  });

  it("reads once on the explicit button and renders the bounded sample with all three kinds", async () => {
    const { reads, read } = deferredReads();
    render(<ProjectJournalReader {...props()} read={read} />);
    clickRead();
    expect(reads).toHaveLength(1);
    expect(reads[0].workRef).toBe(WORK_REF);
    expect(reads[0].signal).toBeInstanceOf(AbortSignal);
    expect(screen.getByText(/Reading the project journal/)).toBeTruthy();
    await act(async () => {
      reads[0].resolve(body());
    });
    expect(screen.getByText(/Records in this view/)).toBeTruthy();
    expect(screen.getByText("Restrict outbound TLS to the release allowlist")).toBeTruthy();
    expect(screen.getByText("Public R2 data-plane reads serve exact keys")).toBeTruthy();
    expect(screen.getByText("Hand off the journal consumer wiring")).toBeTruthy();
    expect(screen.getByText("Decision")).toBeTruthy();
    expect(screen.getByText("Discovery")).toBeTruthy();
    expect(screen.getByText("Handoff")).toBeTruthy();
    expect(screen.getByText("Decision date: 2026-01-15")).toBeTruthy();
    expect(screen.getByText("Verification date: 2026-02-03")).toBeTruthy();
    expect(screen.getByText("Git record commit time: 2026-02-10T08:15:00Z")).toBeTruthy();
    expect(screen.getByText(/actor: ops-agent/)).toBeTruthy();
    expect(screen.getByText(COMMIT)).toBeTruthy();
    expect(screen.getByText("Scanned")).toBeTruthy();
    expect(screen.getByText("9")).toBeTruthy();
    expect(screen.getByText("Omitted")).toBeTruthy();
    expect(screen.getByText("6")).toBeTruthy();
    expect(screen.getByText(/Recorded source snapshots/)).toBeTruthy();
    expect(screen.getByText(/never implies execution, review, acceptance or release/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeTruthy();
  });

  it("renders UNAVAILABLE as a typed answer with reason disclosure and no zero claim", async () => {
    const { reads, read } = deferredReads();
    render(<ProjectJournalReader {...props()} read={read} />);
    clickRead();
    await act(async () => {
      reads[0].resolve(unavailableBody("RECORD_NOT_FOUND"));
    });
    expect(screen.getByText("RECORD_NOT_FOUND")).toBeTruthy();
    expect(screen.getByText(/Unavailable does not mean/)).toBeTruthy();
    expect(screen.queryByText(/Records in this view/)).toBeNull();
    expect(screen.queryByText(/project may have other history/)).toBeNull();
    // A completed UNAVAILABLE answer is still a read: refreshing to re-check is allowed.
    expect(screen.getByRole("button", { name: "Refresh" })).toBeTruthy();
  });

  it("renders the bounded-sample empty note and partial-sample coverage honestly", async () => {
    const { reads, read } = deferredReads();
    render(<ProjectJournalReader {...props()} read={read} />);
    clickRead();
    const empty = clone();
    (empty.journal as { entries: unknown[] }).entries = [];
    coverage(empty).matched = 0;
    coverage(empty).omitted = 0;
    await act(async () => {
      reads[0].resolve(empty);
    });
    expect(screen.getByText(/No records were supplied in this sample/)).toBeTruthy();
    expect(screen.getByText(/project may have other history/)).toBeTruthy();
    expect(screen.getByText(/Records in this view/)).toBeTruthy();
    expect(screen.getByText(/Invalid/)).toBeTruthy();
  });

  it("shows source provenance for a selected recorded change and closes again", async () => {
    const { reads, read } = deferredReads();
    render(<ProjectJournalReader {...props()} read={read} />);
    clickRead();
    await act(async () => {
      reads[0].resolve(body());
    });
    fireEvent.click(screen.getByRole("button", { name: /Restrict outbound TLS/ }));
    const sourceDetails = screen.getByText("Source details").closest("details")!;
    expect(sourceDetails.open).toBe(false);
    fireEvent.click(screen.getByText("Source details"));
    expect(sourceDetails.open).toBe(true);
    expect(screen.getByText("agentos/decisions/DEC-TLS-ALLOWLIST.md")).toBeTruthy();
    expect(screen.getByText(digest(1))).toBeTruthy();
    expect(screen.getByText("AgentOS")).toBeTruthy();
    expect(screen.getAllByText(WORK_REF).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Outbound TLS beyond the allowlist leaked request metadata.")).toBeTruthy();
    expect(screen.getAllByText("Not recorded in the source record.").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Close detail" }));
    expect(screen.queryByText("agentos/decisions/DEC-TLS-ALLOWLIST.md")).toBeNull();
  });

  it("aborts and conceals on selection identity change, ignoring the late reply", async () => {
    const { reads, read } = deferredReads();
    const view = render(<ProjectJournalReader {...props()} read={read} />);
    clickRead();
    expect(reads).toHaveLength(1);
    view.rerender(<ProjectJournalReader {...props({ workRef: OTHER_REF })} read={read} />);
    expect(reads[0].signal.aborted).toBe(true);
    expect(screen.getByText(/has not been read/)).toBeTruthy();
    await act(async () => {
      reads[0].resolve(body());
    });
    expect(screen.queryByText(/Restrict outbound TLS/)).toBeNull();
    expect(reads).toHaveLength(1);
    clickRead();
    expect(reads).toHaveLength(2);
    expect(reads[1].workRef).toBe(OTHER_REF);
    await act(async () => {
      reads[1].resolve(body(OTHER_REF));
    });
    expect(screen.getByText(/Records in this view/)).toBeTruthy();
  });

  it("aborts pending reads and conceals on generation or auth generation change", async () => {
    const { reads, read } = deferredReads();
    const view = render(<ProjectJournalReader {...props()} read={read} />);
    clickRead();
    await act(async () => {
      reads[0].resolve(body());
    });
    expect(screen.getByText(/Records in this view/)).toBeTruthy();
    view.rerender(<ProjectJournalReader {...props({ generation: 2 })} read={read} />);
    expect(screen.queryByText(/Records in this view/)).toBeNull();
    expect(screen.getByText(/has not been read/)).toBeTruthy();
    expect(reads).toHaveLength(1);
    clickRead();
    expect(reads).toHaveLength(2);
    view.rerender(<ProjectJournalReader {...props({ generation: 2, authGeneration: 2 })} read={read} />);
    expect(reads[1].signal.aborted).toBe(true);
    await act(async () => {
      reads[1].resolve(body());
    });
    expect(screen.queryByText(/Records in this view/)).toBeNull();
    expect(screen.getByText(/has not been read/)).toBeTruthy();
  });

  it("clears on canRead revocation and does not redisplay after re-grant with the same generation", async () => {
    const { reads, read } = deferredReads();
    const view = render(<ProjectJournalReader {...props()} read={read} canRead={() => true} />);
    clickRead();
    await act(async () => {
      reads[0].resolve(body());
    });
    expect(screen.getByText(/Records in this view/)).toBeTruthy();
    view.rerender(<ProjectJournalReader {...props()} read={read} canRead={() => false} />);
    expect(screen.queryByText(/Records in this view/)).toBeNull();
    expect(screen.getByText(/was revoked after a read/)).toBeTruthy();
    view.rerender(<ProjectJournalReader {...props()} read={read} canRead={() => true} />);
    clickRead();
    expect(reads).toHaveLength(1);
    expect(screen.queryByText(/Records in this view/)).toBeNull();
    expect(screen.getByText(/does not redisplay/)).toBeTruthy();
    view.rerender(<ProjectJournalReader {...props({ generation: 2 })} read={read} canRead={() => true} />);
    clickRead();
    expect(reads).toHaveLength(2);
    await act(async () => {
      reads[1].resolve(body());
    });
    expect(screen.getByText(/Records in this view/)).toBeTruthy();
  });

  it("shows the strict-decode error state with retry guidance and supports an explicit retry", async () => {
    const { reads, read } = deferredReads();
    render(<ProjectJournalReader {...props()} read={read} />);
    clickRead();
    await act(async () => {
      reads[0].resolve(body(OTHER_REF)); // selection guard must refuse this body
    });
    expect(screen.getByText(/could not be verified/)).toBeTruthy();
    expect(screen.getByText(/rest of the workspace keeps working/)).toBeTruthy();
    expect(screen.getByText(/to retry/)).toBeTruthy();
    clickRead();
    expect(reads).toHaveLength(2);
    await act(async () => {
      reads[1].resolve(body());
    });
    expect(screen.getByText(/Records in this view/)).toBeTruthy();
  });

  it("distinguishes transport failure from decode failure", async () => {
    const { reads, read } = deferredReads();
    render(<ProjectJournalReader {...props()} read={read} />);
    clickRead();
    await act(async () => {
      reads[0].reject(new Error("network down"));
    });
    expect(screen.getByText(/journal source could not be reached/)).toBeTruthy();
    clickRead();
    await act(async () => {
      reads[1].resolve(body());
    });
    expect(screen.getByText(/Records in this view/)).toBeTruthy();
  });

  it("blocks reads when no transport is provided or the selection is not a WS ref", () => {
    render(<ProjectJournalReader {...props()} />);
    clickRead();
    expect(screen.getByText(/reader is unavailable in this workspace/)).toBeTruthy();
    cleanup();
    const blocked = deferredReads();
    render(<ProjectJournalReader {...props({ workRef: "WS:lower-key" })} read={blocked.read} />);
    clickRead();
    expect(blocked.reads).toHaveLength(0);
    expect(screen.getByText(/no qualified workstream reference/)).toBeTruthy();
  });

  it("renders localized zh-CN copy and switches back", async () => {
    const { reads, read } = deferredReads();
    const view = render(<ProjectJournalReader {...props({ locale: "zh-CN" })} read={read} />);
    expect(screen.getByText("项目日志")).toBeTruthy();
    expect(screen.getByRole("button", { name: "读取项目日志" })).toBeTruthy();
    expect(screen.getByText(/尚未读取日志/)).toBeTruthy();
    clickRead("读取项目日志");
    await act(async () => {
      reads[0].resolve(body());
    });
    expect(screen.getByText(/此视图中的记录/)).toBeTruthy();
    expect(screen.getByText("已扫描")).toBeTruthy();
    expect(screen.getByText(/可能未包含其他历史记录/)).toBeTruthy();
    expect(screen.getByText(/记录的来源快照/)).toBeTruthy();
    view.rerender(<ProjectJournalReader {...props()} read={read} />);
    expect(screen.getByText("Project journal")).toBeTruthy();
    expect(screen.queryByText("记录的变更")).toBeNull();
  });
});

it("reads a catalogued workstream without a Runtime root and decodes actual canonical-owner fixture bytes", async () => {
  const canonical = (await import("./fixtures/project-journal-canonical-owner.json")).default;
  expect(decodeProjectJournal(canonical, "WS:ONE").journal?.entries.map(row => row.kind)).toEqual(["HANDOFF", "DECISION", "DISCOVERY"]);
  const reads = deferredReads();
  render(<ProjectJournalReader {...props({workRef: "WS:ONE"})} selection={{workRef: "WS:ONE"}} read={reads.read} />);
  clickRead();
  expect(reads.reads[0].workRef).toBe("WS:ONE");
  await act(async () => { reads.reads[0].resolve(canonical); });
  expect(screen.getByText("The original implementation returned.")).toBeTruthy();
  expect(screen.queryByText(/Parent root/)).toBeNull();
});

it("denies absent authority and clears a same-callback revocation before stale content can return", async () => {
  const reads = deferredReads();
  const blocked = render(<ProjectJournalReader {...props()} read={reads.read} canRead={undefined} />);
  clickRead(); expect(reads.reads).toHaveLength(0); blocked.unmount();
  let allowed = true;
  const canRead = () => allowed;
  const view = render(<ProjectJournalReader {...props()} read={reads.read} canRead={canRead} />);
  clickRead(); await act(async () => { reads.reads[0].resolve(body()); });
  expect(screen.getByText(/Records in this view/)).toBeTruthy();
  allowed = false;
  view.rerender(<ProjectJournalReader {...props()} read={reads.read} canRead={canRead} />);
  expect(screen.queryByText(/Records in this view/)).toBeNull();
  allowed = true;
  view.rerender(<ProjectJournalReader {...props()} read={reads.read} canRead={canRead} />);
  clickRead(); expect(reads.reads).toHaveLength(1);
  expect(screen.queryByText(/Records in this view/)).toBeNull();
});

it("rechecks actual authority when a pending read resolves without a parent render", async () => {
  const reads = deferredReads(); let allowed = true; const canRead = () => allowed;
  render(<ProjectJournalReader {...props()} read={reads.read} canRead={canRead} />);
  clickRead(); allowed = false;
  await act(async () => { reads.reads[0].resolve(body()); });
  expect(screen.queryByText(/Records in this view/)).toBeNull();
  expect(screen.getByText(/was revoked after a read/)).toBeTruthy();
});

it("rejects newline and impossible time/source tuples while preserving canonical numeric keys", () => {
  const numeric = body("WS:1A");
  numeric.journal.entries[0] = {...decision(), id: "DEC:1", source: {...decision().source, path: "agentos/decisions/DEC-1.md"}};
  expect(decodeProjectJournal(numeric,"WS:1A").journal?.entries[0].id).toBe("DEC:1");
  const mutations = [
    (value: any) => { value.source.commit += "\n"; },
    (value: any) => { value.journal.entries[0].recorded_at += "\n"; },
    (value: any) => { value.journal.entries[2].recorded_at = "2026-02-10T08:15:00+99:99"; },
    (value: any) => { value.journal.coverage.scanned = 0; },
    (value: any) => { value.journal.entries[0].next_action = "Invented next action"; },
  ];
  for (const mutate of mutations) {const invalid=body(); mutate(invalid); expect(() => decodeProjectJournal(invalid,WORK_REF)).toThrow();}
  expect(() => decodeProjectJournal(body(WORK_REF+"\n"),WORK_REF+"\n")).toThrow();
});
