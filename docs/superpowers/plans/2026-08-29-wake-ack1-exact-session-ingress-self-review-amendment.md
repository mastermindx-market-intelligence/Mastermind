# Wake ACK1 Exact-Session Ingress — Self-Review Amendment

**Status:** PLAN_ONLY / RECORDS_ONLY / NOT_BUILT. This file changes no source/runtime behavior.

**Execution precedence:** this amendment **supersedes conflicting or less-specific instructions** in `docs/superpowers/plans/2026-08-29-wake-ack1-exact-session-ingress.md`; the parent plan remains controlling everywhere else.

**Current protected source reviewed:** `Mastermind@990b5b6c10ca9acb2f5fa42405c688c3b2abe2fc`, Skillpack `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1. Protected predecessors are #257 RuntimeBinding, #262 current-owner architecture, #254 persisted Wake carrier, and Worker Browser B1 / #153. W3A #250 remains the sole unprotected current-delivery candidate at `85ba1246b376f6264e59671fd0e228a60866afff`; this plan repair authorizes no ACK1 implementation START.

## Why this amendment exists

Plan self-review found a second protected-source mismatch that the parent plan's original Task 1 did not fully state:

```python
TERMINAL_CLOSE = frozenset(
    {LedgerPhase.TARGET_ACKNOWLEDGED, LedgerPhase.SOURCE_RESOLVED}
)
```

Current `assert_causal()` then treats a different later member of that set as `conflicting terminal close`, while `reconstruct_status()` returns the first member it sees. The result is wrong in both directions:

1. `SOURCE_RESOLVED` may currently be persisted without a prior `TARGET_ACKNOWLEDGED` record.
2. Once `TARGET_ACKNOWLEDGED` exists, the constitutionally required later `SOURCE_RESOLVED` record is rejected as a conflicting close.

The protected Wake split spec requires the sequence:

```text
DELIVERED
-> TARGET_ACKNOWLEDGED
-> canonical source reread
-> SOURCE_RESOLVED
```

Therefore ACK1 must repair the existing canonical Wake ledger state machine itself. It must not add a resolver daemon, alternate status table, special canary bypass, or synthetic combined ACK+resolution receipt.

The current-owner review adds a separate acquisition correction. A control-side App Server/reader cannot prove what the target's current provider turn consumed. Raw provider/model bytes remain inside the existing worker-local current `CodexOperatorAdapter` generation/client. The existing WorkerBroker/OHF `ohf-deliver-attention` path may return only a closed authenticated exact-turn projection after matching target Attempt, generation, binding, provider session/native turn, nudge and terminal-trailer reduction. Accepted timeout/effect-unknown retains the W3A fence; it does not authorize a read, retry, failover, or optimistic fence clear.

The Wake obligation's `attempt_id` is source correlation. Canonical root/workstream/seat routing selects the target, and the worker projection names the distinct target current Attempt whose RuntimeBinding is reprojected under the ACK transaction. An ambiguous source-Attempt/target-Attempt join refuses.

---

## Amendment A — Global causal law

Add these requirements to the parent plan's Global Constraints:

- `TARGET_ACKNOWLEDGED` **closes further delivery/nudging** for that obligation but is not the final Wake stream close.
- `SOURCE_RESOLVED` is the final source-resolution close and requires one prior valid `TARGET_ACKNOWLEDGED` record for the same obligation.
- No `DELIVERY_ATTEMPT`, `ACCEPTED`, `DELIVERED`, `FAILED`, or `TARGET_UNAVAILABLE` record may follow `TARGET_ACKNOWLEDGED`.
- One `SOURCE_RESOLVED` record may follow the ACK; its stable command id remains `<WAKE-ID>:RESOLVED` and existing Executive-event replay/conflict law remains authoritative.
- `reconstruct_status()` must return `SOURCE_RESOLVED` when a valid resolution follows ACK; otherwise an ACKed unresolved obligation returns `TARGET_ACKNOWLEDGED`.
- Existing `eligible_for_nudge()` must continue to refuse both ACKed and resolved obligations.
- Human-operator ACK remains a valid acknowledgement mode for source-resolution ordering; the exact-delivery/current-RuntimeBinding proof requirement remains specific to `AckMode.REASONING_SESSION`.

---

## Amendment B — Task 1 RED sequence replaces the parent Task 1 Step 5 expectation

The parent line:

```text
Expected: only the new ACK-evidence tests fail; existing transport/retry/source-resolution laws remain green.
```

is superseded. Current source-resolution ordering is itself intentionally RED.

Before changing `wake_ledger.py`, add these discriminating tests alongside the parent Task-1 tests.

### B1. Resolution without acknowledgement is RED

```python
def test_source_resolution_without_ack_is_causally_refused() -> None:
    obligation = _wake_obligation()
    resolution = resolve_source(
        obligation,
        code=expected_resolution_code(obligation),
        health=SourceReadHealth.HEALTHY,
        source_present=False,
        snapshot_digest="1" * 32,
    )
    with pytest.raises(WakeLedgerError, match="TARGET_ACKNOWLEDGED"):
        assert_causal(
            (
                requested_record(obligation),
                resolved_record(obligation, resolution),
            )
        )
