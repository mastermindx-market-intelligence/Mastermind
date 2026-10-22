# Grok 4.7 Fabric model compatibility candidate

Source basis: installed native generation `0e566251edc32dffbab800d2742bf0c2c45f3ea649254a08da3839a06981cd4f` on M2, inspected October 21/22 2026. The generated overlay is a non-installed candidate; it is NOT evidence of a production runtime switch.

* New worker picker default: `grok-4.7`; the historical ledger fallback is left on 4.6 so old records are not relabeled.
* Keep both `grok-4.6` and `grok-4.7` valid for new and historical receipts, executor validation, usage normalization and operator grant binding. Exact prior-operation reconciliation files remain bound to the original 4.6 records.
* Preserve the existing separate Cursor `cursor-grok-4.6-high` route: it is not Grok Build 4.7, and any fallback to it is a changed model.
* Do not change live leases, service, authentication, active generations, workers, or host placement.
* The four online Ubuntu hosts advertise 4.7 in `grok models`, but this command also said `You are not authenticated`; a successful paid authenticated Grok 4.7 worker return has **not** been established.

`overlay/` is intentionally assembled from the installed exact generation, because `ops/native_fabric/quota_continuity/source` contains earlier baseline preimages, not the complete current installed release. Test scripts `test_model_selection.py` and `test_runtime_compat.py` validate 12 offline selector, execution, private-output, identity, usage and authorization contracts; `tests/test_native_fabric_grok47.py` runs them in repository CI. Run `python3 ops/native_fabric/grok47/qualify_installed_generation.py --installed-store /path/to/native-code-releases` to verify the 85 installed source file hashes and create/verify/select a published generation in a disposable isolated owner without touching the live pointer. The current nine-overlay code-only manifest digest is `b6180122f83214bbc4c48f67b976e86084ae4aebc04082d0689935c52d721905` (stage `-005`). The exact source closure, manifest hashes, actual controlled native publish/select via incumbent generation owner, host bootstrap and authenticated end-to-end return remain mandatory to finish rollout.


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

Stages `-001` and `-002` are superseded by `-003` (which adds the separate legacy Cursor argument-forwarding safety repair). Never publish either earlier stage.

## Expanded routing and native-harness audit (2026-10-22)

See [NATIVE_HARNESS_TRANSITION_20261022.md](NATIVE_HARNESS_TRANSITION_20261022.md) for the current observations, proposed capability/expiry policy, existing-owner integration map and production acceptance scenarios. The Cursor default edit is held by an action-scoped platform safety denial; this audit does not deploy or bypass it.

`analyze_pool_stats.py <canonical-stats-export>` reads an existing `pool stats --class ...` export and highlights missing outcomes, inadequate evaluated samples and separate admission failures. It contacts no provider, writes no registry and changes no routing. Its 10 tests supplement the original 12 model-compatibility tests and five legacy local-Cursor forwarding tests, yielding 32 focused tests; the existing repository CI entrypoint discovers both. A report is not a causal cross-model benchmark or a quota/spend authorisation.


## Separate legacy Cursor model-forwarding repair (source only)

The local `sub.sh cursor` entry previously accepted an explicit model and then omitted the `--model` CLI argument, silently letting the CLI select its own default. This source-only correction preserves the original default when no model is specified and forwards only the already-reviewed `composer-2.5` and `cursor-grok-4.6-high` aliases. Unsupported and new 4.7 aliases are refused. Five isolated subprocess tests exercise the actual shell branch with fake `cursor-agent` and fake slot/ledger helpers: no account, provider, lease, host or production change is made. **This is not the earlier platform-denied Cursor 4.7 default change**, and it does not arm the new 4.7 aliases. The previous staged -002 source is superseded. The currently qualified isolated candidate is `fabric-grok47-stage-20261022-sol-005` with all 85 pinned release-file hashes verified and nine reviewed overlays. This is a candidate only; installed `CURRENT.json` remains sequence 14 on the original generation.

The isolated original publisher now exercises a **two-generation compare-and-swap**: original release selected first, patched release selected against the exact predecessor, then an intentionally stale original expectation refused without changing the selected pointer. It does not select the live M2 generation.


## Local Grok Build default consistency

The same source overlay now sets an **un-pinned local Grok Build call** to
`grok-4.7` *before* the existing economic/policy gate and provider CLI call.
Explicit `grok-4.6` historical pins remain unchanged; unknown models fail with
`LOCAL_GROK_MODEL_REFUSED` (78) without attempting any provider call. The native
Grok adapter's existing `-m` argument receives the normalized model. Five
additional isolated Bash-contract tests cover model default, both pins, and
unsupported identifiers. Total focused test count: **32**, with repository CI
entrypoint and shell checks passing locally. This does not alter any Cursor 4.7
default, weekly exhaustion marker, account permission or live service.

Stage `-003` is superseded by exact pinned stage `-004` at
`/Volumes/Mastermind/agent-workspaces/fabric-grok47-stage-20261022-sol-004`,
manifest `9c8e3fd927fe3c9979db937613fa3fab3625c510007847be1f5af6f997ce31cf`.
Earlier stages `-001`, `-002`, and `-003` MUST NOT be published. The installed
native pointer remained unchanged at sequence 14 after qualification.


## Native headless model identity: v2 (source candidate)

Native Grok usage now issues `mastermind.grok_usage.v2` for *new* attempts,
retaining the exact observed token counts and session identifier. Unlike the
old v1 record, `requested_model` is the CLI selection and `served_model` is
**null** when the provider's final JSON has no explicit model field.
`model_identity_source=requested_cli_only` makes that distinction testable;
a matching native-final `model` string can instead set
`model_identity_source=native_headless_final_model_field`, which is still a
non-cryptographic provider-output observation, not an independent entitlement
attestation. A contradictory native-final model fails closed as
`GROK_NATIVE_FINAL_MODEL_CONFLICT` after process cleanup; private raw JSON is
never sent as the visible result on this path. The existing `validate-usage`
reader accepts historical v1 records without rewriting them and requires a
strict v2 source/field combination. The old normalized-output manifest schema
continues to bind the **requested** model for exact source/command identity.
Three focused regression tests were added, for **35 focused tests** locally.
No API/account/provider invocation, native live generation selection, receipt
backfill or Cursor-model default change occurred during this patch.


## Current qualified release target — only stage -005

The **only publishable candidate after required protected review, CI and owner qualification**
is `/Volumes/Mastermind/agent-workspaces/fabric-grok47-stage-20261022-sol-005`;
manifest SHA256 `b6180122f83214bbc4c48f67b976e86084ae4aebc04082d0689935c52d721905`;
original-owner predicted native generation
`cbf87f8c6e27f1cbae13f034ed8bc77fd1d8b047789c6c01be6f9734faf8ff28`.
All 85 source files match this manifest, and an isolated two-generation original-owner
publish/verify/select + stale-CAS refusal passed. Stages -001 through -004 have
been superseded; **none** may be published. The prior stage sections above are
historical test observations, not current release instructions. Live M2
`CURRENT.json` has not been selected or altered. All required production
acceptance and held Cursor-default constraints remain in force.
