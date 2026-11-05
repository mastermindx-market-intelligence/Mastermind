# Native admission in the existing Fabric broker

This source component adds original Runtime Job/Attempt retention to the existing
Fabric lease database. It is not installed, an authenticated transport, or a new
broker lifecycle. The existing Studio owner must compose the patch and module
together before exposing the closed native operations.

`lease_broker.py.patch` applies only to the retained base fixture SHA-256
`a72bc031ddb81e559e0cf48fcbf824a959edfcf445c1d3d2d89348c3c66c6f0c`.
The resulting broker SHA-256 is
`4cac678defac9116c2324a651a7cd90c5144822d8cd1c2aa64e20c299a2a9267`.
Existing installations with other bytes need source reconciliation, never a
whole-file overwrite using this historical fixture.

The original broker lock and grant transaction retain the lease UUID, complete
binding and immutable grant together. Repeated acquire returns that original
grant or settlement before consulting current quota. Changed root, parent,
fence, request, profile, account, host or model refuses. Read, heartbeat and
settlement require the same binding; ordinary heartbeat/release cannot mutate
native rows. Uncertain native liveness retains capacity and records a sticky
reconciliation requirement rather than expiring the lease.

The five settlement hashes correlate already-verified terminal evidence. They
do not prove it. The authenticated existing owner must verify process closure,
cleanup, assignment observation, Control retention and physical release before
calling settlement. Caller-supplied identity labels and hashes are not grants.

## Verification

The 26 focused admission tests pass, including changed-binding rejection,
lost-response replay, sticky uncertainty and unchanged accounting. Independent
review additionally verified rollback after an injected post-INSERT fault and
identity rejection before global garbage collection. Forty-eight distinct
ordinary broker/placement compatibility checks pass. One copied compatibility
fixture initially lacked `mm_feeder.sh`; its failure is retained, and only that
case was rerun successfully after restoring the exact incumbent dependency.

Run the hermetic focused tests from the repository root with:

```sh
python -m pytest -q tests/test_fabric_native_account_admission.py
```

Evidence and exact review hashes are in `SOURCE_QUALIFICATION.json`.

## Required composition

Before any native row is admitted, all old broker mutators must be quiesced or
verified to use the new version: old code could otherwise expire or release a
native row. The existing Studio lifecycle still needs its real connected Unix
descriptor path, installed Control peer qualification, current Runtime request,
fixed realm/account/physical-host enrollment and terminal-proof verification.
The closed source methods deliberately provide no public CLI or HTTP endpoint.
This qualification does not establish installation, provider START, original
parent consumption, idle Wake, or mission completion.
