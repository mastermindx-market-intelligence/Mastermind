import { expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient } from "./host";
import fixture from "./projects/archive/fixtures/project-archive-owner.json";

const signed = { status: "signed_in" as const, reason: null, acquisition: true, content: false };
const request = () => ({ signal: new AbortController().signal });
async function environment(read = async (): Promise<unknown> => fixture) {
  let notify = (_: unknown) => {};
  const invoke = vi.fn(async (command: string) => {
    if (command === "auth_status") return signed;
    if (command === "executive_auth_status") return { generation: 0, available: false };
    if (command === "read_project_archive" || command === "read_project_archive_page") return read();
    throw new Error("unexpected command");
  });
  const raw = await createNativeClient(invoke as never, async (_event, listener) => { notify = payload => listener({ payload }); return () => {}; });
  return { raw, host: bindMissionHost(raw), invoke, notify };
}

it("reads actual native archive helper output through one fixed rootless command", async () => {
  const env = await environment();
  expect((await env.host.readProjectArchive!(request())).availability).toBe("AVAILABLE");
  expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_archive")).toEqual([["read_project_archive", undefined]]);
});

it("rejects caller catalogue, root and path selectors before native invocation", async () => {
  const env = await environment();
  for (const extra of [{ path: "private" }, { root_job_id: "JOB-1" }, { macro_sha: "a".repeat(40) }, { work_refs: ["WS:FOREIGN"] }]) {
    await expect(env.host.readProjectArchive!({ ...request(), ...extra } as never)).rejects.toThrow("PROJECT_ARCHIVE_REQUEST_INVALID");
  }
  expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_archive")).toEqual([]);
});

it("discards retained archive metadata across signout and reader replacement", async () => {
  for (const kind of ["signout", "reader"] as const) {
    let finish!: (body: unknown) => void;
    const env = await environment(() => new Promise(resolve => { finish = resolve; }));
    const pending = env.host.readProjectArchive!(request());
    if (kind === "signout") env.notify({ status: "signed_out", reason: null, acquisition: false, content: false });
    else env.raw.readProjectArchive = async () => fixture;
    finish(fixture);
    await expect(pending).rejects.toThrow("READ_CANCELLED");
  }
});


it("binds continuation to fixed native cursor arguments and rejects caller paths", async () => {
  const page = structuredClone(fixture);
  page.catalogue.work_refs = [fixture.catalogue.work_refs[1]!]; page.sample.items = [];
  page.sample.coverage.supplied_count = 1; page.sample.coverage.observed_count = 1;
  const env = await environment(async () => page);
  const cursor = { after_work_ref: fixture.catalogue.work_refs[0]!, catalogue_digest: fixture.catalogue.document_digest };
  expect((await env.host.readProjectArchivePage!({ ...cursor, ...request() })).availability).toBe("AVAILABLE");
  expect(env.invoke.mock.calls.filter(([command]) => command === "read_project_archive_page")).toEqual([["read_project_archive_page", { cursor }]]);
  await expect(env.host.readProjectArchivePage!({ ...cursor, ...request(), path: "private" } as never)).rejects.toThrow("PROJECT_ARCHIVE_REQUEST_INVALID");
});

it("withholds continuation replies when the actual source reader changes during acquisition", async () => {
  let finish!: (body: unknown) => void;
  const env = await environment(() => new Promise(resolve => { finish = resolve; }));
  const cursor = { after_work_ref: fixture.catalogue.work_refs[0]!, catalogue_digest: fixture.catalogue.document_digest };
  const pending = env.host.readProjectArchivePage!({ ...cursor, ...request() });
  env.raw.readProjectArchivePage = async () => fixture;
  finish(fixture);
  await expect(pending).rejects.toThrow("READ_CANCELLED");
});
