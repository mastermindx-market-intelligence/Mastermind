# Business Sol Surface Convergence Program Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver ChatGPT Business as the primary Chairman ↔ Sol operating cockpit through one `Mastermind Sol` plugin and small authenticated MCP apps, without replacing any existing Mastermind truth, lifecycle, identity, routing, dialogue, projection, or evidence owner.

**Architecture:** This is a program DAG, not one implementation carrier. The accepted `One Experience, Federated Authority` architecture is decomposed into independently reviewable plugin packaging, OAuth, Steward, Executive, installation, canary, RuntimeBinding, dual-run, cutover, and retirement plans. Every modifying wave reuses the existing canonical owner for its fact and stops before an adjacent owner’s authority.

**Tech Stack:** Existing Mastermind Python 3.11+ repository, GitHub protected source and pull requests, Macro Agent OS Git records, Executive OS/CeoIngress/RuntimeBinding/Wake, MCP 2025-11-25-compatible servers, ChatGPT Business custom apps, OAuth 2.1, Secure MCP Tunnel, MCP Apps UI, pytest.

**Spec:** `docs/superpowers/specs/2026-08-29-business-sol-surface-convergence-design.md`

## Global Constraints

- The architecture carrier is Mastermind PR #234, exact approved head `063585120844ed02f57129770dd964744a4db97a`, operation `business-sol-surface-convergence-f0-20260829-sol-001`.
- Planning source is protected `Mastermind@1b99ea1d0a6232e11fd46915d348685764cb00cf`, Skillpack `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1. Every later START re-pins then-current protected source and loads required procedures from one exact commit.
- PR #234 remains `DRAFT / HOLD-FOR-SOL` while the current `SOL-DIR-PRO` release serialization is active. Planning may proceed on a stacked branch. No Business plan or implementation carrier merges merely to create movement.
- Executive OS remains the sole Job / Attempt / Worker / Event, admission, current-Attempt, lease/fence, retry and requeue authority.
- Agent OS remains the repository-backed workstream / decision / discovery / handoff authority. Linear remains selected projection. Slack remains dialogue/collaboration/audit/fallback transport. GitHub remains implementation and proof truth.
- SessionTargetRegistry / RuntimeBinding and Wake remain the only accepted logical-target, rotating-destination, attention-obligation, delivery and acknowledgement owners.
- Do not create a super-MCP, Business session database, Sol-election service, plugin memory store, second Steward, second Linear synchronizer, second retry plane, second provider router, second scheduler, or another Mastermind OS.
- `Mastermind Sol` generation 1 references Steward and Executive only. Surface presence is excluded until BSC-RB1/BSC-RB2 prove an exact safe seam.
- Workspace Agents do not become the normal Mastermind lifecycle. They may later act only as bounded consumers or ingress clients of the existing Executive system.
- No implementation wave assumes a trusted ChatGPT conversation identifier. Unknown exact reasoning-surface identity remains `UNKNOWN` and cannot be repaired by title, timestamp, Slack principal, model text, browser recency, or activity.
- A Business app connection, OAuth token, ChatGPT confirmation, Slack message, Linear assignment, GitHub check, or plugin installation never grants organizational authority by itself.
- No live secret, OAuth code, token, cookie, provider credential, app secret, browser state, private key, or installed app identifier enters Git, Slack, model-visible logs, argv, environment dumps, test snapshots, or proof receipts.
- Every implementation plan uses RED-first tests, immutable exact heads, exact changed-path census, fresh hosted proof, independent review where required, and a truthful capability state.
- Green CI, app publication, tunnel connectivity, OAuth success, `QUEUED` admission, worker execution, GitHub merge, deployment, production proof, and final Chairman acceptance remain distinct states.

---

## File / Plan Topology

This program plan owns sequencing only. Each implementation subsystem receives its own plan and carrier:

```text
docs/superpowers/plans/
  2026-08-29-business-sol-surface-convergence-program.md
  2026-08-29-business-sol-plugin-packages.md
  2026-08-30-business-sol-oauth-resource-server.md
  2026-08-30-business-sol-steward-app.md
  2026-08-30-business-sol-executive-app.md
  2026-08-31-business-sol-installation-enrollment.md
  2026-08-31-business-sol-read-canary.md
  2026-08-31-business-sol-admission-canary.md
  2026-09-01-business-sol-surface-identity-falsifier.md
  2026-09-01-business-sol-runtime-binding.md
  2026-09-02-business-sol-dual-run-cutover.md
  2026-09-02-business-sol-legacy-subtraction.md
