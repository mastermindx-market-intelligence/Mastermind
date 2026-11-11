import type { ModelConfiguration } from "./model-configuration";

export type RouteRisk = "routine" | "elevated";
export type PolicyReason = "PROVIDER_DISABLED" | "AUTONOMOUS_DISABLED" | "WORKER_NOT_ELIGIBLE" | "CAPABILITIES_MISSING";
export type ConfiguredRouteRow = {
  alias: string; model: string; provider: string; tier: string;
  reasons: PolicyReason[]; missingCapabilities: string[];
};

/** Explain the supplied owner's policy, without choosing an account/model,
 * reserving capacity, evaluating live eligibility, or changing tier order. */
export function explainConfiguredRoute(configuration: ModelConfiguration, workload: string, risk: RouteRisk, exactAlias = "") {
  const route = configuration.routes[workload];
  const tiers = route?.[risk] ?? [];
  const rows: ConfiguredRouteRow[] = tiers.flatMap(tier => tier.model_aliases.map(alias => {
    const model = configuration.models[alias];
    const provider = configuration.providers[model.provider_alias];
    const missingCapabilities = route.required_capabilities.filter(capability => !model.capabilities.includes(capability));
    const reasons: PolicyReason[] = [];
    if (!provider.enabled) reasons.push("PROVIDER_DISABLED");
    if (!provider.autonomous_allowed) reasons.push("AUTONOMOUS_DISABLED");
    if (!model.worker_eligible) reasons.push("WORKER_NOT_ELIGIBLE");
    if (missingCapabilities.length) reasons.push("CAPABILITIES_MISSING");
    return { alias, model: model.model, provider: model.provider_alias, tier: tier.tier_id, reasons, missingCapabilities };
  }));
  const pinState = !exactAlias ? "NONE" : !Object.hasOwn(configuration.models, exactAlias)
    ? "UNKNOWN_ALIAS" : !rows.some(row => row.alias === exactAlias) ? "OUTSIDE_ROUTE" : "IN_ROUTE";
  return {
    workload, risk, revision: configuration.revision, requiredCapabilities: route?.required_capabilities ?? [],
    rows: exactAlias ? rows.filter(row => row.alias === exactAlias) : rows,
    pinState,
    // This is a local explanation of an already authenticated policy snapshot.
    // H2/H3's physical-account and original commitment evidence are separate.
    accountSelection: "NOT_OBSERVED", servedModel: "NOT_OBSERVED", reservation: "NONE",
    liveEligibility: "NOT_EVALUATED", admissionAuthorized: false,
  } as const;
}

export function policyModelCounts(configuration: ModelConfiguration) {
  const models = Object.values(configuration.models);
  return {
    configured: models.length,
    enabledInPolicy: models.filter(model => configuration.providers[model.provider_alias].enabled).length,
    // A configured profile, enabled provider or declared capability is not
    // qualification, current entitlement or successful real execution.
    qualified: null, currentlyEligible: null, realPathProven: null,
    physicalAccounts: null,
  };
}

export function displayObservationTime(value: string, locale: "en" | "zh-CN", timeZone: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  try {
    return new Intl.DateTimeFormat(locale === "zh-CN" ? "zh-CN" : "en-CA", {
      timeZone, year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZoneName: "short",
    }).format(date);
  } catch { return null; }
}
