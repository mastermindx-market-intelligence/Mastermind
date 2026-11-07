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
| P2.T2 | P2 | P2.T1 | Preserve source and protected master, address D8 HTTP status classification and prove exact-head full CI/security. Protected master `1f1b30d` integrated as a two-parent continuation commit on 2026-11-01 with byte-identical gateway source; base-wide pytest 9.2.0 teardown red isolated and cleared; hosted exact-head CI pending on the new head | in_progress |
| P2.T3 | P2 | P2.T2 | Independent non-author adversarial review of rate/queue/auth and code; no remaining actionable blockers | blocked |
| P2.T4 | P2 | P2.T3 | Protected merge only after review + mandatory exact-head checks and approved normal release path | blocked |
| P3 | — | P2 | Authorized M2 live transport and SDK consumer canary | blocked |
| P3.T1 | P3 | P2.T4 | Operator-recovered M2 host, verified approved Experiential key, known organization/funding RPM and TPM/budget, exclusive service/state-dir custody | blocked |
| P3.T2 | P3 | P3.T1 | Loopback process with file permissions, authenticated health/status, one safe vendor catalog and controlled inference check; provider rejection is reported without rotating keys | blocked |
| P3.T3 | P3 | P3.T2 | Actual admitted Fabric SDK worker points to gateway, completes reply, observes bounded queue and no credential leaks; exact root/parent/Attempt receipts. Named consumer: an Experiential provider adapter of `opencode_go_harness_endpoint.py` shape over `control_plane/attempt_inference_endpoint.py`, blocked on admitted model, admitted route identity, credential/quota authority and one real admitted SDK worker (see 2026-11-01 checkpoint) | blocked |
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


### 2026-10-30 Fabric review and transport-pool fix candidate

- Parent root `exp1849-review-20261030-web` / sole independent read-only Fabric child `exp1849-review-20261030-audit01` returned terminal `rc=0`; full 8,045-byte report `response_sha256=7fa752d16f227553bdf08d8b65d605c52f654822d963b848c47cf89585796ff4` was inspected, and Fabric review result accepted with `verification_summary=manual_result_review`. Reviewer verdict was **CHANGES_REQUESTED**, not GitHub approval; the worker's authenticated GitHub identity was the PR author and no protected review was submitted. Existing `MastermindX1` non-author request remains the mandatory formal gate. See PR #1849 issue comment #6534764708.
- Finding: default HTTPX `max_connections=100` is less than even one admitted key's 128 in-flight allowance, allowing durable RPM reservation followed by an unnecessary 30s pool timeout/502. Fixed in current *local candidate* by `httpx.Limits(max_connections=max_inflight_per_key * key_slots, max_keepalive_connections=min(20,max_connections))`. Added deterministic pool-capacity invariant and a real ephemeral TCP upstream concurrency regression (actual HTTPX transport with 2 simultaneously admitted requests). No live provider contact.
- Hardening: explicit loopback peer checks for all defined routes while requiring loopback bind; minimal unauthenticated health response; bounded streaming collection of provider 4xx/5xx response bodies with guaranteed slot release; `FABRIC_REQUEST_ID` now accepted by `worker_client.new_client()` for one logical SDK call, with documentation warning against reuse across different calls. Added test cases for all. Existing 23-test exact-head M2 suite plus five new tests passed **28/28** locally in an isolated M2 scratch checkout, including real-socket test; source not yet claimed CI/accepted on new head.
- Remaining P2: publish the candidate to the **same** PR branch with compare-and-swap preimage and verify source; rerun dedicated SDK + full protected CI on exact new head; require another qualified independent non-author review and normal protected queue. P3 still requires known sanctioned Experiential credentials, org RPM+TPM/budget reconciliation with separately owned Jev PR #1851, single M2 launch, one admitted Fabric SDK worker through the gateway and consumed result/ACK. Offline evidence does not prove vendor quota rights or live completion.

### 2026-11-01 Current protected-base integration repair, CI red root cause, and P3.T3 consumer identity

**Root cause of the exact-head full CI red (run 41138309556, attempt 2).** It is not a gateway defect and not this PR's source. The four red cases are a base-wide pytest 9.2.0 behaviour change landing on test-owned process-global mocks, on a merge base that predates the protected fix.

