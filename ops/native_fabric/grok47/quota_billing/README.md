# Native quota and reset-recovery successor (source-only)

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

After this overlay itself has passed the actual protected source/release gates,
the **existing original native-generation publisher**
may stage these bytes through its complete native-generation builder,
composed only against the exact currently selected sealed predecessor.
The current H6 source recipe below produces complete 107/109/112-file
closures; the historical 85-file count is not an installation target. Publish, verify, and select with its existing compare-and-swap;
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

The cache-only `cached_glm_account_parked` call requires the caller's current
`config_generation` to establish an account-specific hold. The supplied broker
patch replaces that narrow negative check with the qualified paired-window join
and captures its generation on the original lease. A false narrow park result is
not permission to dispatch. Go's existing GoRouter
must export its original successful snapshot clock and binding; this module does
not start a second collector. Existing admission, grants, no-overage controls,
physical-account attestation and budget owners remain authoritative.

Qualification:

```bash
python -m unittest discover -s tests -p 'test_native_fabric_account_quota.py'
python -m unittest discover -s tests -p 'test_native_fabric_glm_reset_recovery.py'
python -m unittest discover -s ops/native_fabric/grok47/quota_billing -p 'test_grok_acp_billing.py'
```

The frozen preimages, candidate, manifests and selected runtime are unchanged.
Protected source acceptance and final native-generation composition/selection are
separate gates; merging this source does not install the H2 behavior.

## GLM manual reset recovery

Compose **all four existing runtime components together**: this `quota_remote.py`,
this `quota_circuit.py`, and the bounded `lease_broker.py.patch` / `pick.py.patch`
against the final composer's current originals. The circuit extends the existing
broker database; it does not create a new admission owner. Keep the frozen
candidate/preimages unchanged. Drain incompatible original quota writers through
the incumbent publisher before selecting the successor; atomic cache publication
requires every active writer to use the same lock. A changed predecessor requires
recomposition and requalification, never a forced patch or manifest edit.

Normal picker/host selection reaches the original on-demand quota reader before
an old cooldown can remove GLM. A successful later observation replaces both
balances and reported reset clocks, including null clocks. The cache's existing
300-second cadence also bounds repeated failed reads. `reconcile-reset --account
<configured-name>` forces one named-account observation immediately after a manual
reset; it never redeems a card or deletes a cooldown.

Each original-owner GET first invalidates old positive evidence with a unique
pending marker in the same cache. Its matching completion replaces that marker.
The short publication lock waits only a bounded interval; no provider request is
replayed. Failed final publication leaves admission closed until the original
owner reconciles the unresolved attempt, including across force/config changes.

A fresh same-generation observation started after a quota-exhaustion failure can
make that exact account's circuit half-open. The incumbent atomic broker permits
one outstanding probe and binds the exact cooldown revision to its lease. Only
the corresponding qualified success clears the SQL row. Authentication/rate
refusals, budgets, disabled accounts and other gates remain. Legacy rows without
a generation and declared shared scopes retain their existing cooldown behavior.

See [reset semantics, operation and acceptance](../../../../docs/HERMES_POOL_H2_GLM_RESET_RECOVERY.md).
No supported public reset-redemption contract was found; autonomous card
consumption is not enabled. This change automates observation/recovery after a
manual or natural replenishment and does not manufacture workload to consume quota.

## H6 complete native-generation composition

The existing builder now accepts `--include-quota-reset-recovery`. It joins exactly
four members over the complete `c7f5d2e62980e4cb38580496ef82125673015881f70d4fc4d6763137eed30459`
APPLICATION parent. The unflagged source, manifest/inventory and historical fixtures
remain unchanged. Use the original Go/HTTP options when preparing those complete
109/112-file layouts; the H2 base alone contains 107 members.

Both broker and picker postimages are reconstructed from exact whole preimages and
pinned patches without fuzz, then checked against their complete postimage hashes.
The existing builder and installer share the same source resolver. Its inventory
records the patch source and hashes rather than presenting derived bytes as an
unchanged candidate. The H2 inverse runs before the pool/admission/carrier inverses.

See the [H6 installation, preimage and rollback map](../../../../review_evidence/fabric_application/h6-recovery-20261107-c2/installation-map.md).
All sixteen reset journeys were also run against the four actual emitted HTTP-stage
members, including the current APPLICATION picker rather than the older Grok picker
used by the component fixture. No provider request or runtime selection is implied.
H3 integer-capacity, whole-operation bounds and common publication fencing remain
separate qualification requirements; this optional source flag does not enable them.
