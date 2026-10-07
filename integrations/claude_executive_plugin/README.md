# Mastermind Executive Claude plugin

Status: **P2 SOURCE CANDIDATE / PRODUCTION INERT / ROLE-CORRECT COO WORKFLOW PACKAGED**

This directory is the private Claude plugin package for Mastermind Executive OS / COO integration.
It packages provider-side workflow and UX around the **existing** Executive, Mission Workspace,
CeoIngress, Runtime, Fabric and capability owners. It does not create another Executive backend,
OAuth client, MCP server, Runtime, queue, scheduler, session registry, retry plane, identity store,
token store, capability authority or source-release controller.

## Current composition

```text
Claude Code / Claude Desktop Code
        |
        v
Mastermind Executive plugin
  - role-correct COO orchestration Skill
  - /executive-context recovery command
        |
        v
separately enrolled user-scope MCP registration: mastermind-executive
        |
        v
#955 Claude local adapter candidate
        |
        v
existing installed Executive /mcp/coo route
        |
        v
existing COO admission / CeoIngress / Runtime / Workspace / Fabric
```

The plugin still ships **without** a plugin-owned `.mcp.json` and without hooks. The source package
therefore cannot install, authenticate or select the Executive connector by itself.

## Backend contract consumed by this package

The current protected Executive COO contract is server version `1.0.0` with exactly these six
role-correct tools:

- `executive_mandate`;
- `executive_state`;
- `executive_inbox`;
- `executive_fabric`;
- `submit_principal_intent`;
- `principal_intent_status`.

The first four recover current mission/runtime context. `submit_principal_intent` submits one
bounded **in-mission COO request** through the existing principal admission path. Acceptance is not
Worker START or completion. `principal_intent_status` reconciles the original request reference
without creating or retrying work.

This package never uses `submit_ceo_intent`. CEO and COO remain different principals/policies.
A future orchestration-root operation for governed fan-out is a separate H4 contract and is not
invented here.

## Connector and authentication boundary

#955 owns the distinct local Claude Executive client/transport candidate. Its current source is
**DRAFT/HOLD** and enrollment is not performed. This plugin does not treat that PR, a source file,
or a successful unrelated connector as proof that the current Claude process is authenticated.

Use the workflow below only when the exact current Claude surface actually exposes the reviewed COO
tool catalog through the separately enrolled `mastermind-executive` user-scope registration.

If the connector is absent, unauthenticated, exposes a CEO-only surface, has the wrong tool schema,
or differs from the reviewed capability generation:

- refuse modifying COO work;
- report the exact connector/profile mismatch;
- do not request tokens or copy credentials;
- do not add another server, tunnel or public endpoint;
- do not fall back from `/mcp/coo` to a CEO route;
- do not reinterpret a legacy CEO tool as COO authority.

## Bounded COO action workflow

A fresh principal first recovers current context through `/executive-context` or the same read
sequence directly.

Before `submit_principal_intent`:

1. read `executive_mandate` for the exact assigned `work_ref`;
2. require the mandate's current new-effect gate to permit the action and the COO to own the turn;
3. verify there is no unresolved effect, reconciliation requirement or live source/lease conflict;
4. keep the request inside the selected Mission Workspace and the mandate's allowed execution
   profiles / write paths;
5. use a stable operation key for the logical operation;
6. do not select provider, account, host, Worker, session or retry carrier in the request.

The public COO request remains bounded to the existing worker profiles. It is not source release,
merge, deploy, service control, credential access or a general Fabric mutation.

After submission:

- an explicit accepted receipt proves admission of the request, not execution;
- record the returned `request_ref`;
- if the response is uncertain or transport is ambiguous, do **not** submit again;
- reconcile only with `principal_intent_status` using that original `request_ref` and exact
  `work_ref`;
- consume current Executive/Fabric state before deciding the next mission action.

A different semantic payload under the same logical operation must reconcile/conflict through the
existing request identity law rather than minting a second operation.

## Recovery workflow

`/executive-context` is intentionally read-only. It should recover the smallest sufficient
frontier from the exact currently authenticated COO surface:

1. `executive_mandate` for the assigned mission;
2. `executive_state` for readiness and grounding;
3. `executive_inbox` only when relevant attention matters;
4. `executive_fabric` for the selected root/children/results;
5. `principal_intent_status` only for an already-existing COO request reference.

Preserve admission, delivery, ACK, START, CI, result and acceptance as distinct facts.

## Surface parity boundary

The plugin targets Claude Code first and may also be loaded by Claude Desktop's Code/plugin surface,
but one surface's success is not inherited by another.

The current #955 adapter candidate concerns the Claude Code user-scope registration path. Therefore:

- source packaging does not prove Claude Code installation or authentication;
- Claude Desktop plugin loading remains a separate exact-version proof;
- Claude Desktop Executive connector availability remains **UNPROVEN** until the real application
  exposes the reviewed COO tool schema;
- do not add an ad-hoc second connector if Desktop does not consume the accepted registration;
- any bundled-MCP/Desktop-extension route requires its own reviewed OAuth/client and schema proof.

## Development loading

Claude Code's plugin structure expects:

```text
.claude-plugin/plugin.json
commands/
skills/
hooks/        # optional; absent
.mcp.json     # optional; absent
```

For source development, load this directory using Claude's supported local plugin mechanism and pair
it only with the separately enrolled Executive connector. The manifest contains no credential,
endpoint secret, client ID, OAuth token, provider account, host identity or mission authority.

## Current capability state

P2 source adds:

- explicit synchronization to the current six-tool COO backend contract;
- current role-correct bounded-action instructions;
- exact original-request reconciliation instructions;
- a read-only mission/context recovery command that includes `executive_mandate`;
- source tests that reject CEO-tool leakage and stale tool/version documentation.

P2 source does **not** prove:

- plugin installation on any Claude surface;
- OAuth/client enrollment;
- the #955 adapter's independent review acceptance;
- exact native principal/profile admission;
- exact Claude-conversation/session isolation;
- successful `submit_principal_intent` on a real mission;
- Worker START or completion;
- H4 governed fan-out;
- Agent OS write authority;
- Company Dialogue CONTINUE/STOP authority;
- browser resource admission;
- source release, merge or deployment.

## Relationship to current carriers

- #962: merged P1 plugin source predecessor.
- #955: current Claude local Executive adapter candidate; separate transport/auth owner, DRAFT/HOLD.
- #676: existing SPEC_ONLY rich-principal / sealed-worker parity architecture.
- #600: existing orchestration-parity design carrier; no duplicate orchestration layer here.
- #919/#992/#660: merged native/adaptor/transport foundations consumed where applicable.
- Mastermind #1236 / PR #1240: current Claude Capability Hardening integration/evidence carrier.

Historical issue/PR text is evidence, not current runtime authority. Current protected procedure,
mission mandate, source custody, capability admission and effect state remain controlling.