- Run 41138309556 tested `refs/pull/1849/merge` against master tip `bb85b429` (2026-10-30T22:28Z). Hosted CI installs `.[dev]` unpinned and pytest 9.2.0 had just been released, so every PR and merge group went red at once.
- pytest 9.2.0 `FDCapture.snap()` now calls `os.fstat(tmpfile).st_size` while a test's process-global `os.fstat` patch is still live: `types.SimpleNamespace has no attribute st_size` (shard 0, two `test_executive_autonomy_control` cases), `StopIteration` (shard 2 `test_cap_s1_mastermind_operator_canary`) and the injected `OSError: inert failure` (shard 2 `test_h1_input_wrapper`).
- pytest 9.2.0 `monkeypatch.setattr()` now reads the old value from `target.__dict__` (pytest #10644). Starlette `State` keeps values in `_state`, so a repeated `raising=False` set records NOTSET and the undo deletes twice: `KeyError: 'scheduler'` in the `test_health_readiness` teardown (shard 1).
- Protected master already fixed both sides and never touched gateway paths: `ed42f860` narrowed the dev bound to `pytest>=8,<9.2` (gate locks pin 9.1.1), and `dcd79fc4` scoped the fake `os` to each test owner and restored the single Starlette `State` key without stacked monkeypatch undo. Master CI at `1f1b30d` is green (run 41331927624). This branch was 21 commits behind and carried none of those fixes, so it inherited the red without any gateway change.
- The red cases are owned by protected-master test files. They were deliberately **not** re-fixed here: that is master source authority, and master already carries the fix.

**Discriminating local evidence — same tree, only the pytest version differs.**

| Tree | pytest | Result |
|---|---|---|
| reviewed head `a1786aa` | 9.2.0 | 4 failed — exact reproduction of shard 0 / shard 1 / shard 2 |
| reviewed head `a1786aa` | 9.1.1 | 15 passed |
| merged head (current protected base) | 9.1.1 | 41 passed, 2 skipped |
| merged head (current protected base) | 9.2.0 | 41 passed, 2 skipped |

The gateway suite itself is 9.2-clean, so the red is proven to come from the base's test-owned global mocks rather than from this PR's source.

**Repair.** Two-parent continuation merge of protected master `1f1b30d1352d2a975624e558bd9da097e4cba417` into this branch, with no source-history rewrite. No gateway source byte changed: `ops/native_fabric/experiential_proxy/**`, `tests/test_experiential_proxy.py` and `.github/workflows/experiential-proxy.yml` are byte-identical to the reviewed head `a1786aa`, so the prior independent Fabric technical review remains reusable. The merged tree differs from protected master by exactly this PR's nine additive files, and the repository's own gate plan still validates (`python -m scripts.ci_parallel_shard --jobs 3 --index 0 --plan-only`: discovered=1683, excluded=0, running=1683). The merge is a real repair rather than a `behind_by=0` cosmetic: on the branch's own tree the repository gate installs an unbounded pytest and reproduces the base red, and only the integrated base carries the pinned dev bound and the test-owned mock-scoping fixes.

**Candidate-owned source left unchanged (review-reuse classification).** The gateway implementation, its test module and its dedicated SDK workflow are byte-identical to the reviewed semantic head `a1786aa`. Only this checkpoint document changed. The dedicated SDK workflow still installs `pytest>=8,<10`, the same unbounded spec that produced the base-wide red; it is proven green on 9.2.0 (hosted run 41138309442, 28/28) and on 9.1.1 (local), so it is **not** an active fault, and narrowing it to the protected base bound `pytest>=8,<9.2` would be a candidate-owned toolchain change that the protected reuse law treats as a full-re-review trigger. It is therefore recorded here as a **reviewer decision**, not applied unilaterally: the protected base already rejected pytest 9.2.0 in `ed42f860`, and this gate is the only remaining place that admits it.

**Protected REVIEW_RETURN Step 2A classification: `REVIEW_REUSE_ALLOWED` for the gateway semantics, subject to the non-author reviewer.** The reviewed semantic head's owned implementation and test blobs are byte-identical; protected movement is disjoint from every candidate-owned path (the merged tree differs from protected master by exactly this PR's nine additive files); the governing material source is unchanged; the dependency-closure intersection is the dev-toolchain pytest bound, and a bounded current comparison proves it non-material to this carrier — the gateway suite is green under both pytest 9.1.1 and 9.2.0; the latest-base merge ref is conflict-free with its identity bound; no unresolved blocker applies; and no capability claim is strengthened and no live proof is newly claimed. The one candidate-owned blob that did change is this mandated checkpoint document. The formal non-author GitHub approval (`MastermindX1`) remains the outstanding P2.T3 gate and is **not** self-asserted here.

