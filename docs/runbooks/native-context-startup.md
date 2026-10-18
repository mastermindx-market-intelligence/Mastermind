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

**Both `--macro-root` and `--expected-macro-sha` are mandatory in workstream mode.** An environment root, sibling checkout or vendor mirror cannot substitute for the assigned source. The legacy company-wide mode retains its original discovery behavior.

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

A follow-up same-record-digest experiment on Macro `a80e6ff8ff771b0f994982b2dfb2de203197dc18` confirmed that even a 12,000-token request returned the same 18,423-token estimate with no handoff. A 24,000-token request included one handoff, 12 decisions and eight discoveries, but still estimated 25,626 tokens and omitted 15 items. The selected handoff was dated 2026-09-29, not this operation's 2026-10-06 continuation. Therefore a larger budget is not a substitute for the exact assigned continuation, and is not a global worker default. Preserve role-specific context/spend bounds.

## Failure guide

| Observation | Correct action |
|---|---|
| Missing explicit source root or pin | Obtain them from the current assignment/source owner. Do not use the legacy environment/sibling/vendor ladder for scoped recovery. |
| No usable Macro checkout | Resolve the installed repository binding. Do not clone an unapproved fallback or use an unrelated global brief. |
| Expected source pin mismatch | Reconcile the assignment's source and the existing checkout. Do not remove the check merely to make startup pass. |
| Canonical compiler exit 1 | Inspect the named workstream's existence/schema using the current Agent OS owner. Error output is intentionally not copied into the prompt by this adapter. |
| Timeout / transport byte ceiling | Context was not emitted. Diagnose the bounded read; do not keep retrying unchanged or treat partial output as success. |
| Reader settlement unknown | Preserve the original reader/carrier and reconcile through its process owner before another attempt. |
| Malformed Git SHA or source-record digest | Reject the payload. The source digest must satisfy the existing `valid_source_records_digest` contract (`sha256:` plus 64 lowercase hex characters). |
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


## Explicit native-pilot limits and observed recall (2026-10-17)

The native adapter's default remains 6,000 **bytes**, not 6,000 tokens. An explicitly
selected project pilot may request up to 32,768 context bytes, under an independent
65,536-byte encoded JSON ceiling. Both ceilings are hard; an oversized complete packet
is still withheld rather than clipped. No launcher, user profile, hook, permission or
worker allowance is changed by this source option. The default reader deadline remains
10 seconds; an explicit on-demand read may use up to the incumbent reader's 60-second
ceiling. Keep expensive hydration out of unbound global startup.

A settled canonical read for `WS:MACRO-CONTEXT-INDEX` at Macro
`eb55c8573d94700dde35b6ce5b9af23738c710c0` returned 22,962 JSON bytes for a
4,000-token request (4,703 estimated tokens, 12 budget omissions). The unchanged
6,000-byte policy correctly withheld the body. With the selected 32,768-byte budget,
the adapter preserved the entire captured packet in 24,544 context bytes / 25,739
encoded bytes. This comparison reused the captured successful result and did not
repeat the compiler read. This ordinary packet fits; giant workstream records still
need canonical source hygiene or bounded expansion, not an unlimited startup budget.

A real M2 Codex 0.159.3 read-only test using the same logged-in account and unchanged
global configuration consumed that complete context through the native nested
`AGENTS.md` instruction chain. It correctly returned the exact workstream, Macro
revision, record digest, selected handoff, token estimate, omission count, advisory
status, absence of automatic successor-wave authority, and lack of verified live PR
state: nine checks passed with no tool calls. The temporary owned fixture was removed.
This is **initial-context comprehension proof**, not an installed SessionStart hook,
a Context MCP call, current-handoff acceptance, or fleet-wide parity.

