# Preserve current GLM quota exclusion during routing integration

Same operation `fabric-routing-deep-audit-20261013-c2-001`, PR #1443 and branch.
Source candidates only; no current host, provider, credential, lease or install
operation. The original native fixture/preparation and host-inspection holds are
not retried or cleared.

## New dependency evidence

Mastermind #1469 at `2d83063f6e4dd22c5b01de195a751c17c556f1b8` carries the existing
ordinary GLM account-quota exclusion repair. Its owner reports scoped independent
review, local adoption and fresh-module checks; this operation has not verified
that installation. Its narrow broker change intersects `account_cap` with
`quota_remote.cached_glm_account_parked` when external gates are enabled. The
predicate consumes cached authoritative account observations only. Missing,
stale, future or reset-passed data does not invent an exhausted-account hold.

Normalized utilization and an expiry preference must never reintroduce an account
that this existing admission owner excluded. The integration therefore adds two
unchanged Git blobs from #1469 as test inputs rather than rewriting its predicate.
The new test reloads the complete #1391-plus-routing broker after applying the
exact #1469 account-cap patch, and checks that only `account_cap` changed. It uses
temporary SQLite, synthetic configuration and cached observations; provider,
credential and refresh entrypoints are guarded against calls.

## Proof status at publication

`tests/test_native_fabric_quota_admission_composition.py` adds five cases:
fresh exhausted-account filtering before ranking (including pinned-account
refusal), plus missing, stale, future and passed-reset observations. Python syntax
and five-case collection pass locally. Behavioral execution requires the exact
complete fixtures on the hosted runner; no passing runtime result is claimed in
advance. The preceding complete-broker composition tests and original native
49-pass/one-failure suite retain their separate proof scopes.

The #1391 native-binding compatibility correction remains the required priority
patch variant. Shared inputs do not authorize blind sequential installation of
independent manifests. Current source-writer custody, combined full-file hashes,
external broker/launcher compatibility, independent review, protected acceptance,
installation and useful original-parent consumption remain required.
