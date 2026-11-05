# Prospective original-parent collection recovery

Status: **F1 source repair qualified; uninstalled, pending the same principal reviewer’s adjudication**.
The four installed preimages are recorded in `BASE.json`; replacement bytes and
case-level evidence are in `QUALIFICATION.json`. This package is disjoint from
PR #1391's accepted `7739ce80c` test-only derivative and does not amend that release.

## Problem and behavior

An interrupted local `fabric_task.py` controller can leave a remote worker running
or completed while its result never reaches the original parent. A stale local log
cannot establish remote termination, cleanup, lease settlement, or retry authority.
Older runs did not retain enough producer-bound original launch evidence to admit
an arbitrary later collector. They remain on their existing owners and carriers.

A **new** ordinary request may explicitly select `--recoverable-return`. Canonical
routing still chooses an eligible GLM, Qwen or MiniMax Linux harness, provider
account and physical host. No route/model/host override, new queue, registry,
transport, worker lifecycle or credential store is added. Operators, qualification
runs, artifact-output contracts, local-M2 runs and existing IDs are excluded from
this opt-in profile. Legacy request behavior remains the default.

The adapter creates private per-run evidence, holds a kernel custody lock and
retains packet/root/assigning-parent/source/host identities before entering the
existing controller. The inherited descriptor survives the controller's Bash
command substitution. After existing broker admission, the controller binds its
exact nonsecret account and lease, support digest, controller generation and time
bounds once, before provider launch. It disables the ordinary admission relaunch
loop for this profile. It uses the existing SCP transport and this run's newly
created support upload directory.

The existing remote executor validates the binding, packet and executing support
closure before physical admission. It writes binding evidence before the existing
owned process executes. After that owner supplies a complete process and cleanup
receipt, the executor writes bounded stdout, process evidence and return code,
then fsyncs a terminal marker last. The private `/tmp/fabric-<scope hash>` directory
is created exclusively; no existing directory or result is adopted or altered.

The adapter's `collect-prospective` command enters the existing
`remote_sub.sh --collect-existing` branch **before** reservation, broker acquisition,
EXIT traps or launch logic. The original assigning native parent must match, and
collection must acquire the original custody inode. This excludes both a surviving
controller and another collector. Packet, source, support, host registry, generation,
lease/account and producer-result/cleanup bindings must agree. The existing fixed
artifact reader and bounded transport deliver only the private producer capsule.

A durable collection-intent precedes the single transport call. Lost response,
partial publication, changed source, or unavailable output cannot trigger a second
read. Final receipt/readback must be durable before `collection-result` can consume
its exact digest. **Collection does not release or renew a lease, launch/relaunch,
clear an effect, mutate accounting, or record acceptance.** It reports
`UNCHANGED_REQUIRES_EXISTING_OWNER` and `NOT_RECORDED` for those obligations. The
existing result and ledger owners must adjudicate any subsequent settlement.

## Bounds and proof limits

- Retained input at most 2 MiB; returned stdout at most 256 KiB. Exceeding the bound
  refuses collection; it is not an invitation to change the original run's limit.
- No collection is automatically scheduled. It is an explicitly admitted owner
  continuation through the existing adapter.
- Native IDs/environment values correlate the resource grant; they are not an
  authentication mechanism or permission to acquire another principal's custody.
- Original host/served-model authenticity is no stronger than the existing admitted
  harness. Local metadata is not a new cryptographic attestation.
- Final unknown publication stays unknown even if a partial receipt file exists.
- No old R2, GLM, MiniMax, Auth0, permission-refused or effect-unknown operation can
  gain prospective evidence through this code. No historical run was read here.
- This source proves neither installed recovery nor RuntimeBinding, idle Wake,
  automatic authenticated native return, lease settlement or parent acceptance.

## Verification

`test_prospective_completion.py`: **44 distinct cases, zero failures/errors/skips**,
retained in `f1-successor.xml`. The predecessor’s 40-case report remains unchanged
in `checks-final.xml`; it does not qualify the successor. Four discriminating F1
checks fail on predecessor source (`f1-old-red.xml`) and pass on the successor. Actual local process/custody tests use inert fixture
children only. The test suite executes the production remote executor, actual
process receipt/cleanup, retained capsule, exact generated read code, collector
publication, and assigning-parent consumption with fake transport/provider inputs.
On macOS, the literal Linux `/tmp` root is mapped to a private temporary fixture;
real file descriptors, no-follow checks, ownership/mode checks, fsync and flock
remain active. The subprocess inheritance test uses the real Bash command
substitution shape from the controller. These are **not** live remote canaries.

Negatives cover active/competing custody, interruption, wrong root/parent, source,
packet, support, host, lease/account/generation drift, cleanup uncertainty, partial
markers, symlinks, shared directory mode, corrupted output, missing producer
binding, lost read/publication/readback, duplicate collection and old-run adoption.

Compatibility run: 27 affected legacy cases passed. Two existing adapter tests
failed because their exact expected dictionaries omit the already-installed
`route_key` and `qualification_host` fields. Both failures were reproduced against
unchanged `base/fabric_task.py`; they are preserved, not hidden or amended here.
Three unrelated old fixture/platform cases were excluded and are not claimed as
passing. Exact selection and diagnostic paths are in `QUALIFICATION.json`.
Python syntax compilation and `bash -n` succeeded. Installed preimages were read
back unchanged after qualification; there was no installation or host effect.

## Existing integration path

1. Original Integrator reviews this immutable four-component package under the
   existing commission. Existing #1391 release continues independently.
2. Any findings are repaired in this same owned worktree; only affected checks are
   repeated. Do not create a replacement worker, review carrier or collector.
3. A later, explicitly permitted source/release interval must recheck all four
   installed preimages and dependencies, perform the existing release/install
   process, and qualify one **new** opted-in run and same-parent consumption.
4. The existing owners retain lease/accounting reconciliation and acceptance;
   no source-only test or collected byte stream settles those effects.

No install command or historical recovery command is included in this package.

## Principal review F1 — corrected dependency closure

The principal reviewer found that the collector imported and embedded the validator
from `remote_sub_exec.py` without including it in `completion_sources()`. The
successor adds that file to the fixed local source keys in both the binding schema
and collector. The existing prelaunch seal, collection admission and publication
rechecks now cover it. No new source path, validator loader or runtime owner is added.

The strengthened fixture copies the actual candidate dependency BEFORE begin/seal;
its reduced inert support manifest hashes those actual bytes. Four old-source REDs
cover change before seal, after binding/before transport, after transport, and
during publication. The admission negative verifies zero transport calls and no
collection intent or receipt. Later drift never publishes a consumable completion
or permits a second read. This is local source proof, not installation, historical
recovery, provider activity, or approval of the full package.