```

This must fail against protected pre-ACK1 source because current `assert_causal()` accepts that sequence.

### B2. ACK followed by resolution is RED

Construct one valid delivery + reasoning-session ACK using the parent plan's new binding-generation/delivered-command evidence, then append a healthy resolution:

```python
records = (
    requested_record(obligation),
    attempt_record(delivery_attempt, LedgerPhase.DELIVERY_ATTEMPT),
    attempt_record(delivery_attempt, LedgerPhase.DELIVERED),
    ack_record(obligation, ack),
    resolved_record(obligation, resolution),
)
assert_causal(records)
assert reconstruct_status(obligation.obligation_id, records) is ObligationStatus.SOURCE_RESOLVED
```

Expected against protected pre-ACK1 source: RED with the current `conflicting terminal close` behavior.

### B3. Delivery after acknowledgement is RED

After a valid ACK, attempt to append any later attempt-scoped record and require:

```text
WakeLedgerError: no further delivery after TARGET_ACKNOWLEDGED
```

Use at least `DELIVERY_ATTEMPT` as the discriminator; do not rely only on `eligible_for_nudge()`.

### B4. ACKed-but-unresolved status remains distinguishable

For:

```text
WAKE_REQUESTED -> DELIVERY_ATTEMPT -> DELIVERED -> TARGET_ACKNOWLEDGED
```

require:

```python
reconstruct_status(...) is ObligationStatus.TARGET_ACKNOWLEDGED
eligible_for_nudge(...) is False
```

Then append `SOURCE_RESOLVED` and require status to advance to `SOURCE_RESOLVED` without changing the ACK event.

### B5. Duplicate close controls

Require direct synthetic causal streams with duplicate ACK or duplicate SOURCE_RESOLVED records to refuse. Normal persistence replay still reconciles through the stable command id and should not produce duplicate records in the first place.

---

## Amendment C — Task 1 implementation: split delivery close from final source close

Replace the current conflated `TERMINAL_CLOSE` state-machine concept inside `control_plane/wake_ledger.py` with two explicit concepts. Exact local names may follow repository style, but the implementation must have this semantics:

```python
DELIVERY_CLOSED_PHASES = frozenset(
    {
        LedgerPhase.TARGET_ACKNOWLEDGED,
        LedgerPhase.SOURCE_RESOLVED,
    }
)
FINAL_SOURCE_CLOSE = LedgerPhase.SOURCE_RESOLVED
```

`TERMINAL_CLOSE` is currently local to `wake_ledger.py`; no external compatibility consumer was found in the protected-source code census. Do not preserve the old name if doing so obscures the two meanings.

### C1. `reconstruct_status()` exact ordering

Do not use "first terminal record wins." Resolve status by explicit phase presence after `assert_causal`-compatible parsing:

```python
phases = {record.phase for record in scoped}
if LedgerPhase.SOURCE_RESOLVED in phases:
    return ObligationStatus.SOURCE_RESOLVED