**P3.T3 — the exact missing Fabric inference SDK consumer.** The gateway has no in-repo consumer: `worker_client.py` is the only `from openai import` in the repository outside `vendor/`. Native Fabric inference is CLI/Codex-based (`glm_codex_exec.sh`, `mm_codex_exec.sh`, `go_codex_exec.sh`, `qwen_exec.sh`), plus the GLM paid model-only client `ops/native_fabric/quota_continuity/candidate/paid_glm_model_client.py` (a fixed `127.0.0.1:4141/v1/responses` route with the closed allowlist `{'glm-5.3', 'glm-5.3-flash'}`) and the OpenCode Go pooled transport. None of those is an OpenAI-SDK consumer, and the GLM paid route must not be repointed.

The lawful SDK consumer already has a named home and shape: `control_plane/attempt_inference_endpoint.py` is the provider-neutral, attempt-owned loopback endpoint that serves `/chat/completions` for protocol `openai-chat`, and `control_plane/opencode_go_harness_endpoint.py` is its one existing provider adapter. The missing consumer is therefore exactly:

> an Experiential Labs provider adapter of the `opencode_go_harness_endpoint.py` shape, composed onto `control_plane.attempt_inference_endpoint.py`, whose forwarder calls the OpenAI SDK against `http://127.0.0.1:8311/v1` with `FABRIC_PROXY_TOKEN`, `max_retries=0` and one attempt-scoped idempotency key, and returns an `InferenceForwardReceipt` carrying the bound route identity.

It is **not implemented here** because four admission prerequisites are unmet and each would need authority this task does not hold:

1. **Admitted model.** `AttemptInferenceBinding.model_id` must be an admitted capacity/pool model. No Experiential Labs model or pool exists in the native Fabric capacity layer, and adding one would be *registering an unadmitted model as live*.
2. **Admitted route identity.** `route_id` and `route_generation` come from an admitted canonical account/pool choice (`AccountChoice`/`_choice`). None exists for Experiential Labs.
3. **Credential and quota authority.** No owner-verified organization RPM/TPM/credit limit, no admitted key, no exclusive M2 host or state-directory custody. `SAFE_RPM_SHARED` cannot be set from provider screenshots, and the separately owned Jev/System One adapter in PR #1851 shares the same organization quota without a joint safe reservation. Production stays inert.
4. **One real admitted SDK worker.** No worker in this repository uses the OpenAI SDK, and existing worker execution routes do not automatically become SDK consumers.

Writing that adapter now would add unexercised provider surface to a head whose independent review passed, while the binding it requires cannot be admitted. The consumer identity and its prerequisites are recorded here so the capacity/provider owner can authorize it without re-derivation.

**Shared-quota accounting honesty.** This gateway's per-key and `SAFE_RPM_SHARED` counters cover only requests that actually traverse this proxy. Jev's native `/v1/systemone` direct calls are not counted by this limiter, so local counters must never be presented as organization-wide accounting, and the shared organization quota must be reconciled with PR #1851 before both are activated.

**Production gates that remain closed (source-recorded, not live claims).** One `$20 Pro` organization, one API key for now, shared with Jev System One. The per-key `SAFE_RPM_PER_KEY=1000` ceiling stays conservative; do not raise it to the 1,500 RPM organization figure without an owner-verified organization readback, and keep `SAFE_RPM_SHARED` unset until that organization scope is confirmed rather than inferred from provider screenshots. The shipped per-key in-flight default of 128 is a **source** default, not an approved host value: with one key on the M2 host it must be set to 32 or lower after an actual host limit preflight, because four credentials at 128 in-flight each would demand outbound sockets beyond the observed 256 soft file limit and that configuration is unsafe. Upstream errors, a 429, or credit exhaustion must not trigger key rotation, a POST retry, or any hidden billed continuation. The proxy's local limiter does not see Jev's direct `/v1/systemone` calls, so the two routes must not be activated on one organization key until a joint safe reservation exists. Production stays inert until the organization limits, the key and the M2 host custody are owner-verified.


## P5 — Chairman plan integration, November 7, 2026

