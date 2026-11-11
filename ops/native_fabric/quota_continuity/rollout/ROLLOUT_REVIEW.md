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


### Current protected APPLICATION consumer qualification — 2026-11-07

The existing contribution now incorporates original #2175 published source 3ec62ffe02f277e3bab530e3ba069f2f86dcd18d, including its protected 5f8c13d realm and persistence changes, without modifying the incumbent workspace. The actual realm module and translation pin now agree at a51e2bce8d9bb312107f975d503abd6541bd5000. All 15 native translation pins, three realm pins and four AUTO pins were independently checked against the current source bytes.

The exact current consumer archive, paired with Macro abab96df55f82cb5c26459a6f51b568d73a6a6f8, passed all 198 cases across the seven required/related commands: 47 inference, eight buffered chat, 32 native text, 23 translation, 14 cross-pool AUTO, 32 U.S. portfolio and 42 regional portfolio. Each command completed with exit 0. No production provider, credential enrollment, trading authority or live installation was involved.

The regional preimage was reproduced in a fresh current-source fixture with one all-thread dump at 20 seconds and a bounded 90-second diagnostic limit. The dump showed the main thread in asyncio runner shutdown with an idle executor worker; the diagnostic timed out. The test had replaced the process-wide Thread class. The repaired fixture preserves that class and its timer/executor initialization, intercepts only the named first-run thread's start method, and forwards all other starts to the original method. It additionally requires one first-run start and a complete original state. The full 42-case regional suite then passed in 62.770 seconds. The old interrupted run and diagnostic timeout remain recorded; production timeouts, provider cancellation, settlement, lease and replay guards are unchanged.

The separate mixed-process generation command had 383 passes, five passing subtests and eight failures. Its realm-projection test imported a source compiler into the same process as immutable-generation startup; the runtime's existing module-identity guard correctly rejected that foreign loaded module. The canonical CI step runs the realm projection in its unittest process and native startup in a separate pytest process. Requalification of the complete 22-case HTTP startup module in that separate process passed with zero failures/errors/skips. No module guard was weakened or test removed. The earlier mixed command is not relabelled as an all-green union run. Current actual native manifests retain 107/109/112 members and the previously qualified d416ac/4812ae/0f6cc8 exact closures.

The actual chat JavaScript and browser test are byte-identical to the preceding three-case Chromium proof, so that proof remains applicable without another browser run.

The current Mastermind OS web source also builds successfully with locked npm dependencies, Node v26.5.0, npm 11.17.0, TypeScript 7.0.2 and Vite 8.3.0. No VITE_* environment or dotenv configuration was supplied. The existing build_os_asset_manifest owner (blob b5465858e011a4651ffe9e822a7ebe3905be823c) and closed profile owner (blob 4f70ff2625d1a3fd8e5d12235d2c3baa28e739c8) accept its actual 12-file licensed profile. All five font/license/notice files are byte-identical to their source public files. Asset-manifest SHA256: f861184272825e11f095eb3f60a3f7c73c6b039b89d02d40306e5cc1058f7f77. The build retains its nonfatal large-chunk and ineffective-dynamic-import warnings; no output was deleted to fit a profile. This is compilation and asset-contract proof, not a canonical protected release receipt or installed/authenticated OS proof.

The complete structured source qualification and source-file capture are retained in review_evidence/fabric_application/hardening-consumer-qualification-20261107.json and hardening-consumer-source-capture-20261107.json. All captured source files matched the working tree before adding these proof documents and this report section. These documentation additions do not change the exercised code. Hosted exact-head checks and incorporation through original #2175 remain separate; J and all existing runtime holds retain their original custody.



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


### S3 APPLICATION publisher and scoped-model composition — 2026-11-07

The first S3 source phase preserves the original #2175 / Macro#10740 carrier. Its exact input is #2175 `d5df6b2ad8b2a49e9c0a98e33f8c7cca14a630a6`, including the scoped-model code and retained J candidate, rather than the earlier312be checkpoint. It incorporates #2187 through #2194's exact two-repair contribution `4d0b4979711759bfe23725246daeae27a7ff94ca` and #2182 publisher `b6174452467a458463b2592d15faeeb939f431d7`. The later sparse-executor delta is not imported: it is not needed for these builds and would change an additional installed member.

