# Mastermind workforce capability integration

**Date:** September 13, 2026. **Owner of this integration proposal:** Sol.
**Scope:** role methods, tool delivery, native harnesses, workspaces and cross-host
work. **State:** source/research candidate, not production acceptance.

Protected procedure/source examined: Mastermind
`9ed16bf0fcc5b47e870350ff2413ff5c8c73b447`; Sol Skillpack 1.0.1 / bootstrap major 1.
This document complements the existing convergence architecture and the operator
environment proposal in PR #584. It does not replace their owners or authorize
unaccepted runtime changes. Re-read current owners before taking a live action.

## 1. What the finished product must do

Chris should describe a desired capability once. Sol should recover relevant
company context, identify the unfinished critical path, and assign the smallest
useful slice to an eligible worker without asking Chris to allocate accounts.
That worker should begin with the right source revision, workspace, role method,
actual tools, data semantics, and acceptance criteria. It should return a useful
artifact or real result rather than an unsupported completion claim. Another
session must be able to continue from durable evidence without recovering an
entire chat history.

The machine job is equally concrete: resolve an existing execution profile to an
eligible provider/account/harness/host, reserve the actual constrained resources,
materialize the approved inputs, observe the real capabilities, execute once,
collect results, reconcile uncertain effects, and return evidence to its owners.

The differentiator is not a large number of agents. It is company-specific research,
product judgment, reusable design/engineering methods, validated intelligence,
correct source and state ownership, and a continuously improving record of which
workflows actually deliver useful results.

A successful final rehearsal must include one real design-to-code feature, two
qualified provider/harness combinations, a second authorized host, a fresh Web
session, and recovery from an interrupted operation without duplicate effects or
manual account/file relaying by Chris. No component's green test substitutes for
that composed journey.

## 2. What exists, and what is still disconnected

The architecture was not absent. Protected source already contains a provider-neutral
`WorkerLaunchSpec`, result and collection contracts, the capability registry and
package-generation logic, and a bounded Codex Skill projection. The problem is the
gap between those owners, native/provider realization, useful role methods, and
real deployment proof. Existing source should be completed, not replaced.

| Capability | Evidence examined | Bounded conclusion |
|---|---|---|
| Common immutable worker inputs/results | `control_plane/worker_execution_contract.py` at the protected pin | Source exists; no fleet health inferred |
| Exact package/Skill identity | `control_plane/executive_capability_packages.py` and protected convergence amendments | Existing owner to extend, not a new registry |
| Codex custom-Skill projection | `scripts/ohf/capability_skill_projection.py` | Codex-scoped implementation; explicitly not the HF1 generic materializer |
| Common multi-provider broker | HF1-B PR #576 | Open source candidate; no heterogeneous production acceptance inferred |
| Plan/provider/harness separation | PRs #577, #578, #581, #583 | Active source candidates; constructor-private credentials and explicit plan gates |
| ACP worker path | PRs #575 and #579 | Provider-free/common-worker rehearsals; native production factory still a separate gate |
| Web/native environment | PR #584, head `194fa4fa34719faba9481e4f82f14e52535595cf` | SPEC_ONLY, owner-preserving delivery plan |
| Paper bridge | PR #585, examined head `220dcd23da09c5782c4b9b7cf699effff0c7eb90` | PARTIAL / BUILT_NOT_PROVEN; native staging reported but real design read/edit/export absent |
| Specialized craft methods | This source package | Executable authoring slice; not installed or runtime-attested |
| Executive connector in this session | Read-only `executive_state` attempt returned MCP transport HTTP 429 | Runtime state unknown; no CEO intent submitted |
| Studio access in this session | Ping responded, subsequent bounded file read timed out | Reachable transport is not proof of usable filesystem/executor |

The Paper candidate reports an open-file/editor initialization failure despite an
app/listener. Its exact next integration task is to obtain a normal approved editor
context and prove one design read/edit/image/JSX journey on its existing carrier.
It is not a reason to write another Paper proxy. Source claims above are not
independent production observations; their proof scope is retained deliberately.

## 3. One system, with different responsibilities

Think of a session as six separate choices:

- **Role:** what job and method the agent follows.
- **Model/provider plan:** the reasoning service and its actual entitlement.
- **Harness:** the program implementing tool calls, permissions, process behavior,
  context management and provider protocol.
- **Tools/plugins:** the allowed ways to reach external resources.
- **Workspace/resource binding:** where this particular task may read or write.
- **Evidence and continuity:** how results become trustworthy and recoverable.

