# H24-05 — Model pool decision projection

## Delivered boundary

`integrations/hermes_models/pool_selection.py` is a typed, pure **read-only
pre-claim projection**. It filters the incumbent Capacity owner's ordered
candidates against independently supplied Router, model capability, provider
health/quota, economics quote, Executive budget and effect facts. It returns an
expiring selection, ranked qualified alternatives, exclusion reasons and quote
provenance. It does not connect to a provider, resolve a credential, reserve a
resource, choose an account, replay a request, or install anything.

Implementation base: `b54cb10e4abdd3766c62d4088f6a576ecfe80437`.
Branch: `sol/h24-05-model-pool-20261106`.
Procedure pin: protected `master@88a8b103a5a69e4b4e870a184655dde9fd5875c3`,
`mastermind.sol_skillpack.v1`, version `1.0.1`, bootstrap major `1`.

The Chairman's current concurrent placement directive permits starting without
an H24-01/H24-02 wave seal. H24-02 is optional input; this change does not import
its branch or modify its owner. The only changed paths are this document, the
new selector and `integrations/hermes_models/tests/test_h24_pool_selection.py`.
PR #2120 integration paths, C29–C34 owners and incumbent implementations remain
outside the owned diff.

**Acceptance level:** source-only/offline. Synthetic positive facts in tests are
not live route qualifications. There is no production activation or serving
claim. No approval, self-merge, installation, credential ceremony, account
pooling, purchase or service activation is part of this packet.

## What the pinned sources actually provide

All implementation links in this section are at the immutable implementation
base. The governing economics law is read at the separate protected procedure
pin; it does not change the candidate's base.

