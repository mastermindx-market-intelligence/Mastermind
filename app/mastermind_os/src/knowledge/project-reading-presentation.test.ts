import { describe, expect, it } from "vitest";
import {
  NATIVE_READINESS_DIAGNOSTIC,
  isReadinessDiagnostic,
  projectReadingPresentation,
} from "./project-reading-presentation";

const READINESS_NOTE_EN =
  "The app could not check whether it can start changes. Reading project sources is checked separately.";
const READINESS_NOTE_ZH =
  "应用暂时无法确认能否发起更改。项目来源能否读取会单独显示。";

describe("projectReadingPresentation qualification label scopes", () => {
  it("labels Inbox as the workspace source in both locales without widening capability", () => {
    expect(
      projectReadingPresentation({
        active: "Inbox",
        locale: "en",
        independentProjectRead: false,
        notice: "",
      }).qualificationLabel,
    ).toBe("Workspace source");
    expect(
      projectReadingPresentation({
        active: "Inbox",
        locale: "zh-CN",
        independentProjectRead: false,
        notice: "",
      }).qualificationLabel,
    ).toBe("工作区来源");
  });

  it("labels an independent project reading route as the workspace source", () => {
    for (const active of ["Knowledge", "Search"]) {
      expect(
        projectReadingPresentation({
          active,
          locale: "en",
          independentProjectRead: true,
          notice: "",
        }).qualificationLabel,
      ).toBe("Workspace source");
      expect(
        projectReadingPresentation({
          active,
          locale: "zh-CN",
          independentProjectRead: true,
          notice: "",
        }).qualificationLabel,
      ).toBe("工作区来源");
    }
  });

  it("keeps the source-status label for ordinary routes without an independent read", () => {
    expect(
      projectReadingPresentation({
        active: "Knowledge",
        locale: "en",
        independentProjectRead: false,
        notice: "",
      }).qualificationLabel,
    ).toBe("Source status");
    expect(
      projectReadingPresentation({
        active: "Search",
        locale: "zh-CN",
        independentProjectRead: false,
        notice: "",
      }).qualificationLabel,
    ).toBe("来源状态");
    expect(
      projectReadingPresentation({
        active: "Projects",
        locale: "en",
        independentProjectRead: false,
        notice: "",
      }).qualificationLabel,
    ).toBe("Source status");
  });
});

describe("projectReadingPresentation readiness classification", () => {
  const independent = { active: "Knowledge", independentProjectRead: true };

  it("renders the exact-sentinel readable note in both locales", () => {
    for (const locale of ["en", "zh-CN"] as const) {
      const view = projectReadingPresentation({
        ...independent,
        locale,
        notice: NATIVE_READINESS_DIAGNOSTIC,
      });
      expect(view.statusNotice).toBe(
        locale === "zh-CN" ? READINESS_NOTE_ZH : READINESS_NOTE_EN,
      );
      expect(isReadinessDiagnostic(NATIVE_READINESS_DIAGNOSTIC)).toBe(true);
    }
  });

  it("retains the raw diagnostic beside the note instead of erasing it", () => {
    for (const locale of ["en", "zh-CN"] as const) {
      expect(
        projectReadingPresentation({
          ...independent,
          locale,
          notice: NATIVE_READINESS_DIAGNOSTIC,
        }).readinessDiagnostic,
      ).toBe(NATIVE_READINESS_DIAGNOSTIC);
    }
  });

  it("suppresses only the classified duplicate body notice on an independent read route", () => {
    expect(
      projectReadingPresentation({
        ...independent,
        locale: "en",
        notice: NATIVE_READINESS_DIAGNOSTIC,
      }).suppressBodyNotice,
    ).toBe(true);
    // Without an independent read the diagnostic stays visible through the
    // original body.
    expect(
      projectReadingPresentation({
        active: "Search",
        locale: "en",
        independentProjectRead: false,
        notice: NATIVE_READINESS_DIAGNOSTIC,
      }).suppressBodyNotice,
    ).toBe(false);
  });

  it("never classifies, suppresses or rewrites unknown-effect or other unavailable wording", () => {
    const otherNotices = [
      "EFFECT_UNKNOWN",
      "Mission source unavailable. No mission, relationship, or content was fabricated.",
      "Capacity source not connected. No host readiness was inferred.",
      "Native readiness receipt unavailable. No source request was attempted. ",
      "native readiness receipt unavailable. no source request was attempted.",
      "Native readiness receipt unavailable.",
      "",
    ];
    for (const notice of otherNotices) {
      expect(isReadinessDiagnostic(notice)).toBe(false);
      for (const locale of ["en", "zh-CN"] as const) {
        const view = projectReadingPresentation({
          ...independent,
          locale,
          notice,
        });
        expect(view.statusNotice).toBe(notice);
        expect(view.readinessDiagnostic).toBeNull();
        expect(view.suppressBodyNotice).toBe(false);
      }
    }
  });
});