A MiniMax or Alibaba model does not become a fully equipped engineer just because
it can answer through a Codex- or Claude-compatible endpoint. A plugin visible in
Sol's Web session is not automatically available to a subprocess on the Mini. A
Grok session and a Cursor session are different execution surfaces even when an
entitlement bundles them. These dimensions must not be collapsed into a provider
name or a single green readiness flag.

Preserve the existing authority split:

| Concept | Owner |
|---|---|
| Jobs, Attempts, Workers, execution/admission/retry | Executive OS |
| Strategy, organizational decisions, discoveries, handoffs | Declared strategy source and Macro Agent OS |
| Capability grants, source generations and attestation | Existing ExecutionCapabilityRegistry/package owners |
| Common worker invocation and native realization | HF1 and its provider adapters |
| Account limits, eligibility and reservations | Existing provider-capacity / Capacity / RF1 owners |
| Multi-host placement | Existing MH1 / Workbench Fleet owners |
| Source/workspace custody and exact writer | Existing source/workspace owner |
| Browser realm, exact session and wake | Browser Resource Fabric / Web-Sol / RuntimeBinding / Wake |
| Code/reviews/CI and full research | GitHub / owning repository |
| Portfolio view | Linear, as projection |
| Dialogue transport and hot state | Slack / Agent Relay / Company Dialogue |

No new worker database, plugin scheduler, desktop queue, quota ledger, transcript
store, password vault, remote shell gateway, or source-index service is needed for
this integration.

## 4. How each worker should actually start

The existing caller should assemble a small task packet from authoritative reads,
not concatenate all company history into every agent's context. It needs the user
and machine outcome, exact source pointers, current assignment, role, scope and
non-goals, relevant data/time/correction behavior, workspace and host references,
actual requested capabilities, budget/resource limits, expected output, acceptance,
stop conditions, and durable continuation location.

The new compiler supplies the **authoring part** of that packet. It validates
completeness, loads the common method and one selected role, and emits a reproducible
brief. It does not fetch current state, bind an assignment, choose a worker, grant
a tool, stage a native package, or construct an Executive request. Its hashes are
not canonical capability digests. The existing caller can use the reviewed result
as ordinary prompt content without calling it an installed Skill.

For real native Skill delivery, use the existing approved package generation. The
runtime must observe that the intended methods and tool schemas are really exposed
and that unexpected ambient capabilities are absent or explicitly classified. Do
not add this package to the first exact four-Skill `mastermind-operator` canary;
create a separately reviewed profile/generation through its owner.

The worker must be able to answer: what am I doing, what exact source am I using,
where may I work, which tools actually work, what is missing, what proof is owed,
and where will the next session find the result? If these cannot be answered,
additional model compute does not fix the problem.

## 5. Role and plugin catalog

Use a small core and selective overlays. Do not attach every connector to every
worker. A method teaches a process; a tool grant enables an action. They must be
reviewed and tested separately.

| Role | Method now supplied | Selective tool needs | Useful output |
|---|---|---|---|
| Orchestrator | Outcome, critical path, decomposition, scarce-capacity choice, integration | Current owner reads, bounded delegation/dialogue when admitted | A completed capability increment, not a fan-out count |
| Designer | Workflow, state matrix, tokens, responsive/accessibility design, engineering handoff | Scoped Paper/Figma, approved source/design assets, visual inspection | Usable design with real states and component/data mapping |
| Frontend engineer | Existing framework/components, real data, interaction and browser proof | Owned source tools, reviewed build recipes, isolated app browser | Integrated visible feature |
| Backend/data engineer | Contract, deterministic authority, correction/idempotency, consumer wiring | Owned source, approved service/data reads, bounded validation | One trustworthy producer-to-consumer vertical |
| Researcher | Primary evidence, contradictions, competitor jobs, falsifiers | Web/docs, approved research stores, source reads | A useful sourced decision input |
| Data scientist | Point-in-time evidence, baselines, held-out/forward validation, failure analysis | Existing data/evaluation tools and bounded compute | Reproducible evidence of useful intelligence |
| Reviewer | Immutable source, intent review, counterexamples, proof scope | Read-only source/diff/tests and approved evidence | Reproducible material findings; no self-merge |
| Verifier | Exact release/target, real journey, inspected evidence, recovery limits | Approved read/observation browser and existing evidence tools | Scope-qualified production proof or an exact failed gate |

