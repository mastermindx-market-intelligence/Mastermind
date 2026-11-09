import { decodeProjectArchive, type ProjectArchiveRead } from "./project-archive";

export interface ArchiveCursor { after_work_ref: string; catalogue_digest: string }
export type AvailableArchive = Extract<ProjectArchiveRead, { availability: "AVAILABLE" }>;
const workRef = (value: unknown): value is string => typeof value === "string" && value.length >= 5 && value.length <= 67 && value.trim() === value && /^WS:[A-Z0-9]+(?:-[A-Z0-9]+)*$/.test(value);
export function validArchiveCursor(value: unknown): value is ArchiveCursor {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const item = value as Record<string, unknown>;
  return Object.keys(item).sort().join(",") === "after_work_ref,catalogue_digest" && workRef(item.after_work_ref) &&
    typeof item.catalogue_digest === "string" && item.catalogue_digest.length === 64 && /^[0-9a-f]{64}$/.test(item.catalogue_digest);
}

/** A cursor is only a selector. The server requalifies its actual catalogue. */
export function nextArchiveCursor(pages: readonly AvailableArchive[]): ArchiveCursor | null {
  const last = pages.at(-1);
  if (!last) return null;
  const checked = pages.reduce((count, page) => count + page.catalogue.work_refs.length, 0);
  const after = last.catalogue.work_refs.at(-1);
  return checked < last.catalogue.qualified_catalogue_count && after
    ? { after_work_ref: after, catalogue_digest: last.catalogue.document_digest } : null;
}

/** Reject overlap, skipped windows or mixed generations instead of deduplicating
 * by hiding conflicts. Every accepted row belongs to one contiguous checked page.
 */
export function acceptArchivePage(previous: readonly AvailableArchive[], raw: unknown,
  owner: { documentDigest: string; workRefs: readonly string[] }): AvailableArchive[] {
  const fail = (): never => { throw new Error("PROJECT_ARCHIVE_PAGE_CHANGED"); };
  if (!/^[0-9a-f]{64}$/.test(owner.documentDigest) || owner.workRefs.length > 500 ||
      !owner.workRefs.every(workRef) || new Set(owner.workRefs).size !== owner.workRefs.length || previous.length > 3) fail();
  const refs = [...owner.workRefs].sort();
  let checked = 0, macro: string | null = null;
  const archived = new Set<string>();
  const pages: AvailableArchive[] = [];
  for (const value of [...previous, raw]) {
    if (pages.length > 0 && checked >= refs.length) fail();
    const page = decodeProjectArchive(value);
    if (page.availability !== "AVAILABLE") throw new Error("PROJECT_ARCHIVE_UNAVAILABLE");
    if (page.catalogue.document_digest !== owner.documentDigest || page.catalogue.qualified_catalogue_count !== refs.length ||
        macro !== null && page.catalogue.macro_sha !== macro ||
        JSON.stringify(page.catalogue.work_refs) !== JSON.stringify(refs.slice(checked, checked + 128))) fail();
    for (const row of page.sample.items) {
      if (archived.has(row.work_ref)) fail();
      archived.add(row.work_ref);
    }
    macro = page.catalogue.macro_sha;
    checked += page.catalogue.work_refs.length;
    pages.push(page);
  }
  return pages;
}
