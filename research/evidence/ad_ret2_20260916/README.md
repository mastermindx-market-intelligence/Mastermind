# AD-RET2 Phase A — durable turn-boundary semantic yield

**Packet:** `autonomy-closure-05-20260916`  
**Capability:** `BUILT_NOT_PROVEN` for Phase A; `PARTIAL` for the assigned journey.  
**Production activation / same-worker continuation:** NOT PROVEN; HOLD.

## Custody and exact source boundary

Parent `agent-fabric-end-to-end-fable-integration-20260913-sol-001`; existing
carrier `C0BSBM78V1N/1789324397.992989`. The incumbent is Claude8 seat
`aa22a3d2-2778-41c7-b61a-6a0e1a81e6c3`. This deliberately delivered Web receiver
uses Slack ChatGPT3; it has no established Executive native RuntimeBinding.

Sol ruling `1789552944.586199` and continuation `1789553094.118549` assigned this
same packet/branch the ONE Phase-A source writer. Source START is
`1789553262.921679`; the subsequent same-key START `1789553419.368249` is recorded,
not interpreted as a new child or writer transfer. Source custody is retained
pending exact-head review/disposition; packet06 remains qualification-only.

Protected/test base: `8ba7deedde164c90298d3e88785d98e02fa5e2d2`.
Managed branch: `sol/autonomy-closure-05-20260916`.
Only production changes: `control_plane/operator_harness_orchestrator.py`,
`control_plane/executive_operator_harness_port.py`, `control_plane/executive_runtime.py`.
Focused test: `tests/test_ad_ret2_turn_boundary.py`. Evidence stays in this directory.

Codex adapter, supervisor, broker, remote adapter, service, laboratory, provider
configuration and host installation remain unchanged. No new loop, queue,
reader, lock service, registry, authority owner or database schema/table is added.
`DIAGNOSIS_PRE_START.md` is historical and its writer-hold conclusion is superseded.

## Before → after

Before, `run_turn` could persist observations only after candidate collection.
A material yield with no candidate lost the semantic observation, although the
already-applied turn was correctly fenced against replay.

Now an explicitly capable caller uses `run_turn(..., allow_semantic_yield=True)`.
After a bounded normalized batch ends with one native `turn/completed` marker,
one material `BLOCKED` or `DECISION_REQUEST` is validated and committed independently
of candidate/role completion. The caller receives `OperatorYieldReceipt`, with
no candidate and no authority to choose a target or resume work. The flag selects
the return contract; it does not replace or bypass Runtime admission.

The default remains False for terminal-only callers. This prevents silently
handing a new return type to consumers that still parse/stop terminal work.
Real native semantic emission and actual consumer integration remain unbuilt
in this slice; synthetic normalized events are not provider qualification.

## Durable contract

`ExecutiveOperatorHarnessPort.record_operator_semantic_yield` delegates to the
existing `OperatorHarnessRegistry.record_semantic_yield` transaction. Shared
`_verified_turn_evidence` retains the exact original TX-5 INTENT/APPLIED provenance
checks used by candidate evidence. Runtime derives Job/Attempt/Worker, epoch,
generation, provider session/native turn and source revision from leased owners,
not model text. `source_revision` is the sealed worker-workspace base SHA, not
an invented installed-host release identity. An unknown root remains unknown.

Material payload is closed: existing Dialogue-validated `body`,
`source_event_time_ms` (nullable), and `replaces_event_id` (must be null in Phase A).
Only paused material work qualifies. Bounds: 64 events, 64 KiB canonical batch,
8 levels, 4096 nodes; non-JSON keys, ambiguous material event IDs, subordinate
claims, mixed ruling/result/STOP, wrong scope, unowned generations and unsupported
corrections refuse. Original source time is distinct from event observation time.

`OHF_SEMANTIC_YIELD_OBSERVED` uses the existing Event store and command
`ohf-semantic-yield:<exact-turn-id>`. Same identity/content replays once; changed
canonical source conflicts. The digest precedes redaction, preventing redaction
from collapsing distinct source claims. Candidate and semantic acceptance are
mutually exclusive. PROGRESS cannot replace an outstanding decision.

Target resolution is explicitly `PENDING_ACTION_TARGET`: target null, delivery
`NOT_PROJECTED`, consumption null, authority false. This is NOT a fabricated
Dialogue/Wake delivery or accepted response. Existing target/Dialogue/Wake owners
must supply those later. The existing TX-5 reservation owner refuses new or
pre-reserved work on that Attempt after a pending yield. No new clearing/decision API is added.
Explicit STOP preserves historical evidence and fences later acceptance/work.

## Executed proof and its ceiling

| Evidence | Actual outcome |
| --- | --- |
| Initial dedicated Phase-A tests before new API | 19 RED |
| Initial implementation | 19 PASS |
| Added hostile cases | 3 RED / 31 PASS |
| Dedicated suite after repairs | 34 PASS |
| Integrated adjacent campaign, including the 34 | 398 PASS |
| Read-only current consumer with Phase A explicitly enabled | 2 intended RED |

The 398-case campaign includes real Runtime/port/orchestrator, terminal-return,
Dialogue/Wake/exact-target, native fake-App-Server and actual-supervisor fixtures.
It is not a live provider mission. Earlier diagnosis logs (288 baseline passes;
16 probes with 5 capability REDs/11 controls) remain historical and are not added
to the integrated count. All fixture identities/clocks are explicitly synthetic.

Three later REDs exposed candidate-overwrite, non-string JSON-key coercion and
ambiguous material event identity; each now passes without weakening assertions.
Test logs and `receipt.json` preserve commands, counts, source hashes and times.
Independent non-author review is NOT PERFORMED. Hosted checks are separate.

## Exact consumer scope gate — do not activate

`probe_consumer_boundary.py` executes the actual supervisor with explicit Phase-A
opt-in and synthetic closed events. Both BLOCKED and DECISION_REQUEST become
durable under a real fixture orchestration root. The current supervisor then
stops the worker once, emits `OHF_EPOCH_ABANDONED`, and raises `StateConflict`,
while the Job remains RUNNING. This is an orphaned responsibility, not continuity.
The probe stays RED at the no-stop assertion. No supervisor source was modified.

The broker/remote path also bundles events, candidate and raw role collection;
the current Codex normalizer emits metadata rather than this semantic body.
Those are separate provider/consumer integration gates, not permission to relax
the protected terminal result validator or remove existing serialization.

**Exact next action for Sol/Fable:** adjudicate the same-child consumer-scope
DECISION_REQUEST against this immutable head, and route one non-author exact-head
review of Phase A. Any expansion must bind the actual supervisor/worker-residency/lease/retry,
broker/remote and semantic producer owners before writes. Source custody stays
with this packet until explicit disposition; CCTX-1 gets no parallel writer.

## Reproduction

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -o addopts='' -q -p no:cacheprovider \
  tests/test_ad_ret2_turn_boundary.py
# 34 PASS
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -o addopts='' -q -s -p no:cacheprovider \
  research/evidence/ad_ret2_20260916/probe_consumer_boundary.py
# 2 expected RED; opt-in research falsifier, not a default CI waiver
```

The original packet's real worker → exact action owner → authorized reply →
same-worker useful continuation → terminal result is NOT COMPLETE. No real
Job/Attempt/Worker, credential/provider, ARM, install, restart or release effect
was performed. Exact parent native wake/consumption is not proven by a Slack post.
Existing Agent OS handoff writing belongs to the incumbent; Linear is projection.
