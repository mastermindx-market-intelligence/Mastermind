# Subagent Fabric: pinned/automatic model, pool and device selection

**Date:** 2026-10-11 America/New_York / 2026-10-12 UTC  
**Operation:** fabric-expiry-selector-20261011-sol-001  
**Disposition:** SOURCE_CANDIDATE / TESTED_ISOLATED / NOT_INSTALLED / NOT_PROVEN_LIVE_AS_NEW_INTERFACE  
**Protected source/procedure baseline:** Mastermind master 25c4b7923734392b1013afae179966985819d847, mastermind.sol_skillpack.v1 version 1.0.1

## User result and acceptance

Allow a newly commissioned Fable, Opus, Sol, Grok, Codex or lower-cost session to request a qualified model or model pool and an eligible device, or select auto for any/all, while preferentially consuming legitimately available subscription capacity shortly before its reset. Do not manufacture work solely to spend quota, claim unknown allowance, bypass task-fit, spawn another lifecycle or move an effectful operation to a different device/account.

Completion requires: (1) selector is in the actual entrypoint used by sessions, (2) routing picks a task-qualified model and eligible host with fresh available quota, (3) the original provider model/host is attested and the child executes and returns to the correct parent, (4) no extra lease/execution after response loss, and (5) the consumed allowance and reset-aware policy are observed on the provider/account that actually ran.

## Source census — what is already installed

Inspected the **installed live M2 Studio Subagent Fabric kit** in its account-local handoff_kits/meta-ceo-b-2026-09-08/ext location; this directory and its ancestors are **not a Git checkout**. Multiple independent owners were actively launching remote_sub.sh jobs on Ubuntu hosts at the time of inspection. No running jobs were touched.

| Component | Observed capability | State |
| --- | --- | --- |
| remote_sub.sh | <host or auto> <mode> <packet_file> <remote_cwd> [model], immutable run ID, existing model/lease/economic checks | Already implemented/active |
| host_pick.py | Eligible host from ext/hosts.json allowed_modes, qualification hold, host freshness/load and lane limits; remote-first | Already implemented/active |
| pick.py | --task-class, --host, --pool, --prefer, --requested-model, --explain; emits POOL, MODEL, HOST, MODE | Already implemented/active |
| pick.py R31 | Qualifying burn-down preference: reset <=36 hours, remaining quota >=15%, only eligible model/pool and fresh paired evidence | Already implemented/active |
| Grok priority | Dated operator-supplied provider screenshot, <=6h observation age and <=6h to reset; configuration enabled 2026-10-11 | Implemented; live read-only selection proven |
| GLM/MiniMax | Provider-authoritative paired weekly quota remaining/reset observations, stale and past-reset refused | Implemented as code, not all accounts independently proven |
| fabric_task.py request | Existing stable run/parent/cwd/packet, --pool, --prefer, --model, host always auto; route rechecked by remote launcher | Partially implemented |
| model exact choice | Lower transport accepts a model; normal high-level picker permits only narrowly justified GLM full-model escalation; arbitrary stronger-model override rejected | Narrow, intentionally guarded |
| account-level multi-window economics | Existing Macro #7116, provider account pool #7142; separate capacity owners | Source candidates, not evidence of live auto account selection |

### Real no-write routing observations

An installed pick.py review request (class review, host auto) selected POOL=grok, MODEL=grok-4.6, reason=execute_order_grok+burn_down_urgent+grok_expiring_priority. It selected ubuntu0 in one observation. The **isolated preview using live read-only picker** selected ubuntu1 later, with the same Grok/expiry reasons; host can change as occupancy changes. An ineligible ubuntu9 pinned-host preview refused before any worker dispatch. A preview does **not** reserve resources.

## Recommended selector contract

Retain existing CLI and owners; the new API is a small extension of fabric_task.py, not a new allocation service.

| Caller request | Semantics |
| --- | --- |
| --pool auto (or omit) | Rank task-qualified eligible pools, applying existing R31 burn-down first when valid |
| --pool glm / grok / minimax / ... | Hard pool constraint; refuse when disallowed, exhausted, stale or host-incompatible |
| --model auto (or omit) | Current model picker chooses the cheapest sufficiently capable allowed model |
| --model <specific qualified model> | Hard exact-model request but **never** bypass model suitability or launch_policy; current high-level exact override remains narrow |
| --host auto (or omit) | Existing eligible-host picker chooses host using live occupancy, allowed_modes and lane ceilings |
| --host ubuntu0 / ubuntu1 / ... | Hard device constraint; refuse if not eligible, fresh or admitted |
| --prefer <pool> | Advisory preference only, subordinate to eligibility, tier and quota |
| --subject-pool <pool> | Existing review independence constraint |
| --class / --task-complexity / --escalation-reason | Existing economic/quality classification and upgrade witness |
| preview --id <stable ID> | Read-only route recommendation; does not reserve/start; same ID allows deterministic routine-cohort sampling |
| request --id <stable ID> | Existing single carrier, existing launch/recovery/return and provider admission; reselect/recheck at actual request |

Automatic preference should be *lexicographic*, not a free-standing numeric expiry score: authority and policy; correct bounded-task difficulty/capability; candidate provider-account quota validity; near-expiration pressure within lawful tier; host feasibility/load; owner-bound claim; result quality/usage feedback. Unknown/stale quota fails closed for urgency. Heavy premium spend is not justified by expiry alone if model quality is not needed. No post-START model/account/host switch absent exact canonical reconciliation.

