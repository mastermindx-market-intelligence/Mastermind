# Executive Capacity CF2-H0 Source-Closure Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the installed promisor-style Macro H0 source with one fully closed ordinary Git
repository, archive the prior source/generation, and publish a new truthfully receipted six-file H0
generation without weakening or running CF2-P0.

**Architecture:** Extend the existing source-contract and artifact owners with a v2 complete-object
transport and pure closure verifier. A new root-only carrier uses the existing H0 lock and one
durable intent to verify a side-by-side candidate before installed mutation, archive/swap the old
source and generation, publish the new generation last, and reconcile crashes without deletion.
P0 receives only a later identity re-pin handoff.

**Tech Stack:** Python 3.9-compatible standard library, Git plumbing, macOS Bash 3.2 and native
filesystem tools, pytest, GitHub Actions, CodeQL.

**Spec:**
`docs/superpowers/specs/2026-08-27-executive-capacity-cf2-h0-source-closure-repair-design.md`

## Global Constraints

- Exact pickup base is protected Mastermind commit
  `be68ec881460aa60d7d77cdb69f7c1cae81f6310`; re-pin protected `origin/master` before review/merge.
- Exact Macro commit is `dcdd939c45b23abce5ba04f95e330ac914a3904b`; exact material digest is
  `35931b4ef965c5d67a7e01444dd483804e48671784716ea8196c94e925466650`;
  the material worktree inventory is the existing ordered eleven-path contract.
- The sanitized old-generation values in the spec are match gates, not proof of installed `.git`
  closure. Any mismatch refuses before installed mutation.
- Alternative B is fixed. Do not strip markers in place or weaken P0.
- Never put repair in `capacity_p0_acceptance.py` or `run-capacity-p0-proof.sh`. Do not edit P0 pins
  before repair merge and native install produce the new exact identities.
- Root is offline. Never read/enumerate provider homes or credentials, use Keychain, perform OAuth,
  call a provider, change/start/load/enable services, create/connect sockets, execute workers, route,
  implement CF2-I, fan out, or fail over.
- Reuse the H0 lock, roots, six-file generation, runtime, topology, telemetry, principals, rollback
  evidence, and canonical helper/contract owners. Create no duplicate state/control plane.
- Every implementation task is TDD: discriminating red test, observed failure, minimum green
  implementation, focused rerun, then a task-local commit.
- Preserve Python 3.9 and Bash 3.2. Do not use `tomllib`, `datetime.UTC`, `Path.is_relative_to`,
  `zip(strict=True)`, pattern matching, associative arrays, or GNU-only options.
- Never delete, reset, overwrite, recursively remove, or auto-retry ambiguous host state. Archive
  by exact verified atomic rename only.

---

## Planned file structure

- `ops/executive_os/capacity_source_contract.py` — v2 working/source/host schemas and truthful
  prior/current preparer provenance.
- `ops/executive_os/capacity_host_artifacts.py` — complete transport/materializer, pure closure/tree
  verification, and resumable intent/receipt publication.
- `ops/executive_os/prepare-capacity-host.sh` — future clean H0 uses v2; not the repair carrier.
- `ops/executive_os/repair-capacity-source-closure.sh` — privileged repair and verify-only carrier.
- `tests/test_executive_capacity_source_contract.py` — exact schema/provenance tests.
- `tests/test_capacity_host_artifacts.py` — transport, closure, metadata, digest/publication tests.
- `tests/test_executive_capacity_source_closure_repair.py` — order, crash, rollback, no-mutation.
- `tests/test_executive_capacity_host_preparation.py` — future clean H0 integration.
- `tests/test_executive_capacity_python39_compatibility.py` — Apple Python proof.
- `ops/executive_os/HOST_PREREQUISITES.md` — build, native ceremony, proof, and P0 handoff.

## Task 1: Freeze the v2 schemas and pure closure verifier

**Files:**

- Modify: `ops/executive_os/capacity_source_contract.py`
- Modify: `ops/executive_os/capacity_host_artifacts.py`
- Modify: `tests/test_executive_capacity_source_contract.py`
- Modify: `tests/test_capacity_host_artifacts.py`