if LedgerPhase.TARGET_ACKNOWLEDGED in phases:
    return ObligationStatus.TARGET_ACKNOWLEDGED
```

Only then evaluate destination-scoped delivery attempt state.

### C2. `assert_causal()` exact state variables

Replace the single `closed: LedgerPhase | None` logic with explicit booleans:

```python
ack_seen = False
source_resolved = False
```

When processing `TARGET_ACKNOWLEDGED`:

1. refuse a second ACK record in the causal sequence;
2. refuse ACK after `SOURCE_RESOLVED`;
3. perform the parent plan's acknowledgement validation;
4. for `AckMode.REASONING_SESSION`, require the exact earlier matching `DELIVERED` record and binding-generation evidence described in the parent plan;
5. set `ack_seen = True`.

When processing `SOURCE_RESOLVED`:

1. require `ack_seen is True` or raise a message containing `TARGET_ACKNOWLEDGED`;
2. refuse a second source-resolution record;
3. preserve all existing `source_ref`, `source_kind`, `expected_resolution_code`, health, absence, timestamp and snapshot-digest validation;
4. set `source_resolved = True`.

When processing any `ATTEMPT_PHASES` record:

```python
if ack_seen or source_resolved:
    raise WakeLedgerError("no further delivery after TARGET_ACKNOWLEDGED")
```

Then preserve all existing attempt ordering/terminal rules unchanged.

### C3. Human ACK ordering

A valid `AckMode.HUMAN_OPERATOR` record sets `ack_seen = True` after its existing operator-authority validation. It does not need provider `DELIVERED` evidence unless a later separate source law explicitly requires that. `SOURCE_RESOLVED` may then follow after the independent healthy canonical source reread.

### C4. Event identity stays unchanged

Do not change:

```text
ACK command id      = <WAKE-ID>:ACK
RESOLVED command id = <WAKE-ID>:RESOLVED
```

Do not merge the two records or copy resolution evidence into the ACK payload.

---

## Amendment D — Task 1 GREEN condition

Task 1 is green only when **both** groups pass:

1. exact reasoning-session ACK-to-DELIVERED/binding-generation tests from the parent plan;
2. source-resolution sequencing tests from this amendment.

Run:

```bash
python -m pytest \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  tests/test_executive_wake_persisted_dispatch.py \
  -q
```

Required semantic result:

```text
DELIVERED without ACK -> DELIVERED_UNACKNOWLEDGED
ACK without matching DELIVERED (reasoning session) -> REFUSE
SOURCE_RESOLVED without any valid ACK -> REFUSE
matching DELIVERED -> exact-session ACK -> TARGET_ACKNOWLEDGED
TARGET_ACKNOWLEDGED -> later delivery -> REFUSE
TARGET_ACKNOWLEDGED -> healthy source-absent resolution -> SOURCE_RESOLVED
```

The parent Task-1 commit remains one coherent Wake-ledger change:

```bash
git commit -m "fix(exec): bind Wake ACK to delivery and source resolution"
```

---

## Amendment E — Task 5 source-resolution proof

Parent Task 5 Step 5 is retained but becomes a **direct regression of Task 1**, not an assumption about pre-existing law.

The end-to-end test must prove all three distinct status snapshots in order:

```python
assert reconstruct_status(oid, delivered_records) is ObligationStatus.DELIVERED_UNACKNOWLEDGED
assert reconstruct_status(oid, acked_records) is ObligationStatus.TARGET_ACKNOWLEDGED
assert reconstruct_status(oid, resolved_records) is ObligationStatus.SOURCE_RESOLVED
```

Also assert `eligible_for_nudge(...) is False` after ACK and remains false after source resolution.

The canonical source reread remains independent. The ACK target/model never supplies `source_present`, source-resolution code, snapshot digest or source-resolution evidence refs.

---

## Amendment F — Task 6 live canary ordering

The live canary's final sequence is explicitly:

```text
real exact-thread provider DELIVERED evidence
-> DELIVERED_UNACKNOWLEDGED
-> target-originated opaque MASTERMIND_WAKE_ACK marker
-> trusted exact-session ingress
-> TARGET_ACKNOWLEDGED
-> mutate the isolated harmless canonical source condition through its owning Executive API
-> healthy canonical source reread proves source absent
-> existing resolve_source()/resolved_record() path
-> SOURCE_RESOLVED
```

The canary must record all three durable command ids separately:

```text
<WAKE-ID>:A<N>:DELIVERED
<WAKE-ID>:ACK
<WAKE-ID>:RESOLVED
```

No step may claim the final state from one combined receipt.

---

## Amendment G — Plan placeholder/type review

The parent plan uses Python `...` only in **interface-signature illustrations**, not as permission to leave implementation bodies incomplete. Workers must implement the concrete behavior specified step-by-step in the parent plan and this amendment; no literal `pass`, `...`, TODO/TBD or stub body is an accepted deliverable.

Exact new public signatures after combining the parent plan + this amendment are:

```python
# control_plane.wake_ledger
def acknowledge(
    obligation: WakeObligation,
    *,
    trusted: TrustedAckContext,
    claimed_obligation_ids: Sequence[str],
    delivered_command_id: str | None = None,
) -> WakeAcknowledgement:
    # full validation described in parent Task 1; no stub body


