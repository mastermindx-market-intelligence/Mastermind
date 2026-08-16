# Executive OS Phase 1G — G0 Architecture Acceptance Index

**Status:** commissioning / gate index; **NO PRODUCTION ARMING**  
**Date:** 2026-08-15  
**Applies to:** PR #66 / Phase 1G Agent Fabric + Workspace CEO Autonomy

---

## 0. Purpose

This file exists so a later implementation or review session cannot accidentally treat the Phase 1G executive-autonomy hardening as an optional side note or mark G0 complete after reviewing only the original six design documents.

G0 is **not complete** until every item in this index is satisfied.

---

## 1. Binding design set and precedence

The Phase 1G architecture must be reviewed as one set:

1. `research/EXECUTIVE_OS_PHASE1G_AGENT_FABRIC_MASTER_DESIGN.md`
2. `research/EXECUTIVE_OS_PHASE1G_INFRASTRUCTURE_DESIGN.md`
3. `research/EXECUTIVE_OS_PHASE1G_MASTERPLAN_AND_WAVES.md`
4. `research/EXECUTIVE_OS_PHASE1G_PROVIDER_EVIDENCE_REGISTER.md`
5. `research/EXECUTIVE_OS_PHASE1G_WORKSPACE_CEO_AUTONOMY_TRACK.md`
6. `research/EXECUTIVE_OS_PHASE1G_WORKSPACE_CEO_EVIDENCE_REGISTER.md`
7. `research/EXECUTIVE_OS_PHASE1G_EXECUTIVE_ATTENTION_AND_CHAIRMAN_CONTROL_AMENDMENT.md`
8. this G0 acceptance index.

For executive attention, semantic triage, direct conversational commissioning, Chairman authorization, activation claims, prompt-injection defense, project strategic closure, and overlapping executive scope, document 7 is the more-specific governing Phase 1G amendment.

Nothing here overrides the higher source law: Charter, strategic state, authority map, accepted directive, Phase 1F contract, and current verified code/evidence.

---

## 2. G0 hard gates

G0 may be declared PASS only when all of the following are true:

### G0-A — documentation-only boundary

- PR #66 still changes no production runtime behavior, schema, credential, scheduler, provider worker, MCP production mode, Slack authorization path, or CEO trigger service.
- No design convenience silently weakens Phase 1C-A, Phase 1F-B/C, trusted MCP caller identity, least-privilege, review independence, or migration-order gates.

### G0-B — independent fresh-context architecture/security review

A reviewer that did **not** author the Phase 1G design/hardening must review the full binding design set against at least:

- duplicate control plane / second scheduler / second priority queue;
- authority widening from labels, model output, semantic recommendations, Slack, GitHub, or chat identity;
- hidden Grok/LLM suppression authority;
- hard-floor demotion;
- semantic-triage outage, staleness, malformed output, and prompt injection;
- event compression losing a late stronger event;
- activation duplicate delivery, duplicate cognition, stale write, and ambiguous timeout;
- overlapping cross-project executive scope;
- Chairman-request identity, supersession, replay, stale-click, and free-form-text bypass;
- immutable commission-reference binding and two-phase artifact/directive failure recovery;
- Job technical completion versus objective/agenda closure;
- Workspace configuration drift and silent reasoning downgrade;
- Secure MCP Tunnel reachability versus authorization identity;
- self-wake/runaway chains, strategic-review make-work, and `NO_ACTION`/deferred-case semantics;
- autonomous self-modification of constitutional authority/wake/reasoning rules;
- migration collision with Phase 1F-B;
- production rollback/drain/kill semantics.

Every confirmed finding must be adjudicated in the binding docs or a follow-up commit before G0 PASS.

A review written by the same session/model that authored the amendment may be useful self-review, but it does **not** satisfy this independence gate by itself.

### G0-C — X0-A live Workspace capability matrix

Run live, zero-production-write canaries against the actual ChatGPT Business workspace and record each row as:

```text
PROVED | REFUTED | STILL_UNKNOWN
```

with evidence class:

```text
OFFICIAL_DOC | LIVE_ACCOUNT_CANARY | OPERATOR_OBSERVED | ARCHITECTURE_INFERENCE
```

Required capability rows:

1. Workspace Agents enabled for this Business workspace.
2. API trigger channel can be published and invoked.
3. Exact normal trigger response shape/status on this workspace.
4. Workspace Agent access-token scope and rotation/revocation behavior relevant to the dispatcher.
5. Stable retry/idempotency mechanism actually available to the trigger endpoint.
6. Conversation-continuity mechanism actually available to the trigger endpoint, if any.
7. Whether any run id/status/URL metadata is actually available on the live account; if not, record REFUTED/STILL_UNKNOWN rather than relying on stale docs.
8. Final response retrievability through the trigger API (current official Help Center says unavailable; live canary confirms current account behavior).
9. Published-agent model selection.
10. Published-agent reasoning-effort selection.
11. Whether deterministic external routing to logical `R0_FAST / R1_DEEP / R2_PRO` can be proved; otherwise R2 autonomous production remains unavailable.
12. Live published config/version identity visibility or the need for operator publication receipts.
13. Custom MCP availability inside the Workspace Agent.
14. Full MCP modifying-action availability and approval behavior for this Business workspace.
15. Secure MCP Tunnel availability/reachability to PR #64 READONLY gateway without public bind.
16. Trusted workspace/app/principal identity visible at the Mastermind side through the actual MCP/tunnel path.
17. Difference, if any, between autonomous Workspace Agent MCP identity and human-started ChatGPT MCP identity.
18. Whether interactive Chairman identity can be proven strongly enough for direct `CHAIRMAN_DIRECT`; otherwise direct chat receives only CEO/app authority and reserved decisions use Chairman requests.
19. Workspace Agent Slack availability relevant to notification/discussion.
20. Whether Slack interactions can produce a strongly identity-bound typed action suitable for Chairman decisions; until proved, Slack remains notification/discussion transport only.
21. Agent-owned versus end-user app connection behavior relevant to service identities.
22. Published MCP tool snapshot/update behavior and configuration drift handling.
23. Any approval/blocking behavior that can prevent modifying calls independently of Mastermind authorization.
24. Global/service limits or behaviors that materially affect trigger retry, timeout, continuation, or scheduling correctness.

**No X0-A observation creates production write authority.**

### G0-D — primary-source evidence reconciliation

The Workspace CEO evidence register must reflect current primary-source facts and must not elevate stale or contradictory product documentation into runtime law.

As of 2026-08-15, current official OpenAI Help Center documentation states:

- Workspace Agents can be API-triggered;
- the API queues the run and returns `202 Accepted` with no response body/run id;
- the final agent response cannot currently be retrieved through the trigger API;
- Workspace Agents allow model and reasoning-effort configuration;
- Workspace Agents can use custom MCPs;
- full MCP including modify/write actions is beta for ChatGPT Business/Enterprise/Edu;
- ChatGPT cannot directly reach a local MCP server, and Secure MCP Tunnel is the documented private-network path.

If another official or live surface exposes richer metadata, record it as separate evidence and prove it on X0-A before making it load-bearing.

### G0-E — explicit commissions after review

After G0-B and G0-C findings are adjudicated, refresh the implementation commissions before build:

- X1-A — private READONLY MCP reachability;
- X2-A — Sol CEO mission/eval corpus;
- X2-B — provider-neutral semantic-triage shadow evaluator;
- X3-A — Executive Attention + Wake Router + activation-claim design/fixture;
- X4-A — Reasoning Governor / deterministic Pro-route proof;
- X5-A — production write, immutable commission, interactive ratification, and Chairman-control contract.

The refreshed commissions must cite the exact G0 review commit and X0-A evidence revision they depend on.

---

## 3. Required G0 review outcome

The independent review ends with one of:

```text
PASS
PASS_WITH_NONBLOCKING_RESIDUE
BLOCK
```

`PASS_WITH_NONBLOCKING_RESIDUE` must name every residue and explain why it does not affect the design baseline or future production authority.

`BLOCK` keeps PR #66 draft/not-mergeable-by-governance until the findings are fixed and re-reviewed.

GitHub technical mergeability is not G0 architectural acceptance.

---

## 4. X0-A evidence artifact

X0-A should be committed as a dated, append-only or revisioned evidence artifact, for example:

`research/EXECUTIVE_OS_PHASE1G_X0A_WORKSPACE_CAPABILITY_MATRIX_YYYY-MM-DD.md`

Each row should carry:

```text
capability_id
claim
status
source_class
source/reference
live_canary_method_if_any
observed_result
security/architecture consequence
load_bearing: yes|no
retest_trigger
observed_at
```

Do not overwrite an old observation to make current behavior look historically stable. Product behavior is volatile; new evidence supersedes prior evidence explicitly.

---

## 5. G0 stop condition

Until the fresh-context review and X0-A matrix are complete and adjudicated:

- PR #66 remains design-only;
- X1/X2/X3/X4 fixture/shadow work may be commissioned only where it does not assume unresolved live platform behavior;
- no production MCP write arm;
- no autonomous CEO wake;
- no Slack Chairman authorization;
- no semantic triage affecting production wake routing;
- no production schema migration dependent on Phase 1G executive-attention concepts.

This is intentional sequencing, not an architecture defect.