**Interfaces:** Produces `SourceClosureEvidence`, `validate_source_closure_evidence`, v2 builders/
validators, `closed_tree_digest`, and exact repair intent/receipt schema validation.

- [ ] **Step 1: Add failing exact-schema tests**

Require these constants and seam:

```python
TRANSPORT_SCHEMA_V2 = "mastermind.capacity_source_transport/v2"
WORKING_DIRECTORY_IDENTITY_SCHEMA_V2 = "mastermind.executive_capacity_working_directory_identity/v2"
SOURCE_CONFIG_SCHEMA_V2 = "mastermind.executive_capacity_source_config/v2"
HOST_RECEIPT_SCHEMA_V2 = "mastermind.executive_capacity_host_preparation/v2"
SOURCE_REPAIR_INTENT_SCHEMA = "mastermind.executive_capacity_h0_source_repair_intent/v1"
SOURCE_REPAIR_RECEIPT_SCHEMA = "mastermind.executive_capacity_h0_source_repair/v1"

@dataclass(frozen=True)
class SourceClosureEvidence:
    object_count: int
    object_inventory_sha256: str
    source_tree_sha256: str
```

Test every exact field set from the spec. Prove refusal for bool/zero object counts, bad digests,
extra fields, stale `promisor_state=offline_no_remote`, stale current preparer `e4e44867...`, absent
prior provenance, wrong old hashes, or differing current preparer/repair commits.

- [ ] **Step 2: Run red**

```bash
python3 -m pytest -q \
  tests/test_executive_capacity_source_contract.py \
  tests/test_capacity_host_artifacts.py \
  -k 'v2 or closure or repair or provenance'
```

Expected: import/attribute failures for the absent v2 contract and evidence type.

- [ ] **Step 3: Implement minimum pure contracts**

Add explicit v2 functions; do not reinterpret v1. Reuse canonical JSON/digests. Implement:

```python
def closed_tree_digest(
    root: Path, *, expected_uid: int, expected_gid: int,
    approved_xattrs: frozenset[bytes] = frozenset({b"com.apple.provenance"}),
) -> str: ...
```

Use no-follow descriptor metadata, the exact row/framing law, and closed refusal for unsupported
types/links/ACLs/xattrs/owners/modes. Keep v1 validation for archived archaeology only.

- [ ] **Step 4: Prove green and commit**

```bash
python3 -m pytest -q tests/test_executive_capacity_source_contract.py tests/test_capacity_host_artifacts.py
/usr/bin/python3 -I -S -B -m py_compile \
  ops/executive_os/capacity_source_contract.py ops/executive_os/capacity_host_artifacts.py
git diff --check
git add ops/executive_os/capacity_source_contract.py ops/executive_os/capacity_host_artifacts.py \
  tests/test_executive_capacity_source_contract.py tests/test_capacity_host_artifacts.py
git commit -m "feat(exec): freeze complete H0 source closure contract"
```

## Task 2: Build the complete offline transport and ordinary materializer

**Files:**

- Modify: `ops/executive_os/capacity_host_artifacts.py`
- Modify: `tests/test_capacity_host_artifacts.py`
- Modify: `ops/executive_os/prepare-capacity-host.sh`
- Modify: `tests/test_executive_capacity_host_preparation.py`

**Interfaces:** Produces
`enumerate_reachable_objects(repository, commit) -> tuple[ObjectInventoryRow, ...]` and
`verify_complete_repository(source_root, manifest) -> SourceClosureEvidence`; future clean H0
consumes the same v2 materializer.

- [ ] **Step 1: Add failing complete-object tests**

Use a fixture whose commit reaches nonmaterial blobs. Require v2 closure/object count/inventory
digest and exact two-member ZIP. Mutate/remove a nonmaterial blob; add `.promisor`, alternate,
shallow, remote, partial-clone/filter config, replacement ref, linked object, unsafe metadata,
attached/dirty worktree, twelfth worktree file, pack trailer, or manifest/object type/size drift.
Prove deleting `.promisor` from an incomplete repository still refuses.

- [ ] **Step 2: Run red**

```bash
python3 -m pytest -q tests/test_capacity_host_artifacts.py \
  -k 'transport or materialize or complete or promisor or alternate or shallow'
```

