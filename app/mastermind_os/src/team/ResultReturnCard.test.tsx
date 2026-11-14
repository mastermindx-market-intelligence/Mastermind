// @vitest-environment jsdom
/** HC08 — the return card consumes ONLY Director F's authoritative contract
 *  (mastermind.execution_return/v1 + delivery receipt), parsed by the real
 *  fail-closed parser. Records come from the committed cross-language fixture
 *  or are minted through the contract's own digest derivation; no fixture
 *  data lives in production code. Acceptance can never render accepted (v1
 *  closes it to not_accepted); unknown GitHub evidence never renders green. */
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  type ExecutionReturnDeliveryReceipt, type ExecutionReturnGithub,
  type ExecutionReturnRecord, deriveStage, mintSubmissionId,
  parseExecutionReturn, parseExecutionReturnDelivery, recordDigest,
} from "../hermes-native/execution-return-contract";
import { ResultReturnCard } from "./ResultReturnCard";
afterEach(cleanup);

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtureDir = path.resolve(here, "../../../../integrations/mmos/fixtures/execution_return_v1");
const sampleRecord: Record<string, unknown> = JSON.parse(
  readFileSync(path.join(fixtureDir, "sample_record.json"), "utf8"));
const sampleReceipt: Record<string, unknown> = JSON.parse(
  readFileSync(path.join(fixtureDir, "sample_receipt.json"), "utf8"));

/** Mint a fully valid record through the contract's own derivation — the
 *  parser's digest, return-id and stage-vs-evidence gates all stay on. */
async function mintRecord(
  github: Partial<ExecutionReturnGithub>,
  resultText = "Implemented with tests.",
): Promise<ExecutionReturnRecord> {
  const gh: ExecutionReturnGithub = {
    branch: null, pr_number: null, pr_url: null, checks: null,
    checks_state: "unknown", merge_state: "unknown",
    installation: "none_claimed", ...github,
  };
  const raw: Record<string, unknown> = {
    schema: "mastermind.execution_return/v1",
    stage: deriveStage(gh),
    acceptance: "not_accepted",
    acceptance_claim_refused: false,
    attempt: {
      attempt_id: "ATT-000001", root_id: "root-wo19-coding-7",
      idempotency_key: "t3-launch-abc123",
      authenticated_namespace: "mastermind:test", t3_thread_id: null,
      t3_run_id: null, seal_digest: "f".repeat(64),
    },
    result: { text: resultText, artifact_refs: ["control_plane/roster_join.py"] },
    github: gh,
    original_requester: {
      teammate_id: "hermes-engineering", conversation_id: "sess-3f9c2",
      project_id: "proj-mmos-v1", authenticated_namespace: "mastermind:test",
    },
  };
  const digest = await recordDigest(raw);
  return parseExecutionReturn({
    ...raw, digest, return_id: "execret-" + digest.slice(0, 32),
  });
}

describe("ResultReturnCard — honest empty state (no producer wired yet)", () => {
  it("says no return is projected instead of inventing one", async () => {
    render(<ResultReturnCard executionReturn={null} />);
    expect(screen.getByText("No execution return is projected yet.")).toBeTruthy();
    expect(
      screen.getByText(/mastermind\.execution_return\/v1 record appears here/i),
    ).toBeTruthy();
    expect(screen.getByText(/delivery and acceptance kept separate/i)).toBeTruthy();
    // Nothing from a record leaks into the empty state.
    expect(document.querySelector("[data-stage]")).toBeNull();
    expect(document.querySelector("[data-delivery]")).toBeNull();
  });
  it("renders the honest zh-CN empty copy", () => {
    render(<ResultReturnCard executionReturn={null} locale="zh-CN" />);
    expect(screen.getByText("尚无执行返回被投影。")).toBeTruthy();
    expect(screen.getByText(/交付与接受始终分开显示/)).toBeTruthy();
  });
});

