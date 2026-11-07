# Preserve provider plans when adding native APPLICATION ingress

This is a closed source composition inside the incumbent native stage builder
and installer. It adds no queue, store, selector, retry owner or runtime daemon.

## Source decision

The existing provider-plan profile contains a complete 116-file postimage. The
previous default APPLICATION base has 107 files; its Go and HTTP variants have
109 and 112 files. Validating those releases independently was insufficient:
both the intact-history and retained-history installers could prepare a move
from the provider postimage to a legacy APPLICATION target, dropping provider
members. The two real-owner regressions reproduced that behavior before this
change.

`composition.json` is bound by the builder's full-file SHA256. It commits the
exact 107-file APPLICATION parent, unchanged historical provider profile,
reviewed patches, existing source additions and complete 116-file combined
postimage. The historical `provider_plans/compose.py`, its profile and its
seq36-to-seq37 provenance remain unchanged.

Six shared files receive exact patches. `pick.py`, `remote_sub.sh`, `slot.py`
and `sub.sh` retain the provider postimages. `fabric_task.py` retains that
provider implementation plus the newer missing-log/orphan-artifact custody
checks. `lease_broker.py` retains current APPLICATION v3 and SQL custody and
restores only the 17-line provider eligibility branch. Nine existing provider
sources are included by exact hash. The other 101 APPLICATION members retain
their literal bytes, including the current host-pull, gateway, collector,
physical-readiness, sparse-source and diagnostic owners.

Provider routing remains WORKER routing. No BytePlus or Experiential pool is
added to the APPLICATION catalogue, and no account, grant or entitlement is
created by this composition.

## Build variants

The builder's defaults are unchanged. Add
`--include-provider-plan-application` to request the closed combined source:

| Flags in addition to the provider flag | Files | Purpose |
| --- | ---: | --- |
| None | 116 | Combined source base |
| `--include-go-application` | 118 | Existing native Go entry and handler |
| `--include-go-application --include-application-http` | 121 | Existing Go and fixed HTTP transport closure |

Example source-only build:

```sh
python ops/native_fabric/quota_continuity/rollout/build_review_stage.py \
  --output /tmp/reviewed-provider-application \
  --include-provider-plan-application \
  --include-go-application --include-application-http
```

The builder verifies the full APPLICATION parent, applies pinned patch bytes to
copied preimages in an isolated temporary directory, verifies all postimages,
and only then writes the reviewed stage. Inventory rows identify patch source,
patch hash, original source and composition preimage separately from historical
installed preimages. Building does not publish, select, install or start it.

The external Go component keeps `dependencies` as its original candidate-source
commitment. `native_stage_dependencies` names the actual combined broker bytes.
Both component owners derive this same closed relation. The installer still
hashes every captured payload; passing the historical broker hash as the staged
dependency is refused.

## Existing transaction owners

Both `_go_plan()` and `_retained_go_plan()` call the same pure transition guard
on their already-verified before/after releases. The complete selected provider
profile is required for either combined Go target. Provider-bearing partial,
changed or mixed predecessors cannot fall through to a legacy target. A
provider predecessor cannot consume a 109/112-file target, and a legacy
predecessor cannot consume a combined target.

The guard checks the frozen `expected_selection` pair, not a fresh independent
CURRENT lookup. Existing apply/reconcile code remains the sole mutation owner:
it verifies source and bridges under its publication lock, rechecks the complete
selection pointer, preserves Studio consumer fences and recovers the original
transaction after an interrupted commit. Completed replay makes no second
selection or write. A changed sequence on the same generation refuses a stale
plan.

The source guard matches the complete reviewed file map, not a hard-coded live
sequence or generation address. Actual generation identity also binds its owner
paths. Installation still requires verified live payloads, locked CURRENT
revalidation, protected source and the original release/effect owner's fences.
A metadata observation of sequence 37 is not live byte verification.

## Qualification

The source report is
`review_evidence/fabric_application/provider-application-transition-20261107.json`.
It records the failing baseline, exact builds and succeeding proof boundaries.
The existing stage suite and new downgrade regressions passed 193 cases; both
installer paths and new transition/recovery cases passed 82 cases. The actual
combined stage passed the existing 21 provider AUTO cases and six local-return
cases. A fresh process reuses the unchanged ten APPLICATION v3 custody tests
and four original-artifact uncertainty tests against hash-verified combined
bytes. The external handler is copied under the fixture's historical
`go_shim.py` name with the identical staged digest.

These tests use disposable owners, synthetic grants and controlled transport.
They prove source and transaction behavior, not installed account admission,
provider usage, production availability or learning effectiveness. The incumbent
CI workflows now include the transition tests and the actual combined-stage
provider consumer. Protected delivery and the first admitted Secretary journey
remain with their existing owners.
