# Fabric router V4 — nonblocking advisory quota selection with complete-account truth

**Status: BUILT_NOT_PROVEN / DRAFT SOURCE PATCH / NOT INSTALLED.** This changes only the existing account-local Fabric picker, quota reader and GLM usage ledger. It creates no new scheduler, cache owner, credential surface, lifecycle, queue, retry system or atomic quota grantor.

## Machine capability

The existing picker can synchronously refresh MiniMax and up to three GLM account quota endpoints during a mere advisory provider ranking. One retained real diagnostic took 76.10 seconds; the same simulated selection took 0.146–0.177 seconds with quota network disabled. This is evidence of a blocking mechanism, **not a production speed acceptance**.

V4 selects using fresh cached provider quota observations only on the advisory route, never the synchronous quota HTTP refresh path. Explicit quota-refresh operations retain their existing behavior. GLM local window state is never published by advisory ranking; real provider accounts and the incumbent lease broker still own quota admission at START. The new GLM host-account pairing in the October 12+ M2 source is preserved. No model, physical-lane cap, disk reserve, root accounting, or paid subscription entitlement changes.

V4 additionally closes an all-accounts truth bug observed in V3: when one GLM account is observed 98% used and a sibling account's quota is missing/stale/future/incomplete, V3 would incorrectly return provider-authoritative PARKED for the *whole* pool. V4 refuses to conclude ALL accounts are exhausted from only partial provider observations. Six adversarial regression cases were red on the unchanged V3 source; all are green after the single-file fix. True all-observed PARKED and available-account OK remain unchanged. Unknown/stale quota remains unknown, not invented capacity.

## Frozen source and verification

M2 source preimage SHA256 (do not apply if any differ):
- ext/pick.py: c2d5420bbaf5b06b47788fecd999b7f920f60fe5f25154f2ab8a22afa2d58b29
- ext/quota_remote.py: 80ce4151a5d3f05528bc3c5e9af214d510ad9d9f17803c62f01a4c2d818ec5ff
- ext/pool_ledger.py: d5785307d39d79eaa6dbdba2bdbfc527c9beb06cfeb55d395797b3954ccff0a6
- orch/fabric/pools.yaml: 987a1237c6d93ab02bc2ac6a3be2ca2a771daf5eca135799cd3c4a8bace8e60c (unchanged)

V4 M2 Python3.14: **227 tests passed**, zero failed/skipped/deselected in integrated-regressions-4.log. Independent Ubuntu1 Python3.12 isolated test logic: **227 passed** in 2.51 sec, with only four controller-dependent priority tests using an explicit test-only simulation of the controller's enabled Grok quota. On Ubuntu1, the actual broker reports Grok capacity 0; without those four test-only assumptions it gives 223 passes, four legitimate broker-cap-dependent priority failures. Do not call this a successful production rollout or quota enrollment. Two older pre-existing test assumptions were separately demonstrated incorrect on unchanged live M2 source and corrected as test fixtures only.

The new V4 modification versus immutable V3 consists solely of quota_remote.py and tests/test_advisory_glm_partial_unknown_v4.py. All other V3 source remains byte-identical. Complete V4 patch uses source preimages above and includes test-only fixes and focused regressions.

Immutable offline V4 archive SHA256: 7d685fbc33568da85592c59d26f2f6e608a97466d5764bb4be46f7be3d16ab3d
Manifest SHA256: 06b10bc80cc1b39cf08217ad3c87a1047c3ed893cc9f7238977179f183326075
Patch SHA256: 7347151ec5a2de9f59c15647b0d18360f35915feabd6d380197cf4361e5f7ace

## Remaining release gates

The PR is an *inert source carrier* until the canonical account-local publisher accepts exact source custody and checked live source preimages, complete support-generation dependencies (notably GLM host-account helper), independent source review, latest-base integration and an authorized activation. After installation, separately prove true picker latency and HTTP-request absence, provider observation freshness, missing-account fallbacks, broker refusals, selected host/model, end-to-end worker completion and rollback.

The independent V8 Ubuntu physical elastic-max installation remains **HELD_PLATFORM_REFUSAL** (original effect fabric-ubuntu-elastic-max-20261010-web-003). V4 never retries, widens or modifies that action; live Ubuntu registries and disk/headroom admission remain untouched.