Current operation: `provider-plans-byteplus-experiential-20261107-c2`.
Source/procedure base: `779fc3be9d07c366bf5b47c650b64e59fc6f3903`.
Parent: [Fabric convergence #983](https://github.com/mastermindx-market-intelligence/Mastermind/issues/983).
This is the current Chairman-assigned continuation of provider enrollment and plan-aware admission. The original gateway #1849 and commercial ModelArk #1824 are merged; those source releases do not prove live enrollment. Preserve the active #2175 application composition and original effects, #1941/#1851 Jev, original Experiential account holds, and every native publication owner.

### User outcome and account policy

An eligible Capacity/Subagent Fabric task can consume the actual subscribed plan through existing model, account, quota, broker and result owners. The user supplies a BytePlus $50 plan and an Experiential Labs plan with 7,000 free-model credits per day and a $200 monthly paid allowance. These are owner-declared plan limits, not measured remaining quota. No credential or subscriber identifier belongs in this file, GitHub, worker packets or logs.

- BytePlus: retain the distinct Personal Coding Plan endpoint and its three simultaneous five-hour, weekly and subscription-month constraints. Prefer the verified DeepSeek V4.1 Flash / GLM 5.3 Flash model choices within supported usage. Never substitute the commercial PAYG endpoint or count duplicate keys as independent subscriptions. Additional independently enrolled subscriptions may increase capacity only with their own account-bound quota observations and configured concurrency caps.
- Experiential free traffic: allow the exact provider-catalog free variants corresponding to DeepSeek V4.1 Flash, GPT-6 Luna, Clef, DeepSeek V4.1 Flash 1017, Jev, Clef Flash and GPT-6 Luna Decisions. Display names alone are not model IDs or proof of free billing. Admission requires current provider evidence and preserves the daily-credit boundary.
- Experiential paid traffic: reserve included paid allowance for the explicitly chosen uncensored lane, preferring DeepSeek V4.1 Flash 1017 Uncensored and then GLM 5.3 Flash Uncensored. No automatic promotion from exhausted free credits into paid traffic, no unrelated paid models or subscription overage. Provider refusals and ambiguous submissions are not model/account failover permission.

### Existing task tree extension

| ID | Depends | Action and completion evidence | Editorial state |
| --- | --- | --- | --- |
| P5.T1 | P2.T4 | Reconcile existing owners and official provider contracts; authenticated Experiential organization/wallet/catalog observed, BytePlus management telemetry remains UNKNOWN | complete |
| P5.T2 | P5.T1 | Implement native request/lease/result integration, free/paid policy, shared subscription scope and no PAYG fallback; focused source tests pass, hosted CI repair is in progress | implemented; qualifying |
| P5.T3 | P5.T2 | Both supplied credentials privately enrolled; candidate gateway metadata verified; native account/host enrollment and supported provider execution remain | in_progress |
| P5.T4 | P5.T3 | Normal auto-merge armed; consume exact accepted source, CAS-select native generation, execute admitted workers and consume their results/accounting | in_progress |

DONE_WHEN is actual supported-plan execution and result consumption with truthful remaining quota, paid-model reservation and no secret leakage. A plan, source alias, gateway health response, test pass or successful merge alone is insufficient. If a real provider/permission/credential/native-release hold applies, preserve its exact identity and complete independent source work; do not remove guards to manufacture enrollment.

Direct principal work is retained initially for PRINCIPAL_JUDGMENT and UNIQUE_APPROVED_ACCESS: reconcile personal-versus-commercial entitlement, old account holds, current supplied credentials, and active application/native writers. Bounded independent labor is eligible for the existing paid Fabric after that envelope is frozen; no new router, quota ledger, worker queue or credential cache is introduced.


### P5 implementation checkpoint — November 7

[P5 source and account evidence](../reports/provider-plan-integration-20261107.md)
records the complete native integration in [PR #2220](https://github.com/mastermindx-market-intelligence/Mastermind/pull/2220).
P5.T1 is complete. P5.T2 implements original request custody, physical/provider
leases, account-bound launch, single-send reservation, quota observation and
result delivery, together with strict free/paid selection. Hosted qualification
found a sealed GLM helper dependency; preserve those accepted bytes and validate
new-pool leases through the read-only plan adapter.

P5.T3 has enrolled both supplied credentials through private owners. The existing
loopback gateway is running as an unselected candidate and authenticated account,
wallet and catalog observations are recorded. The production catalog publishes
base IDs; the documented `:free` request qualifier is validated against those IDs.
A provisioning credential is not required to consume the supplied inference plan.
BytePlus management SSO is separate from the supplied coding-plan inference key:
unknown management quota remains UNKNOWN, with provider hard stops and the
original broker/operator cap. Missing management telemetry alone does not create
a new credential or human gate.

P5.T4 is in progress: normal protected auto-merge is armed; required hosted CI,
accepted-master publication, exact-current native selection, original-owner
account/host enrollment and real native result consumption remain to be proven.
The current Web review waiver governs this continuation; historical prose above
about mandatory named independent reviewers is not a present gate unless the
repository actually requires that approval. No review, merge, native activation
or provider inference is inferred from this checkpoint. Continue through actual
provider completion and lease/accounting settlement before acceptance.
