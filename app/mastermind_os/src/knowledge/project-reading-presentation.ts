/**
 * Pure localized presentation for the workspace qualification details and the
 * shared body notice on the project reading routes.
 *
 * Boundaries:
 *
 * - No React, state, routing, transport, auth, store, decoder, effect or
 *   clock lives here. Every decision is derived from the supplied `active`,
 *   `locale`, `independentProjectRead` and `notice` values, so callers keep
 *   their existing guards, predicates and native readiness effect untouched.
 * - Only the exact native readiness diagnostic literal is classified. Every
 *   other notice — including unknown-effect and other unavailable wording —
 *   is returned verbatim: never suppressed, rewritten or matched by a broad
 *   "unavailable" pattern.
 * - The diagnostic text itself stays the caller-supplied string. This module
 *   manufactures no source fact; the translated note is rendered beside the
 *   raw diagnostic in the caller's closed qualification details, not instead
 *   of it.
 */

export type ProjectReadingLocale = "en" | "zh-CN";

/** The exact native readiness diagnostic; no other wording is classified. */
export const NATIVE_READINESS_DIAGNOSTIC =
  "Native readiness receipt unavailable. No source request was attempted.";

export function isReadinessDiagnostic(notice: string): boolean {
  return notice === NATIVE_READINESS_DIAGNOSTIC;
}

export interface ProjectReadingPresentationInput {
  active: string;
  locale: ProjectReadingLocale;
  independentProjectRead: boolean;
  notice: string;
}

export interface ProjectReadingPresentation {
  /** Qualification summary label for the closed details element. */
  qualificationLabel: string;
  /** Localized readiness note, or the supplied notice verbatim. */
  statusNotice: string;
  /** The supplied exact diagnostic when classified, otherwise null. */
  readinessDiagnostic: string | null;
  /** True only for the classified diagnostic on an independent read route. */
  suppressBodyNotice: boolean;
}

const READINESS_NOTE: Record<ProjectReadingLocale, string> = {
  en: "The app could not check whether it can start changes. Reading project sources is checked separately.",
  "zh-CN": "应用暂时无法确认能否发起更改。项目来源能否读取会单独显示。",
};

export function projectReadingPresentation(
  input: ProjectReadingPresentationInput,
): ProjectReadingPresentation {
  const readiness = isReadinessDiagnostic(input.notice);
  return {
    qualificationLabel:
      input.active === "Inbox" || input.independentProjectRead
        ? input.locale === "zh-CN"
          ? "工作区来源"
          : "Workspace source"
        : input.locale === "zh-CN"
          ? "来源状态"
          : "Source status",
    statusNotice: readiness ? READINESS_NOTE[input.locale] : input.notice,
    readinessDiagnostic: readiness ? input.notice : null,
    suppressBodyNotice: readiness && input.independentProjectRead,
  };
}