The existing Sol/Operator skills retain bootstrap, receive-commission, progress,
escalation, finish and dialogue behavior. Navigator handles where to find a system;
Craft handles how to do the professional work. Reality handles product-journey
inspection. These are complements, not competing general-purpose agent frameworks.

Tool families to compose, in priority order:

1. **Company orientation and execution:** existing Sol, Operator, Cortex/Navigator,
   Executive and dialogue surfaces. Keep current unavailable states visible.
2. **Source and engineering:** GitHub now; existing Workbench Read and bounded Action
   when proven; Code Intelligence's accepted facade later. Do not build another LSP,
   vector index, remote editor or repository reader as a shortcut.
3. **Design and visual verification:** current Paper candidate plus Figma during the
   transition, and the existing isolated browser resource/evidence path.
4. **Domain data, research, deployment and learning:** approved domain tools, bounded
   documentation access, existing deployment owners and analytics/observability.
   Release and database writes belong only in roles with explicit grants.
5. **Artifact production:** document, spreadsheet, presentation and media methods only
   when the assignment needs those deliverables. Do not load them into every coder.

Do not give all workers Slack posting, database writes, deploy access, personal
email, global filesystem access or subscription account controls by default.

## 6. Provider-native delivery, without a lowest-common-denominator rebuild

| Surface | Delivery approach | Gate that must survive |
|---|---|---|
| Codex | Existing worker/App Server adapter; reviewed task prompt and accepted Skill roots/MCP configuration | Exact observed Skill/tool set and sandbox; no ambient global-root surprise |
| Claude Code | Constructor-owned config and custom-subagent definition; explicit method preload where supported | Missing preloads, ambient Skill discovery and effective tools must be checked |
| Cursor | Qualified native CLI/ACP adapter and its reviewed plugin/skill/rule configuration | Verify installed-version behavior and exact tool execution, not just CLI presence |
| Grok | Existing native/ACP qualification path; preserve its provider session and common worker contract | Real native factory, result collection, cancellation and tool loop proof |
| Alibaba | Existing plan/harness-binding candidate, including its separately reviewed Codex-compatible route | Actual plan entitlement, wire protocol, private credential enrollment and real call proof |
| MiniMax / GLM | Existing subscription/profile and compatible-harness work | Do not treat a locally successful experiment as production or unattended permission |
| Web Sol | Approved connected apps and current source procedures; bounded gateway access to host resources | Each actual account/session connection and subject's permissions, not one test for all seats |

Current vendor documentation matters. Claude's current documentation describes
nested subagents, so a blanket assertion that nesting is impossible would be stale.
It also distinguishes skill preloading from all skills discoverable at runtime;
plugin agents ignore certain security-sensitive fields. Company child budgets and
effective configuration must therefore be enforced by the existing runtime, not by
an optimistic prompt or an assumed vendor default. Verify installed versions before
using newly documented features.

Prefer the smallest already-qualified harness for a role. Do not purchase another
plan to solve an unproven tool loop, missing workspace isolation, or a broken
transport. Do not automatically promote any interactive subscription to unattended
use; current plan/profile law and actual entitlement remain explicit gates.

## 7. Paper versus Figma: design and code, not an either/or slogan

Paper's official MCP reference includes `get_jsx`, screenshots, styles and editing,
and documents a design-to-website workflow. Thus the assumption that Paper is only
for drawing is incorrect. Exported JSX is still an intermediate design artifact;
Mastermind's engineer must adapt it to the existing component/data architecture.

Published allowances on the research date: Paper Free has 100 MCP calls per week;
Paper Pro advertises one million per week at $20/editor/month monthly or $16 with
yearly billing. Figma Professional Full/Dev has a published 200 read-tool calls/day
and 10/minute limit; some write tools are exempt. The connected Figma account's
`whoami` reported Full/Pro. These are not measurements of safe concurrency.

Recommendation: qualify Paper as the high-volume authoring surface, retain Figma
for accepted designs and migration checks, and use source code plus real-browser
proof as the engineering acceptance path. Do not cancel Figma or purchase Paper
from this proposal. An approved open editor and a small real round-trip must work
before a subscription decision is allowed to masquerade as integration progress.

Treat the actual desktop design context as one exclusive writer until stronger
isolation is proven. File selection is shared mutable state; a per-call mutex alone
does not establish a whole multi-call task's custody. Extend the existing resource
reservation owner to bind the task's document/app generation. Use read-only copies
or immutable exports for parallel analysis. Never infer safe independent files,
users, tabs, or editor processes from the weekly quota.