Expected: failures because v1 intentionally builds a filtered/promisor repository.

- [ ] **Step 3: Implement complete transport/materialization**

Enumerate all reachable objects with missing-object refusal, batch-check `oid type size`, pack the
complete set, and bind semantic inventory independently of pack bytes. Materialize with `git init`
plus `index-pack`; never write `.promisor` or partial-clone config. Configure only fixed safe local
keys and sparse projection of the eleven paths. Require one pack/index pair, ordinary strict fsck,
complete inventory equality, clean detached status, forbidden-state absence, and safe metadata.

Update future `prepare-capacity-host.sh` to produce v2 receipts through this verifier; add no repair
branch to that script.

- [ ] **Step 4: Prove green and commit**

```bash
python3 -m pytest -q tests/test_capacity_host_artifacts.py tests/test_executive_capacity_host_preparation.py
/bin/bash -n ops/executive_os/prepare-capacity-host.sh
git diff --check
git add ops/executive_os/capacity_host_artifacts.py ops/executive_os/prepare-capacity-host.sh \
  tests/test_capacity_host_artifacts.py tests/test_executive_capacity_host_preparation.py
git commit -m "feat(exec): materialize complete offline Macro source"
```

## Task 3: Add the crash-safe host repair carrier and rollback/recovery

**Files:**

- Create: `ops/executive_os/repair-capacity-source-closure.sh`
- Create: `tests/test_executive_capacity_source_closure_repair.py`
- Modify: `ops/executive_os/capacity_host_artifacts.py`
- Modify: `tests/test_capacity_host_artifacts.py`

**Interfaces:** Consumes the v2 verifier/materializer and existing lock/roots. Produces one intent
archive, archived old source/generation, one repair receipt, one current six-file generation, and
zero-write `--verify-only`.

- [ ] **Step 1: Add failing publication/reconciliation tests**

Require:

```python
def build_source_repair_intent(**fixed_fields: Any) -> dict[str, Any]: ...
def publish_source_repair_intent(
    archive: Path, value: Mapping[str, Any], *, expected_uid: int
) -> str: ...
def build_source_repair_receipt(**fixed_fields: Any) -> dict[str, Any]: ...
def reconcile_source_repair(
    archive: Path, *, expected_uid: int
) -> SourceRepairPosition: ...
```

Test canonical-plus-LF bytes, intent-ID law, no-follow single-link publication, file/directory
fsync, exact idempotent resume, and refusal for prefix drift, two intents, changed payload under the
same ID, extra members, ambiguous positions, or tree-digest mismatch.

- [ ] **Step 2: Add failing Bash order/scope tests**

Require exact order: preflight → H0 lock → candidate build/verify → intent fsync → old source archive
→ candidate install → old generation archive → full reverify → repair receipt → hidden six-file
generation verify → full reverify → final generation rename. Require exact argv and old hashes.
Forbid `rm`, recursive copy, network, credential/provider paths, service-changing launchctl verbs,
socket operations, P0 runner, and worker execution.

- [ ] **Step 3: Run red**

```bash
python3 -m pytest -q tests/test_capacity_host_artifacts.py \
  tests/test_executive_capacity_source_closure_repair.py
```

Expected: absent publication helpers and repair script.

- [ ] **Step 4: Implement minimum carrier**

Use Bash 3.2 `set -euo pipefail`, `umask 077`, fixed roots/tools, and one cleanup trap. Preflight the
sealed repair checkout and preserved H0 state. Acquire the existing lock, reconcile the exact
intent, copy one operator transport by no-follow helper, fully build/verify the candidate, then
publish intent before installed mutation. Atomic-rename and fsync both parents at every move. Bind
the external repair receipt in a v2 host receipt without adding a seventh generation file. Make the
final generation rename the last semantic filesystem mutation.

Implement exact pre-commit restoration/archive law. Restore only intent-bound exact old trees;
archive failures; never delete or overwrite. Ambiguous durability/path state returns exit 70.

- [ ] **Step 5: Add crash-point and verify-only tests**

Using a temporary host adapter, interrupt after each candidate write/fsync, directory fsync,
old-source move, install, old-generation move, receipt publication, hidden-generation move, and
pre-commit point. Same-carrier resume must reach exactly one commit or exact rollback. Assert all
bytes remain archived. Run verify-only twice and prove identical scoped pre/post digests, no lock/
intent write, no launchd change, and no filesystem mutation.