The publisher is merged into the APPLICATION support owner; its resulting support SHA256 is `8fc20a93e4c1b725064398217f8fab25917ad151558d461dc82daebb38920dca`, not the publisher-only bd805865 source. One exact three-member successor binds that support source plus d5df's gateway/broker against the complete repaired APPLICATION107 parent b9fd5f76. Every other104 member is preserved. Relative to the actually installed3ad8c699 base, exactly five members change: the two admission repairs, this support extension and the two already-published d5df dependencies. The eight installed APPLICATION members are never replaced by the old WORKER baseline.

The private inverse view enters the existing admission/APPLICATION/historical validators. Captured Go dependencies are checked against the untouched actual input, so a caller cannot supply stale normalized hashes. Actual emitted manifests/inventories and all historical source/namespace pins retain their meanings. The publisher-only107 c651b8e5 is an explicitly rejected input to this APPLICATION composition, not an allowlisted precursor. The three-member source patch is byte-reversible and source-bound (SHA256 3fe89c2b49afc8b96352c339790d302806fb3d4516407c4476524168367b428c).

| Actual builder variant | Members | Manifest SHA256 | Source inventory SHA256 |
| --- | ---: | --- | --- |
| base | 107 | d8a112411c28c42e812907435f5b182ce351a4cb4c00e47b94ca1ddf58294ac9 | fe542e742b2eb529db9bec2472d4cac236dba8d8403cb99d4d1b7f4ee8939119 |
| application | 109 | 9cad523f30aa098c71c0892005e32a706d1be91921e886e85aa1af0d52781255 | d5aba23e26f5e7f9f57e1b6740efa5f0fe0abea88ffa68cfbac2bc0b63f42670 |
| http | 112 | 6cc737e65083c4af6bfd6f0e60b4de90e19c121148d748dba73271ba11f84771 | 4447318bcea36a4b5471e819d1790445dfbca2adeb2eada2d7db7353fab5fa45 |

Validation is recorded as separate actual runs, never a sum of earlier suites:

- Closure, publisher CAS/unknown-effect behavior, three original builders, missing/partial/foreign/backdated cohorts, stale captured dependencies, publisher-only rejection, actual output provenance and reversible source: **188 passed**, no failures/errors/skips.
- Material packaging/current inventory assertions and the exact historical95/current107 diff: **15 passed**, no failures/errors/skips.
- Changed Go-shim and packaged lane identity checks: **6 passed**, no failures/errors/skips. The d5df Go shim now has53 source-bound reviewed status/permission/input-limit tokens at SHA2561cab35bd; no principal/account identity was introduced.
- Earlier204+83+70 repair receipts remain separate prior evidence. The two repaired runtime members and bound lane are exact source bytes; no unchanged broad repair suite was repeated.
- The broader initializer diagnostic is retained: bundled Python produced40 passes/3 failures (one stale assertion repaired, two runtime limitations); system Python produced75 passes/1 unchanged directory-premise failure/3 skips. No runtime guard, environment contract or CI requirement was weakened. Required hosted qualification remains owed.

Fresh read-only verification through the existing native generation owner confirmed selected ef94479b8c768088e7c6b611d498879b9b6896ba24faa2558135ad8465f8be46, sequence35,107 members, manifest3ad8c6993609b17378c2c248c73fffc210a71754078d3a6bbb71cfaa6e7018c9, unchanged during read. This is a predecessor observation, not a new installed receipt. No live generation, policy, provider turn, service or profile was changed.

Exact inputs, commands, suite/JUnit digests, outputs, installed predecessor observation and remaining acceptance are retained in `review_evidence/fabric_application/s3-source-composition-20261107.json`. Original J, C1#2109, Hermes and Macro consumer custody remains distinct. Source composition does not complete the native owner/compiler/profile/parser and entitlement joins, financial reservation/unknown-spending proof, E3/fresh research/Metabolism consumers, protected release or real application/delegated-child consumed-result acceptance.

### Inherited chat fixture qualification

The incumbent Hermes receipt in #2175/comment6703255977 identified a general-CI fixture that enrolled only the text service while the existing production chat path correctly required `mastermind_chat_fabric`. The chat fixture now qualifies its synthetic transport under that existing service relation and adds a copied mode with the correct transport ID. Production chat identity and the text fixture are unchanged.

