# Native generation rollout candidate

## Decision and status

Use immutable native code generations for new controllers. Keep the incumbent
flat helper files unchanged while old controllers finish. Publish the reviewed
native source group once, resolve the selected generation once per invocation,
and execute its absolute code path. Share the original runtime state owners.

This directory is a local review candidate. Nothing here has been installed on
a native host. All modified code must come from the protected merged source
before the owning deployment operation publishes it. The source manifest is a
byte inventory, not merge approval or proof that any historical operation is
authorized.

The finite publisher, selector, and installer are artifact operations. They do
not acquire provider leases, create a worker queue, retry tasks, settle attempts,
kill processes, modify credentials, or run a persistent scheduler.

## Why a flat files-first install is unsafe

The existing flat `remote_sub.sh` freezes a `SUPPORT_FILES` list, hashes helper
files, and later reopens them during support transfer. Its broker lock is not
held over that interval. Replacing `sub.sh` or another helper between the hash
and transfer can send new code through an old dependency list. The old controller
also invokes its local helpers during settlement. Installing new modules first
does not protect either use.

The proposed native generation fixes these reads by keeping a complete code
directory immutable for the invocation. It does not hold the broker lock while
waiting for controllers. That would obstruct heartbeat and release operations.

## Artifacts

| Artifact | Purpose |
| --- | --- |
| `native_generation.py` | Explicit-manifest publication, verification, atomic selection, and one-time generation launcher |
| `native_install.py` | Prepare a review bundle; install pool/task bridges; later install the remote bridge; restore exact entry preimages on rollback |
| `../candidate/native_runtime_bindings.py` | Translate only declared generation aliases to their original owners before existing strict custody checks |
| `../candidate/` | Exact proposed caller changes and relocated incumbent pool dispatcher |
| `native-code-stage/` | Complete proposed native source group, assembled locally for review |
| `native-manifest.json` | Exact per-file hashes consumed by the native publisher |
| `native-source-inventory.json` | Each file's source, original installed preimage, proposed hash, and byte count |
| `native-preimages.json` | Fixed 75-file installed source inventory, without unrelated runtime metadata |
| `build_review_stage.py` | Rebuild the review stage from a fixed, explicit dependency list |

The baseline closure contains 72 Python/shell helpers plus the original `yes`
guard, `host_pull_probe.template`, and the relocated pool dispatcher: 75 files.
Eight additive helpers bring this proposed native generation to 83 files. No recursive
copy of the kit, arbitrary JSON files, credentials, historical packets, caches,
or old run artifacts is part of that source group.

The three apparent dependencies `lane2.py`, `qwen_review.py`, and `mm_feeder.sh`
were references in comments, not executable dependencies of the selected entry
points. `fabric_operator_recovery.py`, the hardcoded historical importer, is
excluded and unchanged. Existing fixed historical evidence and source-validator
paths remain external references owned by their existing code; their operations
are not invoked or reauthorized by this rollout.

## Code and state layout

Each native generation is an immutable directory under the existing kit:

`<kit>/native-code-releases/<digest>/`

It contains `pool`, `ext/`, `RELEASE.json`, and fixed links to existing owners.
The digest covers the exact source file hashes, state bindings, native schema,
and entrypoints. Code is mode `0555`, metadata `0444`, and the generation
directories `0555`. Verification checks membership, file kinds, modes, source
hashes, and exact symlink targets. The original `ext` and selected store must
have the expected owner; code-source symlinks are refused.

`CURRENT.json` is an atomic selection record. Selection uses compare-and-swap
against the exact previous generation. The launcher reads it once and executes
the verified real generation path. Running controllers do not reopen a mutable
`current/ext` location. Each launcher itself is a single sealed Python file
named by its content hash; it is atomically published before bridges use it.

The launcher removes the inherited `REMOTE_SUB_HERE` override after checking
that any explicit value agrees with the selected generation. Each selected
script derives its code directory from its absolute filename. Exporting that
override into a later explicitly legacy flat controller would recreate a mixed
source group, so it is not propagated.

### Fixed owner references

| Location | Original owner |
| --- | --- |
| `ext/active`, `ext/slots`, `ext/broker` | Existing physical admission and lease owners |
| `ext/state`, `ext/lanes` | Existing controller receipts, telemetry, output and recovery artifacts |
| `ext/hosts.json`, `ext/bailian_policy.json`, `ext/bailian_usage.json`, `ext/GROK_EXHAUSTED`, `ext/glm_window_state.json`, `ext/quota_cache.json`, `ext/glm_capabilities.json` | Original registry, policy, quota and usage state |
| `ext/lane_bin`, `ext/glm_shim`, `ext/go_shim` | Existing separately managed runtime helpers |
| `ext/codex_glm`, `ext/codex_go`, `ext/codex_minimax` | Existing Codex profiles |
| root `orch` | Existing routing/account policy, ledger and status owner |
| root `codex_bailian`, `minimax_claude_home`, `glm_claude_home`, `go_claude_home` | Existing dedicated provider profiles |

