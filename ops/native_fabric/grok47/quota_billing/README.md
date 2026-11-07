# Grok Build ACP billing extension (source-only)

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

The reader only performs authenticated first-party ACP `initialize` and
`_x.ai/billing` calls, never model prompts. It reports a missing
usage percent as UNKNOWN. It never clears `GROK_EXHAUSTED`, grants a
lease, caches optimistic quota, or attests a paid Grok 4.7 result.
A positive same-account/window provider entitlement and incumbent
broker-owned safe marker reconciliation are separate future gates.