The actual required three-module Brain inference discovery passed **46/46** with zero skips, using a disposable copy of paired Macro `abab96df55f82cb5c26459a6f51b568d73a6a6f8` (2,530 exact Git blob checks) and synthetic provider responses. This is separate from the 188 closure/publisher, 15 affected packaging and 6 identity checks above. The whitespace-clean source-forward fixture was also rechecked independently (1/1); its reconstructed source bytes remain exact. Hosted exact-head CI and live consumer acceptance remain owed.

## S3 protected-merge composition and custody follow-through

Protected merge `3ec62ffe02f277e3bab530e3ba069f2f86dcd18d` is composed with the qualified S3 source. Both overlapping files retain the protected realm-preimage and identity changes. The original 107/109/112 builders reproduce the same exact output manifests and inventories above. A separate 46-case material-source revalidation passed; the unchanged prior suites remain their own receipts. Separate shared-account/original-effect checks passed 18 cases, and the new cross-model account-cap concurrency/unknown-hold cases passed 3. No aggregate-suite claim is made.

The six-file J preserving-migration repair is retained as a source candidate under `review_evidence/fabric_application/j-preserving-migration-repair-20261107.*`. Its 28 private-owner, 44 collector and 1 additional Node-owner checks are separate runs. The modern/legacy HTTP suite could not collect locally because its preinstalled MCP client package is absent. This artifact does not change the current collector/native/control generation or authorize a live original-J action. Exact sources, output hashes, receipts and outstanding live qualification are in `review_evidence/fabric_application/s3-source-composition-20261107.json`.


### Combined publisher and sparse APPLICATION source — 2026-11-07

This contribution consumes original #2175 published b955c823767b504853b6d79e44d09fc71cdbdd9c without modifying its active workspace. The original source composer retains the Hermes/native release join. The combined base has exactly 107 members: compared with b955/d8a112, only the sparse executor changes; compared with 317cc5d/d416ac, only the support publisher changes. All 106 other members in each comparison are byte-identical. The installed-parent comparison is against the retained 3ad8c699 observation, not a fresh live read: exactly task, lane, executor, support, gateway and broker differ, with 101 unchanged members.

Both unmodified predecessor builders reject the combined manifest. The existing pool-composition inverse now admits the already-qualified complete sparse parent 1bb6 alongside its unchanged complete parent b9fd. It still requires all three exact publisher/gateway/broker hashes before checking the entire inverse manifest. The normalizer dispatches by the exact publisher member, preserving the older scoped-pair path, then applies the unchanged sparse, admission and APPLICATION inverses. Four explicit complete candidate maps cover the two accepted predecessors and their union. Historical constants remain fixed; actual captured Go dependency equality and staged-byte checks remain unchanged. There is no new transition registry or publication owner.

Actual source builds succeeded:

| Variant | Members | Manifest SHA256 |
| --- | ---: | --- |
| Native base | 107 | 0084f7d0a3b78f3c434c872c9bbf2c5ab764f54cf565d5f24c00480a1855cbfe |
| Go APPLICATION | 109 | 4be0e9c3658fb46d15a795615bf4dc4f7f1502e25e544c00a339d3a5057f5e8a |
| APPLICATION HTTP | 112 | f7b15466dc9e42c20a28814462ecb05c9327d9f12312ff1c5cb45eda0d416ff6 |

The initial focused source run was 561 passed, 3 failed, 6 skipped across 570 cases. All three failures were in the publisher suite. Two were predecessor-specific fixture expectations; the repaired tests retain the exact new sparse-parent assertion, the frozen old-parent assertion and both direct-cohort and full-normalizer unknown-publisher refusals. The selected-publisher child failure was separately diagnosed: the proof venv found PyYAML 6.0.3 only in user site, while the unchanged production child deliberately sets PYTHONNOUSERSITE=1. The same isolated child import failed with ModuleNotFoundError. Installing the already-declared exact PyYAML 6.0.3 dependency into the disposable proof venv made that child import succeed; no production code or isolation guard changed. The complete publisher suite then passed 44/44, including the actual selected immutable publisher subprocess, same-target observation, stale-selection/older-owner refusal and uncertain-reply preservation. The initial 570-case run remains recorded as failed, not retrospectively green. Six skips are the existing Linux-only checks on macOS.