| Existing owner/source | Observed contract | Missing input for live placement |
| --- | --- | --- |
| [Hermes contract](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_models/contract.py) | Role/provider membership, exact wire model IDs, commercial ModelArk realm and disabled Cursor placeholder. | Authenticated, current route eligibility; effective limits; health; quota; price; reservation. Configuration is not admission. |
| [Hermes client](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_models/client.py) | Outage failover only for `read_only`; 429 returns backoff; wrong/missing served model is refusal. | Cross-owner pre-claim composition and proof that a prior read-only attempt had no effect. |
| [Native BYOK](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_harness/native_byok.py) | One configured primary; no native automatic fallback; Cursor/auxiliary activation remains off. | This packet introduces no native renderer or executor integration. |
| [Model Router](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/model_router.py) and [route config](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/config/executive_worker_routes.json) | Logical suitability, ordered tiers and source/profile digests. The enabled `glm.paid.sealed-input` serves `glm-5.3-flash`; it is not Meta-CEO's `glm-5.3` route. Commercial ModelArk aliases are absent; MiniMax's attended route is disabled/non-autonomous. | An exact eligible alias on the actual Hermes surface. Neither family names nor historical role membership fill the gap. |
| [Capacity economics projection](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/capacity_economics_projection.py) | Economics cannot promote a model outside the **first** lawful Router tier. Its generic preview conservatively refuses BytePlus-looking identities. | Commercial ModelArk must arrive from an explicitly qualified incumbent owner path. Do not rename or wrap the old refused preview to manufacture eligibility. |
| [Provider model economics](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/provider_model_economics.py), [catalog](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/config/provider_model_economics.v1.json), and [offer quote owner](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/provider_offer_economics.py) | Static capability/rate declarations and time/context-qualified offer estimates. GLM rates for `opencode_go` do not price Hermes Z.AI BYOK. ModelArk/DeepSeek has no catalog row; GLM/Cursor effective limits are not established there. | Reviewed exact-model/surface capability limits and worst-case cash/native debit quotes. Do not infer discounts, free usage, context limits or pricing from another surface. |
| [Paid Capacity observer](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/control_plane/paid_fabric_capacity.py) | Retained account/broker observations; `provider_readiness` remains `UNKNOWN`. | A separate current owner-qualified readiness fact. Positive utilization/headroom does not fill this field. |
| [Usage meter](https://github.com/mastermindx-market-intelligence/Mastermind/blob/b54cb10e4abdd3766c62d4088f6a576ecfe80437/integrations/hermes_models/metering.py) | Local JSONL observations, not shared quota authority. | Full provider-native horizons, identity, reservations and resets from Shared AI Provider Control. |

The [protected subscription economics law](https://github.com/mastermindx-market-intelligence/Mastermind/blob/88a8b103a5a69e4b4e870a184655dde9fd5875c3/docs/EXECUTIVE_SUBSCRIPTION_CAPACITY_ECONOMICS_LAW.md)
keeps suitability with Router, quota/health with Provider Control, and
claims/budgets/effects with Executive. It requires preserving actual shared
depletion identity and ranking only already-eligible options. H24-05 therefore
preserves **Capacity's supplied rank**, rather than inventing weighted prices or
a fixed GLM/DeepSeek/MiniMax preference ladder. Owner ordering must already
reflect the incumbent economics policy, including opportunity cost where relevant.

## Pure API and exact incumbent fields

```python
decision = project_model_pool(
    demand,
    facts,
    current_sources=current_owner_pins,
    now=utc_epoch_seconds,
)
projection = decision.to_dict()
```

Inputs are frozen dataclasses containing tuples, bounded identifiers, strict
integers and finite nonnegative `Decimal` values. No mapping accepts arbitrary
metadata. Invalid shapes raise `PoolSelectionError` with a fixed message that
does not echo submitted values. Semantic gaps return `BLOCKED` or candidate
exclusions. Nothing is silently coerced into availability.

| Typed input | Exact fields the existing owner must supply |
| --- | --- |
| `Stamp` / `SourcePin` | Owner enum, public opaque issuer/source IDs, 64-hex content revision, observed time and expiry. The caller separately supplies `current_sources` from a current owner read. |
| `Demand` | Request/job IDs, existing Hermes role, maximum input/output tokens **per request**, maximum request count, required capabilities/tools, cash ceiling and `read_only`/`side_effecting`. `demand_digest()` binds all of these. Input includes history/tool definitions; output includes billable reasoning where the provider charges it. |
| `Suitability` — Router | Exact demand digest, first lawful tier ID and eligible model aliases. It is not an arbitrary list of cheaper fallback models. |
| `Capability` — economics/capability owner | Exact model alias, Hermes provider ID, case-sensitive wire model, `hermes.chat_completions` surface, effective context and output ceilings, capabilities, source/expiry. Unknown limits are not unlimited. |
| `Capacity` / `Candidate` — Capacity owner | Exact demand, complete Router `SourcePin` (owner/issuer/source/revision) and tier; unique candidate and owner rank; exact provider/model/alias/surface; issuer/realm/pool and generation; host/lane/worker; source, execution-profile and capability-policy digests; availability, readiness, source and policy qualification. Public digests and booleans alone do not authenticate these assertions. |
| `ProviderFacts` — Shared AI Provider Control | One coherent stamp; issuer/realm auth; exact binding pool health; binding/model health and model cooldown; a complete applicable resource manifest per model; every native resource window, unit, reset, limit, used amount and competing reservations. |
| `Quote` — economics owner | Exact demand, model/alias/provider/surface and binding; quote ID, complete independently current rate-card `SourcePin`, context band, USD maximum cash charge and upper-bound debit **with its native unit** for every applicable resource. The quote is for the entire bounded demand, not one request. Source validity must end no later than the applicable rate/offer boundary. |
| `Budget` — Executive | Job/demand binding, budget identity/revision, request/token/cash ceilings, committed usage and all competing reservations against the applicable shared envelope. |
| `EffectEvidence` — Executive | Exact demand, pre-send/read-only-no-effect/unknown/observed state, failure class, attempted provider, served model and HTTP status when observed, plus a retained no-effect receipt digest for post-send read-only fallthrough. |

`SourcePin` is provenance and movement detection, **not a new signature, seal or
authentication issuer**. The authenticated bridge must verify origin using the
existing owners' actual handles/seals and furnish detached immutable facts.
Do not construct `current_sources` by copying the submitted stamps; that would
defeat source-movement detection. The rate-card source is independently joined
to this current set; its digest is not merely output metadata. Capacity joins
the complete Router source identity, so equal revision hashes from different
issuers or sources are not interchangeable. A missing/moved issuer, revision, expired
snapshot, mixed job or Router revision produces a refusal. Source, profile or
worker movement also changes `candidate_ref()`; the parent must retain the
original candidate to resolve that opaque reference.

### Resource and price semantics

A `Window` with `served_model=None` is one shared depletion resource. A model
window names its exact wire model. Both ModelArk choices can reference the same
daily credit resource; selecting DeepSeek does not replenish it. Duplicate
resource identities are rejected. A model's manifest and quote must name exactly
the observed applicable window set. Missing horizons, incomplete manifests,
stale resets and cross-binding debits fail closed.

For every horizon, maximum debit must fit `limit - used - reserved`. Requests
and tokens must cover the full request count and per-request bounds. Credits
remain the provider owner's units; H24-05 does not invent a token-to-credit
conversion. USD resource debit cannot understate the quoted cash upper bound.
Debit units must match the current native resource; a stable resource ID cannot
reinterpret credits as dollars or requests. A quota window must already have
started at the time the provider balance was observed, as well as remain current
at projection time. A pre-reset balance cannot age into a post-reset allowance.
The same quote must fit both the request cash ceiling and Executive budget
after competing reservations. Exact equality is allowed. An expired window is
never rolled forward or reset locally.

Cash arithmetic uses a local fixed Decimal context with sufficient precision;
parallel callers' ambient precision cannot round an exceeded cap into success.
No cache discount is assumed. Owner quote provenance is returned with the
rate-card revision, validity, cash bound and each native debit/headroom.

## Effect and fallback rules

| Evidence | Projection behavior |
| --- | --- |
| Coherent `PRE_SEND`, no prior response/attempt/effect | May propose the first qualified owner-ranked candidate, including an alternative for a currently unavailable primary. This also applies to a modifying request that has never been sent. |
| `READ_ONLY_NO_EFFECT`, `read_only` demand, current retained no-effect receipt, outage/429 evidence | May propose a qualified alternative. The attempted provider/model is excluded. This does not execute a retry. |
| Unknown or observed prior effect | Returns no selection and no alternatives, regardless of quota, price or health elsewhere. |
| Modifying request presented as post-send read-only/no-effect | Refused. A failure code or caller label cannot erase the effect boundary. |
| 401/403 response or auth-denial outcome | Terminal for this attempt; no failover. Separately, a Provider Control realm denial excludes every pool/model sharing that exact issuer/realm. |
| Model-scoped 429 cooldown | Excludes that binding/model. Other models still use their own health and the same shared windows. A qualifying positive health observation must be at or after the retained cooldown expiry; expiry alone does not manufacture a new positive reading. |
| Wrong/missing successful served-model identity | Terminal refusal, not an outage and not a fallback reason. IDs are not case-folded or family-normalized. |

Cursor remains unselectable while its incumbent profile is disabled. A fabricated
positive Capacity row cannot enable the placeholder. For the other providers,
role membership is only a necessary condition; current owner-qualified route
facts are still required. The selector never mutates `client.py`, `contract.py`,
`native_byok.py`, `metering.py`, Router, quota, credentials or their stores.

## Return schema and H24-02 integration

The output schema is `mastermind.hermes_model_pool_projection/v1`:

- `status`: `PROJECTED` or `BLOCKED`; `selected` and owner-ranked `alternatives`.
- `demand_digest`, `snapshot_digest`, opaque candidate/binding/placement refs.
- Exact canonical provider and wire model, source/expiry, fixed reason codes,
  candidate exclusions and explanatory policy trace.
- Quote provenance and native resource projections. Opaque owner labels are
  SHA-256 references, so raw host/account/source/quote labels are not copied.
- `authority=NONE_PREVIEW_ONLY`, `binding_verification=NOT_PERFORMED`,
  `selection_is_commitment=false`, `capacity_claimed=false`,
  `live_admission=false`, `provider_connected=false`,
  `claim_time_revalidation_required=true`,
  `incumbent_reservation_required=true`.

Each selection expires at its earliest contributing source or quota boundary.
The overall decision expires at the earliest qualified selection/alternative
boundary. A blocked decision has no usable expiry. Outputs are detached from
the frozen input; serialization cannot mutate future reader results.

H24-02 may supply the Capacity portion through an adapter owned by the existing
authenticated parent. Map its exact candidate/worker/host/lane, model, source
and profile facts to `Candidate`; carry its observed/expiry and ordering in
`Capacity`. Do not convert H24-02's projection status into authentication or
grant. If the typed H24-02 return lacks realm binding, generation, policy
qualification or quote/quota details, obtain them from their incumbent owner;
do not guess, install a resolver or treat that omission as a global wave gate.
There is no H24-02 runtime import or dependence on its unsealed source here.

The executing owner must then:

1. Resolve the selected opaque reference against its retained exact candidate.
2. Re-read and authenticate current owner facts, reconcile the existing attempt,
   and reject expired or changed source/profile/realm/effect/budget state.
3. Atomically reserve all applicable native resources and job budget through the
   incumbent reservation path. Two successful readers are not two reservations.
4. Admit and execute only through the existing claim/credential/execution owner.
   If that path refuses or its effect becomes uncertain, retain that result on
   its original carrier. This projection grants no retry or failover authority.

These are existing owner obligations, not a new release gate or control plane.
**Uncertainty retained:** live route qualification, authenticated origin, actual
quota/prices/health, reservation, H24-02 owner integration and provider execution
are not proven by this source packet. They are explicit parent integration
inputs, rather than reasons to delay this independent source deliverable.

## Offline acceptance and parent checksum

Run from the repository root:

```sh
python -m unittest integrations.hermes_models.tests.test_h24_pool_selection -v
python -m unittest discover -s integrations/hermes_models/tests -v
python -m py_compile integrations/hermes_models/pool_selection.py integrations/hermes_models/tests/test_h24_pool_selection.py
git diff --check
```

The focused tests cover role/provider separation, first-tier and owner-order
preservation, read-only outage fallthrough, write/unknown-effect prohibition,
429 vs 401 scope, daily hard caps, shared resources, missing/stale/partial
quotas, cash/request/token budgets, competing reservations, exact model/surface
quotes, source movement, mixed issuer/realm/generation, disabled Cursor,
secret-free output and parallel-reader stability. The package suite also
checks the unchanged incumbent client/profile behavior.

Initial verification: **60 focused tests passed; 82 package tests passed**.
Adversarial inspection then reproduced three consistency defects in the initial
candidate: pre-window quota observations, pre-expiry positive cooldown readings,
and equal-revision/different-origin Router joins. The three regression tests
failed before repair (four assertion failures including the issuer/source
variants). The candidate repairs those defects and additionally binds current
rate-card origin and debit units. Final verification includes these cases.
An initial package run lacked sparse-checkout profile fixtures; expanding the
checkout to the unchanged base fixtures resolved that environment-only failure.
Final candidate verification:

| Command | Observed result |
| --- | --- |
| `python -m unittest integrations.hermes_models.tests.test_h24_pool_selection -v` | 67 tests, `OK`, exit 0. |
| `python -m unittest discover -s integrations/hermes_models/tests -v` | 89 tests, `OK`, exit 0, including the 67 H24 tests and 22 incumbent tests. |
| `python -m py_compile integrations/hermes_models/pool_selection.py integrations/hermes_models/tests/test_h24_pool_selection.py` | Exit 0. |
| Targeted read-only repair inspection | The three reproduced gaps and the rate-card/unit joins were checked; seven targeted regression/recovery tests passed. This is technical decision support, not formal GitHub approval. |

The final diff checksum and whitespace/owned-path verification are returned with
the parent checkpoint. The checksum is deliberately outside this file to avoid
a self-referential digest. There was no hosted CI, installed execution or live
provider test in this bounded source-only verification.

Reproduce the owned diff checksum at the published head:

```sh
git diff --binary --full-index --no-ext-diff --no-textconv b54cb10e4abdd3766c62d4088f6a576ecfe80437 HEAD -- \
  integrations/hermes_models/pool_selection.py \
  integrations/hermes_models/tests/test_h24_pool_selection.py \
  docs/hermes/H24_MODEL_POOL_ECONOMICS.md | sha256sum
```
