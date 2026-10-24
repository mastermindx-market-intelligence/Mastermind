# Manual pool/model selection for Subagent Fabric — source candidate

**Chairman directive, 2026-10-21.** Existing auto routing remains default; an originating session may optionally name a qualified provider pool and an exact model where special intelligence or capability is needed. A pinned Grok request must never silently execute on GLM. Grok 4.7 is an example **not a claim of live provider readiness**, capability entitlement or model quality proof.

## Canonical state

- Executive OS plan-v4 already supports manual placement and fail-closed model pins, with tests in `tests/test_executive_coo_ready_frontier.py`.
- Native `fabric_task.py request` has `--pool/--model`; actual picker currently restricts exact models. [PR #1365](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1365) carries the narrower default-qualified exact-model/preview selector, is open DRAFT/HOLD and not installed. Installed M2 generation differs from that patch's historical preimage (see #1365 issue comment 6287191803).
- The current Web Fabric-only tool `fabric_request` rejects all model/pool fields. Its original source owners have concurrent drafts [#1438](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1438), [#1457](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1457), and [#1536](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1536). Therefore this branch proposes **a non-mutating patch file plus source replay test only**, not a competing modification to their live paths.

## Contract

- Caller may omit routing fields (AUTO), choose `pool` only (POOL), or choose `pool+model` (EXACT_MODEL). Closed provider values, literal model tokens; no arbitrary host/CWD/shell/account or permission widening.
- Before creating any controller for manual requests, the same original `fabric_task.py preview` must return matching `PREVIEW_ONLY/reserved:false`, run ID, provider pool and exact model if requested, using the caller's real classification, review-independence and escalation reason. Any preview unavailable/mismatch rejects `MANUAL_ROUTE_UNAVAILABLE` without submitting work.
- At request, forward exact `--pool/--model` to the existing native picker and **disable automatic cross-provider quota continuation for manually selected routes**. Picker/lease/host/identity guards still recheck on actual launch and may refuse; a preview does not reserve capacity.
- The unchanged `fabric_capabilities` tool reports manual availability only when the native adapter's help advertises `preview`.
- Failures, stale admission, no capacity, permission denies and uncertain modifying effects remain distinct; no replay, retry, alternate carrier or new lifecycle/Capacity owner.

## Proof / release gate

`tests/test_web_fabric_manual_model_patch.py` enforces exact current Git blob preimages, applies the candidate patch only in a disposable directory and runs the entire original Node facade suite with new synthetic negative/positive manual-pin tests. These tests DO NOT prove real Grok-4.7 availability, vision entitlement, transport adoption, real worker START or parent acceptance.

**Do not merge or hot-apply to the installed source.** Existing Web backend owner must reconcile this patch with #1536 result paging, #1566 modern gateway, the actual installed selector/release from #1365, current native provider model catalog and distinct per-model capability/quality gates. Require source-owner admission, exact-head CI, independent review, a safe immutable service release and one origin-session pinned-model START->result->parent consumption->accepted proof. Before any Grok-4.7 canary, verify current provider-native catalog actually exposes Grok 4.7 in an entitled, admitted pool. Unknown is not available.

At this boundary: **BUILT_NOT_PROVEN / MISSION_COMPLETE=false**, no host or provider effects performed. Source baseline `230e9a301ed774e79410829f1b5c049226fa59f1`.

## 2026-10-22 pinned native generation / strict dispatch update

**Current protected procedure:** `master@d31aade92b969e8897513d8634ecd59dba00e1e3` (Skillpack schema v1, version 1.0.1). Original Web backend preimages remain Git blob `6c828312a3de711ded1eaa388efaf4fb4fc4a149`, tests `555d5b89c651c47eb4ed3209063d8bacc7960463`. #1457's older standalone backend is **not** this source: reconcile via incumbent Web owner, not direct patch replay onto that branch.

**Installed M2 routing is an immutable native code generation**, not the old flat editable `pool`/`fabric_task.py`. At read-only observation, `native-code-releases/CURRENT.json` had generation `0e566251edc32dffbab800d2742bf0c2c45f3ea649254a08da3839a06981cd4f`, selection sequence 14. Its sealed source inputs: `ext/fabric_task.py` SHA256 `2294bbcf537ebc7fb91ab03a71f7de85b4c1c8f697932c9e3c8865983dc2633d`; `pool` `4026eb128fe803e575151bbeec49a4d8f5838408db1177feedd64ad24f4f2059`; `ext/pick.py` `74bd656884739d61e7a1892735fdcf7844e030fa55b2dc51ecaad1b4c8560286`. Flat live shims are native-generation launcher bridges. Historical #1365 native preimages drifted; 3 of 7 old bundle patches refused in a disposable flat-copy replay. Neither those patches nor this candidate have been installed.

**Native candidate**, source only: `ops/native_fabric/patches/native_generation_manual_preview_20261022.patch`, SHA256 `53e9c28f43939994f43d6a11018dc0b28cb9eab4d610197cd03c80f94bbeb077`, patches exactly three native files above. Candidate source output SHA256: `fabric_task.py` `b5ca574e05245637eb008a7c248fbdd77e808ee458472f621e935f7fc0c6e892`, `pool` `12602edd2f0bf3a5a789eb2b77043a1973bbed533ff35d307357e00be1531679`, `pick.py` `f785916dc3a7c876af93beefa02bbb663f81124583f8a691d02b13642f203589`. Its pure `preview` uses incumbent picker and economic policy with no reservation or worker; `request --strict-manual-pin` checks the *actually reselected* pool/model before native controller launch, refuses quota-fallback with strict pin, while legacy requests retain existing behavior. Picker exact-model pin is limited to current provider/task default or already documented GLM narrow escalation; it does not admit an arbitrary model, new provider, premium principal, account, host or role. Do not let the ability to parse a model name masquerade as provider qualification.

**Web candidate** `ops/native_fabric/patches/web_fabric_manual_model_20261021.patch` now checks `strict_pin_enforced_at_request=true` and `selection_rechecked_at_request=true` in preview, then invokes native `--strict-manual-pin`. Manual pins do not require or enable automatic quota continuation. `fabric_capabilities.manual_routing.available` is false until the incumbent native CLI advertises both preview and request strict pin. Omitting pool/model keeps AUTO unchanged; explicit `model:auto` with chosen pool pins the provider only.

**No-effect proof completed on M2 isolated scratch**:
- Web patch applied with `git apply --check` to the exact protected source and replayed in a fresh disposable directory; **43/43 Node tests passed**, including strict-preview mismatch, no quota substitution, explicit auto model, and capability advertisement negative.
- Native `ops/native_fabric/verify_native_manual_preview_20261022.py --generation <exact immutable generation>` applied all three file patches from three SHA-bound sealed current inputs in `TemporaryDirectory`, checked exact output SHA, and executed **10/10 provider-free native preview/picker tests** using `qualification/native_manual_preview_fixture.py`. Receipt: `SOURCE_ONLY_TESTED`, `source_count=3`, `sealed_generation_unchanged=true`, `current_selected_at_end=true`, `live_install_performed=false`, `provider_call_performed=false`, `worker_start_proven=false`.
- A read-only real-policy preview with `--pool grok --model grok-4.7` correctly refused: `NONE reason=unknown requested_model (grok-4.7)` (exit 75). Grok 4.7 catalog/entitlement is owned by a *separate session*; its fixture string in tests is **synthetic**, not a measured model or production deployment.

**Release holds**: This PR is DRAFT/source-only. The original native release/selector owner (#1365) must independently reconcile the above pinned input and subsequent generation selection/active writers, decide lawful native installer/manifest integration, and retain existing protected code custody. The incumbent Web source/gateway owner (#1457 with #1536/#1566) must compose the latest Web backend and installed Fabric-only service, maintain the connector's authenticated trust boundary, and separately verify actual web enrollment. No merge/release on CI alone: require independent code review, exact-head hosted CI, immutable source release, current app enrollment/consent, a real origin-session pinned provider/model worker START, served-model evidence, retained result, original parent consumption and accepted completion. Model picker source support is not production availability.

## 2026-10-22 generation-16 source forward port — source only

The earlier generation-14 native patch, verifier and ten-case fixture above are historical preimages, **not current release instructions**. Fresh M2 native `CURRENT.json` readback selected **generation `09b1ff4204c49acc71bb228751c4efefc22c70c89092734d9ea2fafe3fff1a49`, sequence 16**. The three sealed input hashes are now:

- `ext/fabric_task.py`: `2294bbcf537ebc7fb91ab03a71f7de85b4c1c8f697932c9e3c8865983dc2633d`
- `ext/pick.py`: `a776ed140a051e7ac899a5f4b7c641d3d6e46456db287e914a154b3b93e57423`
- `pool`: `4026eb128fe803e575151bbeec49a4d8f5838408db1177feedd64ad24f4f2059`

The new pinned native patch SHA256 is **`917d7a437a0ebfc7d0108879e0b680cac0b16e00262d8edc13809ae4356c86f2`**. Output source hashes: `ext/fabric_task.py` `b5ca574e05245637eb008a7c248fbdd77e808ee458472f621e935f7fc0c6e892`; `ext/pick.py` `34cc6c128b52fdc76d8ebf5d652008cc69381fb4eb042768f5fce50d4df322ea`; `pool` `12602edd2f0bf3a5a789eb2b77043a1973bbed533ff35d307357e00be1531679`.

On a fresh isolated copy of the actual sealed selected source, the patched `fabric_task.py` and `pool` re-applied unchanged, while the picker hunk was forward-ported around the newer explicit Grok 4.6/4.7 pin law from merged #1691. It retains the selected-generation's no-model-echo refusal and does **not** reintroduce an exact Grok-to-Cursor substitution claim; strict Web model pins still refuse actual route mismatch. The fixture now recognizes legitimate native Grok model pins and adds a test for a named provider's task-qualified default vs unqualified/unscoped models.

Evidence from **the new isolated stage**, not the installed generation:
- Exact input `git apply --check`, actual `git apply`, and all three output SHA256 matches passed, including a second independent scratch replay.
- Pinned verifier against the **actual sealed selected generation 16**: `SOURCE_ONLY_TESTED`, **11/11** no-provider tests, `sealed_generation_unchanged=true`, `current_selected_at_end=true`, `live_install_performed=false`, `provider_call_performed=false`, `worker_start_proven=false`.
- A real signed-policy hash-identical **scratch copy** (`pools.yaml` SHA256 `db4e4b1768809bd991003ef045568b480cdb42ea0715a6b73ea5353930bf90d8`) yielded a no-reservation native `preview`: `pool=glm, model=glm-5.3, host=ubuntu0, state=PREVIEW_ONLY, reserved=false, strict_pin_enforced_at_request=true, selection_rechecked_at_request=true`, with a concrete C2 economic escalation witness. This is a prospective route only; it is not a provider lease, actual START or capacity guarantee.

**MAS-258 separation.** The two independent-review attempts against Macro PR #10067 head `4526babd9da6e6331e81ed247c19b59084cbd92b` are terminal rc1/Qwen 429, with no verdict or retry permission. The observed Web `subject_pool=glm` was an **author-pool independence argument**, not a provider selection; the existing Fabric-only facade intentionally has no manual `pool` field. This source-only routing patch is a separate authorized repair, **not** an instruction to retry either failed worker through a different carrier. Macro Draft/HOLD, #9957/#9980, nightly custody, separate release ownership and procedure pin `c9cbee5569ba50e30e28715d930809061a169517` remain unchanged.

**Release remains held** until independently reviewed exact source, latest-base integration/CI, any #1769/#1731 native overlap resolution, a newly protected native immutable generation and installed Web facade under its original restricted service owner. A real authorized future independent review must use a newly admitted run, not replay or repurpose the failed Qwen effects. Web source is unchanged by this native-only forward port. `MISSION_COMPLETE=false`.

## 2026-10-22 protected-Web composition — current candidate source

Protected Mastermind advanced to `35ad72377bda6f23c0cb2401f0260c6a53812e3d`, integrating the independent Fabric acceptance-evidence hardening (#1759). Its Web facade source preimages are `integrations/studio_direct_mcp/fabric-backend.mjs` Git blob `1dfb573f4db36285e0c8513eaaf583dd38c8ecb7` and `fabric-backend.test.mjs` Git blob `87c2bb7078c2cedf2601e0d000cb4a4e5b9b9f01`. The older Web patch/test blob fences are historical and cannot qualify this protected source.

The Web patch was replayed against a copy of those exact protected files, preserving #1759's closed acceptance-evidence code enumeration, then recomposed without modifying protected or installed files. Current Web patch SHA256: **`ccbc88a5b71c676ca193030a33b49efa6653b81c27a105d07df336037284cbe5`**. Exact patch check/replay succeeded in a second independent source copy, with identical resulting backend/test SHA256 (`274c91b04e12241e6b9d815caaf304bb6c89f8ced2ba5435f7973a9de55f18aa` and `3437c9e77108557cf288457e44ec4f4e31a297aa0c4a71b360f125037c0bd965`). The current protected `fixtures/fabric-adapter.py` was used unchanged.

**Proof:** `node --test fabric-backend.test.mjs` completed **45/45 PASS**, including inherited acceptance-evidence negatives plus manual provider/model preview fail-closed behavior. The exact-source Python wrapper against the protected Web blob preimages passed **1/1**, with its copied/replayed Node suite exit zero. No paid provider, live tool-schema refresh, global service install, ledger write, acceptance, or controller launch occurred.

The six source files carried by PR #1692 remain its single candidate. To compose with the current protected baseline, preserve the original PR identity/branch and make a conflict-free current-base integration (only those six candidate-only files added). Do not merge or deploy on source tests alone. Independent source review, exact-head CI/CodeQL, immutable backend/native generation release with original service owner, provider-capacity admission, and a genuinely independent future run/parent consumption/acceptance remain required. Existing Qwen 429 effects may not be retried or accepted as verdicts.

## 2026-10-22 source-audit correction: strict provider mode and pinned test fixture

A separate **read-only source audit** of PR #1692 at head 24e2f6b1703ed2063cc01f9a58659713725da82e issued bounded REQUEST_CHANGES: native _enforce_manual_route checked pool and optional model but not selected MODE. The selected generation-16 picker currently pairs each pool with approved execution modes (grok→grok, bailian→qwen, glm→glm/glm-codex, ocfree→oc-free, go→go-codex), so no actual cross-provider execution was observed. The strict boundary now refuses missing, unknown or cross-family mode even if a future picker incorrectly echoes the requested pool and model.

New pinned native patch SHA256: 1c30952c04e6d130eeae0121cb17e9fb25683cc5eea61c45157967c2ab0f1cdd. Patched ext/fabric_task.py SHA256: b49bd2f92a0394fd3779d132708f00ace89b22669e2264417d089da36dd2579f; pick.py and pool outputs remain the generation-16 hashes above. Revised fixture SHA256: dd2bf01f597b6749d08ebc30092aa59ef9318a8de837c2eaec8504d9e1204f30. The verifier now SHA-binds the fixture and executes its staged copy, not the source path.

**Requalification:** On actual sealed M2 native generation 16, fresh disposable git apply --check and apply, three output hashes, and **12/12** no-provider tests passed. Receipt: SOURCE_ONLY_TESTED, current_selected_at_end=true, sealed_generation_unchanged=true, live_install_performed=false, provider_call_performed=false, worker_start_proven=false, review_required=true. Negatives include wrong, unknown and missing modes; legitimate Bailian/GLM/OpenCode modes remain valid. The read-only source reviewer is not a Fabric independent MAS-258 worker or final release approval.

This correction changes only existing PR #1692 source patch, fixture, verifier and this research note. Installed Fabric remains unchanged; no worker retry, Macro #10067 edit/release, MAS-258 procedure-pin change or #9957/#9980 hold release occurred. Native/Web installation, reviewer acceptance and true provider-pinned MAS independent review still require future guarded stages.

## 2026-10-23 direct integrated Web backend (same original PR)

After the Chairman requested taking PR #1692 on verified inactivity, its source-only
patch was forward-ported to the **actual current protected Web facade**, rather
than being applied onto an obsolete backend blob. The current protected master
was integrated as a parent without conflict; the original patch files, native
qualification and historical source evidence are retained. The Web source now
exposes typed `pool` and `model` on the live `fabric_request` contract, validates
strict native help, performs matching no-effect native preview, and forwards the
strict pin without cross-provider quota fallback. Unspecified routing keeps AUTO.
Current backend Node tests include explicit pool-only, exact model, max turns,
preview mismatch, unsupported native flag, and capabilities negatives. The old
source-only patch replay test was converted into a test of the actual integrated
Node backend; its preimages are historical, not current release instructions.

**Source integration is not release:** installed generation, actual native preview,
provider-specific entitlements, independent review and Web seat installation remain
separate held gates. A synthetic `grok-4.7` test token never establishes that model
is offered or may be routed. Do not issue retries for earlier Qwen 429 operations.

## 2026-10-23 forward qualification against actually selected native generation 21

Fresh same-host `native-code-releases/CURRENT.json` readback selected immutable
**sequence 21** generation `6957399841a2913d5a32deedd633e4c4b5124c3199d0e804fc8a6abe69e8ef51`.
The previous sequence-16 native patch source preimage was no longer applicable.
The *same* existing native patch file `ops/native_fabric/patches/native_generation_manual_preview_20261022.patch`
was forward-ported **in an isolated uninstalled copy only**, preserving current
native request `not_before`, per-request `max_turns`, lease, quota, and source policy.
`verify_native_manual_preview_20261022.py` now pins generation 21, three exact input
hashes, resulting output hashes and new patch SHA256
`b678fa16bc04a075cc87272a30f7ca4a11a9e60391e99c0b44fa46df032376ca`.
Native source qualification readback: **12/12 provider-free tests green**, exact
three-file source preimages valid, `sealed_generation_unchanged=true`,
`current_selected_at_end=true`, `live_install_performed=false`,
`provider_call_performed=false`, and `worker_start_proven=false`.
This supersedes the older generation-16 patch as an installation candidate;
commit history retains the old evidence. Merging this source does not install or
select the native generation. Its publisher/owner must reconcile later movement
again and perform the normal immutable qualification/selection path.

A new independent native `--pool glm` review request of source head `2ffeac8e`
was refused **before worker launch** due zero eligible GLM hosts; the original
run was canonically `REQUEST_REFUSED_BEFORE_LAUNCH`,
`execution_absence_proven=true` and `same_run_replay_allowed=false`. Source
separation and original-root retention were preserved. Host qualification showed
Ubuntu0–3 `probe_exit_1` despite plain M2 SSH reachability for Ubuntu1, while
M1/Ubuntu4 remain explicit-canary-only. No qualification bypass or second
review launch was attempted. A new independent Fabric review can begin only
when a lawful non-Qwen provider/host is actually eligible. GitHub human reviewer
requests are still awaiting a verdict.