Separate complete qualification passed 169 admission/effect cases and 22 native HTTP startup cases. The actual paired Macro abab96df55f82cb5c26459a6f51b568d73a6a6f8 translation path passed 23/23 after binding its one changed admission-fixture blob 4cc542888358bf6b46a1e78c581af5ef2f7178aa. The incoming admission fixture adds shared-account/model contention and unknown-effect capacity tests; its existing consumer fixture behavior is unchanged. All other current translation/AUTO pins remain exact. The stricter distinct-chat-service fixture and negative substitution case are retained.

The earlier 198 consumer, three browser, and complete 12-file frontend results remain separate receipts. The complete frontend source and actual chat asset are byte-identical through this publisher merge; no unnecessary build/browser rerun was used to inflate the counts. Detailed logs, source inputs, before-fix refusals, dependency evidence and actual build digests are retained in review_evidence/fabric_application/hardening-publisher-composition-qualification-20261107.json and its source capture. These source results do not constitute protected final-source delivery, enrolled runtime selection or authenticated live acceptance.

### Retained J candidate: HTTP proof corroborated — 2026-11-07

The exact independent six-file source candidate retained by b955 was applied only to a disposable source export. All six preimages and postimages, compressed digest 4e6c61cdc049aa7f0f24f7b55d1de48158e0fe8eb1ebc175d67c87e9a62c460c and expanded patch digest 5c54b72a5582490f2047ef97b06f1a3b7b6acc957b0ced9ce0e10338fca75f36 were verified. The locked private MCP package was installed with dev dependencies in that export; package and lock inputs remained unchanged.

The complete patched original-delivery.test.mjs suite passed 22/22 using modern client 2.3.1 and legacy SDK 1.25.1 through actual loopback HTTP, the existing private gateway and owned inert Python helpers. This corroborates S3's prior accepted 22-case M1 proof at 07:36, source-linked at #2175/comment6703989157 and discovered after this independent run; it is not claimed as the first closure of that gap. It verifies both clients retain the sealed predecessor observations, use one subordinate reconciliation attempt, preserve held/null slots, and refuse malformed/duplicate predecessor data. No installed host, provider, original collection or real native transition was invoked. The prior 28/44/1 candidate tests remain their separate original receipts. Exact proof is in review_evidence/fabric_application/j-preserving-migration-http-qualification-20261107.json.

A fresh canonical status read also reconciled source-repair migration02 as VERIFIED_TERMINAL, rc1, root_verified=true and controller_return=RECORDED, with reason continuation_evidence_unqualified. Its acceptance remains UNVERIFIED/EXECUTION_NOT_ELIGIBLE; result consumption, retry and dispatch remain unauthorized, and execution_absence_proven=false. Its 190-byte result was not read. This does not settle the original native-driver J effects, which remain UNKNOWN. The separately published candidate has not been applied to the main source or live installation by this contribution. Final source incorporation and native/control closure qualification stay on the original active #2175 carrier.


### Consumed original paired-workflow repair — 2026-11-07

This contribution incorporates original #2175 commit 41e86c7aa89905f9b4592d57fbf32c2d7c0f1458 with its two source paths unchanged. Its CI checkout now consumes Macro 9eb5cb6b28b510ea9e2bf05ae9040528523339df, includes the actual E3 gold fixture, and runs the exact-scoped/E3 suites under the unchanged positive-test and zero-failure/error/skip requirement. This resolves the observed input mismatch in #2194 run 42353416869/job 128346862107: all 31 scoped cases failed fixture setup on the stale 8487163 admission-test identity before runtime assertions. That old hosted run remains failed.

The fixed Macro fixture is blob5440c85291efa25d2635a7034d691607cd4bf885. Its only difference from 704 is the published 4cc5428 admission-test pin. Root verified all 19 identities against actual 17ed files, their committed blobs and b955; every value matches. The incoming source report contains the separate 118-case E3/exact proof and 180-case composed Macro proof against b955. Those are retained original runs, not new tests by this contribution. No duplicate Macro edit or PR was created. The 107/109/112 executable source and emitted manifest inputs are unchanged by this workflow/evidence join.

