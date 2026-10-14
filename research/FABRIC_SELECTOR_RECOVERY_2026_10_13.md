# Fabric Selector — October 13 Source Recovery

**Program:** Mastermind Subagent Fabric automatic expiration-aware model, pool, account and host selection.
**Current carrier:** Draft Mastermind PR #1365, branch sol/fabric-expiry-selector-20261011-sol-001.
**Protected source/procedure pin:** Mastermind master 9a8e9b50b6158eb38af78a5b867eedba1719b908, mastermind.sol_skillpack.v1 1.0.1 / bootstrap major 1.
**Capability:** source implementation BUILT_NOT_PROVEN; live installation and per-account provider-usage proof NOT ESTABLISHED.

## Recovered actual source

The shared M2 account-local Fabric code moved after October 12. Installed lease_broker now has a host/model/account compatibility gate that calls glm_host_account_source.filter_observed_accounts before passing qualified rows into Broker._pick_account via grantable_override. The new expiry preference operates inside that filtered set, preserving the incumbent admission and immutable account/host/model claim.

All source files below were **read-only inspected**; staged changes were built and tested in disposable private workspace source, not installed:

| Original source path | Installed SHA256 preimage | Tested candidate SHA256 |
| --- | --- | --- |
| `ext/fabric_task.py` | `bfa5fcdc3df04d76d6c3b0b2dda2dac17ab4539253ec3ffb86fca4e2c4c13207` | `d2bb8218f74d8d4b17ef51dc7d0ae1c9c27a1f0788583de394a5ce41157b9525` |
| `ext/pick.py` | `c2d5420bbaf5b06b47788fecd999b7f920f60fe5f25154f2ab8a22afa2d58b29` | `48500967290e621b74ae33efb6563ae0c9f50c020c1ba1a4c36aa7b7c643df70` |
| `ext/lease_broker.py` | `a72bc031ddb81e559e0cf48fcbf824a959edfcf445c1d3d2d89348c3c66c6f0c` | `ed864e162238280fa17bc0b05aca6a06b45f700cac5e5160ec020c59c9633567` |
| `ext/tests/test_r31_glm_burn_down.py` | `23cf5a9269c553f9e09cf82ec326878a492b712b73fcae5b3ad32777f4a85d5e` | `30da09d2964c0e3a7be5840bfa5ac0f6c68fe255f28b8fb6c526db03cf5c3203` |
| `bin/pool` | `95dad5ac680d605200252f7152ecc80b77a767016874028288822a98b2b72c78` | `2331854c1613d588094bcca34e75f9c3dd7de4396272e78cf03efbcfcb4d0f8e` |
| `ext/tests/test_pick_policy.py` | `08be5ff6202ee78fe32a720e5aab026a9f0eac6be07da3a3d451b0c7eb5d0e79` | `348a9a20354ac181546c0be56fc9f4b8c63bab1047289941fa3c6a3c7525be47` |

## Exactly one current install proposal

Apply ONLY the seven ordered patch files in `ops/native_fabric/selector_source_bundle_20261012.json`, after current incumbent source-writer and runtime/effect admission. Do not apply the historically superseded older broker patch, older narrow R31 patch or old launcher patch. The release bundle has no install authority.

The unchanged read-only verifier `ops/native_fabric/verify_selector_source_bundle.py` requires exact source and patch SHA256s, replays patches only into an isolated temporary copy, checks six expected outputs and rereads the installed source. It exposes no install, credential, provider, account, worker, lease, service, admission or retry action.


## Host admission, cache safety, regression results

Current broker supports qualified host/account subsets. Added two independent real temporary-SQLite regressions: (1) an expiring account excluded by host qualification cannot be claimed even with unused quota; (2) a caller-pinned account outside the host-qualified subset is refused with no lease. Existing concurrency/cap/fairness and explicit-account checks are retained.

The claim-time quota cache now uses a single O_NOFOLLOW regular-file descriptor, bounded to 1 MiB, with device/inode/size/mtime/ctime agreement before and after reading. Cache swaps, in-place edits, invalid JSON and oversized files all fail closed to neutral selection. It cannot call the provider network during the SQLite claim lock.

The existing source fixture test_explicit_glm_escalation_respects_disabled_host_route was RED against the unmodified installed picker because the test monkeypatch had only one positional arg while production now passes route_key. The source-only test_pick_policy_host_mock_20261013.patch broadens **only the mock signature** to accept keyword args; its refusal assertion is unchanged.

The existing hosted PR CI on October 12 failed solely in test_d8_template_topology_and_protected_defaults because the broker patch filename included the semantic identity token account and the nested patch hunk coordinates 755/757/808/912 were misread as identity values. Reproduced RED against the old PR commit, then GREEN by renaming the source patch to lease_broker_glm_expiry_preference_20261013.patch (unchanged scanner). A synthetic worker_uid=451 source still triggers the guard: renaming did not exempt real identity code.

Source-rebased candidate full integrated result: **366 passed, 7 subtests passed**, testing real isolated SQLite broker claims, GLM quota reader/pool ranking, registered model/host selector, wrapper/preflight and native transport/capability. Read-only verifier: QUALIFIED_SOURCE_ONLY, 6 source files/7 patches matched. No real worker or provider call was launched by the new tests.

## Genuine production / publication blockers

1. This documentation and candidate do not establish an accepted installation, run selection, plugin/CLI upgrade or host/account consumption. The installed kit is active and shared by unrelated workers; preserve current source custody and original roots, never overwrite while another modifying owner or unresolved effect is present.
2. Require exact-head hosted CI (historical RED is not new head GREEN) and an independent current-source review of quota evidence validity, host-compatible account selection, selection policy and pre-START/after-START effect fences.
3. The incumbent authorized Fabric installer must reconcile current installed source hashes, root/parent and active worker returns before applying any managed update. Re-run the no-write preflight first; a changed hash is SOURCE_DRIFT, not automatic retry permission.
4. For PROVEN_LIVE: one real admitted, bounded task must return the actually served model, account and host plus provider-native usage/reset window and accepted result consumed by the same original parent. No added subscription spending or relaunch of the unrelated failed F04 operation is authorized by these source artifacts.
5. Native Auth0/same-parent release gates and the external F04 process-census failure classification remain separate workstream/source owners.

No runtime files, active workers, leases, provider credentials, default account settings or remote devices were changed by this source continuation.
