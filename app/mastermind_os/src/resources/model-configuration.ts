/** Bounded configured-routing view. No live accounts, credentials or admission. */
export const MODEL_CONFIGURATION_SCHEMA = "mastermind.workspace_model_configuration.v1" as const;
const CONFIGURATION_SCHEMA = "mastermind.model_router_configuration.v1";
const MAX_BYTES = 278_528;
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$/;
const DIGEST = /^[0-9a-f]{64}$/;
const SECRET = /xox[baprs]-|xapp-|github_pat_|gh[pousr]_|sk-[A-Za-z0-9_-]{16,}|bearer\s/i;
type Obj = Record<string, unknown>;
export type ModelProviderConfiguration = { adapter_id: string; enabled: boolean; autonomous_allowed: boolean };
export type ModelAliasConfiguration = {
  provider_alias: string; adapter_id: string; model: string; effort: string; cost_class: string;
  capabilities: string[]; worker_eligible: boolean; execution_profile_id: string; execution_profile_digest: string;
};
export type ModelRouteTier = { tier_id: string; model_aliases: string[] };
export type ModelRoutingConfiguration = { required_capabilities: string[]; routine: ModelRouteTier[]; elevated: ModelRouteTier[] };
export type ModelConfiguration = {
  schema: string; owner: "model_router"; scope: "EXECUTIVE_ROUTING_POLICY";
  revision: string; policy_version: string; capability_policy_version: string; capability_policy_digest: string;
  physical_account_pools: "NOT_JOINED"; live_capacity: "NOT_OBSERVED";
  admission_authorized: false; writes_applied: false; credential_resolution_performed: false;
  providers: Record<string, ModelProviderConfiguration>;
  models: Record<string, ModelAliasConfiguration>;
  routes: Record<string, ModelRoutingConfiguration>;
};
export type ModelConfigurationRead =
  | { state: "AVAILABLE"; observedAt: string; configuration: ModelConfiguration }
  | { state: "UNAVAILABLE"; reason: "SOURCE_UNAVAILABLE" | "SOURCE_CHANGED" | "RESPONSE_OVER_BUDGET" | "INVALID_RESPONSE" };

const object = (x: unknown): x is Obj => !!x && typeof x === "object" && !Array.isArray(x);
const exact = (x: Obj, keys: string[]) => Object.keys(x).length === keys.length && keys.every(k => Object.hasOwn(x, k));
const token = (x: unknown): x is string => typeof x === "string" && TOKEN.test(x) && !SECRET.test(x);
const digest = (x: unknown): x is string => typeof x === "string" && DIGEST.test(x);
const tokens = (x: unknown): x is string[] => Array.isArray(x) && x.length <= 64 && x.every(token);
const invalid = (): ModelConfigurationRead => ({ state: "UNAVAILABLE", reason: "INVALID_RESPONSE" });

