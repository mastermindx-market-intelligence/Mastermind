import { describe, expect, it, vi } from "vitest";
import { bindMissionHost, createNativeClient, type AuthState, type RawClient } from "../host";
import { BYOK_ROLES_SCHEMA, decodeByokRolesRead } from "./byok-roles-read";

const signed: AuthState = { status: "signed_in", reason: null, acquisition: true, content: true };
const proof = () => ({ credentials_read: false, provider_called: false, service_observed: false,
  served_model_verified: false, credential_enrollment: "UNVERIFIED" });
const unavailable = () => ({ schema: BYOK_ROLES_SCHEMA, state: "SOURCE_UNBOUND", reason_code: "SOURCE_UNBOUND",
  roles: [], source_observation: null, proof: proof() });
function observed() {
  return { schema: BYOK_ROLES_SCHEMA, state: "OBSERVED", reason_code: "OBSERVED", proof: proof(),
    roles: [{ role: "mmmeta", state: "CONFIGURATION_OBSERVED", requested_provider: "zai", requested_model: "glm-5.3" },
      { role: "mmsecretary", state: "ABSENT", requested_provider: null, requested_model: null }],
    source_observation: { host_binding_sha256: "a".repeat(64), host_boot_id: "01234567-0123-4567-89ab-0123456789ab",
      implementation_sha: "b".repeat(40), metadata_sha256: "c".repeat(64), observed_at_ms: Date.now() } };
}
function clientFixture() {
  let state = signed, generation = 0;
  const listeners = new Set<(state: AuthState) => void>();
  const client: RawClient = { getState: () => state, invalidationGeneration: () => generation,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    signIn: async () => {}, signOut: async () => {}, readPrograms: async () => ({}),
    readWork: async () => ({}), readMission: async () => ({}), readCurrentWindow: async () => ({}),
    readByokRoles: vi.fn(async () => observed()) };
  return { client, change(next = signed) { state = next; generation++; listeners.forEach(fn => fn(state)); } };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

describe("closed authenticated BYOK metadata", () => {
  it("keeps unbound distinct from absence and detaches a valid pair", () => {
    expect(decodeByokRolesRead(unavailable()).roles).toEqual([]);
    const raw = observed(), value = decodeByokRolesRead(raw);
    raw.roles[0].requested_model = "changed";
    expect(value.roles[0]?.requested_model).toBe("glm-5.3");
    expect(Object.isFrozen(value.roles[0])).toBe(true);
    expect(Object.isFrozen(value.source_observation)).toBe(true);
    expect(Object.isFrozen(value.proof)).toBe(true);
  });
  it.each(["extra", "swapped", "duplicate", "connected", "provider_proof", "integer_proof",
    "path", "oversized", "newline", "absent_model", "unbound_roles", "coercion"])("refuses %s", defect => {
    const raw = observed();
    if (defect === "extra") Object.assign(raw, { secret: "must-not-escape" });
    if (defect === "swapped") raw.roles.reverse();
    if (defect === "duplicate") raw.roles[1].role = "mmmeta";
    if (defect === "connected") raw.roles[0].state = "CONNECTED";
    if (defect === "provider_proof") raw.proof.provider_called = true;
    if (defect === "integer_proof") Object.assign(raw.proof, { credentials_read: 0 });
    if (defect === "path") Object.assign(raw.source_observation, { path: "/private/role" });
    if (defect === "oversized") raw.roles[0].requested_model = "x".repeat(9000);
    if (defect === "newline") raw.roles[0].requested_model = "glm-5.3\n";
    if (defect === "absent_model") raw.roles[1].requested_model = "candidate";
    if (defect === "unbound_roles") raw.state = "SOURCE_UNBOUND";
    if (defect === "coercion") Object.assign(raw.roles[0], { state: { toString: () => { throw new Error("coerced"); } } });
    expect(() => decodeByokRolesRead(raw)).toThrow("BYOK_RESPONSE_INVALID");
  });
  it("refuses accessor fields without reading them", () => {
    const raw = observed(), getter = vi.fn(() => "glm-5.3");
    Object.defineProperty(raw.roles[0], "requested_model", { get: getter });
    expect(() => decodeByokRolesRead(raw)).toThrow("BYOK_RESPONSE_INVALID");
    expect(getter).not.toHaveBeenCalled();
  });
  it("requires the raw read and source generation before exposing a host capability", () => {
    const e = clientFixture(); delete e.client.invalidationGeneration;
    expect(bindMissionHost(e.client).readByokRoles).toBeUndefined();
  });
  it("calls the source once for both roles", async () => {
    const e = clientFixture(), host = bindMissionHost(e.client);
    expect((await host.readByokRoles!({ signal: new AbortController().signal })).roles).toHaveLength(2);
    expect(e.client.readByokRoles).toHaveBeenCalledOnce();
  });
  it.each(["aborted", "signed_out"])("refuses %s before source invocation", async defect => {
    const e = clientFixture(), host = bindMissionHost(e.client), controller = new AbortController();
    if (defect === "aborted") controller.abort();
    else e.change({ ...signed, status: "signed_out", acquisition: false });
    await expect(host.readByokRoles!({ signal: controller.signal })).rejects.toThrow();
    expect(e.client.readByokRoles).not.toHaveBeenCalled();
  });
  it.each(["auth", "method", "generation", "abort"])("discards a late result after %s replacement", async defect => {
    const e = clientFixture(), held = deferred<unknown>(), controller = new AbortController();
    const read = vi.fn(() => held.promise); e.client.readByokRoles = read;
    const pending = bindMissionHost(e.client).readByokRoles!({ signal: controller.signal });
    if (defect === "auth") e.change();
    if (defect === "method") e.client.readByokRoles = async () => observed();
    if (defect === "generation") e.client.invalidationGeneration = () => 0;
    if (defect === "abort") controller.abort();
    held.resolve(observed());
    await expect(pending).rejects.toThrow("READ_CANCELLED");
    expect(read).toHaveBeenCalledOnce();
  });
  it("maps the native read to one fixed command with no caller target", async () => {
    const invoke = vi.fn(async <T,>(command: string): Promise<T> => (command === "auth_status" ? signed : unavailable()) as T);
    const native = await createNativeClient(invoke as Parameters<typeof createNativeClient>[0], async () => () => {});
    invoke.mockClear();
    const host = bindMissionHost(native);
    expect((await host.readByokRoles!({ signal: new AbortController().signal })).state).toBe("SOURCE_UNBOUND");
    expect(invoke).toHaveBeenCalledExactlyOnceWith("read_byok_roles", undefined);
  });
});
