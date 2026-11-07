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


### Admission repair on the active APPLICATION carrier — 2026-11-07

This isolated dependent contribution targets the existing #2175 branch at 312be66141bf58c564a11818d63ddd3f958ca0c0. It consumes the exact repair source of #2187 at 3b2338d3946209b6f6ce6a0b694cf609015fb07f, without importing unrelated protected changes into the active branch. #2175 remains the sole final APPLICATION composition carrier. Its live workspace and branch were not changed.

The installed APPLICATION parent has 107-member manifest 3ad8c6993609b17378c2c248c73fffc210a71754078d3a6bbb71cfaa6e7018c9. The current repaired source differs in exactly ext/fabric_task.py and ext/lane_runtime.py. All 105 other entries, including the eight additional APPLICATION component successors absent from the independent WORKER baseline, remain identical.

The existing builder first qualifies and inverses the exact repaired pair against one of two explicit whole parents: the original WORKER 815ec3c880b5f66590b7dcc04ac42c6c5384ba296b44e83af7e96c23326f6347 or the complete APPLICATION 3ad8c6993609b17378c2c248c73fffc210a71754078d3a6bbb71cfaa6e7018c9 with its exact five-member carrier cohort. Its existing APPLICATION inverse then requires e43384b1bfdae31d694f6771455dc32681241c80ec18e7747e364351fe3d92f4, followed by the existing Go historical and dependency checks. Neither the captured dependency map nor the three APPLICATION dependency members are normalized. Both main and Go validation use this same ordering; published manifests and inventories retain actual repaired bytes.

Actual builder receipts:

| Variant | Members | Manifest SHA-256 |
| --- | ---: | --- |
| Native base | 107 | b9fd5f760bd578bb40ef93feee861763d287f098ecddab07ed28f44863ee5da4 |
| Go APPLICATION | 109 | a6de024d6b6d5a560fb670c2a53ff60401e94e843b15a8a112f3a4c469ce8a67 |
| APPLICATION HTTP | 112 | 2fd27a08a973ac153f3f896a2d3213452feeeea46609ddec80c8e3a6eb073bd7 |

Qualification:

- Before composition, the original APPLICATION normalizer rejected the actual two-member repair as a mixed native base. The implemented composition accepts only the exact qualified parents.
- The first 132-case release/packaging suite passed, including distinct WORKER/APPLICATION lineages, partial/foreign/backdated closures, alterations to each preserved APPLICATION member, unchanged caller inputs, and rejection of 109/112 namespaces at the 107-member base boundary.
- After narrowing to the dependent contribution, 376 focused Python cases passed with zero errors, failures or skips (process 49731; 107.725 seconds), covering original-run continuity, real lock contention in both runtime copies, Go closure and extension builds, historical launcher composition, packaging and exact identity review.
- The actual Studio Fabric facade suite passed all 70 cases, including fresh backend generations refusing to redispatch a run with retained orphan evidence; the same process completed with terminal exit 0.
- The active parent already contained a four-line Go shim recovery change but retained its older whole-file identity review. This contribution preserves that code, maps every unchanged reviewed literal to its new source position, and records the one new HTTP conflict status literal at line 2804. The exact current source is c01fffa59c0095355cddda7f31aa76a218f0ee87a30769998d9627ec2ee37cef; the existing identity review now qualifies all 53 sites.
- The broader local native-security module reported 35 passes and 32 failures at the existing FABRIC_SPARSE_GIT_OBSERVATION_UNQUALIFIED boundary. That is not a green security receipt. Hosted Linux qualification remains required; no guard, assertion, Git binary, environment contract or CI gate was weakened.

No live generation was published or selected, no provider task was dispatched, and no APPLICATION profile or service was activated. Final acceptance requires incorporation into #2175 at its then-current head, the original #2187 protected-source integration, exact-head hosted checks, the final protected merge, fresh installed predecessor verification, the existing immutable publisher/selector, and authenticated consumer proof. The installed M2/C26, #398 and original APPLICATION operation holds remain distinct.