- [ ] **Step 6: Prove green and commit**

```bash
python3 -m pytest -q tests/test_capacity_host_artifacts.py \
  tests/test_executive_capacity_source_closure_repair.py
/bin/bash -n ops/executive_os/repair-capacity-source-closure.sh
git diff --check
git add ops/executive_os/capacity_host_artifacts.py \
  ops/executive_os/repair-capacity-source-closure.sh \
  tests/test_capacity_host_artifacts.py tests/test_executive_capacity_source_closure_repair.py
git commit -m "feat(exec): add crash-safe H0 source closure repair"
```

## Task 4: Close the runbook and Apple Python/Bash compatibility

**Files:**

- Modify: `ops/executive_os/HOST_PREREQUISITES.md`
- Modify: `tests/test_executive_capacity_python39_compatibility.py`
- Modify: `tests/test_executive_capacity_source_closure_repair.py`
- Modify: `tests/test_executive_capacity_host_preparation.py`

**Interfaces:** Consumes the exact ceremony contract and helper CLIs. Produces one nonprivileged
build procedure, one offline administrator ceremony, and Apple Python/Bash proof.

- [ ] **Step 1: Add failing runbook/compatibility tests**

Require the runbook to name alternative B, exact old gates, complete v2 transport, no root network,
exact merged repair checkout, one H0 lock/intent, archive-only swap, generation-last commit, two
verify-only passes, explicit P0 re-pin, and every credential/service/socket/worker/CF2-I hold.

Run v2 manifest, object inventory, closure verifier, intent, and receipt pure paths under
`/usr/bin/python3 -I -S -B`. Exercise empty Bash arrays, interrupted canonical-file candidates, and
fixed exit rendering with Bash 3.2-compatible syntax.

- [ ] **Step 2: Run red**

```bash
python3 -m pytest -q \
  tests/test_executive_capacity_python39_compatibility.py \
  tests/test_executive_capacity_source_closure_repair.py \
  tests/test_executive_capacity_host_preparation.py \
  -k 'python39 or runbook or bash or output'
```

Expected: missing new procedure and compatibility coverage.

- [ ] **Step 3: Document exact build/native ceremonies**

Document commands to build the v2 transport from the accepted local Macro commit, record its
SHA-256, seal a detached direct Mastermind checkout at the merged repair SHA, and pass only the
transport path/digest/operator into one native administrator dialog. Document one repair invocation
and two separate `--verify-only` invocations, exact stdout/exits, archive retention, sanitized proof,
and the P0 hold. Do not invent a future merge SHA or generation digest.

- [ ] **Step 4: Make compatibility green**

Keep helpers standard-library-only and Apple-Python importable. Use explicit Bash array-length
guards and fixed `/usr/bin/printf`. Avoid GNU/Bash 4 behavior.

- [ ] **Step 5: Prove green and commit**

```bash
python3 -m pytest -q tests/test_executive_capacity_python39_compatibility.py \
  tests/test_executive_capacity_source_closure_repair.py \
  tests/test_executive_capacity_host_preparation.py
/usr/bin/python3 -I -S -B -m py_compile \
  ops/executive_os/capacity_source_contract.py ops/executive_os/capacity_host_artifacts.py
/bin/bash -n ops/executive_os/prepare-capacity-host.sh
/bin/bash -n ops/executive_os/repair-capacity-source-closure.sh
git diff --check
git add ops/executive_os/HOST_PREREQUISITES.md \
  tests/test_executive_capacity_python39_compatibility.py \
  tests/test_executive_capacity_source_closure_repair.py \
  tests/test_executive_capacity_host_preparation.py
git commit -m "docs(exec): close H0 source repair ceremony"
```

## Task 5: Independent review, hosted CI, merge, native repair, and two verify-only passes

**Files:** no planned code edits; findings return to the owning task.

**Interfaces:** Consumes exact current head, protected-base pin, one operator-built v2 transport,
and one native administrator dialog. Produces exact merge/install/proof identities.

- [ ] **Step 1: Run fresh exact-head local verification**