The publisher does not read or copy these targets. Dangling optional profile or
state references retain the incumbent missing-path behavior. External provider
CLIs, system interpreters, shims, and existing runtime services are separate
owners; the native code manifest does not claim to upgrade or freeze them.

Do not place `pools.yaml` inside a native generation's `ext`. The existing
`fabric_policy_snapshot.py` treats that placement as a remote support snapshot
and expects the remote support schema. Native code keeps reading the original
`../orch/fabric/pools.yaml` owner. Remote support publication continues to own
its existing immutable policy snapshot.

### Strict readers need an explicit binding seam

A raw symlink layout is insufficient. `glm_host_account_source.owned_bytes`
rejects a symlinked `hosts.json`, and `artifact_delivery.DirectoryChain` rejects
every symlink directory component. Both would correctly refuse generation
aliases without the proposed adapter.

`owner_path(path, code_here)` validates only a real sealed native generation:
its metadata digest, original owner, fixed alias table, and visible alias
targets. It substitutes the declared alias prefix with the exact original
owner prefix. It **does not resolve the remaining path or an arbitrary leaf**.
Existing `O_NOFOLLOW`, ownership, mode, and inode checks then operate on the
original path and still reject symlinks inside runtime state.

The operational changes are at `glm_host_account_source.owned_bytes`,
`artifact_delivery.local_file`, and `DirectoryChain.__init__`. The account
probe uses the same `owned_bytes`, and the controller launch-binding writer
uses the same `DirectoryChain`, so these are shared existing-owner seams.
The two historical prestart/preexec leaf readers apply the same mapping only
when loaded from a native generation. Their standalone transferred source does
not import a new helper unconditionally. No custody test or historical source
pin is weakened; changed recovery source may still be refused by its original
exact-source checks.

The separate quota-cache overlay canonicalizes only the default `CACHE_PATH`
before its atomic write, preserving the existing owner when a temporary file is
renamed into place. The root integration owns this source change and its real
cache-replacement test.

The remote `SUPPORT_FILES` and publisher now include `native_runtime_bindings.py`
as one new exact generation. The immediately preceding quota-continuity group
and every older recognized group remain accepted. The helper returns existing
paths unchanged for remote support and flat layouts. There is no import cycle.

## First-ever installation sequence

1. Review and merge the exact native source group, overlays, publisher and
   installer. Rebuild the manifest if any source byte changes. Verify the
   installed preimages against the recorded inventory before publication.
2. Publish the complete reviewed target generation. This may be V1 directly;
   there is no requirement to manufacture a relocated V0. Existing flat V0 code
   remains intact. Publication verifies all code before selection can expose it.
3. Run `prepare` to produce a concrete bootstrap bundle. It retains original
   pool/task/remote bytes, the three proposed bridges, code preimages and absent
   new-module names, interpreter/launcher identities, and a unique bootstrap
   epoch. Inspect this bundle as the reviewable installation result.
4. Run phase 1 through the existing deployment owner. It selects the reviewed
   initial generation, atomically publishes the launcher, and replaces only
   `pool` and the CLI branch of flat `fabric_task.py`. A partially completed
   phase 1 can be retried against the same verified plan.
5. New `pool run`, `pool remote`, other pool subcommands, and facade task CLI
   calls use the immutable generation. Importing flat `fabric_task.py` still
   exposes its original API body. Already-loaded old flat task parents continue
   to call the unchanged flat remote controller and helper closure.
6. The existing owner inventories the finite pre-bridge flat pool/task parents
   and any imported mutating callers. Let those parents finish and reconcile.
   Do not kill them, infer drainage from zero leases, or infer it from elapsed
   time. An old remote controller already running may continue to settle using
   its unchanged flat helpers; the phase-two concern is old producers that can
   still *launch* through the flat remote entry.
7. Bind the owner's reconciliation receipt to this plan/epoch and exact legacy
   producer identities. Phase 2 requires all inventoried producers settled and
   no unresolved imported mutating callers. The installer validates this record;
   it does not manufacture the inventory or adjudicate process effects.
8. Phase 2 atomically replaces flat `remote_sub.sh` with the generation bridge.
   Read back the entry hashes, generation selection, release hashes, and receipt.
   Only then claim the documented flat remote ingress has been upgraded.

