# Original planner request custody during G1 recovery

`OperatorHarnessRegistry._require_orchestration_g1_recovery_predicate` now
uses the original TX-5 `_require_turn_intent` and `_require_turn_applied`
validators. The former duplicated only the legacy v1 receipt shape, so a
valid v2 retained Codex request was classified as incomplete evidence.
The shared validators retain the exact Attempt, worker, session, G1, turn,
operation, selected producer and acknowledged native request. They also
require the original provider-dispatch receipt without a conflicting
unknown-effect receipt. Native request acknowledgment remains distinct
from a valid result or an admitted plan.

## A valid receipt does not authorize another turn

The existing bound Codex planner contract requires its original G1 turn.
`reserve_turn` and provider dispatch already reject a bound planner turn
on G2. Accepting the v2 receipt in the old recovery reader without another
check would allocate and resume G2 before the later turn reservation
refused. The reader therefore reports an explicit retained-custody
boundary before TX-10 changes a generation, releases the original
Executive writer, writes a resume intent or calls the provider.

The original Attempt, native request, immutable producer selection and
receipt remain retained for reconciliation. A matching current frontier
selection cannot authorize a replacement operation. No new planner,
request schema, native turn, grant or recovery queue is introduced.

Legacy v1 recovery retains its prior semantics, including its requirement
for a nonempty acknowledged native turn ID, exact released/dead original
process evidence and absence of competing durable work. Existing live-G1
and sealed-result reconciliation remain independent positive paths.

## Proof and remaining design

`tests/test_operator_g1_turn_custody_recovery.py` exercises the actual
Runtime transaction owner with disposable original-root and nested
planner fixtures. It validates v2 original-request reads, then proves
that an unsupported G2 reservation leaves every event, epoch and process
generation unchanged. Corrupt producer, missing custody or dispatch,
foreign operation or native turn, malformed request digest, downgraded
receipt and contradictory unknown-effect cases are refused before that
boundary. The tests restore the actual event immutability triggers after
constructing corrupt retained fixtures.

The frontier restart test now checks the concrete custody refusal and
zero allocation, new turn, provider resume, stop or read, with the
original turn evidence and producer unchanged. It does not merely accept
an unspecified ambiguity result. The incumbent legacy v1 restart test
still proves a completed same-session recovery through the real Runtime
and supervisor with an inert physical provider.

Recovering a dead bound planner by observing its original native turn is
a separate owner-level design. It must retain the original native request
and materialization custody and qualify a supported read/reconciliation
operation. This increment neither proves that capability nor substitutes
a fresh G2 request for it. It changes no deployment, source activation or
native-origin boundary.