```

Dates after the first plan are planning filenames, not deadlines. Each file is authored only after its entry gate is current and its collision census is complete.

## Program Dependency Graph

```text
BSC-F0  approved architecture / PR #234
   |
   +--> BSC-O0  Agent OS parent + projection reconciliation
   |
   +--> BSC-P1  skills-only marketplace + plugin packages
   |
   +--> BSC-A1  OAuth/resource-server library
              |
              +------------------+
              |                  |
     #224 Secretary contract   AD-ID1/CeoIngress current owner
     #228 Steward core             |
              |                  |
              v                  v
          BSC-S1              BSC-E1
      Steward app + UI    Executive production arm
              |                  |
              +--------+---------+
                       v
                    BSC-U1
          Business app/tunnel enrollment
                       |
                 +-----+-----+
                 |           |
                 v           v
              BSC-C1       BSC-C2
          read canary   harmless admission
                 |           |
                 +-----+-----+
                       v
                    BSC-D1
                dual-run evidence
                       |
             +---------+---------+
             |                   |
             v                   v
          BSC-RB1            Business-first
     surface identity probe   read/root admission
             |
             v
          BSC-RB2
     bounded RuntimeBinding
             |
             +---------+
                       v
                 BSC-CUTOVER
                       |
                       v
                    BSC-R1
             proven legacy subtraction
