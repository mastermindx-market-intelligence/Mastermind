/** One authenticated metadata observation. It never establishes a connected role. */
export const BYOK_ROLES_SCHEMA = "mastermind.workspace_byok_roles.v1";
export const BYOK_ROLES_RESPONSE_CAP = 8192;
export type ByokRole = "mmmeta" | "mmsecretary";
export type ByokRoleState = "ABSENT" | "CONFIGURATION_OBSERVED" | "UNAVAILABLE";
export interface ByokRoleMetadata {
  readonly role: ByokRole;
  readonly state: ByokRoleState;
  readonly requested_provider: string | null;
  readonly requested_model: string | null;
}
export interface ByokSourceObservation {
  readonly host_binding_sha256: string;
  readonly host_boot_id: string;
  readonly implementation_sha: string;
  readonly metadata_sha256: string;
  readonly observed_at_ms: number;
}
export interface ByokRolesRead {
  readonly schema: typeof BYOK_ROLES_SCHEMA;
  readonly state: "SOURCE_UNBOUND" | "UNAVAILABLE" | "OBSERVED";
  readonly reason_code: "SOURCE_UNBOUND" | "SOURCE_UNAVAILABLE" | "SOURCE_CHANGED" | "SOURCE_STALE" | "OBSERVED";
  readonly roles: readonly [] | readonly [ByokRoleMetadata, ByokRoleMetadata];
  readonly source_observation: ByokSourceObservation | null;
  readonly proof: Readonly<{
    credentials_read: false; provider_called: false; service_observed: false;
    served_model_verified: false; credential_enrollment: "UNVERIFIED";
  }>;
}

function refuse(): never { throw new Error("BYOK_RESPONSE_INVALID"); }
function record(raw: unknown, keys: readonly string[]): Record<string, unknown> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(raw))) return refuse();
  const descriptors = Object.getOwnPropertyDescriptors(raw);
  if (Reflect.ownKeys(raw).length !== keys.length ||
      keys.some(key => !descriptors[key] || !("value" in descriptors[key]))) return refuse();
  return Object.fromEntries(keys.map(key => [key, descriptors[key].value]));
}
function list(raw: unknown): unknown[] {
  if (!Array.isArray(raw) || Object.getPrototypeOf(raw) !== Array.prototype ||
      ![0, 2].includes(raw.length) || Reflect.ownKeys(raw).length !== raw.length + 1) return refuse();
  const descriptors = Object.getOwnPropertyDescriptors(raw);
  return Array.from({ length: raw.length }, (_, index) => {
    const descriptor = descriptors[String(index)];
    return descriptor && "value" in descriptor ? descriptor.value : refuse();
  });
}
function matches(value: unknown, pattern: RegExp): value is string {
  return typeof value === "string" && pattern.exec(value)?.[0] === value;
}

export function decodeByokRolesRead(raw: unknown): ByokRolesRead {
  if (typeof raw === "string") {
    if (new TextEncoder().encode(raw).byteLength > BYOK_ROLES_RESPONSE_CAP) return refuse();
    try { raw = JSON.parse(raw); } catch { return refuse(); }
  }
  const body = record(raw, ["schema", "state", "reason_code", "roles", "source_observation", "proof"]);
  if (body.schema !== BYOK_ROLES_SCHEMA) return refuse();
  const proof = record(body.proof, ["credentials_read", "provider_called", "service_observed",
    "served_model_verified", "credential_enrollment"]);
  if (proof.credentials_read !== false || proof.provider_called !== false ||
      proof.service_observed !== false || proof.served_model_verified !== false ||
      proof.credential_enrollment !== "UNVERIFIED") return refuse();
  const rows = list(body.roles);
  let source: ByokSourceObservation | null = null;
  let roles: readonly [] | readonly [ByokRoleMetadata, ByokRoleMetadata] = Object.freeze([]);
  if (body.state === "OBSERVED") {
    if (body.reason_code !== "OBSERVED" || rows.length !== 2) return refuse();
    roles = Object.freeze(rows.map((rawRole, index) => {
      const row = record(rawRole, ["role", "state", "requested_provider", "requested_model"]);
      if (row.role !== ["mmmeta", "mmsecretary"][index] ||
          typeof row.state !== "string" ||
          !["ABSENT", "CONFIGURATION_OBSERVED", "UNAVAILABLE"].includes(row.state)) return refuse();
      if (row.state === "CONFIGURATION_OBSERVED") {
        const identifier = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$/;
        if (!matches(row.requested_provider, identifier) || !matches(row.requested_model, identifier)) return refuse();
      } else if (row.requested_provider !== null || row.requested_model !== null) return refuse();
      return Object.freeze(row) as unknown as ByokRoleMetadata;
    })) as unknown as readonly [ByokRoleMetadata, ByokRoleMetadata];
    const observed = record(body.source_observation, ["host_binding_sha256", "host_boot_id",
      "implementation_sha", "metadata_sha256", "observed_at_ms"]);
    if (!matches(observed.host_binding_sha256, /^[0-9a-f]{64}$/) ||
        !matches(observed.host_boot_id, /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/) ||
        !matches(observed.implementation_sha, /^[0-9a-f]{40}$/) ||
        !matches(observed.metadata_sha256, /^[0-9a-f]{64}$/) ||
        !Number.isSafeInteger(observed.observed_at_ms) || Number(observed.observed_at_ms) <= 0) return refuse();
    source = Object.freeze(observed) as unknown as ByokSourceObservation;
  } else {
    if (rows.length || body.source_observation !== null ||
        typeof body.reason_code !== "string" ||
        !(body.state === "SOURCE_UNBOUND" && body.reason_code === "SOURCE_UNBOUND" ||
          body.state === "UNAVAILABLE" && ["SOURCE_UNAVAILABLE", "SOURCE_CHANGED", "SOURCE_STALE"].includes(body.reason_code))) return refuse();
  }
  return Object.freeze({ schema: BYOK_ROLES_SCHEMA, state: body.state, reason_code: body.reason_code,
    roles, source_observation: source, proof: Object.freeze(proof) }) as ByokRolesRead;
}
