# Grok 4.7 Fabric model compatibility candidate

Source basis: installed native generation `0e566251edc32dffbab800d2742bf0c2c45f3ea649254a08da3839a06981cd4f` on M2, inspected October 21/22 2026. The generated overlay is a non-installed candidate; it is NOT evidence of a production runtime switch.

* New worker picker default: `grok-4.7`; the historical ledger fallback is left on 4.6 so old records are not relabeled.
* Keep both `grok-4.6` and `grok-4.7` valid for new and historical receipts, executor validation, usage normalization and operator grant binding. Exact prior-operation reconciliation files remain bound to the original 4.6 records.
* Preserve the existing separate Cursor `cursor-grok-4.6-high` route: it is not Grok Build 4.7, and any fallback to it is a changed model.
* Do not change live leases, service, authentication, active generations, workers, or host placement.
* The four online Ubuntu hosts advertise 4.7 in `grok models`, but this command also said `You are not authenticated`; a successful paid authenticated Grok 4.7 worker return has **not** been established.

`overlay/` is intentionally assembled from the installed exact generation, because `ops/native_fabric/quota_continuity/source` contains earlier baseline preimages, not the complete current installed release. Test scripts `test_model_selection.py` and `test_runtime_compat.py` validate 12 offline selector, execution, private-output, identity, usage and authorization contracts; `tests/test_native_fabric_grok47.py` runs them in repository CI. Run `python3 ops/native_fabric/grok47/qualify_installed_generation.py --installed-store /path/to/native-code-releases` to verify the 85 installed source file hashes and create/verify/select a published generation in a disposable isolated owner without touching the live pointer. The exact code-only manifest digest from the observed M2 generation is `1a533ce9d673f9f9db94a8ca13b155e42ece1f7461207c51ed7fbd1df4cd979a`. The exact source closure, manifest hashes, actual controlled native publish/select via incumbent generation owner, host bootstrap and authenticated end-to-end return remain mandatory to finish rollout.


## Prepared release input (not installed)

For the exact M2 pinned source generation above, qualification has also produced an
immutable-input *staging candidate* under the existing Mastermind workspaces root:
`/Volumes/Mastermind/agent-workspaces/fabric-grok47-stage-20261022-sol-002`.
It has `source/` and `manifest.json` and verifies all 85 code hashes, without
storing credentials or modifying installed native code, service or `CURRENT.json`.
Reproduction on the same pinned source uses:

`python3 ops/native_fabric/grok47/qualify_installed_generation.py --installed-store "$BASE/native-code-releases" --release-stage "$FRESH_SIBLING_STAGE"`

**Release boundary:** after review/green protected CI and rechecking the exact
incumbent generation, invoke the existing `native_generation.py publish` with
`--source <stage>/source --stable-ext <kit>/ext --manifest <stage>/manifest.json`.
Its returned digest is the only eligible identity for subsequent `verify` and
compare-and-swap `select` (`--expect` pinned prior generation). Reconcile the
existing Fabric/Studio backend and controller path before selection; the native
publisher is not a process/control-plane owner. Test actual new-run model and
result identity after routing capacity permits it. Never force Grok despite the
existing weekly exhaustion/cooldown marker or rewrite old 4.6 receipts.

Release stage `-001` is superseded by `-002` after the Cursor Grok 4.6-specific quality-floor correction. Never publish `-001`.

## Expanded routing and native-harness audit (2026-10-22)

See [NATIVE_HARNESS_TRANSITION_20261022.md](NATIVE_HARNESS_TRANSITION_20261022.md) for the current observations, proposed capability/expiry policy, existing-owner integration map and production acceptance scenarios. The Cursor default edit is held by an action-scoped platform safety denial; this audit does not deploy or bypass it.

`analyze_pool_stats.py <canonical-stats-export>` reads an existing `pool stats --class ...` export and highlights missing outcomes, inadequate evaluated samples and separate admission failures. It contacts no provider, writes no registry and changes no routing. Its 10 tests supplement the original 12 model-compatibility tests, yielding 22 focused tests; the existing repository CI entrypoint discovers both. A report is not a causal cross-model benchmark or a quota/spend authorisation.