The Web path must be the existing authenticated gateway to the bounded Paper
adapter, not a publicly exposed local Paper port or another omnipotent MCP. A Web
session cannot use the Mini's `127.0.0.1` directly. The domain adapter must retain
exact target checks, allowed operations, cancellation/effect reconciliation and
artifact handling, while the existing auth/resource owners retain their authority.

## 8. Where files live and how work moves between machines

| Material | Correct home |
|---|---|
| Reusable approved methods | Owning repository package, exact accepted generation |
| Task source checkout | The task's owner-created host-local workspace at an exact commit |
| Attempt logs/intermediate work | Existing `run_dir` and artifact collection path |
| Product code, test fixtures, approved design/source assets | Owning repository, scoped branch/PR |
| Large/private images and exports | Existing approved artifact custody; publish only authorized references |
| Cross-session decisions/discoveries/handoffs | Macro `agentos/`, following its schema and existing parent |
| Credentials, account homes, browser profiles | Existing private realm/credential owner; never in the task packet |
| Live jobs, quotas and resource claims | Their current owners, not skill files or an ad hoc shared folder |

Use logical references in prompts: repository plus commit plus path, or the existing
artifact reference plus content hash. The runtime resolves host-local paths. Do not
assume every machine has `/Users/chriswong`, the same external drive, an identical
repository checkout, or a mounted shared filesystem.

For a Mini worker needing a Studio design resource, choose among three existing-owner
operations: call the authorized remote resource; request the source owner's bounded
artifact transfer; or request placement of a new eligible task on the resource host.
The model should not improvise SSH credentials, copy browser profiles, or recursively
sync another worker's home. A task does not migrate merely because its model has
changed machines.

Source transfer uses immutable Git snapshots/patches through existing custody.
Artifact transfer uses existing collection, with size/hash/rights validation and
atomic publication at the receiver. Never share a mutable Git index, live runtime
SQLite file, provider home, token file, or browser profile between hosts. A path
is not an artifact identity. A missing mount is a real blocker, not an empty store.

Before START, the current placement owner may rebind eligible unstarted work under
its law. After START or an uncertain effect, keep the binding and reconcile first.
A successor on a new host requires the appropriate explicit transition, input
custody and new runtime observation; it does not inherit authority from a copied
transcript. Separate lifecycle continuity from transport connectivity.

## 9. Capacity and context without uncontrolled fan-out

Admit work only when the intersection of required capabilities, provider entitlement,
actual account quota, host resource headroom, source-writer custody, and exclusive
browser/design resources permits it. Do not reduce unlike limits to a single
misleading numeric capacity value.

Use current provider-capacity observations and reservations. Unknown remaining quota
is not zero and not unlimited; missing reset time is not a guessed hourly schedule.
Record actual plan/account dimensions privately in the existing owner, not in role
source. Existing account-pool policy can reserve scarce principal capacity; this
program should consume it rather than create competing spend counters.

Give orchestrators an explicit child envelope and depth/total-budget constraints.
Children cannot multiply permission or capacity by spawning their own children.
Serialize effect-bearing work on shared resources; parallelize independent read,
research and owned source tasks. Stop/reconcile rather than fail over after an
ambiguous provider or tool effect.

Keep context small: common procedure plus one role method, task facts, relevant
source pointers, and the exact output contract. Load design/data/deployment overlays
only when needed. Do not copy the parent's entire chat or every connected MCP schema.
Critical exclusions and unknowns must remain visible even when a context budget is
exceeded. Reuse the existing bounded Agent OS context compiler rather than build a
new memory/grounding pipeline.

## 10. Delivery sequence and observable acceptance

### Slice A - practical role authoring (this candidate)

Ship one reusable Craft Skill with eight playbooks, a dependency-free briefing
compiler, complete examples and focused tests. Its useful result is a complete,
role-specific task prompt that does not fabricate runtime readiness. Package it for
immediate explicit authoring use. Keep native admission and production claims false.

### Slice B - one rich worker that actually uses its method and tools

Continue the existing package/registry and qualified native adapter owners. Admit a
separate Craft-enabled profile rather than changing the exact four-Skill baseline.
Use one approved disposable assignment. Demonstrate meaningful role-method use,
exact requested/observed capabilities, real source/tool input, an artifact collected
through the existing result contract, and an honest missing-tool failure. Prefer the
already-qualified route; only then generalize across provider candidates.

