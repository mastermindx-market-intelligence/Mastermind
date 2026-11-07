# OMH adaptive effort integration

Operation: `hermes-omh-effort-integration-20261107-ryan01`.
Parent: #983 and the existing Hermes teammate plan #2159, native integration N3/N4.
Procedure/source pin: `c0c4f645ddce048465bd299dc7beb747c810f635`.
This is an implementation slice of that plan, not a new execution or routing owner.

## Outcome and architecture

A user prompt gets the reasoning effort appropriate to its task, on the already selected and authorized model. A continuation/tool loop does not cause uncontrolled rerouting. Manual choices, model capabilities, account budgets and access boundaries remain controlling.

| Layer | Existing owner | Responsibility |
| --- | --- | --- |
| Workflow/category/graph advice | installed Oh My Hermes | Recommend an approach and prepare a graph; advice is not admission |
| Native Mastermind bridge | `integrations/hermes_omh/plugin` | `mmx_omh` and `/mmx-omh`, bound to one profile and immutable source closure |
| Canonical resource preview and execution | existing Capacity / Executive / Fabric | Eligible model/account/host, budgets, dispatch, recovery, usage |
| Parent request effort | Hermes Adaptive Effort `llm_request` middleware | Change only the current eligible request's supported reasoning control |
| Prompt classification | optional Jev, through HAE's existing scorer adapter | Bounded typed choice; no model, account, tool or admission authority |
| Conversation memory, profile, credentials | their existing Hermes owners | No new registry, credential copy, memory service or provider proxy |

Keep OMH's native `omh_delegate_route` child-configuration workflow distinct from parent request middleware. It must not be used to circumvent the existing APPLICATION/Fabric dispatch and accounting path. Leave HAE child scoring disabled in this slice.

## Already implemented versus missing

The protected source includes the native bridge and non-reserving Capacity preview from merged #2196, release `58ac65ae47824750cae32c5ab85b58b6f38e6d5e`. Default M2 profile installation was observed; a previous fresh-loader tool/command/preview canary passed. This does not resolve the original default gateway activation uncertainty.

This operation's non-secret profile read found default Hermes using local Qwen3:14b and fixed medium effort. Secretary uses GLM-5.3/Z.ai, fixed medium effort, OMH enabled, and Capacity MCP declared, but not the native Mastermind bridge or HAE. These are dated configuration observations, not proof of active requests or entitlement.

Earlier downloadable packages are superseded as configuration guidance: `respect_manual_effort`, `effort_floor` and `effort_ceiling` do not exist in HAE v0.4.0's manifest. Their self-tests did not establish compatibility. HAE's actual manual procedure is `/hae off here`, then Hermes' native `/reasoning <supported-level>`; automatic routing resumes explicitly with `/hae always here` on a qualified route.

## Frozen tasks and acceptance

| Task | Owner | Acceptance |
| --- | --- | --- |
| EF1: exact installed source/custody and settings | parent | Pin native/plugin code and actual manifest; reject unsupported settings; no secret output |
| EF2: direct Z.ai compatibility | parent | Exact endpoint/model/API named choices low/high/max; no neighboring proxy/model inference; actual middleware tests |
| EF3: source configuration and migration | parent | Preserve unrelated settings and profile scope; stage off; active per-prompt mode only after route/scorer qualification; child mode off |
| G1: Secretary profile/gateway/key-presence reconciliation | Grok Secretary | Actual START/session, source hashes, writer/effect status; key presence boolean only |
| G2: existing native bridge in Secretary | same Grok assignment | Existing native installer and profile-bound descriptor, no duplicate runtime or unsafe restart |
| G3: real native status/recommend/preview journey | same Grok assignment | Served tool or slash response, canonical PREVIEW_ONLY/reserved=false/recheck=true; negative input proof |
| EF4: active effort journey | parent + same runtime owner | Simple versus complex prompts, supported wire values, manual off, failed scorer, unsupported route, tool-loop reuse and conversation isolation |

Local tests with a synthetic scorer prove wiring, not Jev accuracy, live provider behavior, cost savings, or production acceptance. Installation, loaded activation, request mutation and actual provider completion require separate receipts.

## Upstream compatibility boundary

Use HAE v0.4.0 at `atostivint/hermes-adaptive-effort@c84f1389670cdd5ec4607b13bd32c4809878c415`. Manifest Git blob: `4c989330a925086955a55e5bdd4eff838ed76ed2`. Effort module Git blob: `f8b63e02f868ec7354027384585ba91ddf389738`. Native extension remains within that plugin; no second middleware controls effort.

Current official Z.ai docs list GLM-5.3 low/high/max. The installed Hermes constant also contains medium, and upstream HAE has no exact direct-zai named-choice route. Qualify this discrepancy explicitly instead of assuming prompt instructions make an unsupported value safe. A narrow compatibility patch must bind the direct provider, exact GLM-5.3 ID, Chat Completions API and documented HTTPS Z.ai endpoint. Unknown routes continue unchanged. Never claim an HTTP rejection without observing one.

References: [HAE pinned configuration](https://github.com/atostivint/hermes-adaptive-effort/blob/c84f1389670cdd5ec4607b13bd32c4809878c415/docs/CONFIGURATION.md), [HAE effort implementation](https://github.com/atostivint/hermes-adaptive-effort/blob/c84f1389670cdd5ec4607b13bd32c4809878c415/effort.py), [Z.ai parameter contract](https://docs.z.ai/guides/overview/concept-param).

## Safety, activation and rollback

Preserve existing profile settings, memory selection, secret references, provider/model and admission. Stage HAE with mode off; installation/status does not authorize sending real prompts to TypeSafe. Confirm the exact scorer/key through its existing secret owner before enabling bounded task sharing. Start without dialogue history or target-model context. Missing credentials or a scorer failure preserves the original request; it must not switch providers or invent a free/local scorer service.

The original default gateway reload is EFFECT_UNKNOWN: gateway PID48443/instance a9115d5bee674ff98a3fac21d9ad5ca8 in its original receipt. Do not replay it, restart, kill, replace the session, or claim a new process settles it. Preserve primary/application and enrollment owners #2155/#2186/#2175/#2180 and Macro#10740. No self-merge or production release outside their actual gates.

Detailed runtime assignment and source frontiers: [#983 comment6706043608](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6706043608). Same Grok return thread: Slack C0CBC6AEAQZ / 1794049859.926899. At this document's creation Grok had PICKUP_ACK/queued, not START. Do not infer background execution from delivery.
