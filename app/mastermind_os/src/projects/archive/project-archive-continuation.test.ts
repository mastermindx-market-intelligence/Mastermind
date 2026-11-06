import { expect, it } from "vitest";
import fixture from "./fixtures/project-archive-owner.json";
import { acceptArchivePage, nextArchiveCursor, validArchiveCursor, type AvailableArchive } from "./project-archive-continuation";

const refs = [fixture.sample.items[0]!.work_ref, ...Array.from({ length: 499 }, (_, i) => `WS:ROW-${String(i).padStart(3, "0")}`)].sort();
const owner = { documentDigest: fixture.catalogue.document_digest, workRefs: refs };
function page(index: number) {
  const raw = structuredClone(fixture), selected = refs.slice(index * 128, (index + 1) * 128);
  raw.catalogue.work_refs = selected; raw.catalogue.qualified_catalogue_count = refs.length;
  raw.sample.coverage.supplied_count = selected.length; raw.sample.coverage.observed_count = selected.length;
  raw.sample.items = raw.sample.items.filter(row => selected.includes(row.work_ref));
  return raw;
}

it("reaches all500 supplied records in four explicit bounded pages with unknown company total", () => {
  let pages: AvailableArchive[] = [];
  for (let index = 0; index < 4; index++) {
    pages = acceptArchivePage(pages, page(index), owner);
    const cursor = nextArchiveCursor(pages);
    expect(cursor === null).toBe(index === 3);
    if (cursor) expect(cursor).toEqual({ after_work_ref: refs[(index + 1) * 128 - 1], catalogue_digest: owner.documentDigest });
  }
  expect(pages.flatMap(body => body.catalogue.work_refs)).toEqual(refs);
  expect(new Set(pages.flatMap(body => body.catalogue.work_refs)).size).toBe(500);
  expect(pages.every(body => body.sample.coverage.company_total === null)).toBe(true);
  expect(pages.flatMap(body => body.sample.items)).toHaveLength(1);
  expect(() => acceptArchivePage(pages, page(4), owner)).toThrow("PROJECT_ARCHIVE_PAGE_CHANGED");
});

it("rejects overlap, skipped windows and changed catalogue/source instead of hiding conflicting duplicates", () => {
  const pages = acceptArchivePage([], page(0), owner);
  for (const raw of [page(0), page(2)]) expect(() => acceptArchivePage(pages, raw, owner)).toThrow("PROJECT_ARCHIVE_PAGE_CHANGED");
  const otherCatalogue = page(1); otherCatalogue.catalogue.document_digest = "f".repeat(64);
  expect(() => acceptArchivePage(pages, otherCatalogue, owner)).toThrow("PROJECT_ARCHIVE_PAGE_CHANGED");
  const otherSource = page(1); otherSource.catalogue.macro_sha = "b".repeat(40); otherSource.sample.source_commit = "b".repeat(40);
  expect(() => acceptArchivePage(pages, otherSource, owner)).toThrow("PROJECT_ARCHIVE_PAGE_CHANGED");
  const unavailable = { schema: "mastermind.workspace_project_archive.v1", availability: "UNAVAILABLE", catalogue: null, sample: null, reason_codes: ["SOURCE_CHANGED"] };
  expect(() => acceptArchivePage(pages, unavailable, owner)).toThrow("PROJECT_ARCHIVE_UNAVAILABLE");
});

it("treats cursor fields only as closed selectors and rejects paths, private members and newline aliases", () => {
  const cursor = { after_work_ref: "WS:ROW-127", catalogue_digest: "a".repeat(64) };
  expect(validArchiveCursor(cursor)).toBe(true);
  for (const raw of [{ ...cursor, path: "/private" }, { ...cursor, work_refs: refs }, { ...cursor, root_job_id: "JOB-1" },
    { ...cursor, after_work_ref: "WS:ROW-127\n" }, { ...cursor, after_work_ref: "../private" },
    { ...cursor, catalogue_digest: "a".repeat(64) + "\n" }, { ...cursor, catalogue_digest: "A".repeat(64) }]) {
    expect(validArchiveCursor(raw)).toBe(false);
  }
});
