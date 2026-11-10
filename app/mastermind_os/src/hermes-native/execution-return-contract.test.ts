/** Execution-return contract tests: fail-closed parsing, closed vocabularies,
 * digest/canonical-JSON parity with the Python owner via the committed
 * fixtures, and the stage-ladder + idempotency laws. */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  ACCEPTANCE_STATES, CHECK_CONCLUSIONS, CHECKS_STATES, DELIVERY_SCHEMA,
  DELIVERY_STATES, EXECUTION_RETURN_STAGES, INSTALLATION_STATES, MERGE_STATES,
  REFUSAL_CODE_PATTERN, RECORD_SCHEMA, ExecutionReturnContractError,
  canonicalJson, deriveStage, mintSubmissionId, parseExecutionReturn,
  parseExecutionReturnDelivery, recordDigest,
} from "./execution-return-contract";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtureDir = path.resolve(here, "../../../../integrations/mmos/fixtures/execution_return_v1");
const vocabularies = JSON.parse(readFileSync(path.join(fixtureDir, "vocabularies.json"), "utf8"));
const sampleRecord: Record<string, unknown> = JSON.parse(
  readFileSync(path.join(fixtureDir, "sample_record.json"), "utf8"));
const sampleReceipt: Record<string, unknown> = JSON.parse(
  readFileSync(path.join(fixtureDir, "sample_receipt.json"), "utf8"));

const reject = async (code: string | null, fn: () => unknown | Promise<unknown>) => {
  const guarded = async () => { await fn(); };
  if (code === null) { await expect(guarded).rejects.toThrow(ExecutionReturnContractError); return; }
  await expect(guarded).rejects.toThrow(expect.objectContaining({ code }) as Error);
};

describe("cross-language vocabulary parity (committed fixture)", () => {
  it("the TypeScript vocabularies equal the fixture the Python owner generates", () => {
    expect([...EXECUTION_RETURN_STAGES]).toEqual(vocabularies.stages);
    expect([...ACCEPTANCE_STATES]).toEqual(vocabularies.acceptance_states);
    expect([...CHECK_CONCLUSIONS]).toEqual(vocabularies.check_conclusions);
    expect([...CHECKS_STATES]).toEqual(vocabularies.checks_states);
    expect([...MERGE_STATES]).toEqual(vocabularies.merge_states);
    expect([...INSTALLATION_STATES]).toEqual(vocabularies.installation_states);
    expect([...DELIVERY_STATES]).toEqual(vocabularies.delivery_states);
    expect(REFUSAL_CODE_PATTERN).toBe(vocabularies.refusal_code_pattern);
    expect(RECORD_SCHEMA).toBe(vocabularies.record_schema);
    expect(DELIVERY_SCHEMA).toBe(vocabularies.delivery_receipt_schema);
  });
});

describe("sample record parity (Python-produced, TS-verified)", () => {
  it("parses the committed sample and verifies its digest byte-for-byte", async () => {
    const parsed = await parseExecutionReturn(sampleRecord);
    expect(parsed.stage).toBe("installed_unknown");
    expect(parsed.github.merge_state).toBe("merged");
    expect(parsed.github.installation).toBe("claimed_unproven");
    expect(parsed.acceptance).toBe("not_accepted");
    // The sample bakes in an acceptance-forgery attempt: projected, refused.
    expect(parsed.acceptance_claim_refused).toBe(true);
    expect(parsed.result.text).toContain("→"); // unicode survives canonically
  });

  it("canonical JSON reproduces the Python canonicalization on the sample", async () => {
    // Re-serializing the parsed content through the TS canonicalizer must
    // re-derive the SAME digest Python embedded in the fixture.
    const rebuilt = { ...sampleRecord };
    delete (rebuilt as Record<string, unknown>).digest;
    delete (rebuilt as Record<string, unknown>).return_id;
    expect(await recordDigest(sampleRecord)).toBe(sampleRecord.digest);
    expect(canonicalJson({ b: 1, a: [2, { d: null, c: "x" }] }))
      .toBe('{"a":[2,{"c":"x","d":null}],"b":1}');
  });
});

describe("fail-closed record parsing", () => {
  it("refuses every kind of drift with a typed code", async () => {
    await reject("INVALID_SCHEMA", () => parseExecutionReturn({ ...sampleRecord, schema: "mastermind.execution_return/v2" }));
    await reject("INVALID_VOCABULARY", () => parseExecutionReturn({ ...sampleRecord, stage: "shipped" }));
    await reject("INVALID_ACCEPTANCE", () => parseExecutionReturn({ ...sampleRecord, acceptance: "accepted" }));
    await reject("INVALID_FIELDS", () => parseExecutionReturn({ ...sampleRecord, installed: true }));
    const missing = { ...sampleRecord } as Record<string, unknown>;
    delete missing.github;
    await reject("INVALID_FIELDS", () => parseExecutionReturn(missing));
    await reject("DIGEST_MISMATCH", () => parseExecutionReturn({ ...sampleRecord, digest: "0".repeat(64) }));
    await reject("INVALID_RETURN_ID", () => parseExecutionReturn({ ...sampleRecord, return_id: "execret-" + "f".repeat(32) }));
    await reject("INVALID_VOCABULARY", () => parseExecutionReturn({
      ...sampleRecord, github: { ...(sampleRecord.github as object),
        checks: [{ name: "ci", conclusion: "pending" }] }, }));
    await reject("INVALID_NUMBER", () => parseExecutionReturn({
      ...sampleRecord, github: { ...(sampleRecord.github as object), pr_number: -1 } }));
  });

  it("refuses a re-forged consistent record whose stage outruns its evidence", async () => {
    // Downgrade the stage, recompute digest + return_id so ONLY the honesty
    // invariant can catch it (mirrors the Python re-forge test).
    const forged: Record<string, unknown> = { ...sampleRecord, stage: "result_only" };
    delete forged.return_id;
    const digest = await recordDigest(forged);
    forged.digest = digest;
    forged.return_id = "execret-" + digest.slice(0, 32);
    await reject("STAGE_EXCEEDS_EVIDENCE", () => parseExecutionReturn(forged));
  });
});