describe("ResultReturnCard — stage and GitHub evidence stay honest", () => {
  it("renders the fixture's proven stage (merged + unproven install claim) without ever claiming installed", async () => {
    const record = await parseExecutionReturn(sampleRecord);
    render(<ResultReturnCard executionReturn={record} />);
    expect(
      document.querySelector(".mm-chip-state[data-stage='installed_unknown']")?.textContent,
    ).toContain("Merged — install claim unproven");
    expect(screen.getByText("Claimed, unproven")).toBeTruthy();
    // Green checks are proven green by the record's own evidence.
    expect(document.querySelector("[data-checks='green']")?.textContent).toBe("Green");
    expect(screen.getByText(/ci-union: success/)).toBeTruthy();
    expect(screen.getByText(/lint: skipped/)).toBeTruthy();
    expect(screen.getByText("t3/execution-return-path")).toBeTruthy();
  });
  it("never shows unknown GitHub evidence as green (pr_open record, checks unknown)", async () => {
    const record = await mintRecord({
      branch: "t3/attempt", pr_number: 2400,
      pr_url: "https://github.com/Acme/Mastermind/pull/2400",
    });
    render(<ResultReturnCard executionReturn={record} />);
    expect(
      document.querySelector(".mm-chip-state[data-stage='pr_open']")?.textContent,
    ).toContain("Pull request open");
    const checks = document.querySelector("[data-checks]");
    expect(checks?.getAttribute("data-checks")).toBe("unknown");
    expect(checks?.textContent).toBe("Unknown");
    expect(document.querySelector("[data-merge='unknown']")?.textContent).toBe("Unknown");
    expect(screen.queryByText("Green")).toBeNull();
  });
  it("shows a result-only return with everything unobserved stated, never inferred", async () => {
    const record = await mintRecord({}, "Text-only return.");
    render(<ResultReturnCard executionReturn={record} />);
    expect(
      document.querySelector(".mm-chip-state[data-stage='result_only']")?.textContent,
    ).toContain("Result only");
    expect(screen.getAllByText("Not observed").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("Text-only return.")).toBeTruthy();
    expect(screen.getByText("control_plane/roster_join.py")).toBeTruthy();
  });
});

