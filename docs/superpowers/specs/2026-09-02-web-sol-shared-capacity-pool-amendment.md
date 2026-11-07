# Web-Sol Usage Capacity — Shared Pool Topology Amendment

**Date:** 2026-09-02  
**Owner:** Sol, AI CEO  
**Operation:** `web-sol-pro-usage-observability-20260902-sol-001`  
**Amends:** `docs/superpowers/specs/2026-09-02-web-sol-pro-usage-observability-design.md`  
**Source law:** `docs/EXECUTIVE_WEB_SOL_USAGE_CAPACITY_LAW.md`  
**State:** `SPEC_ONLY / PRODUCTION_INERT`.

## 1. Discovery that requires this amendment

Current OpenAI plan documentation shows that a ChatGPT browser realm is not always the same thing as the resource pool that ultimately funds advanced usage.

At the current research date:

- Business Standard/Premium seats have per-seat included advanced-feature usage;
- a Business workspace may separately hold purchased credits in a **shared workspace pool** that can cover eligible usage after a seat's included allowance is exhausted;
- Enterprise/Edu can have workspace/user usage controls, shared credit/overage resources, and different billing/usage-period rules;
- GPT-5.6 Sol and Sol Pro can have fixed per-message credit rates on applicable flexible-pricing plans while included plan allowances remain separate;
- regular Chat, Work/Codex, included allowance, purchased credits, workspace limits and provider abuse/temporary restrictions can therefore be distinct constraints.

This means the initial intuitive model:

```text
one browser profile -> one quota balance
```

is insufficient for Business/Enterprise and risks double-counting a shared pool once per browser realm.

## 2. Frozen topology

Provider Control vNext must distinguish **realm slots** from **capacity resource pools**.

```text
CapacityRealmSlot
    = one exact managed browser / provider execution realm

CapacityResourcePool
    = one quota/credit/limit resource that can constrain or fund one or more realm slots
```

The relation is many-to-many in principle:

```text
one realm slot
    -> per-seat included allowance
    -> optional workspace shared credits
    -> optional workspace/user spend control
    -> provider/model-specific temporary restriction

one workspace shared credit pool
    -> may be referenced by multiple realm slots
```

Do not copy a shared pool balance into every slot and call each copy independent capacity.

## 3. Capacity resource classes

The initial closed conceptual classes are:

```text
seat_included_allowance
workspace_shared_credits
workspace_user_limit
workspace_group_limit
workspace_default_limit
workspace_overage_limit
subscription_model_allowance
provider_temporary_restriction
concurrency_limit
unknown
```

These names are semantic categories, not a claim that every plan exposes every class.

Each resource has its own:

```text
resource_ref                 opaque, company-local
resource_class
provider
scope                         slot | workspace | group | user | subscription | global | unknown
metric                        requests | percent | credits | currency | concurrency | custom
limit                         nullable
used                          nullable
remaining                     nullable
used_percent                  nullable
reset_at                      nullable
window_type                   nullable
window_duration_seconds       nullable
observed_at
stale_after
provenance
source_ref
```

Unknown dynamic fields remain null.

## 4. Slot-to-resource links require proof

A realm slot may reference a shared resource only when a supported/provider-admin source or reviewed provisioning ceremony proves the association.

A link has conceptual fields:

```text
capacity_capability_id
resource_ref
relationship                 consumes | constrained_by | eligible_for | unknown
link_evidence
linked_at
realm_generation
resource_generation
```

The following are not valid linkage proofs:

- matching browser profile names;
- matching Slack principals;
- both sessions saying `Business Premium`;
- same machine/host;
- same company email domain;
- guessed seat ordinal;
- a user-visible credit total with no supported way to establish which realm consumes it.

If a shared pool is visible but the exact realm-to-pool link is not safely proven, Provider Control may expose the pool as a separate resource while the slot relationship remains UNKNOWN.

## 5. Workspace identity remains opaque

A supported Business/Enterprise administrative source may expose a stable workspace/resource identifier. Provider Control may preserve an irreversible/company-local opaque reference derived through the reviewed provisioning boundary.

