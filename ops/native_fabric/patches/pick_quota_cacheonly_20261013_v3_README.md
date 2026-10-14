# Fabric router: nonblocking advisory quota reads (V3 source-only)

Status: BUILT_NOT_PROVEN, NOT INSTALLED. This proposal modifies the incumbent M2 Fabric picker, quota reader and GLM usage ledger. It adds no separate lifecycle, auth, cache, broker, queue or host-admission authority.

## Why this matters
A live mechanical picker diagnostic took 76.10s when synchronous MiniMax and GLM provider quota refreshes were available. The same route took 0.1774s with those provider reads intercepted. The V3 isolated picker candidate uses ONLY fresh, cached provider observations for advisory ranking and does not publish GLM window-state data. It preserves ordinary provider refresh for explicit readers, the incumbent atomic broker grants at START, and current GLM model-account-host selection.

Stale, absent, future-dated or malformed quota cache entries do not establish provider-authoritative urgency. Default conservative routing remains available. This is not a paid quota, subscription or worker-cap expansion.

## Exact source and evidence
The patch was built against the CURRENT account-local M2 picker with new GLM host-account pairing, not an older kit. Preimage SHA256:
- ext/pick.py: c2d5420bbaf5b06b47788fecd999b7f920f60fe5f25154f2ab8a22afa2d58b29
- ext/quota_remote.py: 80ce4151a5d3f05528bc3c5e9af214d510ad9d9f17803c62f01a4c2d818ec5ff
- ext/pool_ledger.py: d5785307d39d79eaa6dbdba2bdbfc527c9beb06cfeb55d395797b3954ccff0a6
- orch/fabric/pools.yaml: 987a1237c6d93ab02bc2ac6a3be2ca2a771daf5eca135799cd3c4a8bace8e60c (unchanged)

M2 Python3.14: 219 targeted tests passed, zero failed, zero deselected. Two stale pre-existing test expectations were reproduced failing on UNMODIFIED installed source, then fixed in this patch: the new glm_model host-selector argument and unknown Grok quota must not become an invented 100-percent allowance. No tests were skipped in final M2 run.

Ubuntu1 Python3.12 staging: 215 passed and four local-Grok-broker-dependent priority tests failed. Ubuntu1 broker reports Grok capacity ZERO, so its actual hard admission correctly refuses Grok; those four tests require an enabled broker, as on M2. This is NOT a successful Ubuntu1 production release. The latest GLM host-account helper was brought into an isolated Ubuntu1 stage because installed host support remains older.

Sealed M2 source archive SHA256: 7caa32867f0138738c8e378db23d984e0b89daa5827e9516901e1964226452a0
Manifest SHA256: 97829c26d0ffd2057f545d7b22b9498706b276252066d99a2312fb94acb0c62f
Patch SHA256: 225541448ad16ff2daa6e431c43ead45f3e0e18dd04679c3b1181c0ff26bd392

## Release and review gates
This is a source-only integration packet. Before any live change, reconcile exclusive account-local writer custody, exact preimage blobs, current GLM pairing dependency, release support-generation closure and rollback. Obtain independent source review and latest-base test compatibility. Then use the existing authorized publisher and verify true picker latency, source freshness, broker/capacity refusal, model-host eligibility, selected workers and real task outcomes. Never claim production acceptance from source publication or tests alone.

The separate physical Ubuntu V8 elastic-max installation remains HELD_PLATFORM_REFUSAL (original effect fabric-ubuntu-elastic-max-20261010-web-003). No host disk floors, SSH policy, lane ceilings or physical admission are altered by this packet. Never use this PR to replay that held action.