### Slice C - one design-to-code vertical

Use Paper #585's current carrier and complete its editor initialization and real
round-trip. Bind a disposable document, make one approved edit, inspect returned
image bytes, extract JSX, and hand it to an engineer with the actual data/state
contract. Implement one real Mastermind interaction in its owning app and show it
in the approved browser. No permanent mock backend or standalone throwaway page.

### Slice D - heterogeneous harness parity

Integrate the existing HF1-B/provider-profile/plan-binding and ACP work without
competing factories. For each actual route prove skill/prompt delivery, tools,
structured result, artifact collection, process cancellation, quota/auth failure,
and cleanup. Keep default-off profiles off until their exact route is accepted.
A common Python interface is not proof that every provider obeys it.

### Slice E - two-host resource and artifact journey

Finish existing MH1/Workbench Fleet prerequisites. Run a new portable task on the
second host; prove exact workspace/source identity, resource reservation, bounded
artifact handoff, and consumption from the first host. Inject wrong host, stale boot,
missing toolchain, stale source and reply loss. Do not migrate a live browser or
account home. Retain the original operation through uncertain effects.

### Slice F - fresh Web and native user experience

Compose Navigator/Control Room boot, Workbench Read/Action, exact session binding,
and capabilities into the existing operator experience. Show assignment, source,
provider/harness, host, methods actually loaded, tools actually callable, missing
gates, resource/quota state, and evidence. This is an existing-owner projection,
not a new monitoring/control application.

Run a fresh-session end-to-end task and recovery rehearsal. Then measure useful
completion, rework, false completion, human interventions, tool failures, resource
waits and model/tool cost through existing telemetry. The success criterion is
less repeated archaeology and more accepted user capability, not more agents.

## 11. Proof ladder and release limits

Keep these separate: source authored; source reviewed; source protected; installed;
capabilities observed; actual useful tool journey; real production consumer; and
fleet/account/host generalization. Record source and release identities, target,
rights, input time, and what was not tested. No automatic promotion based on a test
count, install success, CLI presence, MCP initialization or a model's self-report.

Tests for the authoring slice cover every role, required fields, unsafe paths,
source SHA syntax, oversized/duplicate/malformed inputs, method digest drift,
misleading Markdown structure, bounded errors and real CLI output. They do not
prove provider behavior, semantic adherence by a model, production isolation,
account entitlements, or a deployed user journey.

## 12. Primary evidence and implementation references

- [Protected Sol index](https://github.com/mastermindx-market-intelligence/Mastermind/blob/9ed16bf0fcc5b47e870350ff2413ff5c8c73b447/docs/sol_skills/INDEX.md)
- [Protected worker contract](https://github.com/mastermindx-market-intelligence/Mastermind/blob/9ed16bf0fcc5b47e870350ff2413ff5c8c73b447/control_plane/worker_execution_contract.py)
- [Exact Skill-set amendment](https://github.com/mastermindx-market-intelligence/Mastermind/blob/9ed16bf0fcc5b47e870350ff2413ff5c8c73b447/docs/superpowers/specs/2026-09-01-agent-operator-skill-set-exposure-amendment.md)
- [Operator environment #584](https://github.com/mastermindx-market-intelligence/Mastermind/pull/584)
- [Paper implementation #585](https://github.com/mastermindx-market-intelligence/Mastermind/pull/585)
- [HF1 broker #576](https://github.com/mastermindx-market-intelligence/Mastermind/pull/576)
- [Plan/harness binding #583](https://github.com/mastermindx-market-intelligence/Mastermind/pull/583)
- [ACP qualification #575](https://github.com/mastermindx-market-intelligence/Mastermind/pull/575)
- [ACP common worker #579](https://github.com/mastermindx-market-intelligence/Mastermind/pull/579)
- [Paper MCP reference](https://paper.design/docs/mcp)
- [Paper pricing](https://paper.design/pricing)
- [Figma MCP limits](https://developers.figma.com/docs/figma-mcp-server/rate-limits-access/)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [Codex Skills](https://developers.openai.com/codex/skills)
- [Codex MCP](https://developers.openai.com/codex/mcp)
- [Cursor documentation](https://cursor.com/docs)

Vendor pages were checked on September 13, 2026. They are descriptive documentation,
not company authority or proof of this installation. Recheck current versions and
actual behavior at adoption. Runtime errors above are this session's observations,
not a declaration that an underlying service is universally down.
