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
    expect(screen.getByText("JOB-1")).toBeTruthy();
    expect(
      screen.getByText(
        locale === "en"
          ? "Completed; acceptance is separate"
          : "已完成；接受状态另行报告",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        locale === "en"
          ? "This is a Work observation, not a company-wide total or an acceptance ruling."
          : "这是工作观测，不是全公司总量，也不是接受结论。",
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
      "Work source unavailable. This is not evidence of zero work.",
    ),
  ).toBeTruthy();
  expect(screen.queryByText("JOB-1")).toBeNull();
});