The future J join also has an exact source-only incorporation receipt. All six retained preimages and previously qualified postimages still match. Replacing only collector 44dcbb64 with f790e953 preserves the other 106 base members and has expected 107 manifest 981ccb955f92b0f49a929e60ba18bd9eed90efff9506d7c19a443f68d7f3ea32; its exact inverse reproduces the complete 0084f7d0 parent. The corresponding expected 109/112 identities are 39fe40008b3269d62c82033ece1826a5224f7d2da49916fa509c1eff8dbcc14b and fe7dc7c71f9f05129f48fcd1f032d92c1ba1e9a0d202217cb64f3bfe0d2029e7. These are static composition identities only, not a new builder qualification or installed generation. S3's active original J/Hermes implementation remains untouched; its eventual qualifier must preserve this sparse executor and publisher rather than silently returning to the old d8a parent.

Exact receipts are hardening-scoped-pin-consumption-20261107.json and hardening-j-incorporation-boundary-20261107.json in review_evidence/fabric_application. The corrected J HTTP receipt explicitly records S3's earlier accepted proof. Existing original-operation holds and the distinction between source, package publication, selection, deployment and authenticated acceptance remain unchanged.

### Paired CI input closure and current provider proof — 2026-11-07

The next exact-head hosted run 42356005158 reached runtime assertions: 117 of 118 paired cases passed, with the Qwen worker-override case failing because the sparse owner checkout omitted `ops/launchd`. The pinned source already contains the expected worker configuration (Git blob e8d8a3e35661f5ff62830b30868240f77c63f3b4). This repair includes that directory and explicitly installs the paired owner’s declared `requests>=2.31` test dependency, matching the original retained candidate workflow (blob946a9d23a356c20f4629e5c15420155d34ea1c43; #2175/comment6704831450). Mastermind’s editable dev install does not declare requests; the E3 suite directly imports it. Provider routing, environment precedence, the Macro 9eb pin, tests and the positive-test/zero-failure/error/skip gate are unchanged. The hosted failure remains retained.

The missing-directory counterexample reproduced as one test/one failure. Adding the directory in an inert archive resolved that assertion; the combined run then had 117 passes and one missing-git-head receipt failure because the archive had no Git metadata. The actual registered, clean Macro 9eb checkout supplied that required input. With actual paired 5ca source it passed all 118 exact-scoped/E3 cases, zero failures/errors/skips, exit0; its Git status remained clean. Log SHA256: 3591090995b75304842076f0b34cb227b2890e9f02ecc0fc8f31bf0fe09ab1cf. No production call or assertion was substituted. The full failed and successful observations are retained in hardening-e3-ci-input-closure-20261107.json. A new hosted run is still required.

The changed Macro provider factory was separately exercised with actual 5ca Mastermind inference consumers and required production/Fabric fixture flags: 47 passes, zero failures/errors/skips, exit0. Exact source archives and log SHA256 d5f3160abe22ac3b2497bab2e42ff2033c91355c1df3e119bd286a466685f6bb are now durably recorded in hardening-current-provider-inference-20261107.json. This is a separate run from the retained 198-case earlier-provider proof, not installed acceptance. All native executable, builder and manifest inputs remain at the qualified 17ed identities.

The preceding f790 collector projection is now explicitly historical. Original #2175 source 2cf01336ba7f7e5bc2011f50c0319892ddebb292 advances the collector to 5219fb35f940831752638d348feefd92d02ad00ba9394fa9d66cf1d281091a9d and retains a pending native companion on the original operation. Those earlier static successor hashes must not be used as the current cohort identity. The active companion's overlapping builder/manifest/inventory/test fence is preserved; this CI-only repair does not implement a competing native inverse or consume its uncertain result.


## 2026-11-07: original J package and sparse executor composition

Consumed original collector/private-J publication `2b8343dd43d2600d4c304977b125118e7ea36348` and recovered the original native package worker's complete four-path artifact (`a71bac2d11eefbc5b56b4b72dab432279d7e2c6de860bfbc0bf83443aaf0c307`). Its commissioned base reproduced all three real builds and 148 stage cases. The original return and its failed incomplete-export attempt remain in the source receipt.

The actual combined source retains the sparse executor and pool publisher. Exact whole-parent checks now admit the separately qualified collector successor at each existing inverse; all 54 previous literal assignments and historical fixture bytes stay fixed. Actual 107/109/112 manifests are `bcfb8c961c51a491cf66faaf697585675152bb6827ae1c070b9efcf5c7018c8e`, `ce7f661017ca993602eaefbe0a3be91df3965689eea9368394e66e9942ad5646`, and `677c3b585e171a99915c764d41ad6a36cfb200aa6c91374744532e7128c1a812`.

The 188-case stage suite passed within the 374-case consumer run. That larger run had 367 passes, six Linux-only skips, and one publisher failure caused by PyYAML being present only in the host user site, which the actual publisher correctly excludes. Installing PyYAML6.0.3 inside the disposable proof venv made the exact affected case pass; the failed run is retained. No guard or assertion was weakened. See `review_evidence/fabric_application/hardening-j-sparse-package-composition-20261107.json`.

This is source composition, not native selection, runtime enrollment, reconciliation of the separate original J driver, or measured availability.

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

### H2 quota-reset successor over current sparse parent — 2026-11-07

The optional --include-quota-reset-recovery flag uses the existing builder and
installer to replace the complete four-member quota reader/circuit/broker/picker
cohort. New output requires exact whole parent
bcfb8c961c51a491cf66faaf697585675152bb6827ae1c070b9efcf5c7018c8e.
The earlier c7f5d2e62980e4cb38580496ef82125673015881f70d4fc4d6763137eed30459
parent remains a separately pinned historical inverse; it cannot authorize new
emission against current source. Partial or foreign members and any other whole
parent refuse. All four H2 preimages and postimages are unchanged by this join.

Validation reverses H2 first, then the existing APPLICATION pool/exact-scoped,
sparse-preflight, admission-integrity and APPLICATION carrier cohorts in order.
Actual emitted H2 dependency bytes remain authoritative for the Go component;
the inverse view is not substituted into its installed-source receipt. The
native entry preloads the existing quota_remote and glm_keys modules through its
original authenticated loader, preserving foreign-module rejection and stable
cache ownership on repeated inspection. Source qualification and regenerated
artifact identities are recorded under review_evidence/fabric_application/
h6-recovery-20261107-c2. No live installation, selection or account admission is
implied by this optional artifact. H3 optimization remains excluded.

## Composed f57b085 x d0c543 qualification-quiescence join (2026-11-07)

The protected qualification-quiescence repair (f57b08549634a5d3ab75f1dbdca6926d9cc8d6b3)
joins the d0c543124b47372becd8ee632a1c29b32ffc3ef0 native staging head. The merged
candidate/lease_broker.py (disjoint edits on both sides) is the only manifest-member
change: ext/lease_broker.py moves from
a84752dc40598bbf8411d7b992d32cda6c76156d534c4925c2eca5083f097360 to
0bbf1ca05b655c30e895cebf63c914cbf97f9d17fc8b3e55c852fd4652ed8807 (211236 bytes), and
the recomposed manifest digest becomes
22905ae361e7076226aa239e947553433274c56f0c3db73c51cad0a317754ada.

The builder qualifies this endpoint additively: the host-pull integrity parent
closure accepts the composed parent
b590442c3e4099a708bf0f34e1a5623669e984bccb90a60f805a68873c5f4c75 (the composed
provider-application closure with the three host-pull members at their preimage
identities) and the composed go-application + application-http parent
b5ceff4116f5407810bfe755151de69ca0ce4fe3276b3e76a10a93e13909a68c beside the frozen
bcfb8c961c51a491cf66faaf697585675152bb6827ae1c070b9efcf5c7018c8e; the application
pool composition cohort accepts the quiescence broker successor for
ext/lease_broker.py only via the exact-or-composed pair; and the admission integrity
closure accepts the composed parent
06c6822a18e92c45519711a40be9cdac5baf4bfb6ddedcbe116922d9f6640741 when the raw view
still carries the exact sparse-preflight executor successor and the exact-or-composed
pool cohort. Every earlier parent constant, historical fixture and preimage remains
frozen; no prior endpoint is replaced or relabelled.