describe("ResultReturnCard — delivered ≠ accepted, structurally", () => {
  it("always renders not_accepted and never an accepted state — even for a delivered receipt", async () => {
    const record = await parseExecutionReturn(sampleRecord);
    const receipt = await parseExecutionReturnDelivery(sampleReceipt);
    render(
      <ResultReturnCard executionReturn={record} deliveryReceipt={receipt} />,
    );
    const acceptance = document.querySelector("[data-acceptance]");
    expect(acceptance?.getAttribute("data-acceptance")).toBe("not_accepted");
    expect(acceptance?.textContent).toBe("Not accepted");
    // No accepted rendering exists anywhere in the card.
    expect(document.querySelector("[data-acceptance='accepted']")).toBeNull();
    expect(screen.queryByText(/^Accepted$/)).toBeNull();
    expect(
      screen.getByText(/acceptance is closed to not_accepted/i),
    ).toBeTruthy();
    // The fixture bakes in a refused acceptance claim; the card says so.
    expect(
      screen.getByText(/claimed acceptance; the contract refused the claim/i),
    ).toBeTruthy();
  });
  it("shows the delivered receipt with its transport facts AND the explicit delivered ≠ accepted line", async () => {
    const record = await parseExecutionReturn(sampleRecord);
    const receipt = await parseExecutionReturnDelivery(sampleReceipt);
    render(
      <ResultReturnCard executionReturn={record} deliveryReceipt={receipt} />,
    );
    expect(
      document.querySelector("[data-delivery='delivered']")?.textContent,
    ).toBe("Delivered");
    expect(screen.getByText("Transport ref adm-42")).toBeTruthy();
    expect(screen.getByText(/Submission execret-/)).toBeTruthy();
    expect(
      screen.getByText(/Delivered ≠ accepted — delivery is an observation/i),
    ).toBeTruthy();
  });
  it("renders refused and unknown receipts honestly, and no-receipt as not observed", async () => {
    const record = await mintRecord({ branch: "t3/x" });
    const mintReceipt = async (
      state: "delivered" | "unknown" | "refused",
    ): Promise<ExecutionReturnDeliveryReceipt> => {
      const conversationId = record.original_requester.conversation_id;
      return parseExecutionReturnDelivery({
        schema: "mastermind.execution_return_delivery/v1",
        return_id: record.return_id, return_digest: record.digest,
        conversation_id: conversationId,
        submission_id: await mintSubmissionId(record.digest, conversationId),
        state,
        transport_ref: state === "delivered" ? "adm-9" : null,
        refusal_code: state === "refused" ? "SESSION_BUSY" : null,
      });
    };
    const { unmount } = render(
      <ResultReturnCard
        executionReturn={record}
        deliveryReceipt={await mintReceipt("unknown")}
      />,
    );
    expect(
      document.querySelector("[data-delivery='unknown']")?.textContent,
    ).toBe("Delivery unknown");
    unmount();
    render(
      <ResultReturnCard
        executionReturn={record}
        deliveryReceipt={await mintReceipt("refused")}
      />,
    );
    expect(
      document.querySelector("[data-delivery='refused']")?.textContent,
    ).toBe("Refused");
    expect(screen.getByText("Refusal code SESSION_BUSY")).toBeTruthy();
    unmount();
    render(<ResultReturnCard executionReturn={record} />);
    expect(
      document.querySelector("[data-delivery='none']")?.textContent,
    ).toBe("Not observed");
    expect(screen.getByText(/No delivery receipt is projected/i)).toBeTruthy();
  });
  it("names a receipt that belongs to a different return instead of merging them", async () => {
    const record = await mintRecord({ branch: "t3/x" });
    const otherReceipt = await parseExecutionReturnDelivery(sampleReceipt); // different return_id
    render(
      <ResultReturnCard executionReturn={record} deliveryReceipt={otherReceipt} />,
    );
    expect(
      document.querySelector("[data-delivery='mismatch']")?.textContent,
    ).toContain("does not match this return");
  });
});

describe("ResultReturnCard — identity and origin", () => {
  it("carries the return identity and original requester from the contract", async () => {
    const record = await parseExecutionReturn(sampleRecord);
    render(<ResultReturnCard executionReturn={record} />);
    expect(screen.getByText("execret-6876dc96ef1f67e0b8525c6115bd95fd")).toBeTruthy();
    expect(screen.getByText("root-wo19-coding-7")).toBeTruthy();
    expect(screen.getByText("hermes-engineering")).toBeTruthy();
    expect(screen.getByText("sess-3f9c2")).toBeTruthy();
    expect(screen.getByText("proj-mmos-v1")).toBeTruthy();
  });
  it("opens the origin through the provided action", () => {
    const onOpenOrigin = vi.fn();
    render(
      <ResultReturnCard executionReturn={null} onOpenOrigin={onOpenOrigin} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open origin →" }));
    expect(onOpenOrigin).toHaveBeenCalledTimes(1);
  });
  it("renders the honest zh-CN record copy with delivered ≠ accepted explicit", async () => {
    const record = await parseExecutionReturn(sampleRecord);
    const receipt = await parseExecutionReturnDelivery(sampleReceipt);
    render(
      <ResultReturnCard
        executionReturn={record}
        deliveryReceipt={receipt}
        locale="zh-CN"
      />,
    );
    expect(screen.getByText("执行返回")).toBeTruthy();
    expect(
      document.querySelector("[data-acceptance='not_accepted']")?.textContent,
    ).toBe("未接受");
    expect(
      document.querySelector("[data-delivery='delivered']")?.textContent,
    ).toBe("已交付");
    expect(screen.getByText(/已交付 ≠ 已接受/)).toBeTruthy();
    expect(screen.getByText(/接受被封闭为 not_accepted/)).toBeTruthy();
  });
});