The preceding native CLI test failed before inference because its configured
`disable_direct_message` required an agent message board not available in that CLI
session. For the no-children diagnostic only, disabling the entire multi-agent/helper
capability made the test run; direct-message suppression, execution rules, hook trust,
and the tightened read-only sandbox were preserved. Do not enable direct messaging,
bypass hook trust, change accounts, or weaken sandbox restrictions to repeat a failure.
Normal interactive sessions require their own capability-compatible profile.

Both Codex and Claude now treat a supported `SessionStart` `fork` event as
`FORK_REQUIRES_REBIND`. It emits no inherited workstream/continuation and invokes no
reader. New sessions do not inherit a lease or assignment merely by copying history.

The old review `native-context-v2-static-review-20261009-001` and the earlier
`EXECUTIVE-AUTONOMY-V1-CLOSURE` hydration uncertainty are distinct held operations.
These new source repairs and the separate read-only test do not resolve, replay or
replace either operation. Source publication, hosted checks, independent current-delta
review, accepted installation, effective hook trust, real task retrieval, and original
parent consumption remain separate proof obligations.


## Call-local settlement and protected Skill rollout (2026-10-17)

The existing CLI now exposes `main_with_outcome` without changing ordinary CLI
stdout, stderr or exit status. Its immutable result belongs to that one call:
`NOT_STARTED` only before reader dispatch; `UNKNOWN` once the runner is invoked and
on any caught runner exception; `SETTLED` only after the existing process owner
returns normally. A malformed payload or changed source pin remains a failed read,
but cannot make a successfully reaped process become unknown. No global result slot,
second runner, error-text parser, automatic retry, or new binding ceremony is added.

The bridge uses the optional typed path when installed in the same source generation.
Settled nonzero results produce `READER_SETTLED_FAILURE`; unknown or malformed results
retain `READER_RECONCILIATION_REQUIRED`. Legacy untyped failures stay conservative.
Boolean exit codes are rejected rather than accepted as integers. The exact-workstream,
source-before/after, complete-payload, and output-bound guards remain intact.
Sixteen new regressions failed before implementation; the combined owning suite now
passes 262 tests, including an actual short-timeout child settled by the existing owner.
Two returned worker drafts were not accepted as implementations because review found
state leakage, unchanged user-visible failure, removed diagnostics and/or false
process-uncertainty classification. The parent applied the corrected minimal boundary
and tested it; do not call those worker drafts approved or silently adopt their tests.

Separately from these unmerged hook repairs, the already-protected `mastermind-sol`
0.2.1 skills-only package was installed using the native Codex plugin manager in the
current user profiles on M2 Studio, M1 Studio and MacBook Pro. All 18 installed files
match protected Mastermind `e77631490e5bddca7d40c8cf039ae7763ce17b99`.
Canonical ordered path-to-SHA256-map digest:
`284447e00874b8a9f4d8bdaeaa52ca9c98a6a3b249264917448bcecf6f444eca`.
The package provides 12 existing Mastermind Skills, with no MCP, hook, or app bundle.
Only native `plugins` and `marketplaces` configuration sections changed; previous
entries, execution rules, sandbox, model, hooks and credentials were preserved.
No credentials were copied. The approved source package is independent of the held
#1307/#1273 hook drafts and does not release or install their code.

A real fresh M2 session listed all 12 methods and successfully read the installed
bootstrap Skill plus its boundary reference through native read-only file tools.
The provider first exposed a relative catalog alias; the actual reads resolved to
the installed cache, so catalog aliases must not be falsely rejected merely because
they are not absolute cache paths. A fresh MacBook session also recognized all 12
Skills. M1 installation and complete file identity are verified, but its native
inference test failed with revoked refresh-token / workspace-routing 401 errors.
The normal user sign-in on that machine is the exact missing action; do not replay
that test, use another account, or copy another machine's credentials.

The paired context-ablation test used the same read-only questions without the
injected context. It correctly returned unknown exact workstream/source/digest/handoff.
The context-supplied session returned the four exact references and all nine checked
facts/authority boundaries. This is one controlled initial-context example, not a
statistical equivalence claim or the eight-family Context Fabric release benchmark.