### Existing sparse preflight repair composed on the APPLICATION successor — 2026-11-07

The preceding two-member composition was published as #2194 at 4d0b4979711759bfe23725246daeae27a7ff94ca, targeting #2175's original branch. This additive follow-up consumes only the existing two-hunk executor repair and behavioral tests from #2007 source 0e20d9b2eaba16219495e4a9489d4e2ae88900fc. It does not import that carrier's older whole executor, fleet operations, account-binding changes, historical effects, or release claims.

The bounded reproducer established that the actual /usr/bin/git observation returned 0 and valid stdout but emitted the sparse-index-expansion advisory on stderr. The original strict observer therefore refused. The adopted source uses only the invocation-scoped advice.sparseIndexExpanded=false setting. Every other stderr, nonzero exit, donor/index/dirty-content check, configuration drift, timeout, output bound and cleanup-unknown classification remains intact. No persisted Git configuration or Git executable was changed.

The same existing repair verifies the exact local commit through the original bounded observer before the effectful workspace helper starts. Missing/noncommit objects produce a known pre-helper refusal; uncertain observations stay uncertain, helper identity is checked again, and a later mint failure retains its existing hold. This consumes accepted source work instead of implementing another preflight or reconciliation owner.

The original patch and test files are byte-identical to their source blobs 7e4d334aa1cf4cee0056cefacb6faff74726d9a9 and dce94f7b2feee2c4420740fa57e954c9ad531e0a. Patch SHA256 is 34d3cbbe2033bc8a1a68d6d711407ad57ee892a951f4ef68303c719f3585a9c9. Its exact application to the current APPLICATION executor yields d15238fa70942463de99ca4f7679ad9e27d6b91f9034ac792f903efd1c22cafc; the historical bb036914 executor remains an immutable predecessor.

The existing builder qualifies this one-member forward delta against the complete repaired parent b9fd5f760bd578bb40ef93feee861763d287f098ecddab07ed28f44863ee5da4 before the earlier admission/APPLICATION/Go normalization chain. Candidate selection captures one of the two exact five-member source maps and compares the staged read to that captured map. Historical cohort constants and all actual-output provenance remain intact. The final 107-member output differs from the original installed 3ad8c699 parent in exactly three members: task, lane runtime, and the explicitly adopted executor successor. All other 104 entries remain identical.

Current actual builder receipts:

| Variant | Members | Manifest SHA-256 |
| --- | ---: | --- |
| Native base | 107 | 1bb6f2ec3af603e44c345558931d3bf5daec28fa7bc9db14cbad830674ea84d0 |
| Go APPLICATION | 109 | 78435663a79524b1134b95ba4046feba6c7fc76e697745ae2acfeec3583a56ed |
| APPLICATION HTTP | 112 | 13ebee6da996713ec363ddbed73164be9b92045070b676e403c9e9d419aaef20 |

The current combined run passed 440 tests with zero failures, errors or skips (process 98608, pytest 122.980 seconds, terminal exit 0). It includes the full native-security and adopted sparse-preflight suites, actual index/config/rules byte preservation, refusal of unrelated stderr, unsafe contents and invalid pins, uncertainty preservation, immutable support publication, the actual inert execution seam, Go generations, historical launcher paths, exact lineage/mixed-parent refusals, packaging and source-identity review. The earlier 35/32 security result remains a retained counterexample and is superseded by this current successful source qualification, not erased.

This change does not reconcile any of #2007's historical Ubuntu2 holds, alter cache or disk guards, activate APPLICATION profiles, or install a live generation. #2175 remains the final composition carrier; #2187 remains the original independent admission-repair carrier. Exact-head hosted checks, coordinated source incorporation, protected merge, existing publication/selection and authenticated live proof remain owed.

## 2026-11-07 scoped-model and Brain fixture composition