Phase 1 is the activation boundary for standard pool commands and native task
CLI calls, including the existing Fabric facade adapter. The production facade
opts eligible commissions into quota continuation; raw pool runs retain their
existing single-run contract. Phase 2 retires the direct flat compatibility
ingress. It requires an actual complete owner record; the inspected broker,
operator and facade sources do not provide a global legacy-parent/importer
registry. Preserve the flat remote entry when that prerequisite is unproven.
The facade can advance after the phase-one selection and entrypoint readback
while those compatibility callers continue on their existing flat closure.

Direct raw flat helpers such as `sub.sh` and `lease_broker.py` remain legacy APIs.
The upgraded pool routes to their new generation counterparts. The rollout does
not claim that every raw helper path is upgraded.

## Paired launcher upgrade boundary

An already installed pool/task bridge is not another first installation.
`prepare` must continue to refuse an already bridged pool. Upgrading the sealed
launcher requires the retained original installation bundle and its exact
phase-one receipt, current paired ingress preimages, and a qualified target
closure. Do not edit the original plan, roll back and rebootstrap, overwrite a
sealed launcher, or infer a legacy-producer drain. The flat remote entry and
all flat helpers retain their existing bytes and owners.

During paired replacement, the existing selection must remain a generation
that both old and new launchers verify. Selection of a generation requiring
the new verifier follows successful readback of both upgraded bridges, through
the original publication lock and selection compare-and-swap. Interrupted
installation is reconciled using its exact retained upgrade identity and
observed bytes; it does not authorize a replacement operation or blind replay.

There is a bounded ingress availability limitation. A process that captured
the old bridge before replacement can reach its old immutable launcher after
the new selection. If that verifier cannot accept the new generation, it must
return a truthful refusal before executing the selected business entrypoint or
admitting work. Do not claim uninterrupted ingress, alter the old launcher,
invent an ingress census/fence, or trigger an automatic replacement/retry.
Already-pinned controllers continue through their original immutable paths;
their operations, roots, leases and retained results are unchanged. Fresh
upgraded entrypoints must verify the intended selected generation.

### Closed 8bc to d044 transition

The existing installer now has `prepare-upgrade` and `upgrade` commands. This
transition accepts only the authentic retained phase-one bootstrap bundle,
its exact owned receipt, the pinned 8bc launcher and derived paired bridges,
and the reviewed 95-member manifest
`6ac208bbd80f706931b11e8147a879f6e3ced6fe704cde7b9f15e1c098e37ee4`.
The new sealed d044 launcher differs only by the two reviewed PyYAML artifact
allowlist names. Neither the original bootstrap plan nor the flat remote entry
is rewritten.