# control_plane.wake_persist.WakeLedgerRepository
def list_ledger_records_on_connection(
    self,
    connection,
    obligation_id: str,
) -> tuple[WakeLedgerRecord, ...]:
    # active-transaction validation + existing event read


def append_records_on_connection(
    self,
    connection,
    items: Sequence[tuple[WakeLedgerRecord, WakeObligation | None]],
    *,
    actor: str = WAKE_EVENT_ACTOR,
) -> tuple[PersistedWakeEvent, ...]:
    # existing causal/replay/_append_one logic on caller transaction


# control_plane.wake_ack_ingress
def acknowledge_consumed_wakes(
    runtime: Runtime,
    registry: SessionTargetRegistry,
    *,
    claim: WakeAckClaim,
    trusted: TrustedWorkerWakeAckProjection,
) -> tuple[PersistedWakeEvent, ...]:
    # one BEGIN IMMEDIATE transaction, target-current RuntimeBinding proof, atomic ACK append


# existing W3A current-owner path only
# CodexOperatorAdapter.deliver_attention -> AttentionTurnObservation
# -> WorkerBroker ohf-deliver-attention -> RemoteCodexOperatorAdapter
# -> CodexCurrentWriterWakeClient -> TrustedWorkerWakeAckProjection
# No new App Server/client/reader/endpoint is permitted.
```

The data classes remain exactly as frozen in the parent plan. `WakeAckClaim.obligation_ids` is nonempty, unique and canonically sorted; duplicate input is a refusal, not silent deduplication.

---

## Self-review result

After applying this amendment's precedence, the plan covers every protected split-spec acceptance boundary discovered in current source:

- exact target delivery evidence before reasoning-session ACK;
- exact current RuntimeBinding/generation/native-conversation verification;
- exact target current Attempt distinguished from the Wake source Attempt;
- worker-local exact-turn reduction through the existing generation/client and broker operation;
- accepted timeout/effect-unknown retains the current-generation fence until exact same-owner completion reconciliation;
- same Executive transaction for current-binding proof + ACK append;
- model-authored surface restricted to opaque Wake ids;
- identical replay/idempotence and changed replay conflict;
- delivery remains distinct from ACK;
- ACK closes delivery but does not falsely close source resolution;
- source resolution is impossible before ACK and lawful after ACK;
- no raw provider session/native turn or model text in durable Wake events;
- no new queue/ledger/session/lock/lifecycle plane;
- production arming remains independent;
- first real proof remains Codex/OHF only.

No implementation START or merge is authorized by this records amendment.