The isolated #2194 contribution consumes published APPLICATION source
d5df6b2ad8b2a49e9c0a98e33f8c7cca14a630a6 from its original #2175 carrier.
The previous contribution parent is
5c6da94136b5a139a0da10312e9af997de2e0c1a. All ten incoming scoped-model
paths retain their exact published bytes. The incumbent branch/workspace and
its J, shared-policy, provider and activation effects were not modified.
This is one captured forward composition, not an open-ended chase of its
active writer or a second final release carrier.

### Exact current closure and actual dependency custody

Before this composition, the real source builder refused the new gateway
and broker at "native sparse commit preflight parent closure differs".
The retained counterexample is /tmp/mmx-d5-composition-before.json.

The existing builder now qualifies one additive two-member successor of
the complete 1bb6f2ec3af603e44c345558931d3bf5daec28fa7bc9db14cbad830674ea84d0
parent. Gateway changes from df0fc6cb3ae0771ea2bcb122bf331e0cfd3ca089b41506a18ae39de37ec021d1
to adad5ea3bcfd091730b92707d1ad231f5566cb200b5ffedfe41ef086aab86949;
broker changes from 42d45e5cefaa9829dae3c7741cbffdc7fe772f534782ee4bb6aa1311fbeacd6b
to a84752dc40598bbf8411d7b992d32cda6c76156d534c4925c2eca5083f097360.
Partial pairs, foreign bytes, changed unrelated members, older executor/task
cohorts and extended or historical namespaces refuse.

The normalization order is now scoped-model pair, sparse preflight,
admission pair, then original APPLICATION carrier. Every earlier parent
constant and historical fixture remains frozen. The actual incoming
manifest is retained separately for captured Go dependency equality;
the caller's dependency map is never normalized or rewritten. The existing
source-capture, staged-byte and composed-component checks remain intact.
The new tests prove that correctly captured current bytes pass and a
historical dependency map cannot authorize those new staged bytes.

Actual outputs retain the bytes that were built:

| Variant | Members | Manifest SHA-256 |
| --- | ---: | --- |
| Native base | 107 | d416ac1611112f757d602ddc73b4ed61636a7dd53c4b66866ce302aeabd7a86f |
| Go APPLICATION | 109 | 4812aec2c4a3bffa73656a520482a55eea2445a3724b5ee1af08e0af88cb8140 |
| APPLICATION HTTP | 112 | 0f6cc8c3fecb119fe272aca5a20e3adc346adeeec82214341b5b8c27f9667440 |

The base differs from the previously observed installed APPLICATION parent
3ad8c6993609b17378c2c248c73fffc210a71754078d3a6bbb71cfaa6e7018c9
in exactly five explicit members: task, admission lane, sparse executor,
gateway and broker. The other 102 members are identical. This is a
comparison with the captured predecessor, not a fresh installation claim.

The incoming Go handler stays byte-identical to d5df6b2:
1cab35bdf7ee8fce5f12237035556a9ab4314299c5d7b71c0f44df320fe0dab7.
Its exact 53-site identity review preserves 51 unchanged mapped sites,
moves the existing recovery-unavailable 503 within its new conditional,
removes the deleted fixed-scope 400 and reviews the new scoped-conflict
409. No general literal exemption was added.

### Actual Brain consumer qualification

Hosted CI42344753231 on the earlier 5c6da941 contribution reached the actual
Brain composition gate and failed 8 cases with 3 errors. Its chat fixture
only enrolled mastermind_text_fabric, while the current chat driver
correctly requests mastermind_chat_fabric.

The fixture now declares its own chat transport, mode, capability and
credential reference through the actual Macro owner. A negative case
proves that the text mode/grant cannot substitute, even if its allowed-lane
list contains the chat lane. Production role selection is unchanged.

The same paired proof exposed a cleanup defect after a two-second fixture
arrival assertion failed: aclose() was called while the original
anext task still ran. Its finally path now releases and reaps that same
task before closing the generator, and always restores the loop exception
handler. The two-second startup assertion and runtime timeouts are
unchanged; the original arrival delay is not attributed to a proven cause.