The capacity projection must not publish:

- raw workspace name;
- member email;
- billing contact;
- invoice id;
- provider admin credential;
- full provider workspace id if an opaque local ref suffices.

Browser Web-Sol does not discover workspace membership by reading account menus or credentials.

## 6. Included allowance and purchased credits are sequential resources, not one sum

For a Business seat, the practical path may be:

```text
seat included allowance
    -> if exhausted and feature is eligible
    -> workspace shared purchased credits
    -> subject to workspace/user/group/overage controls
```

Do not render:

```text
remaining = included_remaining + workspace_credits
```

unless the provider contract explicitly makes those units and accessibility comparable. Even when both are request/credit-like, one can be unavailable because:

- the seat's feature is not credit-eligible;
- the workspace has disabled or capped credit usage;
- another seat consumes the shared pool first;
- a user/group limit blocks usage before the pool is empty;
- provider temporary restrictions override commercial headroom.

Provider Control therefore models **constraints and fallback resources**, not a single arithmetic balance.

## 7. Capacity is not spend authority

A shared credit balance being available is an operational fact. It does not authorize Mastermind to spend purchased credits.

Future Executive planning must keep at least these gates separate:

```text
model/execution suitable?
realm eligible and healthy?
provider capacity resource available?
workspace/user policy allows use?
company spend/budget authority allows use?
current operation may start on this realm?
```

A `workspace_shared_credits` resource may be healthy while `spend_authorized=false` under company policy. Capacity may explain the option but may not convert it into authority.

This is especially important when included subscription usage is economically preferred but shared credits/overage are metered.

## 8. Control Room projection

The UI should show the hierarchy rather than pretending each account has an independent wallet.

Example:

```text
ChatGPT Web Realm B — Business Premium
Realm state                 AVAILABLE
Mastermind Pro submits      23 [EXACT LOCAL]
Seat included headroom      UNKNOWN
Seat included reset         UNKNOWN

Workspace resource          Shared credits [LINK PROVEN]
Workspace credits remaining 4,250 [PROVIDER REPORTED]
Workspace usage period      Monthly [PROVIDER REPORTED]
Spend policy                HOLD / NOT AUTHORIZED

Forecast                    Seat exhaustion unknown
```

For two realms consuming the same shared pool, Control Room should render one pool identity/reference and two links, not two cloned credit balances.

## 9. Forecasting implications

Historical learning must distinguish:

```text
turns until seat included allowance exhausted
credits/messages consumed after fallback to shared pool
workspace shared-pool burn across all linked realms
provider temporary restriction incidence
```

A forecast for one realm cannot assume the shared pool is static because other realms/users can consume it. Shared-pool forecasts therefore require pool-level observation freshness and should expose uncertainty from unobserved external consumption.

## 10. Versioned Provider Control requirement

`CAP-WEB-F0` must explicitly evaluate whether the accepted Provider Control vNext needs first-class shared resources and slot-resource links. The design must preserve the current `mastermind.provider_capacity.v1` contract for existing consumers.

Do not represent a shared pool by:

- duplicating quota horizons into every slot;
- creating a Web-Sol-local workspace credit database;
- adding a second Capacity service;
- treating a Control Room join as canonical association;
- using Executive Jobs/Attempts as the pool ledger.

Macro Shared AI Provider Control remains the one owner of provider capacity topology.

## 11. Source-law additions frozen by this amendment

The following statements are now part of WSX-Q0 architecture:

1. browser realm identity and capacity-resource identity are separate;
2. one realm may consume multiple distinct resources;
3. one shared resource may serve multiple realms;
4. shared resource balances are stored once canonically and referenced, not cloned per realm;
5. slot-to-pool membership requires supported/provisioned evidence;
6. available purchased credits do not grant spend authority;
7. included allowance, shared credits, usage limits and provider restrictions are not arithmetically collapsed;
8. unknown linkage remains UNKNOWN rather than guessed from plan/account labels;
9. current Provider Capacity v1 is not patched in place to obtain this topology;
10. no quota visibility feature may become account switching or usage-limit evasion.