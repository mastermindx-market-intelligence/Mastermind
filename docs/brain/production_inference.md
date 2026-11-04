# Brain production API mode composition

Status: source implementation; not enabled or deployed. Part of [Mastermind #983](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983).

## Consumer and owner

The existing `brain.client.call_model` dispatcher supports the explicit backend `production_mode`. It calls `brain.production_inference`, which delegates to Macro's existing `engine.provider_production_modes.call_mode`. The CIO weekly narration is the verified no-tools consumer; other callers of the same tuple contract can use the same dispatch path. This does not replace Macro's streaming/tool-using Brain gateway.

Macro retains its mode catalog, pinned destinations and models, credential resolution, qualification, provider-health writer, and usage ledger. The adapter creates no account registry, semaphore, lease, request journal, retry queue, price table, or subscription fallback. Caller seat/book/role and the actual mode/model are retained in the existing Brain response log. Usage is written only by Macro, not again by Brain cost_guard.

This is **production API mode composition**, not unified Fabric pool admission. MiniMax PAYG and GLM PaaS use separate products/credentials/billing identities from their Fabric subscriptions. The current API has no atomic shared capacity reservation or durable operation/attempt identity. Logging a result does not establish either. A caller must not interpret a transport failure as permission to resubmit through another backend.

## Explicit configuration

An operator can select the implementation with:

```sh
BOT_LLM_BACKEND=production_mode
BOT_LLM_PRODUCTION_MODE=minimax_payg_api
```

The equivalent server-owned `config/agents.yml` fields are `backend: production_mode` and `production_mode: minimax_payg_api`. An explicitly empty mode does not use the config default. An unknown or empty explicit backend is unavailable; it does not silently become the legacy waterfall.

Selection does not enable a provider. Macro's reviewed `config/provider_production_modes.v1.json` remains authoritative and ships both modes disabled. Its GLM request profile remains `UNQUALIFIED_PENDING_CANARY`, even if someone sets the mode enabled. The adapter does not install credentials, change qualification, expose endpoint/model overrides, or change production configuration.

The paired Macro transport change is [3078e01887a5dc9faa0e403fd01ef51897e978d8](https://github.com/mastermindx-market-intelligence/macro/commit/3078e01887a5dc9faa0e403fd01ef51897e978d8). It sets `max_retries=0` on the existing MiniMax Anthropic SDK client. Install the compatible owner before enabling this path. A single Python transport invocation is otherwise insufficient to exclude SDK replay.

## Source proof

`tests/integration/test_production_inference_composition.py` exercises the real CIO narration, Brain dispatcher, adapter, Macro mode validation and call path, response normalization, provider-health writer and usage writer. Only the provider SDK/network and asynchronous response-log sink are controlled. Synthetic credentials and temporary ledgers prevent live effects.

Run with the actual Macro source importable through the normal vendor path or an explicit test PYTHONPATH:

```sh
PYTHONPATH=.:/path/to/macro MM_REQUIRE_PRODUCTION_MODE_COMPOSITION=1 \\
  python -m unittest discover -s tests/integration \\
  -p test_production_inference_composition.py -v
```

The required flag turns a missing Macro owner into a failure. Without it, environments that lack the vendored Macro owner report a composition skip; a skipped suite is not cross-repository integration proof.

Fourteen tests passed against Mastermind source base `8c417f6baf9ee19e7172efb9fea009e28ccf6769` plus this change, and Macro base `52abe2e183833a216267942a99513e6c9cbe062f` plus the paired retry change. Cases include actual CIO attribution, one usage row, disabled/missing/unknown mode, unqualified GLM before credential resolution, invalid pinned destination, bounded token request, empty output, unavailable owner, logging failure, and timeout after one dispatch without fallback. This proof is local source composition; it is not a live provider, VPS, browser, shared-pool or release receipt.

## Remaining programme

Continue the existing [Macro #7179 design](https://github.com/mastermindx-market-intelligence/macro/pull/7179): ordinary application inference uses Shared AI Provider Control; durable agent tasks use authenticated Executive/Fabric jobs. Preserve its Draft/HOLD and the original Brain Experiential branches [#1918](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1918) and [#1946](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1946). The new dispatcher arm is independent of Experiential semantics and must be combined with them through normal source integration, not by replacing their branch.

Full Fabric integration still requires an owner-qualified eligible route projection, same-account atomic admission and operation reconciliation, production-suitable execution profiles, the streaming/tool gateway composition, deployment and authenticated product-path proof.
