# OMH adaptive effort qualification — 2026-11-07

Parent #983 / #2159; implementation #2213; operation `hermes-omh-effort-integration-20261107-ryan01`.

## What is proven

The existing HAE v0.4.0 payload, pinned to `c84f1389670cdd5ec4607b13bd32c4809878c415`, was downloaded to an isolated M2 temporary directory, its archive members inspected, and its changed-file preimages checked. The candidate adds one pure exact-route vocabulary helper plus a guard inside HAE's existing middleware. No second effort middleware, provider route, account selection or execution owner was introduced.

Twenty repository unit tests passed. They cover manifest/configuration failure behavior and exact route/build guards. The candidate settings were separately validated against the actual pinned plugin.yaml: both `off` and `always`, 15 settings each. The manifest's YAML `off` is correctly retained as a string.

The second native qualification run passed **154 tests, zero failures, zero errors, zero skips**, in 3.54 seconds. It used Hermes' real PluginManager and middleware dispatcher, the actual installed Z.ai Chat Completions request builder, temporary Hermes homes, an empty bundled-plugin directory, a synthetic named-choice scorer, and the upstream suite's session-wide socket prohibition. No real model or classifier was invoked.

Selected native test files: `test_mmx_zai_dispatcher.py`, `test_dispatcher_integration.py`, `test_native_choice_middleware.py`, `test_conversation_mode.py`, `test_turn_scope.py`, `test_scorer_circuit_breaker.py`, `test_effort.py`, `test_subagent.py`.

Proven cases include all three GLM levels; new-prompt switching; tool-loop decision reuse; manual conversation off; global off; malformed scorer choice; missing-key fail-open; unsupported route without writable control; child scoring off; concurrent conversations; unchanged input/sibling request fields; and rejecting a same-turn endpoint change even when HAE's existing session identity is unchanged.

## Candidate identity

- Upstream manifest Git blob: `4c989330a925086955a55e5bdd4eff838ed76ed2`.
- Upstream effort Git blob: `f8b63e02f868ec7354027384585ba91ddf389738`.
- Upstream middleware Git blob: `0dfb76d4f8a63c61e0f5dc28dba604e3da6b2bcb`.
- Patched effort SHA256: `7d517ffef39eea6e179eb2b894e98925cb807e4467433bba72780d2dfc31027f`.
- Patched middleware SHA256: `f9e3a3f4f42e0a1d3b627b9009749770bce47ba69051c2b0646088e4511aa0ae`.
- Route helper SHA256: `61d1e4b5c4926f2eb3ec137163a117076fd8fd2f10f0564add0efd173e838106`.
- Candidate and logs remain on M2 under `/tmp/mmx-hermes-effort-ryan01.H2y7Vm/candidate2` and `native-qualification2.{log,xml}`. This temporary test path is not a runtime installation or durable source owner; repository source and this receipt own the result.

A successful build receipt is `BUILT_NOT_INSTALLED`. It verifies the changed preimages and output hashes, not a signed full-tree attestation. Unknown direct-zai GLM-5.3 endpoints/API modes now explicitly fail open before using a retained choice; other provider/model families retain upstream behavior. This refines the architecture document's earlier broad phrase about unknown routes.

## How to reproduce without changing a live profile

Using a qualified isolated test environment with pytest9.1.1 and ruamel.yaml0.19.1, and a read-only Hermes source root:

1. Obtain the exact upstream source revision through the normal source owner. Inspect it; do not use a live profile as build input.
2. Run `python integrations/hermes_omh/stage_hae_zai.py --source <pinned-upstream> --output <new-nonserving-directory>`.
3. Copy `integrations/hermes_omh/qualification/test_mmx_zai_dispatcher.py` into that candidate's `tests/` directory.
4. Run the named tests from the candidate, setting `HERMES_SOURCE_ROOT` to the qualified Hermes source, `HERMES_HOME` and pytest `--basetemp` to new operation-owned temporary paths. Keep the upstream no-network conftest. Do not run the live gateway or mutate its package environment.
5. Generate an off candidate with `python integrations/hermes_omh/effort_config.py --manifest <candidate>/plugin.yaml --mode off`. Output is only a settings fragment. The native install/config/activation owner, not this builder, applies it after qualification.

## What is not proven

No claim of installed/activated dynamic effort, live Jev classification, API-key validity, classifier accuracy, provider acceptance, cache behavior, savings, or fleet-wide rollout is made by these tests. The default and Secretary .env files and this tool process did not declare a TypeSafe key; other secret stores and gateway memory were not enumerated.

We tested OMH's existing local workflow classifier with synthetic tasks as an alternative. Its top recommendation for `Architect a distributed transaction system and prove its recovery invariants` was accessibility-audit / light / medium confidence. This falsifies the assumption that workflow reasoning_demand is a reliable generic effort classifier. It is not silently substituted for Jev, and no additional scorer service is created to work around missing credentials.

Grok Secretary owns G1–G3 native bridge enrollment and served-path qualification in the original Slack thread1794049859.926899. The last observed response at this receipt is PICKUP_ACK/queued, not START or completion. Parent does not overlap its live profile writer. The default gateway's original reload EFFECT_UNKNOWN, active APPLICATION releases, and worker enrollment refusal remain fenced under the full source brief #983 comment6706043608.
