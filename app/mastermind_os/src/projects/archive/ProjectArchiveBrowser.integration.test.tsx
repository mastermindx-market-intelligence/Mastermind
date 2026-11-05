// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { OfficeProjection } from "../../meta-ceo/projection";
import fixture from "./fixtures/project-archive-owner.json";
import { decodeProjectArchive, type ProjectArchiveRead } from "./project-archive";
import { ProjectArchiveBrowser } from "./ProjectArchiveBrowser";

afterEach(cleanup);
const refs = [...Array.from({ length: 128 }, (_, i) => `WS:AAA-${String(i).padStart(3, "0")}`), fixture.sample.items[0]!.work_ref];
function response(index: number) {
  const raw = structuredClone(fixture), selected = refs.slice(index * 128, (index + 1) * 128);
  raw.catalogue.work_refs = selected; raw.catalogue.qualified_catalogue_count = refs.length;
  raw.sample.coverage.supplied_count = selected.length; raw.sample.coverage.observed_count = selected.length;
  raw.sample.items = raw.sample.items.filter(row => selected.includes(row.work_ref));
  return decodeProjectArchive(raw);
}
function programs(): OfficeProjection["programs"] {
  return { source: { owner: "AGENT_OS", ref: fixture.catalogue.document_digest, revision: "synthetic-publication-one", observed_at: "2026-11-04T10:00:00Z", state: "CURRENT", coverage: "SUPPLIED_SCOPE" }, reason: null,
    value: { state: "AVAILABLE", reason: "AVAILABLE", programs: refs.map(workRef => ({ workRef, title: "Supplied " + workRef, state: "done", nextAction: null, nextActionWithheld: false, rootState: "UNKNOWN", rootJobId: null, rootCandidates: [] })) } };
}
const generation = () => 1, canRead = () => true;

it("traverses explicit Load more to a real-shaped archive record and returns without current Mission navigation", async () => {
  const read = vi.fn(async () => response(0)), readPage = vi.fn(async (_request: { after_work_ref: string; catalogue_digest: string; signal: AbortSignal }) => response(1)), navigate = vi.fn();
  render(<ProjectArchiveBrowser scopeKey="workspace-one" programs={programs()} read={read} readPage={readPage}
    sourceGeneration={generation} canRead={canRead} onNavigateMission={navigate} />);
  fireEvent.click(screen.getByRole("button", { name: "Archived projects" }));
  await screen.findByText(/128 checked of 129 supplied records/);
  expect(screen.getByText("No archived projects are declared in the checked sample.")).toBeTruthy();
  expect(screen.getByText("The remaining supplied records have not been checked.")).toBeTruthy();
  expect(readPage).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Check more supplied projects" }));
  await screen.findByText(/129 checked of 129 supplied records/);
  expect(readPage).toHaveBeenCalledTimes(1);
  expect(readPage.mock.calls[0]?.[0]).toMatchObject({ after_work_ref: refs[127], catalogue_digest: fixture.catalogue.document_digest });
  expect(screen.queryByRole("button", { name: "Check more supplied projects" })).toBeNull();
  const input = screen.getByRole("searchbox", { name: "Find an archived project" });
  fireEvent.change(input, { target: { value: "Source-backed" } });
  fireEvent.click(screen.getByRole("button", { name: "Open read-only " + fixture.sample.items[0]!.title }));
  expect(screen.getByRole("article", { name: "Archived record (read-only)" })).toBeTruthy();
  expect(screen.getByText(fixture.sample.items[0]!.objective)).toBeTruthy();
  expect(navigate).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: /^Restore$|^Archive$|^Send$/ })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Back to archived list" }));
  expect((screen.getByRole("searchbox", { name: "Find an archived project" }) as HTMLInputElement).value).toBe("Source-backed");
  expect(read).toHaveBeenCalledTimes(1); expect(readPage).toHaveBeenCalledTimes(1);
});

it("masks accumulated pages and discards a late continuation after an identical-document publication change", async () => {
  let finish!: (value: ProjectArchiveRead) => void;
  const read = vi.fn(async () => response(0)), readPage = vi.fn(() => new Promise<ProjectArchiveRead>(resolve => { finish = resolve; }));
  const source = programs();
  const rendered = render(<ProjectArchiveBrowser scopeKey="workspace-one" programs={source} read={read} readPage={readPage} sourceGeneration={generation} canRead={canRead} />);
  fireEvent.click(screen.getByRole("button", { name: "Archived projects" })); await screen.findByText(/128 checked of 129 supplied records/);
  fireEvent.click(screen.getByRole("button", { name: "Check more supplied projects" }));
  const changed = structuredClone(source); changed.source.revision = "synthetic-publication-two";
  rendered.rerender(<ProjectArchiveBrowser scopeKey="workspace-one" programs={changed} read={read} readPage={readPage} sourceGeneration={generation} canRead={canRead} />);
  expect(screen.queryByText(/128 checked of 129 supplied records/)).toBeNull();
  await act(async () => { finish(response(1)); });
  await waitFor(() => expect(screen.queryByText(/129 checked of 129 supplied records/)).toBeNull());
  expect(screen.queryByText(fixture.sample.items[0]!.archive.archived_by)).toBeNull();
  expect(read).toHaveBeenCalledTimes(1); expect(readPage).toHaveBeenCalledTimes(1);
});


it("forwards the caller-owned New project action without starting an archive read", () => {
  const create = vi.fn(), read = vi.fn(async () => response(0));
  render(<ProjectArchiveBrowser scopeKey="workspace-one" programs={programs()} read={read}
    sourceGeneration={generation} canRead={canRead}
    newProjectControl={<button type="button" onClick={create}>New project</button>} />);
  fireEvent.click(screen.getByRole("button", { name: "New project" }));
  expect(create).toHaveBeenCalledTimes(1); expect(read).not.toHaveBeenCalled();
});
