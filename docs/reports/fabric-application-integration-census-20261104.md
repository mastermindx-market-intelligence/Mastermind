# Fabric application integration: source census and migration map

Recorded 2026-11-04. Programme: [Mastermind #983](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983). Application source: [Mastermind #2050](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2050), paired with [Macro #10727](https://github.com/mastermindx-market-intelligence/macro/pull/10727).

## Outcome and present evidence

The original outcome is shared use of the full eligible Subagent Fabric catalog by Mastermind, Macro Dashboard, Terminal, Neural Web, AI Brief, Admin and Brain chat, through existing routing/capacity owners and with authenticated production proof. That outcome is **not complete**. A source-only component, a discovered pool name, successful CI or a merged transport is not application availability.

The source census verifies **173 Git blobs at exact repository commits**, including **254 relevant Python call expressions in 73 files**. These are static call expressions, not counts of users, running jobs, requests, deployed routes or percentage completion. The full evidence is [fabric-ai-callsite-census-20261104.json](fabric-ai-callsite-census-20261104.json); every row includes repository, commit, path, blob, byte verification and discovered calls. The scanner never imports project code.

| Repository | Source pin |
|---|---|
| Mastermind | `8c417f6baf9ee19e7172efb9fea009e28ccf6769` |
| Macro | `52abe2e183833a216267942a99513e6c9cbe062f` |
| Terminal | `494f75ad48aba86e0916cef21ffdacadef8fea28` |

Discovery combined repository trees, indexed code queries, partitioned queries with complete result counts, direct reads of known application boundaries, and explicit inspection of oversized modules that code search missed. The large Macro Brain gateway and marketing copywriter were inspected directly. All 173 materialized source files matched their Git blob IDs; no parse errors or mismatched blobs were accepted.

**Coverage boundary:** this is a bounded static source census. It includes all identified call families and the named product surfaces, plus deployment/routing-owner context. It is not proof that every dynamic import, generated command, optional plugin, runtime-only configuration, scheduled process or deployed source revision has been enumerated. The live VPS census and real consumer traces remain owed; the attempted intended SSH service read was authentication-denied. The original two delegated census results were not consumed because their original effects remain unresolved. The independently verified source inventory does not depend on those results.

## Product routes and required integration

| Product or workload | Verified current source route | Migration consequence |
|---|---|---|
| Brain web chat and research | [engine/neuralweb/brain_gateway.py](https://github.com/mastermindx-market-intelligence/macro/blob/52abe2e183833a216267942a99513e6c9cbe062f/engine/neuralweb/brain_gateway.py): lane provider builders, direct message creation, failover and streaming/tool loops | Integrate the owner-selected route while preserving authenticated users, turn identity, tools, SSE, cancellation, quotas and retained results. A text-only completion adapter cannot replace this contract. |
| Terminal Brain | [terminal/app/api/brain/[...path]/route.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/494f75ad48aba86e0916cef21ffdacadef8fea28/terminal/app/api/brain/[...path]/route.ts): authenticated, allowlisted gateway proxy | Keep this proxy and principal boundary. Provider integration belongs in the upstream Macro gateway; prove the Terminal browser path after rollout. |
| Terminal legacy copilot | [terminal/app/api/copilot/route.ts](https://github.com/mastermindx-market-intelligence/mastermind-terminal/blob/494f75ad48aba86e0916cef21ffdacadef8fea28/terminal/app/api/copilot/route.ts): deprecated proxy to the same Brain gateway | Preserve rollback semantics. It is not a separate model pool. The pinned Terminal runtime search found no direct provider SDK matches. |
| Neural Web question answering | [engine/neuralweb/ask_brain.py](https://github.com/mastermindx-market-intelligence/macro/blob/52abe2e183833a216267942a99513e6c9cbe062f/engine/neuralweb/ask_brain.py): shared provider construction plus message calls | Preserve response shape and tool/context requirements; route through the same qualified inference owner. |
| Neural Web Cortex | [engine/neuralweb/cortex.py](https://github.com/mastermindx-market-intelligence/macro/blob/52abe2e183833a216267942a99513e6c9cbe062f/engine/neuralweb/cortex.py): shared inference plus separate SDK-related context | Preserve analysis/publication boundaries and capability requirements; do not equate all Cortex actions with plain text. |
| Neural Web response evaluation and trade memory | `engine/neuralweb/response_eval.py`, `trade_memory.py` | Reuse the same eligible route/admission and existing evaluation/retention contracts. Evaluation output is not trade authority. |
| AI Brief final assembly | [engine/neuralweb/daily_brief.py](https://github.com/mastermindx-market-intelligence/macro/blob/52abe2e183833a216267942a99513e6c9cbe062f/engine/neuralweb/daily_brief.py) | Deterministic assembly; migrate upstream model producers, not the final builder. Preserve deterministic degraded output. |
| AI Brief / Master Brain upstream synthesis | [engine/master_brain.py](https://github.com/mastermindx-market-intelligence/macro/blob/52abe2e183833a216267942a99513e6c9cbe062f/engine/master_brain.py): translated shared waterfall for its DeepSeek-shaped config; custom endpoint bypass through `_client` otherwise | The candidate now has explicit production API selection before either legacy branch, proven through real synthesis and cache/attribution tests. Native Fabric admission remains open; a prompt hash is not an original provider-attempt identity. |
| AI Desk and stock-desk consumers | `engine/ai_desk.py`, `engine/stock_desk.py`, and the Master Brain contract | Preserve the actual upstream producer and consumer result validation rather than adding another model client. |
| Admin orchestrator chat | [admin/orchestrator_chat.py](https://github.com/mastermindx-market-intelligence/macro/blob/52abe2e183833a216267942a99513e6c9cbe062f/admin/orchestrator_chat.py): separate credential discovery/client builder and tool loop | Explicit bypass from the central builder. Replace discovery/execution composition only after an eligible tool-capable owner binding exists; preserve Admin read tools and response contract. |
| Admin AI cost / Prophet / Brain activity | `admin/ai_cost.py`, `admin/prophet.py`, `app/brain_runs.py`, `lib/ai_costs.py` | Primarily projections of existing owners. Show actual provider/model/mode/usage and unknown states; do not create a second quota or cost ledger. |
| Mastermind reasoning seats | [brain/client.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/8c417f6baf9ee19e7172efb9fea009e28ccf6769/brain/client.py) and callers `strategist`, `gate_officer`, `risk_officer`, `macro_risk`, `committee`, `panel`, `cio` | Shared dispatcher is the common integration point. New explicit production-mode composition is tested for the real CIO narration; native shared capacity remains unimplemented. |
| Mastermind typed harness reasoning | [brain/cli_bridge.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/8c417f6baf9ee19e7172efb9fea009e28ccf6769/brain/cli_bridge.py), `codex_bridge.py`, [brain/provider_waterfall.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/8c417f6baf9ee19e7172efb9fea009e28ccf6769/brain/provider_waterfall.py) | Preserve typed MCP tools, workspace/run ownership and effect refusal. The existing waterfall reads Macro OAuth candidates directly and bypasses its general provider builder. |
| News, policy, narrative and risk lobes | `news_llm`, `commodity_news`, `narrative_brain`, `risk_brain`, `risk_radar_review`, `uk_policy_brain`, `whitehouse_brain`, `altdata_brain`, `influence/extract` | Most use shared construction/execution, but direct compatibility constructors remain in several modules. Migrate both, retaining schemas and publication gates. |
| China/macro news and translation | `china_news`, `macro_news`, `china_news_intel`, `news_translate`, `translate`; Mastermind `brain/translate.py` | Legacy direct SDK/client paths need explicit coverage; changing only `llm_auth` will not cover them all. |
| Earnings, qualitative extraction and catalyst analysis | `earnings_qual`, `qual_extraction`, `catalyst_tone`, `catalyst_stock`, `company_intelligence/e3_shadow_compiler` | Includes custom OpenAI-compatible endpoint helpers and direct constructors. Preserve structured-output checks; account for additional application retries after invalid output. |
| Marketing generation | `copywriter`, `copy_auditor`, `copy_critic`, `copy_review`, `cold_read`, `fomc_desk`, `hot_tape_llm`, `reply_voice`, `intelligence_llm`, `breaking_summary`, `publish_time_content`, `content_studio` | Shared construction is common, but copywriter adds retries/failover and some cached clients omit policy identity. An owner-admitted Fabric request must not enter those legacy retry paths. |
| Press/research production | `engine/press/writer.py`, `research_triage.py`, `research_veto.py`, `engine/research_intelligence/extractor.py` | Preserve research provenance, veto/publication gates and stable producer identity; delegate actual durable agent work through Executive rather than an inference shim. |
| Metabolism and scheduled cognition | `agenda`, `attention`, `audit`, `propose`, `adjudicate`, `standout_auditor`, and their scripts including dream/shadow cycles | Background workload eligibility is distinct from an attended worker. Share the real account admission; preserve existing budgets and jobs. |
| Probes and research scripts | `key_pool_probe.py`, drift checks, causal/signal-foundry brainstorming, evaluation and dry-run scripts | Operational/test consumers are separately identified; do not treat a successful probe as full product coverage or run dummy provider probes for discovery. |
| Local statistical/ML models | `engine/meta_label.py`, `lib/flow_score.py`, and eight identified sklearn source/script uses | These execute local fitted models, not the LLM provider waterfall. Retain validation and their existing deployment/trade restrictions. They do not become interchangeable with Fabric language models. |
| Research code-generation engine | `engine/research_codegen/transport.py`, `prefix_driver.py` | Current source explicitly keeps real-engine transport dormant pending qualification. Synthetic execution evidence cannot authorize a live model/worker path. |

The JSON inventory gives the individual files, functions and call expressions behind these grouped routes. A category denotes a source pattern, not a claim that the path is deployed or always executed.

## Existing load-balancing owners

1. **Macro shared inference:** [engine/llm_auth.py](https://github.com/mastermindx-market-intelligence/macro/blob/52abe2e183833a216267942a99513e6c9cbe062f/engine/llm_auth.py) owns provider construction, ordering and ordinary callback execution, with `key_pool`, `provider_health` and `ai_costs` as incumbent state/telemetry owners. Its general `make_call` may advance on ambiguous SDK/connection/server exceptions; it has no original durable provider-attempt contract. An ordinary additional Fabric rung would therefore be unsafe.
2. **Macro account/capacity observations:** [engine/provider_capacity.py](https://github.com/mastermindx-market-intelligence/macro/blob/52abe2e183833a216267942a99513e6c9cbe062f/engine/provider_capacity.py) is explicitly read-only. Its source catalog is the existing Claude/Codex/DeepSeek capability slots. It is not an atomic capacity claim and must not be treated as one.
3. **Native Fabric execution:** ModelRouter handles suitability; Runtime/Capacity own admission/claims; existing brokers own dispatch and leases. A pool status table or caller-provided root label does not grant application execution.
4. **Attempt-scoped inference:** [control_plane/attempt_inference_endpoint.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/8c417f6baf9ee19e7172efb9fea009e28ccf6769/control_plane/attempt_inference_endpoint.py) and [control_plane/fabric_packet_inference.py](https://github.com/mastermindx-market-intelligence/Mastermind/blob/8c417f6baf9ee19e7172efb9fea009e28ccf6769/control_plane/fabric_packet_inference.py) preserve an existing admitted Attempt and restricted packet contract. They are not a public web inference service or a new admission authority.
5. **Production APIs:** [engine/provider_production_modes.py](https://github.com/mastermindx-market-intelligence/macro/blob/52abe2e183833a216267942a99513e6c9cbe062f/engine/provider_production_modes.py) already owns distinct MiniMax PAYG and GLM PaaS modes. These are separate products and billing identities from subscription pools. Both ship disabled; GLM's request profile remains unqualified.

The existing [#7179 design and guard](https://github.com/mastermindx-market-intelligence/macro/pull/7179) remain the governing integration target: ordinary site inference through the shared provider owner; durable agent work through authenticated Executive service principals. The draft guard must not be duplicated or treated as already deployed.

## Native pool observations and eligibility

The installed canonical `pool status` command reported nine configured lease-broker groups at **2026-11-04T09:23:59Z**: **bailian, minimax, grok, cursor, glm, go, ocfree, codex-native, claude-native**. Its own stated coverage is the configured lease ledger only; execution hosts can differ. These names are neither a complete attested model catalog nor a production entitlement. At that instant MiniMax showed 7/7 held, including the original unresolved census leases; no leases were released by this operation.

The protected [config/subscription_provider_profiles.v1.json](https://github.com/mastermindx-market-intelligence/Mastermind/blob/8c417f6baf9ee19e7172efb9fea009e28ccf6769/config/subscription_provider_profiles.v1.json) explicitly marks its GLM coding-plan, Alibaba personal, MiniMax token-plan and BytePlus personal profiles interactive-only, with unattended-background and production-backend use disabled. Do not infer that another product with the same provider name inherits permission. Remaining pools require their own qualified binding and workload eligibility; absence from this file is not permission.

Detailed original runtime observations and unresolved effects are retained on [the existing programme record](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983#issuecomment-6627496975). No worker output was accepted to establish this census.

## One native pool: executable-contract determination

OpenCode Go supplies a concrete example of the missing connection:

| Boundary | Current evidence | Consequence |
|---|---|---|
| Transport | [Mastermind #622](https://github.com/mastermindx-market-intelligence/Mastermind/pull/622) is merged. The current `OpenCodeGoPooledTransport` uses owner-injected account resolution and credentials, keeps the logical session/body/model, and refuses ambiguous replay. | Reuse this transport; do not build another pool client. |
| Account resolver | [Macro #7142](https://github.com/mastermindx-market-intelligence/macro/pull/7142) is still Draft, head `7b3da996324ae92c1bf65413acf7666914ae4a54`, described as partial and production-inert. Its [explicit release hold](https://github.com/mastermindx-market-intelligence/macro/issues/7142#issuecomment-5807868648) requires current integration/release evidence. A [non-author source review](https://github.com/mastermindx-market-intelligence/macro/pull/7142#pullrequestreview-5766694663) now verifies the actual 36 selector/observation tests and corrects the historical 84-test overclaim; the Draft/release hold remains. `engine/provider_account_pool.py` is absent from the pinned Macro main tree. | No installed application resolver is established by the merged transport. |
| Usage source | [Macro #7143](https://github.com/mastermindx-market-intelligence/macro/pull/7143) is still Draft, head `facf7074dbbe58a3a9ffef4eae0ca92c97031634`; its body still requires real-account observation and exact-head qualification. | Do not manufacture quota or treat parser fixtures as live capacity. |
| Atomic admission | The transport explicitly leaves Job/Attempt/Worker authority to Executive and account ranking to Shared Provider Control. | Application composition must consume the existing claim owner; a new semaphore or journal would duplicate it. |
| Production application eligibility/binding | No qualified site-inference binding was established in this investigation. Historical source checkpoints explicitly preserve production-inert/qualification boundaries. | Resolve the actual eligible binding and existing source dependencies before writing an application wrapper. |

The canonical paid GLM path is also not a generic full-pool application service: `paid_fabric_admission.py` requires Runtime admission, current autonomy/source status and the original broker lease; its capacity observer always projects provider readiness UNKNOWN and grants nothing. Its sealed GLM model-only profile does not establish authorization for arbitrary site requests or other pools.

## Implemented source slice

[Mastermind #2050](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2050) adds explicit `production_mode` dispatch to the existing Macro production API owner. [Macro #10727](https://github.com/mastermindx-market-intelligence/macro/pull/10727), at `09f0385c2ed3d9060362f3cf20e705bcb7db6043`, disables implicit MiniMax SDK retries and connects explicit Master Brain/AI Brief synthesis to the same incumbent owner. Twenty-eight local composition tests pass (14 CIO, 14 Master Brain), covering actual consumer calls, single owner accounting, cache/model truth, unavailable modes, post-dispatch failure without replay, and intentional style-rewrite semantics. The new Macro suite is wired into the existing CI job. An additional required step inside existing Mastermind full-CI shard zero checks out the paired Macro revision/configuration and verifies the normal vendor-bootstrap fixture before any suite-reuse decision. The existing protected fan-in and four-job policy are preserved; fast PR checks or a skipped discovery class are not composition proof. [Implementation and reproduction](../brain/production_inference.md).

This slice does not claim native pool admission, live credentials, production enablement, installed code, web streaming or successful VPS deployment. It is independent of the held Experiential Brain branches #1918/#1946 and the #7179 guard.

## Remaining sequence and acceptance

- Establish one production-eligible native inference binding using the existing registration, account, admission and reconciliation owners. Resolve the original dependency PRs; do not recreate them.
- Expose the full qualified catalog to the common router, with capability requirements for tool use, streaming, structured output, context and workload class. Select only eligible pools per request; a full catalog does not mean every model can serve every contract.
- Integrate ordinary consumers through that owner, covering direct constructors, custom endpoint bypasses, client caches and application-level retry loops found here. Carry original producer/turn identity; ambiguous dispatch remains on its original attempt.
- Integrate Brain web/Admin tool and streaming paths without losing authentication, turn retention, tool results, quota checks or cancellation semantics. Retain Terminal's existing authenticated proxy.
- Move upstream AI Brief/Neural Web producers; preserve deterministic assembly, output validation, publication and research/trade boundaries.
- Restore intended VPS access, enumerate deployed services/schedules and enabled configurations, deploy only the actual qualified merged source, then prove authenticated user/machine paths. Exercise success, saturation, pre-dispatch refusal, ambiguous dispatch, streaming cancellation and degraded output through the real owners.
- Retire bypasses only after their named consumer paths are proven. Confirm one account-capacity authority and one usage record per real attempt across website inference and native workers.

The missing live VPS access, unresolved original Fabric effects and unqualified application bindings block their respective execution lanes. They do not erase the source work or authorize retries, alternate credentials, new ownership planes or parent completion.

## Reproduce the static inventory

With the source checkouts at the named commits:

```sh
python scripts/census_application_ai.py \
  --manifest docs/reports/fabric-ai-callsite-census-20261104.json \
  --source Mastermind=/path/to/Mastermind \
  --source macro=/path/to/macro \
  --source mastermind-terminal=/path/to/mastermind-terminal \
  --output /tmp/fabric-ai-callsite-census.json
```

The script requires explicit local roots, checks each file against its Git blob, parses source without executing it, and exits nonzero for a mismatched blob or parse failure. The report is evidence, not a new runtime registry or dynamic account catalog.