```

BSC-P1 and BSC-A1 may execute in parallel only after BSC-F0 is protected and their current path census remains disjoint. BSC-S1 and BSC-E1 may execute in parallel only after their distinct owner dependencies are protected and no source path collision exists.

---

### Task 1: Protect the approved BSC-F0 architecture without disturbing the autonomy release train

**Files:**
- Existing: `docs/superpowers/specs/2026-08-29-business-sol-surface-convergence-design.md`
- Existing carrier: Mastermind PR #234
- Existing exact head: `063585120844ed02f57129770dd964744a4db97a`

**Interfaces:**
- Consumes: Chairman written-spec approval recorded on PR #234; current protected Skillpack; current `SOL-DIR-PRO` release serialization evidence.
- Produces: one protected architecture source law that downstream plans may cite from current `master`.

- [ ] **Step 1: Re-pin the release gate immediately before any readiness change**

Read:

```bash
git fetch origin master
git rev-parse origin/master
git show origin/master:docs/sol_skills/INDEX.md | sed -n '1,40p'
```

Expected: one exact protected commit, compatible Skillpack, and no unresolved source collision that invalidates the approved architecture.

- [ ] **Step 2: Re-read current director serialization and exact PR state**

Required facts:

```text
current protected Mastermind SHA
current #234 head SHA
current #234 changed-file census
current required check conclusions
current release serialization owner and hold/release edge
```

If the current director has not released nonurgent Mastermind records merges, leave #234 DRAFT/HOLD. Do not post a competing release direction.

- [ ] **Step 3: Verify exact architecture evidence**

Run from an isolated checkout at the exact PR head:

```bash
git diff --check origin/master...HEAD
python3 - <<'PY'
from pathlib import Path
p = Path('docs/superpowers/specs/2026-08-29-business-sol-surface-convergence-design.md')
text = p.read_text(encoding='utf-8')
assert 'TBD' not in text
assert 'TODO' not in text
assert 'One Experience, Federated Authority' in text
assert 'REJECTED_BY_DESIGN' in text
print({'bytes': len(text.encode()), 'lines': len(text.splitlines())})
PY
```

Expected: exit 0, exact one-file records scope, no unreviewed semantic amendment.

- [ ] **Step 4: Obtain the authoritative release edge or preserve the hold**

Release owner either:

```text
SOL RELEASE / READY FOR FINAL REVIEW
```

or preserves:

```text
DRAFT / HOLD-FOR-SOL / release serialization active
```

No downstream implementation START occurs while the spec is absent from protected `master`.

- [ ] **Step 5: Merge only on a fresh exact-head gate**

Require:

```text
expected protected base
expected #234 head
required repository test = success
current security analyses = success
exact one-file diff
current Sol architecture review = PASS
release hold cleared
```

After merge, record the protected merge SHA. A merged records file remains `SPEC_ONLY`; it does not make Business convergence built.

---

### Task 2: Reconcile the organizational parent and selected portfolio projection (BSC-O0)

**Files:**
- Read: Macro `agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md`
- Read: Macro `config/mastermind_programs.yml`
- Create or modify only after lawful owner resolution: one Macro Agent OS workstream/wave, decision, discovery, or handoff record
- Optional Linear projection: one selected Project/Issue binding under the existing projector owner

**Interfaces:**
- Consumes: protected BSC-F0 architecture; current Macro Agent OS schema; current program registry; existing `WS:CHAIRMAN-CONTROL-ROOM` scope.
- Produces: exact durable organizational parent, or an explicit `ORGANIZATIONAL_PARENT_UNRESOLVED` hold; selected Linear projection only after canonical identity exists.

- [ ] **Step 1: Compile the current candidate parent**

Run in current Macro main:

```bash
python3 scripts/agentos.py validate
python3 scripts/agentos.py compile-context --workstream CHAIRMAN-CONTROL-ROOM --text --budget 12000
```

Expected: either a valid current workstream context or an exact inability to resolve that key. Do not infer a parent from title similarity.

- [ ] **Step 2: Test semantic fit against the accepted architecture**

The existing workstream is a lawful parent only if its objective/program/ownership can contain:

```text
Business Chairman ↔ Sol operating surface
plugin and app convergence
Executive/Steward integration
Business migration and cutover
```

without changing the workstream into a generic infrastructure catch-all.

- [ ] **Step 3: Record one of two closed outcomes**

Outcome A:

```text
parent = WS:CHAIRMAN-CONTROL-ROOM
new wave = BSC
next action = protect F0, then execute BSC-P1 and BSC-A1 under separate carriers
```

Outcome B:

```text
ORGANIZATIONAL_PARENT_UNRESOLVED
reason = no accepted program/workstream identity fits without semantic distortion
next action = Sol/Chairman program-registry ruling before Agent OS creation
```

Do not create a near-duplicate workstream to make Linear tidy.

- [ ] **Step 4: Validate and ship the organizational record through Macro Git**

Run:

```bash
python3 scripts/agentos.py validate
python3 scripts/agentos.py status --dry-run
python3 scripts/agentos.py compile-context --workstream CHAIRMAN-CONTROL-ROOM --text --budget 12000

