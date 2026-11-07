// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { OfficeProjection } from "../../meta-ceo/projection";
import fixture from "./fixtures/project-archive-owner.json";
import { decodeProjectArchive, type ProjectArchiveRead } from "./project-archive";
import type { ArchiveProjectsViewProps } from "./ArchiveProjectsView";
import { ProjectArchiveBrowser } from "./ProjectArchiveBrowser";

const observed = vi.hoisted(() => ({ current: null as unknown }));
vi.mock("./ArchiveProjectsView", () => ({ ArchiveProjectsView: (props: ArchiveProjectsViewProps) => {
  observed.current = props;
  return <div><button onClick={props.onRead}>Read fixture</button><button onClick={() => props.onChangeMode("archived")}>Archive view</button>
    <div data-testid="archive-data">{props.archived.map(row => row.title).join(";")}</div></div>;
} }));
afterEach(cleanup);
const WORK = fixture.sample.items[0]!.work_ref;
const ACTIVE = fixture.catalogue.work_refs.find(ref => ref !== WORK)!;
const permitted = () => true;
function programs(): OfficeProjection["programs"] {
  return { source: { owner: "AGENT_OS", ref: fixture.catalogue.document_digest, revision: "synthetic-collection-observation", observed_at: "2026-11-04T10:00:00Z", state: "CURRENT", coverage: "SUPPLIED_SCOPE" }, reason: null,
    value: { state: "AVAILABLE", reason: "AVAILABLE", programs: fixture.catalogue.work_refs.map((workRef, i) => ({ workRef, title: workRef === WORK ? "Archive fixture" : "Done without archive declaration", state: "done", nextAction: null, nextActionWithheld: false,
      rootState: "RESOLVED", rootJobId: `JOB-${i + 1}`, rootCandidates: [`JOB-${i + 1}`] })) } };
}
const props = () => observed.current as ArchiveProjectsViewProps;
const body = () => decodeProjectArchive(fixture);

it("opens explicit archive context while preserving exact current root navigation separately", async () => {
  const read = vi.fn(async () => body()), navigate = vi.fn(); const source = programs();
  render(<ProjectArchiveBrowser scopeKey="workspace-one" programs={source} read={read} sourceGeneration={() => 1} canRead={permitted} onNavigateMission={navigate} />);
  fireEvent.click(screen.getByText("Archive view"));
  await waitFor(() => expect(props().status).toBe("ready"));
  expect(props().mode).toBe("archived");
  expect(props().archived[0]!.work_ref).toBe(WORK);
  expect(props().projects.map(row => row.workRef)).toEqual([ACTIVE]);
  expect(props().projects[0]!.archiveStatus).toBe("NOT_DECLARED");
  act(() => props().onInspectArchive(WORK));
  expect(props().inspectedWorkRef).toBe(WORK);
  expect(navigate).not.toHaveBeenCalled();
  act(() => props().onOpenProject?.(WORK)); expect(navigate).not.toHaveBeenCalled();
  act(() => props().onOpenProject?.(ACTIVE));
  const row = source.value!.programs.find(card => card.workRef === ACTIVE)!;
  expect(navigate).toHaveBeenCalledExactlyOnceWith({ workRef: ACTIVE, rootJobId: row.rootJobId }, "current");
  expect(read).toHaveBeenCalledTimes(1);
});

it("never classifies Projects as active before archive evidence and masks foreign catalogue data", async () => {
  const invalid = structuredClone(fixture); invalid.catalogue.document_digest = "f".repeat(64);
  const read = vi.fn(async () => decodeProjectArchive(invalid));
  render(<ProjectArchiveBrowser scopeKey="workspace-one" programs={programs()} read={read} sourceGeneration={() => 1} canRead={permitted} />);
  expect(props().projects.every(row => row.archiveStatus === "UNKNOWN")).toBe(true);
  fireEvent.click(screen.getByText("Archive view"));
  await waitFor(() => expect(props().status).toBe("unavailable"));
  expect(props().archived).toEqual([]); expect(props().coverage).toBeNull();
  expect(props().projects.every(row => row.archiveStatus === "UNKNOWN")).toBe(true);
});

