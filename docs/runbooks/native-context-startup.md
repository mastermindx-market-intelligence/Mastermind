# Native principal startup and Web handoff

This runbook consumes existing owners. It is not a new mandate, memory store, tool grant, installation receipt or execution profile. The related implementation plan is `docs/superpowers/plans/2026-10-06-native-context-continuity.md`.

## What the first repaired command does

From the assigned Mastermind workspace, after the candidate has passed its applicable source gate:

```sh
python3 scripts/ceo_boot_packet.py \
  --workstream WS:EXECUTIVE-CAPACITY-FABRIC \
  --macro-root '<approved Macro checkout>' \
  --expected-macro-sha '<exact approved 40-character Macro commit>' \
  --context-budget 4000 \
  --timeout 15
```

The workstream and Macro commit come from the current assignment/source owner, not a remembered example. A harness-launched session must reuse its assigned workspace; it must not allocate another checkout to make the command work. An attended Web session uses the installed `mmx-workspace` owner.

This opt-in path emits the canonical `context_bundle.v1` JSON produced by Macro `scripts/agentos.py compile-context`. It does not run the global brief or mix unrelated global handoffs into the task. Omitting `--workstream` preserves the previous company-wide boot-packet behavior. `--json` is optional in workstream mode because that mode always returns canonical JSON.

`--expected-macro-sha` checks checkout HEAD before and after the read and matches the compiler's reported `repo_sha`. It is a drift guard, not a signature, immutable filesystem snapshot, native loading attestation, proof that the commit is protected/current, or runtime permission. The caller must establish the approved source. The canonical source-record digest identifies the compiler's actual record inputs; unrelated dirty-file/liveness questions remain with their existing owners.

## Startup order

Read the current assignment first. Establish which role is actually assigned: Web CEO, native principal, admitted operator or sealed leaf. Do not infer role from a model name or executable.

Load protected Mastermind INDEX and required procedures from the same exact protected commit. Include ACTIVE_EXECUTION and SESSION_RELIABILITY when enrolled. The current user directive is intent; retrieved packets and organizational memory are evidence. Reconcile current source custody and unsettled effects before modifications.

Read the exact workstream bundle with the command above. Preserve `generated_at`, `repo_sha`, `source_records_digest`, the selected target, degraded inputs and all omissions. Then read the **exact latest cumulative continuation named by the assignment/carrier**. A generic global latest-handoff list is not a substitute. Reconcile stale source against current GitHub/Runtime facts at the relevant boundary.

Recover the original mission and DONE_WHEN, current phase, verified results, remaining acceptance, scope/non-goals, DO_NOT_REDO, active children, source workspace, unknown effects, and exact next action. Keep a compact in-scope working set; do not load the entire company backlog.

Inspect the actual native tool catalog. Separate a listed tool, authenticated connection, role-admitted effect and successful authorized read. Unprobed write/child-launch capability remains UNKNOWN. Do not install or grant all Web tools to a sealed leaf to imitate a principal. Use the qualified capability package for that role.

Begin the next useful authorized action. A successful startup read is not the completion of the mission. Save material deltas through the existing Agent OS/GitHub/Runtime owners before unrecoverable context growth, then continue while useful safe work remains.

## Native loading requirements

For Codex, the installed owner must check the real instruction discovery chain, including global/project/nested precedence and any active override. Official documentation describes `AGENTS.override.md` precedence and a combined instruction byte limit; an enormous root file is not proof that every instruction loads. Verify in a fresh session which sources were loaded, and ask the session to recover one frozen mission without supplemental coaching. Keep current approval/security settings unchanged.

For Claude Code, use the native `/context` view to verify which instruction files actually loaded. `/memory` helps locate/edit memory files but is not by itself loading proof. Official documentation describes machine-local auto memory and states that the main conversation's auto memory is not generally loaded into subagents. Therefore Agent OS remains the cross-machine owner, and leaf task context must be deliberately supplied through the existing Fabric/Craft path.

The existing Claude SessionStart mechanism is a suitable eventual consumer for dynamic mission context after host/profile review. It runs on new/resumed sessions. Do not create a second session scheduler, auto-answer permission prompts, or silently install a command hook into provider homes. #518 owns the shared bootstrap Skill; #1240/#1269/#955/#1264 own the Claude principal/plugin/auth composition. Provider-native loading and auth must be proven separately for each adopted configuration.

