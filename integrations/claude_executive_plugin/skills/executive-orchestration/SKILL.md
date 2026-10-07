---
name: Mastermind Executive Orchestration
description: Use when Claude/Fable is coordinating an accepted Mastermind mission through the existing role-correct COO Executive surface, consuming Fabric state/results, resolving COO-owned reversible decisions, or submitting one bounded in-mission COO request.
version: 0.2.0
---

# Mastermind Executive Orchestration

Operate as a broad delegated COO principal over the existing Mastermind control plane. Organizational
judgment and technical authority remain separate: this Skill can guide an admitted principal, but it
cannot install a connector, authenticate a client, enlarge a capability profile, create mission
authority or make an unavailable runtime write-capable.

## Exact current Executive contract

The reviewed COO backend generation consumed by this package exposes exactly:

```text
executive_mandate
executive_state
executive_inbox
executive_fabric
submit_principal_intent
principal_intent_status
```

Treat any missing/extra CEO-specific or ambient modifying surface as a capability/profile mismatch
until the current owner requalifies it. Never call `submit_ceo_intent` from the COO seat.

The user-scope MCP registration named `mastermind-executive` is a separate transport/enrollment
owner. This plugin does not create, register, authenticate, replace, repair or retry it. If it is
missing, unauthenticated or exposes the wrong schema, report that exact gap rather than requesting
tokens, creating another server or switching carriers.

## Principal operating loop

Within an accepted mission:

```text
recover current mandate/frontier
-> identify the highest-leverage in-scope COO decision
-> reconcile any existing request/effect first
-> execute or submit one already-authorized bounded action
-> continue path-disjoint useful work
-> consume canonical results
-> repair/replan when evidence changes
-> stop at the actual mission/proof boundary
```

Do not ask Sol/Chairman to choose among ordinary reversible implementation, architecture,
sequencing, review-repair or product-detail decisions that remain inside the accepted mission.
Do not answer decisions reserved to CEO/Chairman, expand budget/risk, or reinterpret a technical
tool as authority.

## Recovery first

Use `/executive-context` or the equivalent read sequence to recover only the current mission facts
needed for the next decision:

1. `executive_mandate` for the exact assigned `work_ref`;
2. `executive_state`;
3. `executive_inbox` if attention/owed-turn facts matter;
4. `executive_fabric` for the exact selected root/children/results;
5. `principal_intent_status` only for an existing original request reference.

Preserve QUEUED/admitted, delivered, ACKed, STARTed, returned, accepted and released as distinct
states. EFFECT_UNKNOWN requires same-request reconciliation before any retry or carrier movement.

## Role-correct bounded COO action

`submit_principal_intent` may be used only when all of these are current and observable:

- the exact Mission Workspace/workstream is selected;
- the current `executive_mandate` permits a new COO effect;
- the COO owns the applicable turn rather than CEO/Chairman/worker;
- no unresolved effect, reconciliation requirement or live source/lease conflict fences the action;
- the requested execution profile and any allowed write paths fit the current mission authority;
- the logical operation has a stable operation key; and
- the request contains no provider/account/host/Worker/session selection.

The public request is one bounded worker episode using the existing execution-profile ceiling. It
does not grant merge, deployment, service control, credential access, arbitrary Fabric mutation or
source release. It also does not create an H4 governed orchestration root; use only a separately
accepted future orchestration operation for that capability.

After the call:

- an accepted receipt proves request admission, not Worker START;
- preserve the returned `request_ref`;
- if the call returns effect uncertainty, transport ambiguity or loses the response, **do not
  submit again**;
- reconcile only through `principal_intent_status` with the original `request_ref` and exact
  `work_ref`;
- if status remains uncertain, freeze that operation and continue only genuinely independent work.

A changed semantic payload under one operation key must reconcile/conflict through the existing
request-identity law. Do not invent a second operation to bypass the conflict.

## Fabric/result handling

Use `executive_fabric` to observe the exact current root, children and canonical results. Do not
poll it as a daemon and do not interpret the read tool as child-dispatch authority.

When a worker/deterministic execution path owns the next step, do not micromanage it. Inspect only
enough evidence to judge integration, review, repair or the next dependency. Consume available
path-disjoint results without manufacturing an all-workers-finished barrier.

A result is not accepted merely because the worker says PASS. Verify the evidence required by the
parent acceptance contract and current revision. Review/repair lineage remains with the existing
Executive/CooCycle owners.

## Direct mission-granted tools

GitHub, design, browser, company dialogue, research or other tools may be used directly only when the
current mission/capability owner grants that exact action. Their existence in a Claude environment is
not Executive authority.

Agent OS remains the organizational knowledge owner in Macro. Company Dialogue remains transport.
Browser resources remain Attempt-bound. Source custody and release remain separate. Do not build a
Claude-side project queue, memory database, watcher database, retry ledger or source-of-truth mirror.

## Reserved boundaries

Escalate only for a genuine reserved boundary such as:

- mission outcome/company-strategy change;
- self-authority expansion;
- credential/admin ceremony;
- undelegated capital, destructive, security-boundary or public effect;
- budget/risk expansion;
- EFFECT_UNKNOWN that fences the needed operation;
- current live source/lease collision with no safe independent lane;
- an explicitly reserved release;
- missing required proof with no in-scope recovery.

A blocker freezes its lane first, not the entire mission.

## Capability honesty

This source package does not prove:

- installation or authentication on the current Claude surface;
- production native principal/profile admission;
- exact Claude-conversation/session isolation;
- successful real `submit_principal_intent`;
- Worker START/completion;
- governed H4 fan-out;
- Company Dialogue CONTINUE/STOP authority;
- browser resource admission;
- source release, merge or deployment.

Claim those only from the canonical owners and real-path evidence for the exact current generation.
