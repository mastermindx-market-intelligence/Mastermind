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
| P2.T1 | P2 | P1 | Run async regression tests with local stdlib `asyncio.run` adapter to preserve hash-locked dev environment; verify normal + SDK CI | implementation_complete |
| P2.T2 | P2 | P2.T1 | Preserve source and protected master, address D8 HTTP status classification and prove exact-head full CI/security | in_progress |
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

**Work:** The first integrated candidate added `pytest-asyncio` to the dev extra, which made the RWE-P0 shadow gate correctly reject stale Linux/macOS hash-locked environment files. Rather than weakening that evidence contract or manually changing locks, restore the protected master `pyproject.toml` blob unchanged. Keep every async test coroutine and assertion intact; wrap only the test callable with `functools.wraps` + stdlib `asyncio.run`, leaving pytest parametrization and fixture signatures intact. This was verified locally with `pytest --noconftest -p no:asyncio` (20 passed, one native SDK skip) and again with the normal plugin present (same result). The dedicated SDK workflow retains the actual `AsyncOpenAI` installation/import and runs all 21 tests on hosted CI without needing `pytest-asyncio`. Run both hosted workflows and reconcile standard full CI.

**Acceptance falsifier:** A green SDK-only workflow with red normal `test` gate, failures on async cases without the plugin, a stale hash-locked RWE environment, a stale branch base, or a merge without non-author review is *not* P2 completion. A real `tests/test_ceo_submit_armed_composition.py` regression on integrated source must be investigated, not explained away.

**Route/review:** routine implementation by incumbent source writer; independent reviewer for security, queue and cancellation path. No Fabric child is implied by this task tree.

## Source progress and unreconciled deployment evidence

- Candidate source: `53f96d226848cd6c102b208eb77ca541e95e3ac5`, PR #1849, published 8 new source/test/workflow files.
- Host-independent suite: 21 native-SDK tests completed successfully under isolated CI; CodeQL success on the candidate.
- Standard main CI failed: shard 2 lacked async plugin; shard 1 had an unexpected `503` in the CEO submission topology assertion.
- Candidate integrated protected master `a4525e3e7e9251951567a9142392df962bd06ba2` through the two-parent commit `9b0adb5b9fa81f33af95167e489e3777a5e76f98` without rewriting source history. After integration, the initially added pytest dependency triggered RWE shadow lock refusal; this subsequent repair keeps the protected master dependency manifest unchanged. Neither green full CI nor release is claimed.
- Non-author reviewer `MastermindX1` requested, not accepted.
- Prior Studio Direct `studio_ping`/fleet transport returned an MCP SSE 429; no live credentials or Fabric requests were attempted on its behalf.

## Continuity pointers

The pinned organizational plan remains whichever existing Agent OS workstream the authorized organizational writer confirms. Read its current waves, `next_action` and latest dated valid handoff if linked. GitHub [PR #1849](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1849) is this implementation's durable source/evidence pointer; the current PR head and CI/checks are authoritative for implementation facts. Executive OS remains authority for admitted runtime execution, not this task tree. Update these tasks at material source or acceptance boundaries only.

### P2.T2 source guard correction — 2026-10-25

- Normal CI run `40195557499` tested the async-suite repair: shards 0 and 2 passed. Shard 1 failed only `tests/test_ceo_submit_armed_composition.py::test_d8_template_topology_and_protected_defaults`; its protection scanner reported `['503']` from changed source. The scanner must remain intact.
- Explicit gateway overload responses now pass the Python standard-library `HTTPStatus.SERVICE_UNAVAILABLE` IntEnum to `JSONResponse.status_code` instead of the ambiguous bare 503 constant. This retains the wire status: `int(HTTPStatus.SERVICE_UNAVAILABLE) == 503` and FastAPI JSONResponse still emits 503. No queue behavior or caller contract changed. The gateway's positive offline suite passed 20 cases, one optional native-SDK skip locally, with actual native SDK proven separately in CI; full source guard awaits hosted proof on the integrated head.
- Protected master advanced two non-overlapping commits from `a4525e3e7e9251951567a9142392df962bd06ba2` to `bb85b429f2ffffd38408080ce4df7d6378c34100`; those source paths remain preserved by a new two-parent continuation commit on original PR #1849. Review/merge still require fresh exact-head CI and non-author verdict. No live keys or host installation.

### P2.T2 queued-disconnect guard — 2026-10-25

- Later exact head `3b3c610eaaf34b8816f3bfb2016d4e00b8e8d1e8` proved normal CI 40199693920, native SDK 40199693995 and all exact-head CodeQL/static checks green. GitHub PR #1849 was marked Ready for review, and non-author `MastermindX1` remains requested with a Slack handoff but no accepted reviewer verdict.
- A new targeted ASGI test shape demonstrated a material missing behavior: after buffering the request body, the previous queue waited without observing `http.disconnect`; an abandoned caller could still trigger a billable upstream send at eventual admission. This source slice introduces an ASGI disconnect listener, a queued admission cancellation signal and wakeup, and a best-effort no-content response only for an already departed caller. If an RPM reservation won the race, it is conservatively retained in SQLite while its in-flight lease is released before any vendor call. Host runtimes and worker routing remain unchanged.
- Fresh hosted head tests and independent review **must** qualify this new candidate; the older green CI is prior-head evidence only. Same-organization Jev/System One PR #1851 is separately owned and outside this proxy's route allowlist. Aggregate vendor RPM/TPM must be reconciled before both implementations use an organization key at once.

### P2.T2 admission-clock regression repair — 2026-10-25

- Source-head `606efbc37dc9eceee25f9d331c471c941772bee8` standalone native SDK suite [40210246568](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/40210246568) passed **all 23** test cases, and CodeQL/static analysis passed. Full CI [40210246586](https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/40210246586) failed only shard 2 `test_queued_instead_of_429_when_all_slots_reach_ceiling`: the test measured mocked provider-arrival clock `seen[1]-seen[0]` at 37ms versus a hard 60ms lower bound. Admission happens before request forwarding and scheduler effects make vendor-arrival spacing non-authoritative. Do not weaken the production rate limiter.
- Replace *test-only* wire timing assertion with observation of `SlidingWindowAdmissions.events[slot][-1]` at each successful `acquire` return, before another `await`; compare consecutive durable admission timestamps with configured `window_s` allowing 1ms for time resolution. Keep all three genuine HTTP requests, mock provider count and success/no-local-429 assertions. Local bounded targeted pytest on older equivalent acquisition test passed; this exact published source requires new-head hosted CI and non-author review. No production gateway or worker control changed in this repair.