export function decodeModelConfiguration(value: unknown): ModelConfigurationRead {
  try {
    const encoded = JSON.stringify(value);
    if (typeof encoded !== "string" || new TextEncoder().encode(encoded).length > MAX_BYTES) return invalid();
    if (!object(value) || !exact(value, ["schema", "availability", "observed_at", "source_owner", "reason_codes", "configuration"])
      || value.schema !== MODEL_CONFIGURATION_SCHEMA || value.source_owner !== "model_router") return invalid();
    if (value.availability === "UNAVAILABLE") {
      const reasons = value.reason_codes;
      if (value.configuration !== null || value.observed_at !== null || !Array.isArray(reasons) || reasons.length !== 1) return invalid();
      if (reasons[0] === "SOURCE_UNAVAILABLE" || reasons[0] === "SOURCE_CHANGED" || reasons[0] === "RESPONSE_OVER_BUDGET")
        return { state: "UNAVAILABLE", reason: reasons[0] };
      return invalid();
    }
    if (value.availability !== "AVAILABLE" || typeof value.observed_at !== "string"
      || value.observed_at.length > 64 || !/(Z|\+00:00)$/.test(value.observed_at)
      || !Number.isFinite(Date.parse(value.observed_at))
      || !Array.isArray(value.reason_codes) || value.reason_codes.length) return invalid();
    const c = value.configuration;
    if (!object(c) || !exact(c, ["schema", "owner", "scope", "revision", "policy_version", "capability_policy_version",
      "capability_policy_digest", "physical_account_pools", "live_capacity", "admission_authorized", "writes_applied",
      "credential_resolution_performed", "providers", "models", "routes"])
      || c.schema !== CONFIGURATION_SCHEMA || c.owner !== "model_router" || c.scope !== "EXECUTIVE_ROUTING_POLICY"
      || c.physical_account_pools !== "NOT_JOINED" || c.live_capacity !== "NOT_OBSERVED"
      || c.admission_authorized !== false || c.writes_applied !== false || c.credential_resolution_performed !== false
      || !digest(c.revision) || !digest(c.capability_policy_digest) || !token(c.policy_version) || !token(c.capability_policy_version)
      || !object(c.providers) || Object.keys(c.providers).length > 128
      || !object(c.models) || Object.keys(c.models).length > 1024
      || !object(c.routes) || Object.keys(c.routes).length > 128) return invalid();
    const providers: Record<string, ModelProviderConfiguration> = Object.create(null);
    for (const [name, row] of Object.entries(c.providers)) {
      if (!token(name) || !object(row) || !exact(row, ["adapter_id", "enabled", "autonomous_allowed"])
        || !token(row.adapter_id) || typeof row.enabled !== "boolean" || typeof row.autonomous_allowed !== "boolean") return invalid();
      providers[name] = { adapter_id: row.adapter_id, enabled: row.enabled, autonomous_allowed: row.autonomous_allowed };
    }
    const models: Record<string, ModelAliasConfiguration> = Object.create(null);
    for (const [name, row] of Object.entries(c.models)) {
      if (!token(name) || !object(row) || !exact(row, ["provider_alias", "adapter_id", "model", "effort", "cost_class",
        "capabilities", "worker_eligible", "execution_profile_id", "execution_profile_digest"])
        || !token(row.provider_alias) || !Object.hasOwn(providers, row.provider_alias) || !token(row.adapter_id)
        || row.adapter_id !== providers[row.provider_alias].adapter_id || !token(row.model) || !token(row.effort)
        || !token(row.cost_class) || !token(row.execution_profile_id) || !digest(row.execution_profile_digest)
        || !tokens(row.capabilities) || typeof row.worker_eligible !== "boolean") return invalid();
      models[name] = { provider_alias: row.provider_alias, adapter_id: row.adapter_id, model: row.model,
        effort: row.effort, cost_class: row.cost_class, capabilities: [...row.capabilities], worker_eligible: row.worker_eligible,
        execution_profile_id: row.execution_profile_id, execution_profile_digest: row.execution_profile_digest };
    }
    const routes: Record<string, ModelRoutingConfiguration> = Object.create(null);
    for (const [kind, row] of Object.entries(c.routes)) {
      if (!token(kind) || !object(row) || !exact(row, ["required_capabilities", "routine", "elevated"])
        || !tokens(row.required_capabilities)) return invalid();
      const readTiers = (tiers: unknown): ModelRouteTier[] | null => {
        if (!Array.isArray(tiers) || tiers.length > 64) return null;
        const answer: ModelRouteTier[] = [];
        for (const tier of tiers) {
          if (!object(tier) || !exact(tier, ["tier_id", "model_aliases"]) || !token(tier.tier_id) || !tokens(tier.model_aliases)
            || tier.model_aliases.some(alias => !Object.hasOwn(models, alias))) return null;
          answer.push({ tier_id: tier.tier_id, model_aliases: [...tier.model_aliases] });
        }
        return answer;
      };
      const routine = readTiers(row.routine), elevated = readTiers(row.elevated);
      if (!routine || !elevated) return invalid();
      routes[kind] = { required_capabilities: [...row.required_capabilities], routine, elevated };
    }
    return { state: "AVAILABLE", observedAt: value.observed_at, configuration: {
      schema: CONFIGURATION_SCHEMA, owner: "model_router", scope: "EXECUTIVE_ROUTING_POLICY", revision: c.revision,
      policy_version: c.policy_version, capability_policy_version: c.capability_policy_version,
      capability_policy_digest: c.capability_policy_digest, physical_account_pools: "NOT_JOINED", live_capacity: "NOT_OBSERVED",
      admission_authorized: false, writes_applied: false, credential_resolution_performed: false, providers, models, routes,
    } };
  } catch {
    return invalid();
  }
}