it("discards late replies across workspace, permission and source changes", async () => {
  for (const kind of ["workspace", "permission", "source"] as const) {
    let finish!: (value: ProjectArchiveRead) => void, allowed = true, generation = 1;
    const read = vi.fn(() => new Promise<ProjectArchiveRead>(resolve => { finish = resolve; }));
    const getGeneration = () => generation, canRead = () => allowed;
    const source = programs();
    const rendered = render(<ProjectArchiveBrowser scopeKey="workspace-one" programs={source} read={read} sourceGeneration={getGeneration} canRead={canRead} />);
    fireEvent.click(screen.getByText("Archive view")); expect(read).toHaveBeenCalledTimes(1);
    if (kind === "permission") allowed = false;
    if (kind === "source") generation = 2;
    rendered.rerender(<ProjectArchiveBrowser scopeKey={kind === "workspace" ? "workspace-two" : "workspace-one"} programs={source} read={read} sourceGeneration={getGeneration} canRead={canRead} />);
    await act(async () => { finish(body()); });
    expect(props().archived).toEqual([]); expect(props().inspectedWorkRef).toBeNull();
    expect(read).toHaveBeenCalledTimes(1);
    rendered.unmount();
  }
});

it("clears retained archive metadata immediately when catalogue publication changes", async () => {
  const read = vi.fn(async () => body()), generation = () => 1, source = programs();
  const rendered = render(<ProjectArchiveBrowser scopeKey="workspace-one" programs={source} read={read} sourceGeneration={generation} canRead={permitted} />);
  fireEvent.click(screen.getByText("Archive view")); await waitFor(() => expect(props().status).toBe("ready"));
  act(() => props().onInspectArchive(WORK));
  const changed = structuredClone(source); changed.source.ref = "b".repeat(64);
  rendered.rerender(<ProjectArchiveBrowser scopeKey="workspace-one" programs={changed} read={read} sourceGeneration={generation} canRead={permitted} />);
  expect(props().archived).toEqual([]); expect(props().inspectedWorkRef).toBeNull();
  expect(read).toHaveBeenCalledTimes(1);
});

it("keeps stale or missing Programs provenance from exposing an archive read", async () => {
  for (const kind of ["STALE", "WITHHELD", "UNKNOWN"] as const) {
    const source = programs(); source.source.state = kind;
    const read = vi.fn(async () => body());
    const rendered = render(<ProjectArchiveBrowser scopeKey="workspace-one" programs={source} read={read} sourceGeneration={() => 1} canRead={permitted} />);
    fireEvent.click(screen.getByText("Archive view"));
    expect(props().projects).toEqual([]); expect(props().archived).toEqual([]);
    expect(read).not.toHaveBeenCalled(); rendered.unmount();
  }
});


it("masks accumulated pages when publication revision changes even with identical document bytes", async () => {
  const read = vi.fn(async () => body()), generation = () => 1, source = programs();
  const rendered = render(<ProjectArchiveBrowser scopeKey="workspace-one" programs={source} read={read} sourceGeneration={generation} canRead={permitted} />);
  fireEvent.click(screen.getByText("Archive view")); await waitFor(() => expect(props().status).toBe("ready"));
  const changed = structuredClone(source); changed.source.revision = "new-publication-same-document";
  rendered.rerender(<ProjectArchiveBrowser scopeKey="workspace-one" programs={changed} read={read} sourceGeneration={generation} canRead={permitted} />);
  expect(props().archived).toEqual([]); expect(props().coverage).toBeNull();
  expect(read).toHaveBeenCalledTimes(1);
});


it("displays the separately acquired current catalogue without widening the C archive basis", async () => {
  const source = programs(), open = vi.fn(), read = vi.fn(async () => body());
  const current = { state: "AVAILABLE" as const, reason: "AVAILABLE", programs: [
    { ...source.value!.programs[0], workRef: "WS:NEW-CURRENT-DATA", title: "Current DATA" },
  ] };
  let allowed = true;
  const acquired = { value: current, current: () => allowed };
  render(<ProjectArchiveBrowser scopeKey="workspace-one" programs={source} currentCatalogue={acquired}
    read={read} sourceGeneration={() => 1} canRead={permitted} onOpenProject={open} />);
  expect(props().projects.map(row => row.workRef)).toEqual(["WS:NEW-CURRENT-DATA"]);
  expect(props().projects[0].archiveStatus).toBe("UNKNOWN");
  act(() => props().onOpenProject?.("WS:NEW-CURRENT-DATA"));
  expect(open).toHaveBeenCalledExactlyOnceWith("WS:NEW-CURRENT-DATA");
  fireEvent.click(screen.getByText("Archive view"));
  await waitFor(() => expect(props().status).toBe("ready"));
  expect(props().archived.map(row => row.work_ref)).toEqual(fixture.sample.items.map(row => row.work_ref));
  expect(read).toHaveBeenCalledTimes(1);
  allowed = false;
  act(() => props().onOpenProject?.("WS:NEW-CURRENT-DATA"));
  expect(open).toHaveBeenCalledTimes(1);
});