The exact paired Macro source is
abab96df55f82cb5c26459a6f51b568d73a6a6f8, matching the incoming CI fixture.
The first local attempt lacked claude_agent_sdk and is not a pass.
An isolated proof environment uses SDK0.2.179, the exact version resolved
by the hosted job, satisfying the source-declared >=0.2 dependency.
It does not install or activate a company service.

### Qualification receipts and retained failures

- Actual source builds succeeded for all 107/109/112 variants.
- The generation/identity run initially had 326 passes and one stale
  historical-dependency fixture failure. The fixture now supplies its
  own historical dependency map; the separate current-byte comparison
  and new stale-map refusal cases remain.
- The combined 741-case run had **734 passed, 1 failed, 6 skipped**.
  The sole failure was the H1 packaging test's old expected changed-member
  set. Its exact successor expectation now includes the gateway/broker
  pair; the complete affected suite passed **4/4** afterward.
  This is not represented as one all-green union run.
- All six skips are explicit Linux-only initializer, memfd/fd-exec/getpath,
  xattr or proc-FD checks on macOS. Hosted Linux CI remains their proof.
- The actual paired Brain/Fabric composition passed **47/47**, including
  the new role-isolation case.
- The buffered native chat suite passed **8/8** after the cleanup repair,
  preserving original provider observation, cancellation, usage, lease
  close and no-reissue assertions. Its earlier 7-pass/1-error result is
  retained separately.
- The prior 70-case facade proof remains attached to unchanged task/lane
  and facade source; it was not rerun or relabeled as a new receipt.

Combined qualification log SHA-256: b0a034a64344ed1ff1fb43fd39f373f50722593ef373863032fd7387ed215b28;
XML: 050a2c56fa1644f3518f09e0fcff5dda399c14b7ab40a5ca86eb269a57e69fd3. Focused packaging log:
c4b808d34f4db00b333696dec1f3a43a2887d8bfe0cb7af07a3cb98ff43a7830; XML: eb0a79aa4b092239dad50b4a6fb864548c54afd48e5012916aff89ff5f3de105.
Paired Brain log: a6cf325c4f2a786a027ed5feff63346faabc0c541774c9974885d6dfb18dbfd7.
Final buffered log: 7100d11e3601bd1e46907312ae8e815c82ddf21fd39d83fd8084cdbf1dd6c6f2.
Final disposable source-capture SHA-256:
ce6971a18e2b220c18c1a8bba55a695f78a3e7684decd2c3497b7712a930e000.

Whitespace qualification: the new delta against 5c6da941 passes
git diff --check. The full contribution against d5df6b2 reports exactly two
blank unified-diff context lines (11 and 12) in the byte-identical adopted
sparse preflight patch. Its original Git blob remains
7e4d334aa1cf4cee0056cefacb6faff74726d9a9 and SHA-256 remains
34d3cbbe2033bc8a1a68d6d711407ad57ee892a951f4ef68303c719f3585a9c9.
All other contribution paths pass the full check. The preserved patch was
not rewritten to erase its required context prefix, and no checker or
repository-wide whitespace rule was relaxed.

### Delivery boundary

Incorporate this exact contribution through original #2175, preserving its
active scoped-model/J/shared-policy work and paired Macro carrier. If its
published head advances again, reconcile the subsequent delta; none of this
proof transfers automatically to new bytes. #2187 remains its independent
protected native repair, and #2185's source merge does not prove installed
Hermes enrollment.

Required hosted checks, protected final-source delivery, fresh installed
predecessor/generation/sequence verification, the existing immutable
publisher/selector and authenticated consumer acceptance remain separate.
No live provider/account invocation, runtime selection, live enrollment, new
scheduler or generic transition registry was introduced by this contribution.


### Remaining paired-consumer qualification at the d5 epoch — 2026-11-07

