# Experiential Labs inference gateway — Fabric delivery task tree

> Task hierarchy for Mastermind PR [#1849](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1849). It is not a new worker lifecycle, queue, credential manager, source lease, or Agent OS workstream.

## Identity and objective

- **Chairman objective:** Existing authorized Fabric OpenAI SDK workers connect to one local OpenAI-compatible endpoint. Requests are distributed over 1–4 authorized Experiential Labs API keys, each capped at 1,000 submissions per rolling 60 seconds, with bounded waiting instead of local 429 failures.
- **Owning repo / task tree:** `mastermindx-market-intelligence/Mastermind`, `docs/plans/EXPERIENTIAL_FABRIC_GATEWAY.md`, candidate PR #1849. Git blob/commit identity is read from the published file at the inspected PR head, not from an unverifiable self-referential hash.
- **Protected source procedure:** `a4525e3e7e9251951567a9142392df962bd06ba2`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1, current as of 2026-10-25.
- **Accountable delivery function:** Current assigned CEO/Sol integration leader. PR author history is not a live worker lease or reviewer.
- **Agent OS workstream / latest handoff:** No dedicated Experiential workstream identified in the checked Macro workstream listing; `WS-EXECUTIVE-CAPACITY-FABRIC` owns broader provider capacity but its existing waves must not be reassigned. **PLAN_NOT_ORG_LINKED** until the incumbent Agent OS writer confirms ownership and adds the path, if appropriate. The GitHub PR description is the current source checkpoint, not an Agent OS handoff.
- **Task tree first authored:** 2026-10-25 UTC; review and acceptance are separate from source publication.

**Machine/user job:** A real enrolled Fabric worker can make successful SDK Chat/Responses requests through a single approved local transport, and local saturation waits fairly without sending a provider 429 or unintentionally spending another credential. The gateway is deliberately **below** existing `fabric_task.py`, `pick.py`, Executive admission, model/pool selection, `pool_ledger.py`, RuntimeBinding, and secrets management.

**DONE_WHEN:** The exact reviewed release is merged through protected gates, installed with a verified eligible key in an authorized M2-owned host, a real admitted SDK-based Fabric worker completes an inference through the proxy, a second controlled request demonstrates queueing at the configured local ceiling, the consumer can retrieve the result, and no new worker lifecycle, unauthorized provider switch or key exposure occurred. The requested 1,000 RPM/key is a **local safety ceiling**, not evidence of vendor authorization for 4,000 aggregate RPM.

**Non-goals / stop rules:** Never infer organizational quota from the number of keys; no key/model/account cycling after an upstream 429 or transport uncertainty, no unbounded HTTP waits or buffers, no credential export to a worker, no live deployment or worker dispatch based merely on green CI, no automatic failover to other host/capacity carriers, no self-approval or self-merge.

## Hierarchy and acceptance matrix

| ID | Parent | Depends | Deliverable and evidence / falsifier | Editorial state |
|---|---|---|---|---|
| P1 | — | — | Outbound inference transport source with no scheduler replacement | implementation_complete |
| P1.T1 | P1 | — | Provider endpoint forwarding, SDK compatibility, Chat/Responses/SSE, authenticated loopback, strict route allowlist; PR #1849 exact code | implementation_complete |
| P1.T2 | P1 | P1.T1 | SQLite persisted rolling per-key admission, optional org-shared RPM across rotated keys, FIFO, bounded queue count/bytes, stream slot release, no blind POST replay; regression suite | implementation_complete |
| P1.T3 | P1 | P1.T2 | Dedicated native OpenAI SDK CI on candidate: run 40122896228 passed 21 tests, real SDK imported; no vendor calls | implementation_complete |
| P2 | — | P1 | Standard source release and independent reviewer acceptance | blocked |
| P2.T1 | P2 | P1 | Fix standard CI async fixture gap by declaring `pytest-asyncio` in `[project.optional-dependencies].dev`; full hosted CI passes exact integrated head | ready |
| P2.T2 | P2 | P2.T1 | Preserve all 8 gateway source files and protected master changes; test exact new combined head and security analysis | ready |
| P2.T3 | P2 | P2.T2 | Independent non-author adversarial review of rate/queue/auth and code; no remaining actionable blockers | blocked |
| P2.T4 | P2 | P2.T3 | Protected merge only after review + mandatory exact-head checks and approved normal release path | blocked |
| P3 | — | P2 | Authorized M2 live transport and SDK consumer canary | blocked |
| P3.T1 | P3 | P2.T4 | Operator-recovered M2 host, verified approved Experiential key, known organization/funding RPM and TPM/budget, exclusive service/state-dir custody | blocked |
| P3.T2 | P3 | P3.T1 | Loopback process with file permissions, authenticated health/status, one safe vendor catalog and controlled inference check; provider rejection is reported without rotating keys | blocked |
| P3.T3 | P3 | P3.T2 | Actual admitted Fabric SDK worker points to gateway, completes reply, observes bounded queue and no credential leaks; exact root/parent/Attempt receipts | blocked |
| P4 | — | P3 | Operationalization and future key expansion after observed vendor limits | proposed |
| P4.T1 | P4 | P3.T3 | Incremental slots 2–4 only after quota/funding and need verified; monitoring, graceful restart and operator runbook/rollback | proposed |

### P2.T1 — CI integration repair (next source slice)

**Input:** Protected master `a4525e3e7e9251951567a9142392df962bd06ba2` and original draft PR #1849 head `53f96d226848cd6c102b208eb77ca541e95e3ac5`. Standard CI 40122896249 failed on shard 2 because async pytest support is not in the repository dev installation; 20 async tests refused to execute. Dedicated isolated SDK workflow `40122896228` passed 21 tests with the correct plugin installed. Master at `a4525e3e7e9251951567a9142392df962bd06ba2` has independent green CI `40191846689`; old shard 1 failure in CEO topology is not sufficient evidence that the proxy changes that test.

**Work:** Add only the established pytest plugin to the dev extra; preserve test discovery and existing tests, do not suppress failures or weaken CI. Integrate protected master without overwriting unrelated changes. Run exact-head normal CI and dedicated SDK suite; inspect failures and repair only caused issues.

**Acceptance falsifier:** A green SDK-only workflow with red normal `test` gate, a skipped async test set, a stale branch base, or a merge without non-author review is *not* P2 completion. A real `tests/test_ceo_submit_armed_composition.py` regression on integrated source must be investigated, not explained away.

**Route/review:** routine implementation by incumbent source writer; independent reviewer for security, queue and cancellation path. No Fabric child is implied by this task tree.

## Source progress and unreconciled deployment evidence

- Candidate source: `53f96d226848cd6c102b208eb77ca541e95e3ac5`, PR #1849, published 8 new source/test/workflow files.
- Host-independent suite: 21 native-SDK tests completed successfully under isolated CI; CodeQL success on the candidate.
- Standard main CI failed: shard 2 lacked async plugin; shard 1 had an unexpected `503` in the CEO submission topology assertion.
- Current protected master is newer and green, but candidate is behind. No merge or release is claimed.
- Non-author reviewer `MastermindX1` requested, not accepted.
- Prior Studio Direct `studio_ping`/fleet transport returned an MCP SSE 429; no live credentials or Fabric requests were attempted on its behalf.

## Continuity pointers

The pinned organizational plan remains whichever existing Agent OS workstream the authorized organizational writer confirms. Read its current waves, `next_action` and latest dated valid handoff if linked. GitHub [PR #1849](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1849) is this implementation's durable source/evidence pointer; the current PR head and CI/checks are authoritative for implementation facts. Executive OS remains authority for admitted runtime execution, not this task tree. Update these tasks at material source or acceptance boundaries only.
