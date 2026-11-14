// @vitest-environment jsdom
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ProjectRunOutcome } from "./ProjectRunOutcome";
import { ProjectDeliveryPanel } from "./ProjectDeliveryPanel";
import {
  mintSubmissionId,
  parseExecutionReturn,
  parseExecutionReturnDelivery,
} from "../hermes-native/execution-return-contract";
afterEach(cleanup);

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtureDir = path.resolve(here, "../../../../integrations/mmos/fixtures/execution_return_v1");
const sampleRecord: Record<string, unknown> = JSON.parse(
  readFileSync(path.join(fixtureDir, "sample_record.json"), "utf8"));
const sampleReceipt: Record<string, unknown> = JSON.parse(
  readFileSync(path.join(fixtureDir, "sample_receipt.json"), "utf8"));

/** A contract-minted refused receipt for the same return (refusal code is the
 *  only lawful receipt state besides delivered/unknown that renders). */
async function refusedReceipt(record: { digest: string; return_id: string }) {
  const conversationId = "sess-refused";
  return parseExecutionReturnDelivery({
    schema: "mastermind.execution_return_delivery/v1",
    return_id: record.return_id,
    return_digest: record.digest,
    conversation_id: conversationId,
    submission_id: await mintSubmissionId(record.digest, conversationId),
    state: "refused",
    transport_ref: null,
    refusal_code: "GATE_CLOSED",
  });
}

describe("ProjectRunOutcome (TD07)", () => {
  it("renders fully from a null run naming its missing sources, without fabricated values", () => {
    render(<ProjectRunOutcome run={null} />);
    expect(screen.getByText("No run is projected for this project yet.")).toBeTruthy();
    expect(screen.getByText(/execution return, delivery receipt and retained-activity trail appear here/)).toBeTruthy();
    expect(screen.getByText("The execution trail is not projected yet.")).toBeTruthy();
    expect(screen.getByText(/retained-activity read, which is not wired/)).toBeTruthy();
    expect(screen.getAllByText("Not projected").length).toBeGreaterThanOrEqual(5); // artifact rows
    expect(screen.getAllByText("Unknown").length).toBe(6); // bound-session rows
    for (const fabricated of [/ubuntu/i, /gpt-?\d/i, /claude/i, /sonnet/i, /opus/i, /haiku/i, /gemini/i]) {
      expect(screen.queryByText(fabricated)).toBeNull();
    }
  });

  it("shows the honest preparing state when a run exists but no return record", () => {
    render(<ProjectRunOutcome run={{ executionReturn: null, deliveryReceipt: null, trail: null }} />);
    // The state appears in both the heading and the chip.
    expect(screen.getAllByText("Preparing the result").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("The coding turn has ended. Its result is still being assembled.")).toBeTruthy();
    expect(screen.getByText(/verified files, checks, and source/)).toBeTruthy();
  });

  it("renders a contract-minted return: stage, checks, PR, artifacts, delivered receipt, trail", async () => {
    const record = await parseExecutionReturn(sampleRecord);
    const receipt = await parseExecutionReturnDelivery(sampleReceipt);
    render(
      <ProjectRunOutcome
        run={{
          executionReturn: record,
          deliveryReceipt: receipt,
          trail: [
            { title: "Dispatch", detail: "Admitted on the Executive path", timestamp: "2026-11-09T00:00:00Z" },
            { title: "Run", detail: null, timestamp: null },
          ],
        }}
      />,
    );
    // Stage follows the contract vocabulary (chip + composed heading).
    expect(document.querySelector(".mm-chip-state[data-stage='installed_unknown']")).not.toBeNull();
    expect(screen.getAllByText(/Merged — install claim unproven/).length).toBeGreaterThanOrEqual(2);
    // Checks summary, PR link, artifact refs.
    expect(screen.getByText("Green · 3 checks")).toBeTruthy();
    expect(screen.getByRole("link", { name: /pull\/2338/ })).toBeTruthy();
    expect(screen.getByText("2 refs")).toBeTruthy();
    expect(screen.getByText("control_plane/roster_join.py")).toBeTruthy();
    // Receipt states: delivered, with delivery ≠ acceptance kept separate.
    expect(screen.getByText("Delivered")).toBeTruthy();
    expect(screen.getByText("Not accepted")).toBeTruthy();
    expect(screen.getByText(/Delivered ≠ accepted/)).toBeTruthy();
    // Trail steps render with detail and timestamp.
    expect(screen.getByText("Dispatch")).toBeTruthy();
    expect(screen.getByText("Admitted on the Executive path")).toBeTruthy();
    expect(screen.getByText("2026-11-09T00:00:00Z")).toBeTruthy();
  });

  it("renders a refused receipt with its refusal code", async () => {
    const record = await parseExecutionReturn(sampleRecord);
    const receipt = await refusedReceipt(record);
    render(<ProjectRunOutcome run={{ executionReturn: record, deliveryReceipt: receipt, trail: null }} />);
    expect(screen.getByText("Refused")).toBeTruthy();
    expect(screen.getByText("Refusal code GATE_CLOSED")).toBeTruthy();
  });

  it("renders breadcrumb, subject heading and the open-code action", () => {
    const onOpenCode = vi.fn();
    render(
      <ProjectRunOutcome
        run={{ executionReturn: null, deliveryReceipt: null, trail: null }}
        breadcrumb={["Code", "Connect the team roster", "Run"]}
        subject="Engineering · Mastermind OS"
        onOpenCode={onOpenCode}
      />,
    );
    expect(screen.getByText("Code / Connect the team roster / Run")).toBeTruthy();
    expect(screen.getByText("Engineering · Mastermind OS / Preparing the result")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open coding session →" }));
    expect(onOpenCode).toHaveBeenCalledTimes(1);
  });

  it("carries zh-CN strings for the new surface copy", () => {
    render(
      <ProjectRunOutcome
        run={{ executionReturn: null, deliveryReceipt: null, trail: null }}
        locale="zh-CN"
      />,
    );
    expect(screen.getAllByText("正在准备结果").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("编码回合已结束。其结果仍在组装中。")).toBeTruthy();
    expect(screen.getByText("执行轨迹尚未投影。")).toBeTruthy();
    expect(screen.getByText(/保留活动读取供给/)).toBeTruthy();
    expect(screen.getByText("绑定会话")).toBeTruthy();
    expect(screen.getByText("结果产物")).toBeTruthy();
    expect(screen.getAllByText("未知").length).toBeGreaterThanOrEqual(6);
  });

  it("exposes keyboard focus targets on its heading", () => {
    render(<ProjectRunOutcome run={null} />);
    expect(document.getElementById("mm-run-outcome-heading")?.getAttribute("tabindex")).toBe("-1");
  });

  it("mounts inside ProjectDeliveryPanel after the task section", () => {
    const { container } = render(
      <ProjectDeliveryPanel
        objective={null}
        owner={null}
        route={null}
        delegatedTask={null}
        run={{ executionReturn: null, deliveryReceipt: null, trail: null }}
        executionReturn={null}
        trail={[]}
      />,
    );
    expect(screen.getByText("Run and return")).toBeTruthy();
    expect(screen.getAllByText("Preparing the result").length).toBeGreaterThanOrEqual(1);
    const sections = Array.from(container.querySelectorAll("section"));
    const codingIdx = sections.findIndex((s) => s.classList.contains("mm-delivery-coding"));
    const runIdx = sections.findIndex((s) => s.querySelector(".mm-run-outcome"));
    expect(runIdx).toBeGreaterThan(codingIdx);
  });
});