git diff --check
```

Expected: schema-valid Git record, no control-plane behavior, no false claim that implementation started.

- [ ] **Step 5: Project selectively to Linear only after canonical identity exists**

The projection names BSC-F0, BSC-P1, BSC-A1 and the current gate. It does not create one issue per app call, skill, Job, Attempt, Business chat, or test case.

---

### Task 3: Build the production-inert plugin package vertical (BSC-P1)

**Files:**
- Plan: `docs/superpowers/plans/2026-08-29-business-sol-plugin-packages.md`
- Implementation paths: `.agents/plugins/**`, `plugins/mastermind-sol/**`, `plugins/mastermind-operator/**`, `scripts/validate_mastermind_plugins.py`, `tests/test_mastermind_plugin_packages.py`

**Interfaces:**
- Consumes: protected BSC-F0; current OpenAI marketplace/plugin/skill contracts; no live Business app.
- Produces: deterministic skills-only marketplace and two plugin packages; no `.app.json`, MCP declaration, installed app ID, OAuth, network, or runtime action.

- [ ] **Step 1: Execute the separate BSC-P1 plan exactly**

The P1 plan owns all TDD tasks and exact file contents. This program plan does not widen it.

- [ ] **Step 2: Require one independently useful output**

A workspace admin can import the marketplace at a reviewed commit and inspect/install skills-only packages without creating a Desktop-only plugin or connecting any live app.

- [ ] **Step 3: Stop at `BUILT_NOT_PROVEN / PRODUCTION_INERT`**

Repository validation and hosted CI do not prove ChatGPT Business import. Real workspace import belongs to BSC-U1/BSC-C1.

---

### Task 4: Build the shared OAuth/resource-server boundary (BSC-A1)

**Files:**
- Future plan: `docs/superpowers/plans/2026-08-30-business-sol-oauth-resource-server.md`
- Expected implementation home: `integrations/business_mcp_auth/**`
- Expected tests: `tests/test_business_mcp_auth.py`, `tests/test_business_mcp_auth_adversarial.py`

**Interfaces:**
- Consumes: protected BSC-F0; current official MCP authorization requirements.
- Produces: SDK-minimal token verification and resource/scope/subject policy reused by Steward, Executive, and Dialogue edges; no auth server and no credential store.

- [ ] **Step 1: Author the separate A1 plan from then-current official specifications**

The plan must freeze:

```text
protected-resource metadata
authorization-server discovery contract
PKCE S256 requirement
issuer verification
audience/resource verification
expiration/not-before verification
scope verification
app-specific subject policy
401 + WWW-Authenticate challenge
JWKS refresh and failure behavior
redacted logging
```

- [ ] **Step 2: Preserve app/resource separation**

A Steward token cannot call Executive. An Executive token cannot call Dialogue. A token with broad text claims but wrong resource fails.

- [ ] **Step 3: Prove hostile token refusal**

Negative matrix includes unsigned, wrong key, unknown key id, wrong issuer, wrong audience/resource, missing scope, unauthorized subject, expired, future, malformed, oversized, and secret-bearing error paths.

- [ ] **Step 4: Stop before production enrollment**

A1 produces a library and hermetic resource-server fixtures only. Real IdP configuration, client registration, app IDs, OAuth consent, redirect URIs and tunnel setup belong to U1.

---

### Task 5: Expose the real Steward through an authenticated Business read app (BSC-S1)

**Files:**
- Future plan: `docs/superpowers/plans/2026-08-30-business-sol-steward-app.md`
- Existing owners: `integrations/mastermind_secretary_mcp/**`, `control_plane/executive_steward.py`, Chairman Control Room compositor
- New edge/UI paths determined by current protected source after #224/#228 release

**Interfaces:**
- Consumes: protected BSC-F0, accepted BSC-A1, protected Secretary six-tool contract, protected Executive Steward core.
- Produces: authenticated read-only remote MCP edge and optional in-chat Control Room UI over real Steward facts.

- [ ] **Step 1: Wait for both existing read owners to protect**

Required:

```text
Secretary/Steward six-tool MCP contract protected
Executive Steward read core protected
exact tool/server schema digests known
no replacement read plane required
```

- [ ] **Step 2: Author S1 as one vertical**

Journey:

```text
Business user authenticates
→ calls one six-tool Steward app
→ real source-attributed composition
→ structured/text result
→ optional Control Room component renders same result
```

- [ ] **Step 3: Require read-only and prompt-injection proof**

No tool call, UI event, returned `next_action`, Slack text, PR body, Agent OS record, or widget state can server-chain into a write.

- [ ] **Step 4: Require UI independence**

Break/disable the component and prove the model can still complete the workflow using structured tool output.

- [ ] **Step 5: Stop before Business production proof**

S1 source acceptance is `BUILT_NOT_PROVEN`. Tunnel/app/OAuth proof belongs to U1/C1.

---

### Task 6: Arm the existing Executive MCP for one authenticated Business CEO intent (BSC-E1)

**Files:**
- Future plan: `docs/superpowers/plans/2026-08-30-business-sol-executive-app.md`
- Existing owners: `integrations/executive_mcp/**`, `control_plane/ceo_request.py`, `control_plane/ceo_intent.py`, CeoIngress/Executive service host composition

**Interfaces:**
- Consumes: protected BSC-F0, accepted BSC-A1, accepted AD-ID1 transport-neutral request identity, current CeoIngress host/source acceptance.
- Produces: a separately versioned authenticated production edge preserving the exact five-tool Executive contract; no worker dispatch.

- [ ] **Step 1: Reconcile all active collision owners before plan authoring**

Do not modify paths owned by active AD-ID1, CeoIngress, Executive MCP, Capacity, SessionTarget, or host-enrollment carriers. Adopt their protected contracts after they land.

- [ ] **Step 2: Preserve the exact public surface**

```text
executive_state
executive_inbox
executive_job
ceo_intent_status
submit_ceo_intent
```

No sixth admin tool, provider selector, generic command, merge/deploy action, Agent OS writer, or session action.

- [ ] **Step 3: Bind transport identity without trusting model fields**

Production submit requires exact authenticated subject/resource/scope plus current Mastermind authority and grounding. `actor=ceo-sol` remains provenance only.

- [ ] **Step 4: Reuse the dedicated CeoIngress peer boundary**

Verify the exact principal/socket topology and minimal environment. Do not widen the general Executive control socket peer list.

- [ ] **Step 5: Prove submission semantics**

Accepted call creates one canonical `QUEUED` Job with `dispatched=false`, zero Attempt and zero Worker claim. Same key/payload reconciles. Changed payload conflicts. Response loss uses status read under the same intent and app.

- [ ] **Step 6: Stop before live Business submission**

E1 source is `BUILT_NOT_PROVEN / production-disabled-or-unenrolled` until U1/C2.

---

### Task 7: Build the deterministic Business installation and enrollment ceremony (BSC-U1)

**Files:**
- Future plan: `docs/superpowers/plans/2026-08-31-business-sol-installation-enrollment.md`
- Expected scripts/runbook: `ops/business_plugins/**`, `docs/BUSINESS_SOL_INSTALLATION.md`
- Generated local artifact: plugin `.app.json` files outside Git until exact app IDs are reviewed for publication

**Interfaces:**
- Consumes: accepted P1/A1/S1/E1 source; Business admin access; exact app IDs and OAuth/tunnel configuration supplied through native admin surfaces.
- Produces: draft Business apps, private tunnel, OAuth connections, app-bound plugin generation and redacted installation receipts.

- [ ] **Step 1: Build verify-only preflight before mutation**

Preflight proves:

```text
expected workspace/admin role
expected marketplace commit
expected app/server schema identities
expected local endpoints
no conflicting app generation
no secret-bearing argv/environment
```

- [ ] **Step 2: Separate human secret/admin ceremony from model-visible automation**

Passwords, MFA, OAuth consent secrets, client secrets and tunnel credentials remain in native hidden/admin surfaces. The model receives only bounded success/refusal metadata.

- [ ] **Step 3: Generate exact `.app.json` only from real app IDs**

The generated file uses supported app ID formats and `required` flags. It is never fabricated from symbolic IDs. The plugin manifest gains the `apps` reference only in the app-bound generation.

- [ ] **Step 4: Refuse Desktop-only packaging**

No `mcp.json` or `.mcp.json` enters the ChatGPT-web plugin. The plugin references registered apps through `.app.json`.

- [ ] **Step 5: Leave all apps DRAFT until canaries pass**

U1 installation does not equal production acceptance.

---

### Task 8: Prove the real Business read journey (BSC-C1)

**Files:**
- Future plan: `docs/superpowers/plans/2026-08-31-business-sol-read-canary.md`
- Evidence path determined by the plan; sanitized receipts only

**Interfaces:**
- Consumes: U1-installed draft marketplace/plugin/Steward app/tunnel/OAuth.
- Produces: real Business-account read proof and failure-state proof; zero canonical modification.

- [ ] **Step 1: Start one fresh ordinary Business chat**

Verify plugin and app availability without Agent Mode or Workspace Agent execution.

- [ ] **Step 2: Exercise all Steward tools**

Require exact tool census, current source identities, source freshness, typed unknown/degraded states and bounded outputs.

- [ ] **Step 3: Render and visually inspect the Control Room component**

Inspect normal, narrow, empty/degraded and source-disagreement states. Component failure must preserve text/structured tool usability.

- [ ] **Step 4: Restart/re-authenticate**

Stop/restart the app edge/tunnel and prove no canonical state changes, clean reauthentication and truthful unavailable state during the interruption.

- [ ] **Step 5: Record zero-write proof**

No Executive Job, Agent OS record, Slack message, Linear mutation, RuntimeBinding, or app-generated lifecycle fact is created.

---

### Task 9: Prove one harmless Business Executive admission (BSC-C2)

**Files:**
- Future plan: `docs/superpowers/plans/2026-08-31-business-sol-admission-canary.md`
- Canonical evidence: Executive intent/Job receipt plus sanitized external receipt

**Interfaces:**
- Consumes: accepted C1, U1-installed Executive app, E1 production arm, explicit current Chairman authorization for the exact canary.
- Produces: one authenticated `research_only` root admission, no execution.

- [ ] **Step 1: Freeze the harmless canary envelope**

The objective is read/research-only and requires no worker execution to prove admission. Record the exact operation key and normalized payload before submission.

- [ ] **Step 2: Confirm once through ChatGPT and submit once**

Require exact authenticated Chairman subject and current grounding.

- [ ] **Step 3: Verify canonical result**

Expected:

```text
one intent
one root Job
status=QUEUED
dispatched=false
Attempts=0
Worker claims=0
```

- [ ] **Step 4: Verify duplicate and conflict behavior**

Exact replay returns the same Job. Changed objective under the same operation key refuses and creates no second Job.

- [ ] **Step 5: Exercise response-loss reconciliation**

Lose the client response after possible commit; use `ceo_intent_status` through the same app/intent. Do not resubmit through Slack, another Business chat, another app or another account.

- [ ] **Step 6: Terminalize or preserve the canary according to Executive source law**

The canary must not remain as false active work. Its closeout is canonical Executive state, not deletion of evidence.

---

### Task 10: Falsify or establish exact Business reasoning-surface identity (BSC-RB1)

**Files:**
- Future plan: `docs/superpowers/plans/2026-09-01-business-sol-surface-identity-falsifier.md`
- No production RuntimeBinding write in this task

**Interfaces:**
- Consumes: accepted C1 Business app/tunnel environment.
- Produces: observed trusted request metadata, compaction/reconnect/multi-chat evidence, and one explicit ruling: accepted seam or `NO_TRUSTED_EXACT_SURFACE_IDENTITY`.

- [ ] **Step 1: Capture only documented/trusted metadata classes**

Never log bearer tokens, prompts or transcripts. Record whether the server receives any platform-authenticated conversation/session handle and its stability properties.

- [ ] **Step 2: Run two-chat and reconnect matrix**

Test:

```text
same OAuth user, chat A
same OAuth user, chat B
chat reload
conversation compaction
plugin reinstall
OAuth reconnect
tunnel restart
```

- [ ] **Step 3: Test server-minted advisory surface references**

Determine whether an opaque reference carried in conversation/widget state survives honestly enough for presence only. Test copy, collision, loss, theft, expiry and replay.

- [ ] **Step 4: Emit one closed verdict**

Accepted:

```text
TRUSTED_NATIVE_SURFACE_HANDLE
```

or:

```text
OPAQUE_ADVISORY_SURFACE_REF_ONLY
```

or:

```text
NO_TRUSTED_EXACT_SURFACE_IDENTITY
```

None grants action authority by itself.

---

### Task 11: Extend existing RuntimeBinding for bounded Business presence only if RB1 passes (BSC-RB2)

**Files:**
- Future plan: `docs/superpowers/plans/2026-09-01-business-sol-runtime-binding.md`
- Existing owners only: SessionTargetRegistry / RuntimeBinding / Executive events / Steward projection

**Interfaces:**
- Consumes: accepted RB1 seam; current RuntimeBinding and action-authority source law.
- Produces: bounded surface registration/heartbeat/focus/retire projection and stale/conflict behavior; no new session database.

- [ ] **Step 1: Reuse existing event/idempotency ownership**

Do not add `business_sessions`, `sol_owner`, heartbeat database, watcher registry or app-local persistence.

- [ ] **Step 2: Separate presence from authority**

Model-callable operations may update only:

```text
register_surface
heartbeat_surface
set_surface_focus
retire_surface
get_my_surface
```

`ACTION_BOUND` is derived, never claimed.

- [ ] **Step 3: Prove stale and stolen references are harmless**

At worst, presence/focus becomes refused or stale. No CEO intent, child continuation, ruling, merge, retry or successor commission becomes reachable.

- [ ] **Step 4: Prove one-authoritative-child-turn behavior**

Two Business surfaces may observe one return. Only the canonically joined current target can act after the separate child-action integration is accepted. Before that integration, both remain read/advisory for child turns.

---

### Task 12: Run dual operation, cut over deliberately, and subtract only proven-replaced scaffolding (BSC-D1 / CUTOVER / R1)

**Files:**
- Future plans:
  - `docs/superpowers/plans/2026-09-02-business-sol-dual-run-cutover.md`
  - `docs/superpowers/plans/2026-09-02-business-sol-legacy-subtraction.md`
- Durable closeout: owning repository docs plus Macro Agent OS and selected Linear projection

**Interfaces:**
- Consumes: C1/C2 acceptance and, for exact child-turn Business authority, RB2 acceptance.
- Produces: Business-first operating mode, rollback proof, measured operating improvement, and explicit retained/retired legacy surface ledger.

- [ ] **Step 1: Run Business and existing surfaces together**

Compare over representative live work:

```text
grounding
responsibility/attention
runtime and next action
source disagreements
root operation identity
receipts
failures and reconnect
Chairman intervention burden
```

- [ ] **Step 2: Establish Business-first reads/root admission**

Business may become primary for reads and confirmed new-root admission after C1/C2 even while exact existing child-turn authority stays on the prior bound surface.

- [ ] **Step 3: Establish Business child-turn authority only after RB2**

No implicit transfer from account migration, plugin installation, newest tab, Slack principal or conversation recency.

- [ ] **Step 4: Keep Slack, Linear and GitHub in their final roles**

Slack stays cross-provider dialogue/Workrooms/audit/fallback. Linear stays selected projection. GitHub stays implementation/evidence.

- [ ] **Step 5: Retire one scaffold at a time**

Every retirement record names:

```text
old capability/path
replacement capability/path
production receipt
rollback
surviving role
owner
```

- [ ] **Step 6: Prove the Chairman zero-shuttle journey**

Representative period includes new intent, worker return, Sol continuation, blocker, safe retry/rollover, effect-unknown hold, source disagreement and final closeout. Chairman performs zero routine Slack archaeology, message shuttling, watcher repair, provider-account selection or session hunting.

- [ ] **Step 7: Update durable memory and declare exact residual capability states**

Do not call the program complete unless Truth, Intelligence, Product and Learning standards in the architecture are all satisfied.

---

## Program Stop Conditions

The program is not complete when the plugin files exist, an app is published, OAuth connects, the tunnel is online, a Job is `QUEUED`, CI is green, or one canary passes.

It is complete only when:

```text
Business Chat is the primary Chairman ↔ Sol cockpit
current procedure loads dynamically
Steward reads are source-attributed and correction-safe
bounded Executive admission is authenticated and idempotent
multiple chats cannot manufacture authority
exact child-turn authority is either proven or explicitly remains on another bound surface
Slack/Linear/GitHub retain their correct roles
rollback is proven
legacy scaffolding is subtracted only after replacement proof
Chairman intervention burden is observably reduced
```

## Immediate Next Action

After PR #234 is protected and the current release serialization permits a new independent implementation carrier, execute `docs/superpowers/plans/2026-08-29-business-sol-plugin-packages.md` as BSC-P1 on a fresh isolated branch/worktree. BSC-A1 may be planned/executed in parallel only after a fresh path/authority census proves it is disjoint. No other downstream Business wave starts from this program plan alone.