```bash
git status --short
git rev-parse HEAD
git diff --check origin/master...HEAD
python3 scripts/ci_pytest.py --plan-only
python3 -m pytest -q \
  tests/test_executive_capacity_source_contract.py \
  tests/test_capacity_host_artifacts.py \
  tests/test_executive_capacity_host_preparation.py \
  tests/test_executive_capacity_source_closure_repair.py \
  tests/test_executive_capacity_python39_compatibility.py \
  tests/test_capacity_broker_topology.py tests/test_executive_launchd_config.py
/usr/bin/python3 -I -S -B -m py_compile \
  ops/executive_os/capacity_source_contract.py ops/executive_os/capacity_host_artifacts.py
/bin/bash -n ops/executive_os/prepare-capacity-host.sh
/bin/bash -n ops/executive_os/repair-capacity-source-closure.sh
```

Require clean head, zero excluded CI tests, and mutation evidence that removing any closure check is
killed.

- [ ] **Step 2: Obtain independent adversarial review**

Review exact head against complete ordinary closure, metadata, byte framing, intent/crash/rollback,
final rename, prior/current preparer truth, P0 separation, and forbidden host behavior. Any blocker
returns to TDD repair and fresh exact-head review.

- [ ] **Step 3: Publish one PR and require hosted exact-head proof**

Re-pin `origin/master`; reconcile Skillpack/H0/P0/source movement before push. Require hosted CI and
CodeQL on the current PR head. Green CI is implementation proof, not installed H0/P0 proof. Re-pin
head/base immediately before protected merge.

- [ ] **Step 4: Build/verify one complete transport outside privilege**

Using the merged helper and accepted local Macro repository, build one v2 transport. Record its ZIP
and manifest SHA-256, object count/inventory digest, and material digest. Independently extract and
verify in a disposable non-root path. Missing objects or semantic drift stop the ceremony.

- [ ] **Step 5: Run one native repair ceremony**

From a sealed root-owned detached checkout at the repair merge, run the repair exactly once. Require
exit 0 and exact stdout `H0_SOURCE_CLOSURE_REPAIR_PASS_NOT_P0_ACCEPTED\n`. On exit 70 reconcile the
same intent/carrier; do not create another transport/archive/operation. Any mismatch holds P0.

- [ ] **Step 6: Run two independent verify-only passes**

Invoke the exact merged carrier twice with `--verify-only`. Each must emit exactly
`H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED\n`. For each, require identical pre/post scoped digests,
archived old trees, one visible new generation, complete source closure, disabled/unloaded labels,
and absent sockets.

- [ ] **Step 7: Record the boundary**

Mark H0 closure `PROVEN_LIVE` only after both passes. Keep P0 `BUILT_NOT_PROVEN`/held. Do not run P0,
OAuth, services, providers, routing, workers, or CF2-I.

## Task 6: Hand off exact new identities to a separate CF2-P0 re-pin carrier

**Files:** no repair-carrier edits; the later P0 carrier owns its own diff/proof.

**Interfaces:** Consumes Task 5 merge/native receipts. Produces one bounded continuation packet.

- [ ] **Step 1: Assemble the continuation packet**

Include repair PR/merge; current preparer/repair commits; transport/manifest hashes; object count/
inventory digest; new generation/source-config digest; all six new generation hashes; repair receipt
hash; archived old tree digests and `e4e44867...` provenance; repair/two-verify sentinels; zero-write
evidence; holds and contradictions.

- [ ] **Step 2: State exact P0 re-pin work**

The later carrier rebases immutable Task 3 head
`e315ba003511dd1b52ef7a41da2a7d6bb187621b` onto current protected master, replaces old H0 pins only
with observed Task 5 values, validates v2 receipts, and calls the pure closure verifier instead of
assigning `lazy_fetch_impossible=True`. It then repeats independent review, hosted CI, merge, and
native P0 proof.

- [ ] **Step 3: Stop**

Do not edit/run P0 in this carrier and do not infer `GROUNDED_CF1_GIT_RELEASE_PATH_ACCEPTED` from H0
repair. Return to Sol with CF2-I, OAuth, services, providers, routing, workers, fan-out, and failover
held.