After publishing and verifying that protected closure, run the protected
installer's `prepare-upgrade --original-bundle <retained-bootstrap-bundle>
--target-generation <published-digest> --output <fresh-external-bundle>`.
Review its exact captured selection and ingress preimages, then invoke
`upgrade --bundle <same-external-bundle>`. These are source command forms,
not evidence of an installed upgrade. `prepare` remains inappropriate for an
already bridged installation.

The original publication lock serializes the finite operation. A durable
intent inside the existing bootstrap artifact directory binds the exact
upgrade plan before any bridge write. Each replacement requires the original
or this transaction's exact new bytes; foreign bytes refuse. Both bridges
must read back successfully before CURRENT advances from the full captured
selection. Six tested interruption edges recover only this same retained
transaction, including a committed pointer with a missing completion receipt.
At that selected edge the exact sealed launcher and both bridges must already
exist; only the missing receipt may be written. Their loss or alteration is an
inconsistent state that refuses without repair. A completed invocation performs
no writes. The receipt has no clock, nonce, fresh authority or external issuance:
its full bytes derive from the retained plan digest, original bootstrap digest,
exact previous/selected pointer and fixed bridged/legacy disposition. Thus loss
after issuance can restore only that identical original receipt, never a new
terminal identity or target effect. A changed selection, foreign
intent, conflicting receipt or unrecognized partial state cannot be repaired
or reactivated by this command. There is no automatic replacement or retry
of a refused business operation. No quiescence, legacy drain, provider
readiness or absence of unknown work is inferred.

## Rollback and failure handling

Rollback restores only the exact original ingress bytes, child ingress first;
it does not move or replay attempts, delete generations, alter state, or kill
processes. Existing generation controllers keep their pinned files. Rollback is
terminal for that bootstrap epoch. Reinstallation requires a fresh prepared
epoch and fresh legacy-parent reconciliation, preventing reuse of an earlier
empty/settled census after new legacy parents have started.

Generation selection can also be rolled back for future calls by an exact
compare-and-swap. It is never a claim that a running attempt resumed on another
model. Old generations are retained; this candidate contains no TTL cleanup.

The artifact lock is independent of provider/physical admission. It is acquired
without waiting indefinitely and is never used to block broker heartbeat or
release. Unknown source changes, incomplete declared files, conflicting ingress
preimages, malformed selection, changed bindings, and unsealed publication
identities fail closed. A final generation whose sealing failed is retained as
unusable rather than silently repaired or selected.

## Offline verification and the remaining host proof

The suite exercises real subprocess pauses across the original hash/copy seam,
an old flat parent crossing phase 1, two immutable generations overlapping,
interrupted phase-one installation, interruption before launcher publication,
source tampering/missing files/symlinks, exact rollback, and stale reconciliation
after rollback. Real account-reader tests verify original-owner reads and reject
both owner-leaf and state-internal symlinks. Historical reader tests read only
dummy local fixture data. Remote publication tests import the actual adapter
from the sealed new support group and preserve the preceding group.

Run the suite with:

```sh
python3 -m unittest discover -s rollout -p 'test_*.py' -v
```

The container has world-writable `/tmp` and `/workspace` ancestors. The unchanged
full `DirectoryChain` correctly refuses those paths, so that one integration
proof skips locally. On the native host, set `NATIVE_ROLLOUT_TEST_ROOT` to a
fresh owned `0700` fixture parent under a trusted home path and run the same
suite. The test then exercises the real directory traversal without modifying
or mocking its custody checks. It writes only temporary dummy code and state.

`python3 rollout/build_review_stage.py --output <artifact-directory>` rebuilds
the stage and both source manifests from the fixed source list and committed
preimages. When deploying, run that builder from the actual merged release and
write its artifacts outside the immutable release. No recursive runtime copy or
working-tree source can enter publication through this construction.

The parent integration separately owns the real provider-wrapper rejection/
success/denial fixture, protected source merge, facade runtime release, live
source readback, finite legacy-parent census, and final deployment receipts.
This handoff alone does not assert those operations are complete.


## Forward plain collection and current Git observation (source qualification)

These are separate consumers of the existing transport and original state owners.
Neither is installed or live from this source publication.

New ordinary non-operator GLM/Qwen plain requests retain the exact transported
packet in the existing request store. After observed acquisition, the controller
reads back the remote packet and complete immutable support manifest/files, then
fsyncs their bound prelaunch record before the first worker launch. The existing
original-delivery collector requires that evidence and its ordering, original
root/parent/run/host and acquisition witness. A lost foreground handle can then
return the original bytes without changing controller/lifecycle truth, releasing
a lease, accepting work, authorizing cleanup or permitting a replay. Older runs
without this producer contract remain refused; fixed historical scopes are unchanged.

The additive `current-source` command composes the native invocation owner, existing
host registry/strict host-key SSH transport, generated Git reader and exclusive
receiver-bound publication. It does not recover a historical run. The owning OS
principal and its current external commission/tool/resource permission authorize
the invocation. Request labels, the environment observer correlation and typed
invocation are not credentials or proof of that external permission. The route is unavailable until its qualified immutable generation is installed and
selected. Registry registration binds the lane host and strict-SSH alias; provider
`allowed_modes` retain their existing enum and grant no source-read authority. This
change installs no grant, signer, source-custody registry or generic issuer. The
caller must already hold permission for the declared host/custody and receiver.

A request binds `schema=mastermind.fabric_current_source_request.v1`, `run_id`,
`root`, current `observer`, distinct `receiver`, registered `host`, exact absolute
`worktree`, `git_dir`, `common_dir`, lowercase 40-hex `commit`, finite `sources`
(entries with `path`, optional exact `blob` and `size`), and bounded `limits`
(`max_file_bytes`, `max_bytes_total`, `deadline_ms`). `historical` is optional opaque
reference only. Every field is included in the request digest. A real linked
worktree must declare its gitdir/common-dir pointers and backlink exactly.

The additive custody-resolution request variant replaces both `git_dir` and
`common_dir` with `custody={"mode":"worktree_pointer_graph","boundary":...}`.
The boundary is an exact absolute, non-root resource selector which strictly
contains the selected worktree. It carries no authority beyond the caller's
current scoped commission and tool/resource permission. Mixed or incomplete
variants refuse. This mode reads only the selected worktree's `.git`, the
resolved gitdir's `commondir`, and its `gitdir` backlink. Ordinary repositories
resolve to `worktree/.git`; linked repositories must prove the standard
`common_dir/worktrees/<id>` relationship and the backlink to the selected
`worktree/.git` before object access. Every resolved path must remain inside
the declared boundary and pass the existing FD, ownership, mode and no-follow
checks. It does not search for repositories or infer custody from a host label.

The returned resolution records actual custody and bounded pointer evidence,
bound to the original request digest. The receiving composition independently
checks the pointer relationships before publication. Pointer bytes and identities
are revalidated around capture; a changed graph refuses without partial source
delivery. The explicit triple variant remains supported. Neither variant proves
current worktree cleanliness or reads an index or working source files.

The receipt delivers raw commit/tree objects and selected blob bytes as base64,
with Git identities and path membership independently revalidated locally. With
an empty `sources` list it proves the commit and its root tree only; it is not a
complete source snapshot or history bundle. Up to eight finite paths may be
requested; further objects, parent history, full-tree closure and worktree
cleanliness are not claimed. This route is enough to deliver selected pinned
source bytes, not a blanket assertion that an unknown target is currently clean.
No PNG or working-file/census export is implemented. Loose Git objects use bounded
raw reads. Packed reads require Linux's enforced 512 MiB address-space cap plus
bounded stdout/stderr and whole-request deadlines; unsupported platforms refuse.
Alternates, unsafe/promisor packs, symlink custody, changed objects, unknown fields,
wrong binding, duplicate or interrupted destination publication all refuse.

Proposed invocation **after protected merge, qualified generation rollout and
current effect admission** (not an available installed recovery command):

```sh
python3 <kit>/ext/fabric_task.py current-source --request <owned-request.json> --destination <new-evidence-directory>
```

The request must name the actual current observer and separately authorized
receiver; historical `WS:MARKET-OS` labels cannot supply ancestry or admission.
For target commit `9704aa8e358d2cf8440e293a30a09a24be9038b2`, neither source
custody nor bytes have been observed by this qualification. Existing published
images do not require this Git route.

Relative to the prior qualified current-source generation, custody resolution
changes only `current_source_observation.py` and its native `fabric_task.py`
owner wiring. It uses the same transport and publication route; no new command,
host probe, registry or lifecycle is installed. Its complete 83-file closure must
still be rebuilt and published from protected merged source, then selected with
the existing fresh-predecessor CAS. A source PR or candidate invocation is not
permission to install or execute that route.

The smallest combined immutable-generation delta is the three plain producer/collector
files, the additive observation module, and its narrow `fabric_task.py` and
`artifact_delivery.py` wiring; the explicit stage/inventory includes their exact
closure. Existing controllers keep their original immutable generation paths and
flat compatibility helpers remain unchanged. Publication must use protected merged
bytes. Read and retain a fresh `CURRENT.json` generation and sequence at the owning
rollout boundary. The incumbent selector takes `--expect <prior-generation>`
(or `absent` for a genuinely unselected store), verifies that exact generation
under its publication lock and increments the observed sequence. Its API does
not accept a caller-bound sequence comparison; this source does not claim a
two-field CAS or add one. Never substitute a stale observed generation or force
selection. Installation, installed-route/host qualification, current scoped
permission and target proof remain separate owner operations; this PR performs none.


Protected Qwen priority integration retains all four PR1731 candidate files byte-exact.
The canonical builder still verifies all nine accepted Grok overlay bases; six are
staged directly and exactly three closed forward candidate hashes preserve the
previously reviewed fresh-usage reader and caller UTC narrowing. The other91
member bytes equal the accepted7efa closure. The finite upgrade target now pins
the resulting95-member manifest6ac208bb; launcher8bc-to-d044, original epoch,
preimages, intent, lock, CAS and receipt-only recovery behavior are unchanged.


### Hook-free physical diagnostic (prospective source capability)

`host_pull.sh --diagnose-physical ubuntu0` is an exclusive one-shot through the
existing fixed selected target and transport, with strict host-key verification
and no host-key updates. It skips HOST_ENV and all account-readiness/config
loading. It returns closed JSON marked DIAGNOSTIC_ONLY, published=false and
readiness=NOT_REQUESTED; it never writes host snapshots or starts/restarts a
daemon. Consequently an old flat daemon cannot replace this invocation's result,
and the result is not a host-picker or broker admission input.

The incumbent remote lane_runtime.py must be a held, no-follow, bounded, owned
regular file identical to the selected release before its existing --occupancy
CLI is executed from those held bytes. Mismatch/refusal or failed transport is
unavailable, not spare capacity. Other physical measurements remain the existing
template observations, including UNKNOWN occupancy where the existing census
cannot establish it. Account/launcher configuration equivalence remains separate.

Source review and protected publication do not authorize installation, selection
or a remote diagnostic invocation. A prospective consumer must first qualify
actual selected closure, exact registry/target/key policy and producer identity,
then consume only that original invocation's detached result. Lost or ambiguous
response is not permission to replay. No normal refresh or hook execution is
implied by this capability.


## 2026-11-07: original-artifact and admission-load repairs

Operation: `fabric-admission-integrity-20261107-sol-001`, isolated attended Web
workspace, based on protected `615146aac6a1b0c0933bc9b815517a2fd285ed4a`.
Governing source pin remains compatible
`e63d8acaebe0d3cee1ce7cfb8d85294bf0c57f46`.
This continues P3/P7 of the existing
[Hermes/Fabric convergence plan](../../../../docs/superpowers/plans/2026-10-24-meta-ceo-open-harness-convergence-masterplan.md).
Direct principal implementation is the bounded `CRITICAL_PATH_SHORTCUT` join;
this Web session has no verified authenticated native root/parent binding for
paid worker admission. Adapter availability is not worker-start proof.

Two reproduced defects are repaired through their existing owners:

- A request interruption after packet fsync and before descriptor publication
  left the original run occupied, while status returned `NOT_FOUND`. The
  original reader now checks the same fixed packet/result artifacts used by
  the request duplicate guard. Retained or unreadable evidence returns existing
  `STATUS_UNREADABLE` / `ARTIFACT_UNVERIFIED` vocabulary. It supplies no root
  attestation, result contents, execution-absence proof or replay authority.
  Truly absent artifacts still return `NOT_FOUND`.
- Both the current native lane and the packaged attended backend sampled live
  load before waiting for the physical admission lock. They now take the
  default sample under that lock immediately before the existing admission
  decision. Explicit fixture load, slot limits, resource floors, original lease
  custody and release protocol are preserved.

### Exact source and closure

| Current source | SHA256 |
| --- | --- |
| Native `fabric_task.py` | `1bdec660216cd3218d46c5740eee7d4f24a74c3f2dc23b61083dfc503c9d1d68` |
| Native `lane_runtime.py` | `b0f8c77af1ddd1eab7b1bd5b3188e6a15f79ceac5a80cbdcdb65c9998a2bce6b` |
| Packaged attended `lane_runtime.py` | `764d140d598734d3607f697bea911c873d72ede08331308347d45a8f9451a996` |

The native builder accepts the repaired members only as one complete successor
of parent manifest
`815ec3c880b5f66590b7dcc04ac42c6c5384ba296b44e83af7e96c23326f6347`.
It checks the entire captured parent closure, not independently allowlisted
member combinations. Historical validation uses a temporary inverse view;
emitted manifests and inventories retain the actual repaired hashes.
Historical inputs and their transformation pins are unchanged.

| Built variant | Members | Manifest SHA256 |
| --- | ---: | --- |
| Native base | 107 | `8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6` |
| Existing Go application extension | 109 | `2ef78df1ba17579339e3d86733bfb48343f5bba156e9a16108f31b7539acf571` |
| Existing HTTP extension | 112 | `efb5ffc514dbd9a2fa3df44aab9e869ef544e36d4fbbb1b0651713c0ee1404fd` |

Native forward fixture:
`tests/fixtures/fabric-native-admission-integrity-20261107.patch`,
SHA256 `68c1abf049ee9e4c04fc749eebb9a4b99ba71a71c22945e0f5d02bc8fe107753`.
Packaged forward fixture:
`tests/fixtures/fabric-bound-admission-load-20261107.patch`,
SHA256 `d42895edd9d2e8507e402ab7a98a854486f5d7b466e2735da219180514a18cc0`.
Both reconstruct the exact prior bytes in reverse and the current bytes forward.
The packaged provenance records its distinct parent. Its existing identity
literal locations and spellings are unchanged; the current whole-file source
pin is qualified by the identity suite.

### Observed qualification

- Original packet crash test failed before the repair with `NOT_FOUND`.
- Separate-process load tests failed against both original runtime copies:
  after waiting for the lock, they admitted using the stale `0.0` sample.
- Native request, physical admission and exact identity qualification:
  **204 passed, 8 subtests passed**. The admission cases cover rising and falling
  load while locked, the explicit-load seam, and two contenders for one slot.
  The winner remains held until both admission decisions are observed.
- Native generation qualification: **83 passed**, including real 107/109/112
  builds, exact forward/reverse source reconstruction, retained historical
  generations, and partial/foreign/backdated/changed-parent rejection.
- Existing MCP facade suite: **70 passed**. Two fresh backend instances both
  refuse the orphan original run after a status read; neither dispatches.
- The broader security-composition run on the M2 was **35 passed, 32 failed**.
  The first failure was the existing sparse-donor Git observation refusing as
  unqualified; this run is not green and its cause is not inferred as a repaired
  behavior. Required hosted Linux checks remain owed.
- `git diff --check` passes. No provider, live worker or host admission is
  established by these inert fixtures.

### Existing application carrier consumption

[PR #2175](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2175)
remains the APPLICATION final carrier; its captured head for this analysis is
`39f4b50bcb3840f5b254dbcd753f3f1f5fc8a7cf`. This independent native repair does not
replace or modify that operation's branch/workspace, nor absorb the separate
policy-publisher change in #2182.

At #2175's next integration boundary, consume this complete protected successor
on that original branch. Preserve its five-member APPLICATION cohort and
original historical parent. Its whole-manifest base check must explicitly
compose the exact two-member repair successor; merely merging leaf bytes,
repinning historical inputs, or allowing arbitrary "current" hashes is invalid.
Regenerate the actual final inventory and rerun its 107/109/112 and mixed-cohort
qualification against the resulting head.

### Acceptance still owed

Protected merge and installation are separate. Rebuild from the merged source,
then use the existing immutable-generation publisher/selector and exact fresh
predecessor comparison. Preserve live writers, retained unknown effects and
all operation-specific holds. Observe the installed selected generation and
the original reader/physical admission behavior before claiming runtime repair.
The packaged attended backend retains its existing enrollment boundary.

These repairs neither establish a measured 99% useful-task SLO nor guarantee
that a host can never fill. They prevent two concrete unsafe decisions while
preserving finite capacity and conservative recovery.


### CI current-manifest reconciliation — 2026-11-07

The first hosted run, 42339309433 at source a6c849d76d5c16d3853e9a70cf16486872c7d11d, exposed stale current-manifest assertions in catalog staging, host-pull admission, and the paid initializer. The native manual-AUTO historical reconstruction also still began at the prerepair task. The related current-generation source-closure assertion was found by a bounded source scan and corrected with the same complete current manifest.

Only current qualification pins now identify the actual repaired 107-member manifest 8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6 and lane b0f8c77af1ddd1eab7b1bd5b3188e6a15f79ceac5a80cbdcdb65c9998a2bce6b. The historical manual-AUTO test first inverses the hash-bound forward repair in its disposable stage, proves the exact 2d66d51376b4bfd9740947988777809ee53c0314d7155ad2bd73c9a9ec44b7e4 predecessor, and retains every older fixture and hash unchanged.

Focused verification of all five affected qualification files passed (process 92160, terminal exit 0). The actual runtime repair, repaired release output, installer history, security floors, and production selector are unchanged. A fresh hosted run at the successor commit remains required; the earlier failing run is not delivery proof.

Deployment constraint: the observed live 107-member generation ef94479b8c768088e7c6b611d498879b9b6896ba24faa2558135ad8465f8be46, sequence 35, has complete manifest 3ad8c6993609b17378c2c248c73fffc210a71754078d3a6bbb71cfaa6e7018c9. It contains eight other component successors that this protected107 source baseline does not contain. Do not select this baseline over it. The original APPLICATION composer #2175 must preserve those bytes and qualify the two repaired members against that complete parent before existing publication/selection. No live release was published or selected in this work.


### Protected merge-queue translation qualification — 2026-11-07

PR CI 42341854901 at 3b2338d3946209b6f6ce6a0b694cf609015fb07f passed all six repository shards and required test. Its original protected queue then composed protected 5f8c13da926011fb5fdc8cea21287b532ac968db at merge candidate 490ad30a9ed88c6133bd87d2deefd921e2a3e9a7. Queue CI 42345135020 failed only the actual Brain composition gate: the translation fixture still pinned the prior provider-realm module. The original queue entry was reconciled absent before any resubmission.

The same native repair now incorporates that protected source. The translation fixture pins the complete actual control_plane/codex_provider_realm.py blob a51e2bce8d9bb312107f975d503abd6541bd5000. The protected delta adds the closed candidate-only commercial realm and rejects invalid use-policy flag combinations; it does not enroll an account or destination. All exact-source checks remain in place, and all 15 native translation pins remain unchanged.

The required translation consumer suite passed all 23 cases in an isolated copy of the actual CI archive paths, paired with exact Macro f0375acf4ba076718e7cb420ed28ab61fb0a4f26. This executes the real owner, HTTP, admission, cache-lock, durable replacement, usage and close paths with synthetic provider observations. Source-capture SHA256: bf37f2383d38f608df5227ffd7b72c4f61e7f3d8162941c7274328bd6073bc59. Test-log SHA256: d21549e9dd8928fb20e680c3f2a80781e3f8831f0a4553ee6f8490a58e03712a. The isolated proof interpreter used claude-agent-sdk 0.2.179, matching the version resolved by the observed hosted CI installation.

A separate 53-case realm/readiness run had 52 passes and one failure: the M2-installed Codex binary hashes to 8813367285524ac798dd96d1b071aea30d58708c7226fd236cd275cf1cfdee31 while the existing readiness pin expects 16593cc2f422d5f398a8e40f550ebbaf1245392528957be342c295920a300704. That failed local installed-harness check is retained; neither the readiness pin nor the installed binary was changed. Its log SHA256 is 694bc8f1b0618d7e71ea60c694c131727aa24750822423d61fe6d0a2f8d3e578. It does not invalidate the independent inert translation proof or establish live harness readiness.

The native release remains the repaired 8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6 manifest. The prohibition on selecting this baseline over installed sequence 35 remains. The APPLICATION composition is carried by original #2175, with the bounded #2194 contribution retaining the accepted scoped-model source and exact parent closures. No release selector, host admission, provider enrollment or unknown effect changed. Fresh exact-head required CI and protected queue proof remain the source-delivery gate.

### Protected historical-realm fixture join — 2026-11-07

The original queue entry was removed by the GitHub merge-queue bot at08:45:46 (event35423056040). Its removal reason was not inferred from that event. A fresh source merge preview independently found exactly one conflict against protected547a880894b0f3d28a6d5118ee2534287b3fc1c0, in the translation fixture. The protected change correctly pins the historical realm preimage consumed by application_http_sources instead of the unrelated current realm module. This merge consumes that complete test file byte-identically (blobb3e00e1c3d507dc276f0f24d40e0665448f1e18a); no source pin is weakened or bypassed. Governing source law is unchanged.

The actual composed source was paired with exact Macro9eb5cb6b28b510ea9e2bf05ae9040528523339df in isolated source fixtures. The first export omitted scripts/translate_all.py and retained22 passes/one error. Adding that exact staged-tree input (blob117dc03971230945fcf50816447f7e6a2e651a5a) resolved the fixture gap. The complete23-case translation suite then passed, exit0, log SHA256 ea509ad0367a2a748ffd43b65f9a68042344e1be3ecea84774c6b5a9c831dd0b. Failed and successful exports are separate receipts in review_evidence/fabric_admission/protected-translation-20261107.json.

The repaired native sources and manifest are unchanged from0a41; its retained installed APPLICATION generation constraint remains binding. No installed Codex or provider was invoked. New exact-head hosted CI and the normal protected queue remain required; the prior removed queue request is not treated as an active effect.


## 2026-11-07: no-replay CI settlement boundary

Required CI run `42359846449`, shard4 job `128365751637`, exposed an inherited race in `test_signed_consumed_parent_second_turn_original_read_and_no_replay`: its duplicate-turn event snapshot preceded the original dispatcher appending `JOB_COMPLETED` for `JOB-002`. The duplicate returned the correct original result; the test already awaited that original task later. The same test and turn owner bytes exist in protected `064a08b2c6360ece12999f1d7f2d712062ea0636` and the passing workspace-release shard.

Moved the existing bounded original-task wait before the event snapshot. Full event-log equality and the exact two native turns remain required; no production path or assertion was loosened. The complete12-case turn file passed with zero failures/errors/skips. Evidence: `review_evidence/fabric_admission/turn-settlement-ci-20261107.json`. The native manifest remains the previously qualified WORKER107 identity and must not replace the larger APPLICATION installed generation.

### Combined host-pull source image — 2026-11-07 (#1836)

The host-pull composition advances the ordinary current source image from
`8af7302990d7e77112457090767265d7eb43a4f544ec533bf9b517c5eb6c35c6`
to
`a42259df6aa9dc910abd3e6eacb75f30b9089663d569c88f946f965bc8ceedd3`.
The existing builder emitted 107 members, 75 baseline files and 3,089,380
payload bytes. Its source-inventory SHA256 is
`553b24be3cbb9523d618ebdbfd95421b39dc9ef5783cff0946404dba5787c298`.

Only `ext/host_pull.sh`, `ext/host_pull_backend.py` and
`ext/host_pull_daemon.sh` change in that manifest and inventory. All other
member hashes, metadata and installed-preimage identities remain intact.
The builder validates one exact three-member inverse against the complete
8af730 parent, then uses the unchanged 815ec admission-parent guard; emitted
metadata continues to identify the actual repaired bytes. The historical
95-member upgrade and 6ac208 manifest are unchanged.

The earlier variant table and dated CI records above describe their original
source epochs. Their 8af730 identity remains historical predecessor authority;
it must not be globally replaced with the new current identity. Current
qualification consumers bind the generated a42259 manifest. The catalog and
paid-initializer expectations each require only that current-pin correction:
the initializer's historical comparison still has 95 original members,
12 additions, 36 changed common members and 59 unchanged original members.

The three historical host-pull payloads are retained as authenticated fixture
data for the old 102-member stage. Current Go tests first normalize the
validated host epoch before exercising the older admission inverse. Hosted
native preflight job 128415654001 in workflow 42376687583 passed these consumers;
that run's ordinary shard 5 subsequently identified the two stale current-pin
assertions above. This records the distinct results and does not claim the
full workflow passed.

The combined-image technical source review covers the unchanged production
composition. Source qualification and a protected merge do not authorize an
installed generation, CURRENT change, launchctl action, H1 admission, provider
or worker start. Existing APPLICATION #2175 composition and enrollment
constraints remain separate; no installed generation was replaced or selected.
