// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { OfficeWorkRead } from "./OfficeWorkRead";
import { decodeWorkDocument } from "../work";
import raw from "../fixtures/work-service-available.json";
afterEach(cleanup);
it.each(["en", "zh-CN"] as const)(
  "renders the actual closed Work source with separate acceptance/coverage in %s",
  (locale) => {
    const document = decodeWorkDocument(structuredClone(raw))!;
    expect(document).not.toBeNull();
    render(
      <OfficeWorkRead state={{ kind: "DOCUMENT", document }} locale={locale} />,
    );
    expect(
      screen.getByText(locale === "en" ? "Work item JOB-1" : "工作项 JOB-1"),
    ).toBeTruthy();
    expect(
      screen.getByText(
        locale === "en"
          ? "Completed; acceptance is not reported here"
          : "已完成；此处未提供验收状态",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        locale === "en"
          ? "Only the work provided for this view is shown."
          : "这里只显示此视图已提供的工作。",
      ),
    ).toBeTruthy();
  },
);
it("keeps unavailable different from a qualified zero and performs no read", () => {
  render(
    <OfficeWorkRead
      state={{ kind: "UNAVAILABLE", reason: "SOURCE_OWNER_NOT_CURRENT" }}
    />,
  );
  expect(
    screen.getByText(
      "Work information is unavailable. This does not mean there is no work.",
    ),
  ).toBeTruthy();
  expect(screen.queryByText("JOB-1")).toBeNull();
});

it.each([
  ["en", "NEEDS_SOL", "Sol needs to act"],
  ["en", "NEEDS_WORKER", "A worker needs to act"],
  ["zh-CN", "NEEDS_SOL", "需要 Sol 处理"],
  ["zh-CN", "NEEDS_WORKER", "需要执行者处理"],
] as const)(
  "keeps full references and translates %s %s without inventing a name",
  (locale, actor, label) => {
    // Presentation-only variant; no authenticated producer/owner claim.
    const document = decodeWorkDocument(structuredClone(raw))!;
    const row = document.groups.QUEUED[0],
      id = "JOB-" + "1234567890abcdef".repeat(3);
    row.root_job_id = id;
    row.next_actor.value = actor;
    render(
      <OfficeWorkRead state={{ kind: "DOCUMENT", document }} locale={locale} />,
    );
    expect(screen.getByTitle(id).textContent).toContain("JOB-1234…abcdef");
    expect(screen.getByText(id, { selector: "code" })).toBeTruthy();
    expect(screen.getByText(label)).toBeTruthy();
    expect(screen.queryByText(actor)).toBeNull();
  },
);
