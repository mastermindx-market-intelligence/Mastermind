# OHF-P1B Independent Architecture and Security Review

**Date:** 2026-08-20
**Commission:** OHF-P1B
**Frozen contract:** `mastermind.operator_harness/v1`
**Reconciled base:** `49c363a8b95d368aab249eff75b4d371cdc59c6c`
**Review boundary:** the complete uncommitted P1B delivery tree that will be
committed without source changes before an optional exact-SHA laboratory canary
**Code-to-canary verdict:** **PASS**

## 1. Independence and method

The review was deliberately split from implementation. An independent critic
first inspected the full implementation and reproduced release-blocking states
with local SQLite, fake App Server, process, and filesystem probes. The owners
of the runtime/schema and adapter/process slices then remediated their respective
findings. Finally, those owners exchanged slices and performed read-only
reciprocal review of code they did not author.

No review step called a live provider, read credential contents, registered a
worker, selected a production adapter, changed routing, migrated an authoritative
Executive database, or armed production.

## 2. Release blockers found and closed

The initial independent pass found four P1 defects on the then-current tree.
They were treated as hard release blockers despite green focused tests.

### 2.1 Cross-Attempt dispatch poisoning

`commit_provider_dispatch` previously admitted an operation by receipt kind
without proving the immutable Event and durable target belonged to the leased
Attempt. A second Attempt could write the first Attempt's dispatch marker and
force the rightful owner into `EFFECT_UNKNOWN`.

The final implementation validates, in one `BEGIN IMMEDIATE` transaction:

- exact command, aggregate, INTENT kind, Job, Attempt, worker, and quota;
- the operation-specific payload schema and exact key set;
- the durable epoch, generation, provider session, and turn target;
- `CURRENT` epoch state and held Executive writer authority; and
- the requested operation kind before appending the dispatch marker.

A two-Attempt regression proves the foreign lease is refused, leaves no poison
marker, and does not prevent the rightful Attempt from committing dispatch.

### 2.2 NULL-unsafe provider-session projection

The first v3 projection trigger used ordinary SQLite comparison semantics,
which permitted one side of the epoch/generation provider-session projection to
be `NULL` while the other carried `S1`.

The final INSERT and UPDATE triggers use NULL-safe `IS NOT` comparison. Raw SQL
tests reject `NULL/S1`, `S1/NULL`, and `S1/S2` projections. Lawful TX-3 remains
valid because it updates the epoch from `NULL` to `S1` before updating the
generation to `S1` in the same transaction.

### 2.3 TX-2 without a durable TX-1 seal

Raw SQL could previously stamp `execution_mode='OPERATOR_HARNESS'` with no
requested profile and reach TX-2 without a durable `OHF_PROFILE_SEALED` Event.

The final database boundary requires a non-null profile/digest pair for OHF
mode. The service boundary verifies the digest over canonical profile JSON, and
TX-2 independently requires the exact immutable TX-1 Event whose digest matches
the Attempt projection. A forged valid-looking projection without TX-1 is
refused before any epoch or generation is allocated.

### 2.4 Leader exit mistaken for whole-writer release

Graceful stop previously treated App Server leader exit `0` as sufficient even
when a descendant remained alive in the same private process group.

The final adapter consumes a typed `AppServerStopProof`. The laboratory client:

1. requires an attested private process group;
2. closes leader stdin and waits boundedly;
3. observes whether group members survive the leader;
4. applies group `SIGTERM`, then `SIGKILL` if needed; and
5. returns proof only after the private group is positively observed empty.

An inaccessible or ambiguous group becomes `UNKNOWN` and produces an
effect-unknown refusal. The adapter removes local worker ownership and returns
`PROVEN_DEAD + RELEASED` only after the typed proof and leader return code `0`.
A real fake-process regression covers a TERM-ignoring same-group descendant.

## 3. Other high-risk invariants rechecked

The completed review and regression matrix also cover:

