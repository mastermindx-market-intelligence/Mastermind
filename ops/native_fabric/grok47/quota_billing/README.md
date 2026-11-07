# Native quota reader successor (source-only)

This directory provides a **reviewable replacement source** for the existing
native Fabric runtime file `ext/quota_remote.py`. It does **not** create
a new quota, identity, account, broker, lease, or watcher authority.

The original `ops/native_fabric/quota_continuity/source/quota_remote.py`
is an immutable installed preimage, locked by
`rollout/native-preimages.json`. The incumbent
`quota_continuity/candidate/quota_remote.py` is likewise preserved:
its SHA256 `3c1484864848b5cdf4daeecde092f7c407ab313a9f0d94a7f0fd204dbcf813b8`
matches the selected generation-16 runtime before this change. Never edit
those frozen source/candidate files, nor the rollout manifest/inventory
owned by pending Fabric PR #1720 for this feature.

After this overlay itself has merged through protected master and passed
independent review, the **existing original native-generation publisher**
may stage these bytes as `ext/quota_remote.py` in the complete 85-file
closure, composed only against the exact currently selected sealed
predecessor. Publish, verify, and select with its existing compare-and-swap;
a new selected generation or conflicting source invalidates the stage.
The `grok47/qualify_installed_generation.py` historical stage owner
has a fixed nine-file overlay set and is **not** extended or used for this
separate follow-up.

The Grok branch only performs authenticated first-party ACP `initialize` and
`_x.ai/billing` calls, never model prompts. It reports a missing
usage percent as UNKNOWN. It never clears `GROK_EXHAUSTED`, grants a
lease, caches optimistic quota, or attests a paid Grok 4.7 result.
A positive same-account/window provider entitlement and incumbent
broker-owned safe marker reconciliation are separate future gates.

## H2 account evidence

The same successor now adds account/configuration-bound GLM and MiniMax observations,
Go usage/debit normalization, and the original reader's `show --qualified` projection.
See [H2 coverage and qualification](../../../../docs/HERMES_POOL_H2_ACCOUNT_COVERAGE.md)
for exact account/model/workload coverage, installed refresh evidence and remaining joins.

A reset boundary invalidates cached readiness until the original reader observes the
provider again. Every required window must be usable on the same account. Missing,
malformed, future, stale and failed observations cannot establish headroom. Local
estimates remain telemetry. Terminal provider refusal is retained in the existing
cache with the attempted configuration generation; `--force` does not clear it.

The cache-only `cached_glm_account_parked` call now requires the caller's current
`config_generation` to establish an account-specific hold. H3 must compose that
argument and consume qualified paired windows before this successor is selected.
A false narrow park result is not permission to dispatch. Go's existing GoRouter
must export its original successful snapshot clock and binding; this module does
not start a second collector. Existing admission, grants, no-overage controls,
physical-account attestation and budget owners remain authoritative.

Qualification:

```bash
python -m unittest discover -s tests -p 'test_native_fabric_account_quota.py'
python -m unittest discover -s ops/native_fabric/grok47/quota_billing -p 'test_grok_acp_billing.py'
```

The frozen preimages, candidate, manifests and selected runtime are unchanged.
Protected source acceptance and final native-generation composition/selection are
separate gates; merging this source does not install the H2 behavior.