Hosted CI 42347674382/job128329140052 independently passed the exact-scoped Macro proof (31 tests, zero failures/errors/skips), the 47 inference cases and eight buffered-chat cases at 73967dc143f19ccb8391f55d413280f4d427774a. It then stopped at the native-text fixture's missing agents.yml prerequisite. The local same-epoch proof reproduced that failure before repair. A separate local continuation also exposed six stale native pins in the translation fixture and four in the shared AUTO fixture used by both portfolio suites; these previously unexecuted later stages were not inferred green from the earlier steps.

The repair supplies only the inert _cfg prerequisite inside the late-selection test and asserts that the candidate callback actually ran once. Production ordering and all existing before/after selection guards remain unchanged. Both source fixtures now pin the exact d5 carrier blobs already present in the composition. Complete source checks remain intact, the other nine translation native pins and all three realm pins retain their actual current values, and historical input pins are unchanged. The protected commercial realm must be consumed together with its corresponding current fixture pin; it is not stamped into the standalone d5 source.

Separate actual paired Macro abab96df55f82cb5c26459a6f51b568d73a6a6f8 requalification produced:

| Consumer | Cases | Result | Test-log SHA256 |
| --- | ---: | --- | --- |
| Native text and selection fences | 32 | passed | 3bf8cfad81a37b09d6fedd9943aa660f8aabb07c6be64ecc4ccefbb7bb4db81e |
| Translation original operations and durable cache | 23 | passed | b5294a2235a4adb187ef6cd5521e093817a05e62fa48ef588a28381b3986f2c2 |
| Cross-pool AUTO | 14 | passed | 151296dbb9410bf3338143bfa003974d1069117bdd0f16557c4cb3af4d05b8f9 |
| U.S. portfolio original-operation paths | 32 | passed | 26c4dba294866b3b86f36870a3de744f1611085a33a1ee2bac4f2d8b5dd6b1c2 |
| Actual chat asset in Chromium / Playwright 1.62.0 | 3 | passed | c9e3e9dc17ca196f9c2b4bf6cf4b3f6824cdd65f9406239aba2508be853d3054 |

The regional suite is not qualified by these results. Its log stopped advancing for approximately 295 seconds in the China daily/first-run case. A bounded interrupt of that original disposable test process at 5m20s found that the case had subsequently completed and the suite had progressed to the lost-submission-ack case awaiting the actual provider observation thread. The run ended with signal status -2 and no complete test summary; log SHA256 f31c1df9062faa790271e135ba208b3f5507dca69a2c69ef985bacebc2923426. The main-thread trace does not establish the blocked worker's cause. No production timeout, guard, account or runtime state was changed to mask this incomplete proof.

The browser proof used actual app/static/chat.js SHA256 a8d10d9edda239164167ee633ed1c7fc41b888ed17ab42855e8909b07547ec2e, preserving partial text, unresolved tools and original-request recovery; failed identity storage sends no HTTP request. It is local browser/source proof, not authenticated live provider acceptance.

Source ancestry was explicitly completed after the attended commit tool retained a pending MERGE_HEAD while committing a single-parent source tree. The completed local merge 820ce4a0d88bd7fed3979fef6b8408d47c53d41b has parents 73967dc143f19ccb8391f55d413280f4d427774a and d5df6b2ad8b2a49e9c0a98e33f8c7cca14a630a6; its source tree is byte-identical to 73967dc. Original #2175 has now published its protected-source merge as 3ec62ffe02f277e3bab530e3ba069f2f86dcd18d. Its original active workspace remains untouched; further contribution qualification must name the actual consumed epoch.

Original J source-repair custody remains separate. A bounded canonical fabric_status read for fabric-app-j-preserving-migration-20261107-02 under root fabric-application-integration-20261104-sol observed ACTIVE_OR_WAITING / worker UNKNOWN, no result or return code, root_verified=false and execution_absence_proven=false. The retained controller poll had advanced to 07:02Z / 3144 seconds against its 7189-second wait. Retry, dispatch and result-consumption authorization were all false. No replacement task, result consumption, installation, cleanup or transition was attempted. The earlier unavailable process session does not prove absence; no host/cache path is inferred from it.
