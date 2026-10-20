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
Six new helpers bring the proposed native generation to 81 files. No recursive
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
