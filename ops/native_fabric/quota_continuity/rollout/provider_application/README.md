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

For the provider-only variant, the external Go component keeps `dependencies`
as its original candidate-source commitment. `native_stage_dependencies` names
the actual combined broker bytes. Both component owners derive this same closed
relation. The installer still hashes every captured payload; passing the
historical broker hash as the staged dependency is refused.

## Compose quota recovery with provider preservation

Add `--include-quota-reset-recovery` to the same provider build to include the
completed H2 quota-recovery source. The file counts remain 116, 118 and 121.
The builder first creates the exact provider/APPLICATION parent, then applies
the existing H2 four-member overlay to its exact preimages. The historical
H2-only 107/109/112 family and provider-only family retain their own identities.

The combined base manifest is
`b49e1350b83afd4f2c439e7b13b2b7079a4db88dd7d9d6b0cf9801c423f29547`.
Its inverse must reconstruct the entire provider parent
`f256ac145cbf66c5b325d8f8d1cbe5d5e096646b2796bbe05efb45d6fb21dfd4`
before the existing provider inverse may run. This rejects a partial quartet,
the historical H2 broker/picker mixed with provider members, or a foreign parent.
It does not add the provider parent to the historical H2 allowlist.

The new broker and picker retain both provider admission and H2 recovery:

| Member | Provider preimage | Combined H2 postimage |
| --- | --- | --- |
| `lease_broker.py` | `05880dc3e6f0849ff1f39094e2dbfe778797ebaddc04acd3b7474598888ca4cd` | `3a210b259681460ec1e8ded91c45f84f6807e6ba4da1704b1ce587693d6531ed` |
| `pick.py` | `37c8809c1fbb7106f98f133347efe20524dbaec176122ed5ad40dbf244fa04b3` | `a61e4bd966cb3ce94cb00c262170453840edea02c4eb4d42b1521d097476a1dc` |

The existing H2 remote/circuit replacements are unchanged. The task, all nine
provider additions and every other base member retain their provider-variant
bytes. Incoming `native_go_entry.py` retains its authenticated quota reader and
GLM key reader preloads.

For this combined variant, the existing dependency record describes the final
broker and nests both exact patch steps. Its `provider_preimage` records the
original candidate, provider patch and intermediate provider postimage; its
outer composition records the H2 patch and final bytes. The source inventory
uses the same provenance. Both ordinary and retained installers authenticate
this full record and the actual payload before preparing the original Go
transaction. No live selection, new transaction, or replacement recovery owner
is introduced by composing these sources.

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

The initial provider-only source report is
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

The joined provider-plus-H2 qualification is recorded separately in
`review_evidence/fabric_application/provider-quota-joined-composition-20261107.json`.
Its fixtures exercise both existing installer owners, interrupted selection and
receipt recovery, sealed quota-reader loading, mixed-cohort refusal, the original
GLM claim/settlement cases, and APPLICATION v3/artifact custody on the actual
emitted source. Existing CI owners run these tests and both provider consumers.

## Preserve the selected remote-placement provider family

The opt-in --include-provider-plan-remote-placement composes the exact
protected current116-remote-placement provider family with APPLICATION.
It requires --include-provider-plan-application and keeps the existing
116/118/121 member counts. The live sequence-39 observation motivated this
source join; acceptance depends on the complete file map, not sequence 39
alone.

The selected provider picker is
f6f62ba50502ed337598f21de94606f3a6c51ba1e4942765548bdffbe1edb019.
The source-owned remote-placement.json authenticates the unchanged original
APPLICATION composition, the protected provider profile and its exact forward
patch. The builder first verifies the complete original combined parent, then
applies that patch to a copied picker and verifies the entire new postimage.
Every other payload remains byte-identical to its corresponding existing
provider/APPLICATION variant. The inventory retains both composition steps
and their distinct source, intermediate and installed preimages.

| Variant with both provider flags | Members | Manifest SHA256 |
| --- | ---: | --- |
| Base | 116 | 75ad0d9aad8361de2b2d11734f90b2f08906f6a731062393f0b10f0eb29a4819 |
| Go APPLICATION | 118 | 0784394d60fbc858729dd64cd2877826c229cf471d82eaf3631fca51357f3cad |
| Go APPLICATION plus HTTP | 121 | be0143144b8da556fc7b83690da1ff68e9bd4e67d9e8f4a16483621be0258cef |

Both existing installer paths require the complete remote-placement provider
predecessor and a complete matching APPLICATION target. They reject a picker
rollback, an unqualified older provider predecessor, a partial or changed map,
and a mixed target. The inverse authenticates the complete input before
normalizing a copy for the unchanged original guard. The caller's map is never
modified.

Example source-only HTTP build:

    python ops/native_fabric/quota_continuity/rollout/build_review_stage.py \
      --output /tmp/reviewed-remote-provider-application \
      --include-provider-plan-application \
      --include-provider-plan-remote-placement \
      --include-go-application --include-application-http

This option cannot be combined with --include-quota-reset-recovery: the
existing H2 composition changes the same picker and has its own exact source
family. The builder refuses that unqualified pair before preparing output.
Existing default and H2 families retain their original bytes and identities.

Installation uses the intended complete 118- or 121-member target in the
original Go transaction. Selecting the 116-member base first does not qualify
a later Go transition. Actual protected release, original installer-bundle
custody, full current native selection and account/grant eligibility remain
required. Building and disposable-owner tests do not activate a live service.