- immutable epoch/generation identity and session projections;
- exact TX-3 and TX-11 target binding, including refusal to overwrite G1;
- proof-gated same-OperationId replay for TX-2, TX-5, and TX-10;
- APPLIED/EFFECT_UNKNOWN receipt exclusivity;
- candidate evidence provenance from exact TX-5 INTENT and APPLIED receipts;
- candidate and failure-detail persistence-boundary redaction;
- credential-home owner, mode, hardlink, and symlink-ancestry isolation;
- response-ID/notification demultiplexing during delayed interrupt;
- durable interrupt INTENT/dispatch/APPLIED/EFFECT_UNKNOWN orchestration;
- lease heartbeat, expiry fencing, and CAS supervisor takeover;
- legacy complete, fail, rate-limit, and cancel paths refusing to release a live
  OHF writer;
- typed reconcile observations before graceful writer release;
- offline TX-9 invalidation on the staged restore copy before atomic swap; and
- absence of production adapter registration, routing, or enablement.

## 4. Independent final verdicts

The reciprocal runtime/schema review returned **PASS**, with no P0, P1, or P2
finding. Its focused command ran 56 tests, and its decisive three-case replay
ran separately with all three passing.

The reciprocal adapter/process review returned **PASS**, with no P0, P1, or P2
finding. It exercised the real fake-process descendant containment cases and
the authoritative writer-release boundary. A read-only isolated probe also
confirmed that `PermissionError` while observing a process group is treated as
unprovable, never empty.

One low-priority evidence gap remains: the exact `PermissionError -> UNKNOWN ->
adapter effect-unknown` sequence is not a dedicated checked-in fake-process
test. The laboratory branch was directly exercised, the adapter boundary is
explicitly fail-closed, and the gap does not weaken the release verdict.

## 5. Exact pre-commit evidence

All commands below ran after remediation and final formatting on the frozen
delivery tree.

```text
python3 -m pytest -q -p no:cacheprovider \
  tests/test_ohf_*.py tests/test_codex_operator_adapter.py \
  tests/test_executive_os_sqlite.py tests/test_executive_backup.py
=> 196 passed

python3 -m pytest -q -p no:cacheprovider \
  tests/test_codex_operator_adapter.py tests/test_ohf_attestation.py \
  tests/test_ohf_auth_isolation.py tests/test_ohf_codex_app_server_probe.py \
  tests/test_ohf_p1a_minimal_surface.py tests/test_ohf_probe_inertness.py \
  tests/test_ohf_probe_redaction.py tests/test_ohf_probe_schema.py \
  tests/test_ohf_protocol_fidelity.py
=> 63 passed

python3 -m pytest -q -p no:cacheprovider \
  tests/test_executive_os_phase1fb.py tests/test_executive_wake_persist.py
=> 40 passed

python3 -m pytest -q -p no:cacheprovider \
  tests/test_executive_worker_auth_provisioner.py \
  tests/test_provider_identity_readiness.py
=> 44 passed

PYTHONDONTWRITEBYTECODE=1 <declared-python-3.12>/bin/python \
  scripts/ci_pytest.py
=> discovered=272 excluded=0 running=272; exit 0

python3 -m py_compile <all changed Python implementation files>
=> exit 0

git diff --check
=> exit 0
```

The host Python 3.14 sealed-regression sweep has one inherited failure in
`test_launchd_activated_unix_socket_is_reused_and_not_unlinked`. The same test
fails identically in a clean detached worktree at base `49c363a...`; the service
and test files are unchanged by P1B. The authoritative declared Python 3.12
repository gate is green.

## 6. Release boundary

This PASS authorizes only commit and the commission's optional, isolated,
read-only exact-SHA laboratory canary. It does not authorize production worker
registration, routing, provider credential changes, an authoritative database
migration, write-capable Codex use, or production arming. If the laboratory
preflight cannot prove every isolation gate, the canary is cancelled and the
code remains eligible for inert delivery with that null result reported.
