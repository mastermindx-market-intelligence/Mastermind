import { describe, expect, it } from "vitest";
import { byokRoleView } from "./byok-role-view";
import { BYOK_ROLES_SCHEMA, decodeByokRolesRead, type ByokRolesRead } from "./byok-roles-read";

function observation(): ByokRolesRead {
  return decodeByokRolesRead({
    schema: BYOK_ROLES_SCHEMA, state: "OBSERVED", reason_code: "OBSERVED",
    roles: [
      { role: "mmmeta", state: "CONFIGURATION_OBSERVED", requested_provider: "zai", requested_model: "glm-5.3" },
      { role: "mmsecretary", state: "ABSENT", requested_provider: null, requested_model: null },
    ],
    source_observation: {
      host_binding_sha256: "a".repeat(64), host_boot_id: "12345678-1234-1234-1234-123456789abc",
      implementation_sha: "b".repeat(40), metadata_sha256: "c".repeat(64), observed_at_ms: 1800000000000,
    },
    proof: { credentials_read: false, provider_called: false, service_observed: false,
      served_model_verified: false, credential_enrollment: "UNVERIFIED" },
  });
}

describe("authenticated BYOK presentation mapping", () => {
  it.each(["LOADING", "SOURCE_UNBOUND", "UNAVAILABLE"] as const)(
    "does not retain an earlier observed body when the current state is %s", state => {
      expect(byokRoleView({ state, body: observation() })).toEqual({ state });
    },
  );

  it("projects only the ordered requested configuration and role states", () => {
    const body = observation();
    expect(byokRoleView({ state: "OBSERVED", body })).toEqual({ state: "OBSERVED", roles: [
      { role: "mmmeta", state: "CONFIGURATION_OBSERVED", requestedProvider: "zai", requestedModel: "glm-5.3" },
      { role: "mmsecretary", state: "ABSENT" },
    ] });
    expect(body.source_observation?.implementation_sha).toBe("b".repeat(40));
  });

  it("preserves unavailable role evidence without configuration fields", () => {
    const source = observation();
    const body = decodeByokRolesRead({ ...source, roles: [source.roles[0], {
      role: "mmsecretary", state: "UNAVAILABLE", requested_provider: null, requested_model: null,
    }] });
    expect(byokRoleView({ state: "OBSERVED", body }).roles?.[1]).toEqual({ role: "mmsecretary", state: "UNAVAILABLE" });
  });

  it("refuses an observed state with no matching observed body", () => {
    expect(byokRoleView({ state: "OBSERVED", body: null })).toEqual({ state: "UNAVAILABLE" });
    const source = observation();
    const body = decodeByokRolesRead({ ...source, state: "SOURCE_UNBOUND", reason_code: "SOURCE_UNBOUND",
      roles: [], source_observation: null });
    expect(byokRoleView({ state: "OBSERVED", body })).toEqual({ state: "UNAVAILABLE" });
  });

  it("does not make a presentation row from an inconsistent internal role pair", () => {
    const source = observation();
    const swapped = { ...source, roles: [source.roles[1], source.roles[0]] } as ByokRolesRead;
    expect(byokRoleView({ state: "OBSERVED", body: swapped })).toEqual({ state: "UNAVAILABLE" });
    const missing = { ...source, roles: [{ ...source.roles[0], requested_model: null }, source.roles[1]] } as ByokRolesRead;
    expect(byokRoleView({ state: "OBSERVED", body: missing })).toEqual({ state: "UNAVAILABLE" });
  });
});
