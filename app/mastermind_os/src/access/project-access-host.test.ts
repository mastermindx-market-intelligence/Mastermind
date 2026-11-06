// @vitest-environment node
import { it, expect, vi } from "vitest";
import fixture from "./fixtures/current-grants.json";
import v5 from "./fixtures/v5-current-grants.json";
import {
  projectAccessHostMethods,
  projectAccessPublicSelection,
} from "./project-access-host";
import { bindMissionHost, createNativeClient } from "../host";
const auth = {
  status: "signed_in" as const,
  reason: null,
  acquisition: true,
  content: false,
};
const request = () => ({
  selection: { work_ref: "WS:ONE" },
  signal: new AbortController().signal,
});
it("requires actual generation/auth and decodes all permission facts", async () => {
  const raw = vi.fn(async (): Promise<unknown> => fixture),
    client = { getState: () => auth, readProjectAccess: raw };
  expect(
    projectAccessHostMethods(client, () => 0).readProjectAccess,
  ).toBeUndefined();
  const host = projectAccessHostMethods(
    { ...client, invalidationGeneration: () => 0 },
    () => 0,
  );
  await expect(host.readProjectAccess!(request())).resolves.toEqual(fixture);
  raw.mockResolvedValueOnce({ ...fixture, eligible: true });
  await expect(host.readProjectAccess!(request())).rejects.toThrow(
    "RESPONSE_INVALID",
  );
  const refused = projectAccessHostMethods(
    {
      ...client,
      getState: () => ({ ...auth, acquisition: false }),
      invalidationGeneration: () => 0,
    },
    () => 0,
  );
  raw.mockClear();
  await expect(refused.readProjectAccess!(request())).rejects.toThrow(
    "UNAUTHORIZED",
  );
  expect(raw).not.toHaveBeenCalled();
});
it.each(["epoch", "generation", "method", "abort"])(
  "withholds late grant facts after %s changes",
  async (change) => {
    let epoch = 0,
      generation = 0,
      finish!: (body: unknown) => void;
    const client = {
      getState: () => auth,
      invalidationGeneration: () => generation,
      readProjectAccess: vi.fn(
        () =>
          new Promise<unknown>((resolve) => {
            finish = resolve;
          }),
      ),
    };
    const controller = new AbortController(),
      r = { selection: { work_ref: "WS:ONE" }, signal: controller.signal },
      pending = projectAccessHostMethods(client, () => epoch)
        .readProjectAccess!(r);
    if (change === "epoch") epoch++;
    else if (change === "generation") generation++;
    else if (change === "method")
      client.readProjectAccess = vi.fn(async () => fixture);
    else controller.abort();
    finish(fixture);
    await expect(pending).rejects.toThrow("AUTH_CHANGED");
  },
);
it("rejects foreign authority selectors and accessor requests before reading", () => {
  expect(
    projectAccessPublicSelection({ ...request(), principal: "forged" }),
  ).toBeNull();
  expect(
    projectAccessPublicSelection({
      ...request(),
      selection: { work_ref: "WS:ONE", root_job_id: "JOB-1" },
    }),
  ).toBeNull();
  let reads = 0;
  const hostile = request();
  Object.defineProperty(hostile, "selection", {
    enumerable: true,
    get() {
      reads++;
      return fixture.selection;
    },
  });
  expect(projectAccessPublicSelection(hostile)).toBeNull();
  expect(reads).toBe(0);
});
it("uses only the fixed native read and detached project selection", async () => {
  const invoke = vi.fn(async (command: string) =>
    command === "executive_auth_status"
      ? { generation: 0, available: false }
      : command === "auth_status"
        ? auth
        : fixture,
  );
  const client = await createNativeClient(
      invoke as never,
      async () => () => {},
    ),
    host = bindMissionHost(client);
  await expect(host.readProjectAccess!(request())).resolves.toEqual(fixture);
  expect(invoke.mock.calls.slice(2)).toEqual([
    ["read_project_access", { selection: { work_ref: "WS:ONE" } }],
  ]);
});

it("decodes v5 DATA and proposal grants separately from ordinary READ", async () => {
  const client = {
    getState: () => auth,
    invalidationGeneration: () => 0,
    readProjectAccess: vi.fn(async () => v5),
  };
  const body = await projectAccessHostMethods(client, () => 0)
    .readProjectAccess!(request());
  expect(body).toEqual(v5);
  expect(body.schema).toBe("mastermind.workspace_project_access.v2");
});