describe("stage ladder mirrors the Python derivation", () => {
  const github = (over: Partial<Parameters<typeof deriveStage>[0]>) => ({
    branch: null, pr_number: null, pr_url: null, checks: null,
    checks_state: "unknown", merge_state: "unknown", installation: "none_claimed",
    ...over,
  });
  it("advances only as far as evidence proves; unknown never green", () => {
    expect(deriveStage(github({}))).toBe("result_only");
    expect(deriveStage(github({ branch: "b" }))).toBe("branch_pushed");
    expect(deriveStage(github({ branch: "b", pr_number: 7 }))).toBe("pr_open");
    expect(deriveStage(github({ branch: "b", pr_number: 7, checks_state: "unknown" }))).toBe("pr_open");
    expect(deriveStage(github({ branch: "b", pr_number: 7, checks_state: "green" }))).toBe("checks_green");
    expect(deriveStage(github({ branch: "b", pr_number: 7, checks_state: "failed" }))).toBe("checks_failed");
    expect(deriveStage(github({ branch: "b", pr_number: 7, checks_state: "green", merge_state: "not_merged" }))).toBe("checks_green");
    expect(deriveStage(github({ branch: "b", pr_number: 7, checks_state: "green", merge_state: "merged" }))).toBe("merged");
    expect(deriveStage(github({ branch: "b", pr_number: 7, checks_state: "green", merge_state: "merged", installation: "claimed_unproven" }))).toBe("installed_unknown");
    expect(deriveStage(github({ installation: "claimed_unproven" }))).toBe("result_only");
  });
});

describe("delivery receipt parsing and idempotency identity", () => {
  it("parses the committed Python-produced sample receipt", async () => {
    const parsed = await parseExecutionReturnDelivery(sampleReceipt);
    expect(parsed.state).toBe("delivered");
    expect(parsed.transport_ref).toBe("adm-42");
    expect(parsed.refusal_code).toBeNull();
    expect(parsed.submission_id).toBe(
      await mintSubmissionId(parsed.return_digest, parsed.conversation_id));
  });

  it("submission id mint is deterministic and input-sensitive", async () => {
    const digest = sampleRecord.digest as string;
    const first = await mintSubmissionId(digest, "sess-3f9c2");
    expect(first).toBe(sampleReceipt.submission_id);
    expect(await mintSubmissionId(digest, "sess-3f9c2")).toBe(first);
    expect(await mintSubmissionId("0".repeat(64), "sess-3f9c2")).not.toBe(first);
    expect(await mintSubmissionId(digest, "sess-other")).not.toBe(first);
    expect(first).toMatch(/^execret-[0-9a-f]{32}$/);
  });

  it("refuses receipt drift: states, codes, submission identity", async () => {
    await reject("INVALID_SCHEMA", () => parseExecutionReturnDelivery({ ...sampleReceipt, schema: "other/v1" }));
    await reject("INVALID_VOCABULARY", () => parseExecutionReturnDelivery({ ...sampleReceipt, state: "maybe" }));
    await reject("DELIVERED_WITHOUT_REF", () => parseExecutionReturnDelivery({ ...sampleReceipt, transport_ref: null }));
    await reject("UNKNOWN_WITH_REF", () => parseExecutionReturnDelivery({ ...sampleReceipt, state: "unknown" }));
    await reject("REFUSAL_WITHOUT_CODE", () => parseExecutionReturnDelivery({ ...sampleReceipt, state: "refused" }));
    await reject("CODE_WITHOUT_REFUSAL", () => parseExecutionReturnDelivery({ ...sampleReceipt, refusal_code: "SESSION_BUSY" }));
    await reject("SUBMISSION_ID_MISMATCH", () => parseExecutionReturnDelivery({
      ...sampleReceipt, submission_id: "execret-" + "0".repeat(32) }));
    await reject("INVALID_REFUSAL_CODE", () => parseExecutionReturnDelivery({
      ...sampleReceipt, state: "refused", transport_ref: null, refusal_code: "not a code" }));
    await reject("INVALID_FIELDS", () => parseExecutionReturnDelivery({ ...sampleReceipt, extra: 1 }));
  });
});