Primary platform documentation, checked 2026-10-06:
- https://developers.openai.com/codex/guides/agents-md
- https://code.claude.com/docs/en/memory
- https://code.claude.com/docs/en/hooks#sessionstart

## Context is too large or incomplete

`token_estimate > token_budget` is not automatically a compiler bug. The canonical compiler deliberately retains mandatory workstream constraints and accounting tails. Never slice the JSON or discard constraints until it fits, and never describe a partially read payload as fully loaded.

An actual M2 read on 2026-10-06, against Macro `610889a4e3088bd9dacafedb43a8617fdcd9a894`, requested 4,000 tokens and returned an 18,423-token estimate, 85,388 bytes, 43 budget omissions and three degradation messages. The workstream section alone serialized to 61,967 bytes across 59 items; decisions, discoveries and handoff sections contained no items. Two warnings reported truncated active-build PR coverage. This is evidence about that exact local source/read, not all current checkouts.

Consequently, the launcher must not infer that omitted handoffs do not exist. Read the exact current continuation separately, or use a justified larger budget while preserving all warnings. Durable source hygiene belongs to Agent OS: summarize historical settled work with exact evidence links and retain all still-applicable constraints. Such a repair needs semantic review; do not weaken compiler preservation rules to hide bloated records.

## Failure guide

| Observation | Correct action |
|---|---|
| No usable Macro checkout | Resolve the installed repository binding. Do not clone an unapproved fallback or use an unrelated global brief. |
| Expected source pin mismatch | Reconcile the assignment's source and the existing checkout. Do not remove the check merely to make startup pass. |
| Canonical compiler exit 1 | Inspect the named workstream's existence/schema using the current Agent OS owner. Error output is intentionally not copied into the prompt by this adapter. |
| Timeout / transport byte ceiling | Context was not emitted. Diagnose the bounded read; do not keep retrying unchanged or treat partial output as success. |
| Reader settlement unknown | Preserve the original reader/carrier and reconcile through its process owner before another attempt. |
| Wrong schema / duplicate JSON keys / wrong target | Refuse the response as context; do not guess which field or workstream was intended. |
| Degraded or no-answer payload | Preserve it as knowledge uncertainty, never as admission or permission. Retrieve only the needed missing canonical evidence. |
| Required native tool absent | Report the exact missing tool/profile; continue unrelated safe work. Do not infer the whole Fabric is down. |
| Work accepted or queued | Await actual START/result under the existing owner; do not claim execution. |
| Unknown modifying effect | Freeze that operation/carrier and reconcile; no alternate tool/account/model replay. |

## One reusable Web-to-native handoff shape

The existing canonical continuation/commission owner supplies this content; this is a presentation checklist, not a new stored schema:

```text
Current mission and why it matters:
DONE_WHEN and required production/browser proof:
Current explicit assignment and role:
Protected Skillpack repository/commit:
Implementation repo/branch/head and assigned workspace:
Agent OS WS / exact cumulative handoff reference / source digest:
Verified results and evidence refs:
Decisions, rejected approaches, DO_NOT_REDO:
Allowed surfaces, write paths and non-goals:
Current runtime/custody/admission references:
Actual tool observations and missing capabilities:
Confirmed effects, unknown effects, active children and return obligations:
Next useful action and ordered dependencies:
Reserved decisions / exact human-only gate, if any:
Return destination and acceptance owner:
```

Do not paste hidden reasoning, entire chat history, credentials, broad personal memory, or every repo's backlog. A leaf receives the bounded subset appropriate to its commission. A resumed principal must recover active child returns as well as its local next edit.

## Adoption acceptance, not just installation

For each selected Codex/Claude host and principal profile, record source publication, installed revision, selected native configuration, observed instruction/catalog loading, successful authorized tool read, task recovery, one useful child/result cycle where admitted, and checkpoint restart. Each row is separate. One profile passing does not establish another account/host/harness.

Do not count this runbook or the provider-free tests as a native canary. Exact-head review/CI, role-qualified installation, any required human-only authentication and real same-parent continuation proof remain release obligations.