## Built in this candidate (not installed)

Two artifacts:
- ops/native_fabric/patches/fabric_task_expiry_host_select_20261011.patch
- ops/native_fabric/patches/fabric_task_expiry_host_select_20261011.tests.py.txt

The patch extends the real installed fabric_task.py code (source SHA256 **cbd46bd88a4e5d545c77010bfb9eb1997399fe4f5cc67596210e849858eddd99**) with:
1. preview subcommand, reusing pick.format_pick and pick.launch_policy and returning PREVIEW_ONLY/reserved=false.
2. --host for existing request, default auto, selecting only through incumbent host registry and checks.
3. Literal --pool auto and --model auto normalized to absence of override, preserving existing native defaults.
4. Host-selector validation and a refusal to combine ordinary --host with the separately held --qualification-host path.
5. Original run ID/parent/packet/remote_sub.sh transport, quota owner and effect fences unchanged.

Isolated target source SHA256 **958ab7be33bf24ce4a40d3af8e9689628fe9f6bda025f1f75b47952cc5072d3b**. Patch is bound to that installed source revision; it is not a general fuzzy replay recipe. Test fixture is stored as .py.txt to avoid accidental normal repository collection since it needs the actual installed external-kit Python modules.

### Reproducible offline qualification on original M2 source owner

Only after exact source ownership and effects are reconciled, copy the real ext directory to an isolated temporary test area. Compare its original fabric_task.py SHA256 with the expected hash above, reject if mismatched. Apply with git apply --check then git apply from the source directory's parent (strip only the a/ and b/ path prefixes as appropriate); do not apply over the shared active installation as a convenience.

Run PYTHONDONTWRITEBYTECODE=1, PYTHONPATH=<isolated candidate>:<source ext>, and execute:
~~~bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q \
  test_fabric_selector.py --tb=short -o addopts=''
~~~

This isolated test **passed 15 checks in 0.36s** on M2 Python 3.14. Tests cover route auto, exact host/pool/model forwarding, explicit auto normalization, invalid host pre-dispatch refusal, qualification-host conflict, immutable run-ID forwarding, model-policy refusal without dispatch, preview-only and CLI request forwarding.

A live *read-only* preview also ran successfully against the installed picker:
~~~bash
python3 fabric_task.py preview --id mmx-expiry-readonly-01 \
  --class review --pool auto --host auto --model auto
~~~
It returned PREVIEW_ONLY/reserved=false, Grok 4.6, Ubuntu1 and the exact burn-down/expiring priority reasons. No worker was launched or quota consumed. The independently installed older test_fabric_task.py is stale: baseline failures include a missing ext/pools.yaml fixture and expectations predating route_key and qualification_host arguments. Its failures are **not new-selector regressions** and were not silently declared green.

## Existing owners, overlap and effects

Do **not** create a second router, account registry, quota source, lease/retry/queue, transport or authority. Real owners: existing Model Router suitability; provider-control quota evidence and Capacity selection; host_pick for physical suitability; remote_sub/lease_broker/Executive runtime for start/effects; Agent OS for cross-session continuity.

Pre-existing relevant PRs:
- Mastermind #1247: capacity-conserving owner-bound economic previews, **not installed**
- Mastermind #1248: TaskFit + model-specific native planning candidate, **not installed**
- Macro #7116: multi-window subscription quota economics and measured cost, **draft/hold**
- Macro #7142: provider-account selection candidate, **draft/partial**
- Mastermind #1228: local orchestrator policy installer owner, held; don't bypass
- Native model/provider realm qualification and all-account quota observations remain separate

At inspection, installed fabric_task.py changed concurrently (new qualification_host path), and its source dir is not a git checkout. This candidate **does not overwrite that live owner**. The specific source collision is a genuine release/installation blocker, not a reason to fabricate an installed feature. No credentials, enrollment, workers, leases, authentication, production flags, active job binding, services or deployments were modified.

## Finish path / acceptance gates

1. Reconcile the incumbent live fabric_task.py writer and its active revision/effects; check hash and port the small patch onto the new source if drift occurred. No blind replay and no duplicate carrier.
2. Integrate the tested selector into the actual canonical managed launcher for Fable/Opus/Codex sessions, including CLI help/profile visibility. Preserve qualification_host and the lower remote_sub authority.
3. Add fully representative provider-account windows from the existing provider owner. GLM/MiniMax can use source-verifiable observations; Grok screenshot urgency automatically expires, not a permanent quota claim. Reuse #7116/#7142 only upon accepted source/release gates.
4. Qualify actual host+model+account telemetry and one bounded canary with strict source/model/host attestation and accepted original-parent result. Use a real task, not quota-burning busywork.
5. Test invalid host, stale quota, model mismatch, not-author reviewer, lane ceiling, concurrent claims, zero budget, and EFFECT_UNKNOWN (no alternate-host resend). Run exact-head CI and independent review before installation; verify live after publication/installation separately.
6. Expose usage/accepted-output feedback through existing result evidence; prioritize expiring capacity **only** while feasible and economically justified, not across unrelated capability tiers.

**Outcome at this branch:** expiry-aware automatic placement is already operational for the observed Grok case. The explicit-host + preview high-level entrypoint is isolated-source implemented and tested, **not live installed**. End-to-end new-interface acceptance is incomplete until writer reconciliation, managed installation, authenticated model/account proof and real accepted parent return.
