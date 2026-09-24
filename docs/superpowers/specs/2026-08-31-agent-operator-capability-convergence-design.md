# Mastermind-X Agent / Operator Capability Convergence — Cross-Provider Pack, Browser and Host Integration

**Date:** 2026-08-31  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** **SOL ARCHITECTURE FREEZE / RECORDS ONLY / PRODUCTION INERT**  
**Operation key:** `mastermind-agent-operator-capability-convergence-f0-20260831-sol-001`  
**Protected Mastermind / Skillpack basis:** `12c2cb8993f78e81c6cb9e9a75a9829f9b194dab`, `mastermind.sol_skillpack.v1` v1.0.1, bootstrap major 1.  
**Existing owners extended, not replaced:** Executive OS / `ExecutionCapabilityRegistry`; Operator Harness / HF1; Business Sol Surface Fabric F2 attestation; Worker Browser / DevServer Resource Fabric; Capacity Fabric / RF1 / MH1; Agent OS durable organizational knowledge.  
**Completion law:** this document freezes a missing convergence layer only. It creates no Executive Job, Worker, Attempt, provider process, plugin install, MCP connection, browser process, host broker, provider credential, runtime binding, production route, or new organizational workstream.

---

## 0. Observable mission and CEO ruling

Give every **eligible, governed Executive Attempt** the exact company working method and execution capabilities it requires — skills, approved MCP identities, approved resources, and later attested plugin bundles — regardless of whether the selected execution surface is Codex, Claude Code, Grok Build, ZCode/GLM, or a later provider adapter.

Do this without making the Chairman install or synchronize provider-specific tooling, without asking each worker to reconstruct Mastermind procedure from prompt history, and without creating a new Agent OS tools platform, plugin database, session system, browser scheduler, desktop allocator, host control plane, or provider-specific lifecycle.

The architecture ruling is:

> **Mastermind standardizes one sealed capability contract, not one provider package format. `ExecutionCapabilityRegistry` remains the canonical grant/attestation owner; HF1 remains the common worker-harness boundary; provider adapters deterministically materialize and observe the native package/configuration required by one sealed Attempt; Browser Resource Fabric and MH1 remain separate resource/host owners.**

A plugin, skill, MCP server, browser, host, CLI, tmux session, or provider-native subagent is a capability or execution substrate. None is company authority merely because the provider exposes it.

The old architectural question — “should Agent OS workers get custom plugins/MCP/skills/tools and desktop/browser access?” — is therefore answered **yes, but through existing canonical owners and exact capability profiles, not through an Agent OS execution platform**.

---

## 1. Intent recovery — the 10/10 outcome

### 1.1 Chairman job

The Chairman should be able to give Sol one outcome and remain out of routine tool transportation.

He should not need to:

- remember which Claude/Codex/Grok/GLM environment has the newest Mastermind procedure;
- paste the same operator instructions into many sessions;
- install or update plugins for each worker by hand;
- choose a computer because only one happens to have the right tooling;
- carry screenshots or browser observations from workers back to Sol;
- decide whether a provider-specific extension changed the worker's authority;
- repair provider drift by manually rebuilding local configuration;
- infer whether an installed skill/plugin was actually the reviewed generation.

### 1.2 Sol / machine job

For every claimed Attempt, the machine must be able to answer before the first work turn:

1. Which exact execution profile was authorized?
2. Which exact custom skill/plugin bundle generation does that profile require?
3. Which exact source commit, manifest and file digests define that generation?
4. Which MCP servers, tools, resources and network/write policies are allowed?
5. How does this provider natively receive those capabilities?
6. What did the provider process actually load?
7. Did the observed custom skill content match the expected digest rather than only the same name?
8. Did any ambient plugin, skill, MCP server, browser resource, hook or other extension appear unexpectedly?
9. Is browser or GUI capability actually available on the selected host without colliding with another actuator?
10. If launch/materialization/transport becomes ambiguous, what exact same-Attempt reconciliation path applies?

If those questions cannot be answered at the precision promised by the profile, launch refuses or the route is removed from eligibility. A model must never be asked to “behave as if” a capability was absent or present when the runtime cannot prove it.

### 1.3 Moat

The moat is not a marketplace manifest. It is a governed executive workforce whose capabilities are portable **without losing identity, provenance, authority boundaries, or production proof**.

That creates compounding value:

- company procedure is improved once and reused across providers;
- cheap/abundant models become more useful because the surrounding working method is consistent;
- provider swaps do not silently change tool authority;
- capability drift becomes observable and testable;
- browser/product proof can be delegated instead of transported by the Chairman;
- provider performance can later be evaluated against the same capability envelope rather than incomparable environments.

---

## 2. Current-source capability ledger

This ledger is based on protected Mastermind `12c2cb8993f78e81c6cb9e9a75a9829f9b194dab` and current canonical source law. It deliberately separates architecture, built source and production proof.

| Capability | State | Current ruling |
|---|---|---|
| Agent OS durable organizational knowledge | `PROVEN_LIVE` | Owns workstreams, decisions, discoveries and handoffs. It is not a dispatcher, worker lifecycle, plugin registry, session registry, browser allocator or host scheduler. |
| Executive Job / Attempt / Worker / Event authority | `BUILT_NOT_PROVEN` for the current autonomy release posture | Remains the only runtime lifecycle authority. This program does not add another queue or job type. |
| `ExecutionCapabilityRegistry` closed execution profiles | `BUILT_NOT_PROVEN / PRODUCTION_UNARMED` | Already models skills, MCP servers, resources, plugins, sandbox, approvals, network, write authority, auth realm and native-helper ceiling. |
| Exact MCP identity/schema attestation | `BUILT_NOT_PROVEN` | Current Codex rich-operator path can compare exact MCP server identity/version/tool schema/auth status before work. |
| Custom skill identity field | `PARTIAL` | `CapabilityIdentity` and `ObservedCapabilityIdentity` already contain `skill_content_digest`, but the current profile compiler and Codex observer do not populate it for custom skills. |
| Custom skill grants in production profiles | `NOT_BUILT` in current policy | Profile schema supports `skills`, but all protected current profiles have an empty skill list. |
| Plugin grants | `NOT_BUILT` by deliberate gate | Registry loader refuses non-empty plugin grants until exact installed-bundle attestation exists. This is a safety property, not a missing list entry. |
| Business Sol plugin source packages | `BUILT_NOT_PROVEN / PRODUCTION_INERT` | BSC-P1 protected `mastermind-sol` and `mastermind-operator` skills-only packages. Merge/import/install/live-app proof are separate. |
| BSC-F2 installed plugin/app generation attestation | `SPEC_ONLY` | Existing architecture already assigns immutable plugin generation, repository SHA, manifest/file digests, inventory and revocation to `ExecutionCapabilityRegistry`. This is the canonical owner to extend. |
| Common provider-neutral rich Worker Harness (HF1) | `SPEC_ONLY / DEPENDENCY_GATED` | Existing hybrid-workforce architecture requires one common contract rather than provider-specific brokers. It must follow the accepted Capacity/Router dependency chain. |
| Codex App Server rich operator adapter | `BUILT_NOT_PROVEN / PRODUCTION_UNARMED` | Real requested/observed capability attestation exists, but current adapter is Codex-specific. |
| Grok native substrate G0 | `BUILT_NOT_PROVEN / PRODUCTION_INERT` | Provider substrate exists without a second lifecycle; automatic routing remains gated behind common harness / routing acceptance. |
| Worker Browser B1 local-review adapter | `BUILT_NOT_PROVEN / PRODUCTION_DISARMED` | Source is protected. Real governed installed-path proof is still required; source presence does not mean every worker has browser access. |
| Later company-production read-only browser profile | `SPEC_ONLY` | Worker Browser F0 explicitly anticipates exact company-owned production origins after local-review proof. |
| Arbitrary public-internet worker browser | `NOT_BUILT / DEFERRED` | Not required for the first browser autonomy proof. Must be justified by a concrete job and a separate egress profile. |
| Chairman-authenticated browser reuse | `REJECTED_BY_DESIGN` | Worker browser/desktop capability must not copy or reuse the Chairman's browser profile/cookies/session state. |
| Generic arbitrary desktop control for every worker | `REJECTED_BY_DESIGN` as the default | Computer-use/GUI must be an explicit isolated resource with a host/seat mutex and bounded authority. |
| Multi-host Worker Broker / GUI placement (MH1) | `SPEC_ONLY / DEPENDENCY_GATED` | Existing plan already defines one canonical Executive Runtime plus authenticated host-local brokers and GUI mutex through Worker/resource capacity. |

### 2.1 The actual missing layer

After subtraction, the missing architecture is narrow:

> **A provider-native capability materialization and observation layer that consumes one canonical sealed execution profile and one attested bundle generation, stages the exact native provider representation inside the Attempt boundary, and proves what the provider loaded before work.**

That layer is missing. The surrounding registry, lifecycle, browser resource, host placement and provider-neutral harness owners already exist or are separately planned.

---

## 3. Canonical ownership and no-rebuild boundaries

| Fact / behavior | Canonical owner | This program may do |
|---|---|---|
| Job / Attempt / Worker / Event lifecycle, claim, retry, completion | Executive OS | Consume exact Attempt identity; never create another lifecycle. |
| Capability profile, source grant, generation, revocation, expected digests | `ExecutionCapabilityRegistry` + accepted BSC-F2 evolution | Compile/materialize from it; never create a `worker_plugins` registry. |
| Provider-neutral session/start/resume/events/cancel/reconcile contract | Operator Harness / HF1 | Add provider materialization/observation adapters under that boundary. |
| Provider-private config/layout/start semantics | Provider adapter | Implement only the native mechanics needed to realize the sealed contract. |
| Organizational procedure/handoff truth | Agent OS | Record durable rulings/handoffs only; never use Agent OS as live plugin/session state. |
| Browser/devserver process realm and browser proof | Worker Browser / DevServer Resource Fabric | Reuse exact browser profiles/resources; do not create `BrowserJob` or browser DB. |
| Host eligibility, quota, reserve, resource placement | Capacity Fabric / RF1 / MH1 | Request capabilities/host resource needs; do not choose hosts inside a plugin. |
| GUI actuator concurrency | Existing Worker/resource capacity | Represent one isolated desktop/seat as one resource realm; no desktop scheduler. |
| Code/branch/PR/CI/evidence | GitHub | Store source packages, plans, exact reviewed implementation evidence. |
| Portfolio projection | Linear | Optional selective projection only after canonical state exists. |
| Transport/hot-state dialogue | Slack / Company Dialogue / Wake | Never infer capability or authority from sender/prose. |

### 3.1 Explicitly forbidden duplicate systems

This program must not create:

- `Agent OS Tools Runtime`;
- `Session OS`;
- `Plugin OS`;
- `Browser OS`;
- `Desktop Scheduler`;
- `Host Scheduler` beside Capacity/MH1;
- `ClaudeJob`, `GrokJob`, `GLMJob`, `BrowserJob` or provider-specific lifecycle rows;
- a plugin install status database separate from the canonical capability registry / provider readiness evidence;
- a second retry/effect-unknown system;
- a second provider credential registry;
- a provider-specific durable memory store;
- one permanent watcher/tmux loop per worker.

---

## 4. Product and value model

### 4.1 User value

The visible product is not “workers have plugins.” The user capability is:

> Sol can commission the same bounded company job to any eligible execution surface and receive a result produced under the same reviewed working method and capability envelope, with browser/product proof when the profile requires it.

### 4.2 Machine value

A common capability envelope lets routing separate **reasoning quality** from **execution environment**:

```text
Job requirements / authority
        ↓
Model Router quality + method requirements
        ↓
required execution_profile_id + exact bundle generation
        ↓
Capacity Fabric: eligible provider realms + host/resource availability
        ↓
Executive claim
        ↓
provider-native materialization + observed attestation
        ↓
first work turn only after ALLOW
```

Provider price or availability may choose among already-eligible implementations. It may not silently downgrade tools, procedure, browser proof or authority enforcement.

### 4.3 Research / intelligence value

Once the same operator procedure and capability envelope can run across providers, provider evaluation becomes more meaningful. We can compare:

- completion quality;
- repair rate;
- tool-call correctness;
- browser-review usefulness;
- context efficiency;
- latency;
- cost;
- failure/reconciliation rate;
- tendency to request unnecessary authority;
- reviewer disagreement.

Without capability parity, “model performance” is confounded by different tools and instructions.

### 4.4 Commercial and cost value

This architecture is what allows lower-cost and subscription-backed workers to absorb routine work without turning every new provider into a bespoke integration project. Frontier capacity remains reserved for tasks whose quality class requires it; mature operator procedure and tools follow the job rather than the brand.

### 4.5 Data moat

The durable moat is the history of exact `(job class, model/provider, capability profile, bundle generation, browser/resource envelope, result, review, repair, production proof)` receipts. A later eval/placement layer can learn from that evidence without changing lifecycle authority.

---

## 5. Experience architecture — full execution journey

### 5.1 Normal path

```text
Chairman outcome
  ↓
Sol / Fable bounded child Job
  ↓
Executive route + claim
  ├─ requested model / provider class
  ├─ execution_profile_id + profile digest
  ├─ capability policy version/digest
  └─ exact capability/bundle generation requirements
  ↓
Attempt sealed
  ↓
provider adapter materializes native config/package
  ├─ Attempt-owned staging only
  ├─ no credentials written
  ├─ no authoritative workspace mutation
  └─ exact staged inventory/digests observed
  ↓
provider process starts
  ↓
native runtime observation
  ├─ harness binary/version
  ├─ effective skills + content identity
  ├─ effective plugin/app generation
  ├─ MCP identities/tool schema
  ├─ browser/resource identity if requested
  ├─ sandbox / approval / network
  ├─ auth realm fact
  └─ workspace identity
  ↓
existing pure launch comparator
  ├─ ALLOW → first work turn
  └─ REFUSE → stop/reconcile; no work turn
  ↓
normal events / candidate result / review / proof
```

### 5.2 No magical “install then trust” step

Installation/import is not attestation. A provider may cache, shadow, override, reload, disable or merge extensions. Therefore both stages matter:

1. **Source/materialization receipt:** what exact reviewed bytes/config were intended and staged.
2. **Runtime observation:** what the provider process actually reports/discovers/loads.

Where the provider cannot expose an exact runtime content digest, the route must honestly say so. Write-capable profiles fail closed at insufficient precision. Read-only experiments may run only under an explicit degraded research profile that cannot be promoted as exact parity evidence.

### 5.3 Failure-state UX

The system must surface typed reasons rather than asking the Chairman to debug configuration:

- required bundle generation unavailable on host;
- source generation revoked;
- native manifest digest mismatch;
- skill name present but content digest unknown or wrong;
- required skill absent;
- ambient/unrequested custom skill present;
- plugin present but generation cannot be proven;
- extra MCP server/tool schema drift;
- provider runtime reload changed extension state after seal;
- provider surface cannot express a required capability;
- plugin requires interactive installation/login during a Job;
- browser resource unavailable;
- browser egress/network boundary mismatch;
- GUI actuator busy;
- host/provider readiness stale;
- materializer attempted to write credentials;
- materializer attempted to mutate the authoritative workspace;
- process/session effect became unknown after a modifying provider call.

These map into existing lifecycle/failure authority. They do not create a capability-pack job status system.

---

## 6. Canonical capability-pack architecture

### 6.1 What the “Mastermind Operator Capability Pack” is

It is a **versioned repository source package and deterministic projection**, not a new product/runtime authority.

Conceptually it contains:

```text
canonical operator workflow skills
provider-native manifest projections where required
references to independently governed MCP capabilities
references to independently governed browser/resources
optional hooks/commands only when separately reviewed
```

The package source belongs in GitHub. Its allowed generation, source tree and revocation belong in the existing capability registry after BSC-F2 lands.

### 6.2 What it is not

The pack is not allowed to contain or grant:

- Executive authority;
- Worker identity;
- Job ownership;
- credentials/tokens;
- mutable provider session IDs;
- host placement;
- arbitrary shell/network permission;
- hidden retries;
- durable memory;
- automatic production deploy/merge authority;
- a generic “do anything in Mastermind” MCP server.

### 6.3 Source-first, provider-native projections

We standardize the **semantic capability identities and source bytes**, then project them into provider-native layout.

A single canonical workflow skill may have one reviewed `SKILL.md` source. Provider packaging may differ. If a provider requires generated metadata, the generated native manifest is deterministic and included in the attested bundle inventory.

Avoid hand-maintaining four semantically divergent copies of the same procedure. Provider-specific text is allowed only where the provider genuinely has different invocation semantics; the shared company method remains common.

### 6.4 No runtime self-install

A model may not decide mid-Job to install, update or enable a new capability in order to complete the task.

Production-capable routes use one of two reviewed patterns:

1. **READY-slot provisioning:** immutable capability bundle already provisioned and attested before the Worker realm becomes READY; or
2. **Attempt staging:** the provider supports a process-scoped local package/config path that the supervisor can stage from an already-approved immutable source without credentials or external install side effects.

The second pattern uses the existing `stage_operator_config` side-effect law: Attempt-owned staging only, no process start in staging, no credential write, no authoritative workspace mutation.

Package manager downloads, marketplace installs and browser downloads are provisioning activities, not model actions.

---

## 7. Exact identity and attestation law

### 7.1 Reuse the existing capability identity schema

The OHF contract already carries:

```text
CapabilityIdentity.skill_content_digest
ObservedCapabilityIdentity.skill_content_digest
```

The first custom-skill vertical must populate those existing fields. **Do not create `SkillGrantV2`, `AgentSkillRegistry` or another capability identity.**

For a required company-owned skill, name-only attestation is insufficient.

### 7.2 BSC-F2 remains plugin-generation owner

BSC-F2 already freezes the required plugin source attestation shape in the existing `ExecutionCapabilityRegistry`:

- capability ID;
- repository identity;
- immutable commit SHA;
- marketplace path;
- plugin root path;
- native manifest digest;
- exact skill inventory and per-file digests;
- required app-reference inventory;
- package generation;
- revocation state.

This program consumes that accepted contract after it lands. It must not pre-empt F2 by creating a sibling bundle registry.

If F2's accepted field/type names differ from any example in this document, the accepted F2 source wins. The invariant is the identity precision and ownership boundary, not a speculative class name.

### 7.3 Materialization receipt

Provider materialization produces an Attempt-scoped **non-authority observation/artifact**, conceptually:

```json
{
  "schema_version": "mastermind.capability_materialization_receipt/v1",
  "attempt_id": "...",
  "execution_profile_id": "...",
  "execution_profile_digest": "...",
  "capability_policy_digest": "...",
  "provider": "...",
  "harness_kind": "...",
  "bundle_capability_id": "...",
  "bundle_generation": "...",
  "bundle_source_commit": "...",
  "bundle_source_digest": "...",
  "native_manifest_digests": {},
  "skills": [
    {"name": "...", "skill_content_digest": "..."}
  ],
  "staged_files": [
    {"relative_path": "...", "sha256": "...", "bytes": 0}
  ],
  "wrote_credentials": false,
  "mutated_workspace": false,
  "started_process": false
}
```

This receipt may be carried through existing Attempt evidence/attestation artifacts or event payloads according to accepted implementation. It is **not** a new durable table or launch authority.

### 7.4 Runtime observation

After process initialization, the adapter must observe capabilities at the strongest truthful precision the provider exposes.

For company custom skills, the preferred proof order is:

1. provider reports exact loaded file/content identity;
2. supervisor proves the process-scoped resolved skill root is exactly the staged immutable directory and computes the same digest;
3. provider reports only a name — insufficient for exact parity unless a process/loader isolation proof makes alternate content impossible.

A provider's UI saying “enabled” is not enough for write-capable exact parity.

### 7.5 Ambient capability rule

Unrequested custom plugins/skills/MCP servers/hooks that can influence work are not harmless convenience. They are part of the effective environment.

- write-capable profile: unexpected influence capability refuses launch;
- exact-review profile: unexpected influence capability refuses launch;
- deliberately exploratory read profile: ambient capability may be allowed only when named in `allowed_ambient` at an accepted precision and cannot gain write/network authority.

### 7.6 Reload / mutation after launch

Providers that hot-reload extension state create a post-attestation drift risk. Production profiles must either:

- pin the process to immutable process-scoped paths with reload disabled/irrelevant; or
- re-observe an immutable generation token before each effect-bearing turn/tool phase; or
- mark the provider route ineligible for exact write capability.

A background plugin refresh may not silently change an existing Attempt's authority envelope.

---

## 8. Provider-native mapping

Provider support changes over time. Before each implementation vertical, re-read current official provider documentation and the exact installed binary/runtime. The provider mapping below is architectural intent, not permission to skip runtime falsification.

### 8.1 Codex

Current official OpenAI documentation describes plugins as installable packages for ChatGPT and Codex that may contain skills, MCP servers, or both, with a universal plugin directory and local-marketplace development path. Codex also has current first-class “Build skills,” “Build plugins,” MCP, App Server and non-interactive surfaces.

Mastermind therefore should not invent an ad-hoc Codex extension format. The Codex adapter should consume the accepted OpenAI-native plugin/skill configuration and use App Server observations where available.

Important distinction:

- BSC's `mastermind-operator` package is already a protected source package for the Business/Sol experience;
- a worker Attempt may reuse common skill source and package generation law;
- app/Business authority bindings are **not** inherited merely because Codex can load the same plugin source.

### 8.2 Claude Code

Current Claude Code plugin architecture packages skills, agents, hooks and MCP servers. A provider adapter may use a process-scoped local plugin directory for a bounded canary if the installed runtime proves exact isolation.

Mastermind policy remains stricter than provider convenience:

- no mid-Job marketplace fetch;
- no unreviewed hook execution;
- no credential files inside the plugin;
- exact bundle digest before launch;
- observed/isolated loaded generation before work.

Claude native subagents remain provider subordinates unless separately represented as Executive child Jobs under existing organizational-work law.

### 8.3 Grok Build

Current xAI documentation states that Grok Build supports skills, plugins, marketplaces, hooks and MCP servers and is compatible with Claude Code plugin/skill/MCP/instruction formats. It also explicitly states that a skill's `allowed-tools` field does **not** grant or restrict tools.

That validates two architecture choices:

1. Prefer a shared Claude-compatible source projection for Grok unless a real canary proves Grok-specific metadata is required.
2. Never use skill frontmatter as Mastermind authority enforcement. Executive profile/sandbox/network/tool policy remains the enforcement plane.

### 8.4 ZCode / GLM

Current ZCode documentation supports plugins containing skills, commands, subagents, MCP servers and hooks; it looks for `.zcode-plugin/plugin.json` and then a Claude-compatible `.claude-plugin/plugin.json`. It can also import skills from Codex/Claude-class agents.

The security implication is explicit: enabling a plugin grants code-execution trust and plugins may see inherited environment variables. Therefore:

- immutable reviewed source only;
- no uncontrolled environment inheritance;
- no model-controlled enable/install path;
- no symlink-to-moving-source production proof;
- process/workspace reload behavior must be falsified before exact parity.

GLM is a model/provider choice; ZCode is an execution surface. Do not collapse those identities.

### 8.5 tmux

Tmux receives **no Mastermind plugin architecture**. It is only a host-local process continuity/container mechanism underneath an approved provider adapter.

A tmux pane cannot prove:

- Job ownership;
- Worker identity;
- provider account;
- bundle generation;
- current write authority;
- result acceptance.

Those remain canonical Executive / adapter facts.

---

## 9. Browser and computer-use architecture

### 9.1 “Any session can use a browser” means eligibility, not ambient desktop access

The target experience is:

> Any governed Attempt whose job requires browser proof and whose provider/host can implement the exact browser profile may be routed to that capability without Chairman manual transport.

It does **not** mean every chat inherits an unrestricted desktop/browser.

### 9.2 Preserve Worker Browser B1

The first profile remains `operator.browser.local-review.v1` under the existing Worker Browser / DevServer Resource Fabric:

- exact Attempt worktree;
- loopback devserver;
- pinned Playwright MCP;
- isolated browser/context;
- structured + visual review proof;
- no public egress;
- no Chairman cookies/profile;
- browser artifact receipt through the normal Attempt result path.

First priority is real installed-path proof of B1, not a replacement browser framework.

### 9.3 Next browser profile after B1 proof

The next useful expansion should be a **read-only company-production inspect profile** limited to exact company-owned origins needed for product QA/observability.

It should preserve:

- isolated worker browser identity;
- exact allowlisted origins;
- no arbitrary auth inheritance;
- no production admin mutation unless a later separate profile is explicitly justified;
- explicit network receipt and redirect/subresource falsifiers.

### 9.4 Arbitrary public web

Arbitrary public-web navigation is not automatically granted just because a research worker benefits from web access. It is a separate egress capability with different data-exfiltration, prompt-injection and provenance risks.

When a concrete workflow needs it, define a separate read/research profile with:

- explicit egress class;
- download/file policy;
- origin/protocol restrictions where practical;
- browser-vs-shell network distinction;
- provenance capture;
- no authenticated Chairman state;
- no widening of source-write authority.

### 9.5 Authenticated company web workflows

If a later worker must operate an authenticated company console, use a dedicated worker-owned account/browser realm or service integration with independently managed credentials. Never copy the Chairman's personal browser profile to make automation convenient.

### 9.6 GUI mutex

One physical interactive desktop seat must have at most one active actuator unless independently proven isolation supplies separate desktops/sessions.

This mutex belongs to existing Worker/resource capacity and MH1 placement. A plugin cannot reserve a screen by itself.

---

## 10. Host and fleet architecture

### 10.1 MH1 remains the host owner

The target fleet remains:

```text
canonical Executive Runtime
        ↓ authenticated MH1 transport
host-local Worker Broker A / B / C / ...
        ↓
provider-local credentials + provider process + Attempt staging + resources
```

The capability pack is materialized **after** an eligible host/Worker realm is selected. It cannot become a hidden placement engine.

### 10.2 Credentials stay host-local

A plugin/package must never solve cross-host setup by copying provider credentials or browser profiles. Host-local Worker readiness owns the credential realm.

### 10.3 Host preference / reserve policy

Preferences such as preserving scarce interactive machines for Chairman use belong in Capacity Fabric reserve/cost/placement policy. Do not hard-code machine names or “avoid host X” logic inside provider adapters or capability packages.

### 10.4 Remote ambiguity

A remote timeout after a modifying provider/session operation is `EFFECT_UNKNOWN`. The same Attempt/Worker/host carrier must reconcile before a different host or provider is eligible. Capability portability is not permission for blind failover.

---

## 11. Deterministic vs provider-observed vs model-generated work

| Concern | Method |
|---|---|
| Bundle source digest / file inventory | deterministic cryptographic calculation |
| Profile → provider-native config projection | deterministic materializer, versioned/tested |
| Provider capability discovery | provider/runtime observation |
| Launch allow/refuse | deterministic pure comparator over requested vs observed facts |
| Capability route eligibility | deterministic constraints + accepted provider readiness facts |
| Model work result | statistical/model-generated, separately reviewed |
| Browser visual judgment | model-generated judgment over exact browser evidence; receipt is deterministic evidence metadata |
| Plugin/skill authority | never model-generated; effective authority comes from canonical profile + runtime gates |
| Provider quality tier | empirically evaluated/calibrated, not inferred from plugin support |

---

## 12. Dependency DAG and bounded vertical waves

This program must not jump active gates.

### 12.1 Existing prerequisite chains remain authoritative

```text
Capacity / routing / provider commonality:
CF2-H0 → CF2-P0 → CF2-I → RF1 → HF1 → provider family verticals

Business plugin attestation:
BSC-F0/F1 → BSC-F2 installed plugin/app generation attestation → later app/auth generations

Browser:
B1 source (protected) → installed-path B1 production proof → later exact production-inspect profile

Multi-host:
HF1 + accepted Capacity seams → MH1 host broker/resource placement proof
```

This records-only architecture does not reorder those owners.

### 12.2 New convergence waves

#### CAP-F0 — this architecture freeze

**Observable mission:** freeze the missing provider-native materialization/observation layer and subtract all existing owners.

**State after this document:** `SPEC_ONLY`.

#### CAP-S1 — exact custom-skill content vertical on Codex

**Prerequisites:** accepted BSC-F2 source-generation contract (or an accepted narrower registry evolution that provides the same source/digest truth) and current protected Codex rich-operator source.

**Mission:** one read-only Codex operator profile requires one Mastermind operator workflow skill whose requested and observed `skill_content_digest` match exactly before the first work turn.

**Why first:** it exercises an already-existing OHF identity field and current Codex attestation path without pretending full plugin-bundle support is solved.

#### CAP-M1 — provider-neutral materializer seam

**Prerequisite:** accepted HF1 interface and CAP-S1 evidence.

**Mission:** implement deterministic Attempt staging/materialization as an HF1/common-harness concern so the same sealed capability source can be expressed through provider-native layout without lifecycle divergence.

#### CAP-C1 — Claude Code parity vertical

**Prerequisites:** HF1 accepted; Claude provider readiness/adapter available; exact native plugin/skill behavior falsified.

**Mission:** run the same read-only operator skill generation and exact capability profile on Claude, with requested/observed parity and no ambient extension drift.

#### CAP-G1 — Grok parity vertical

**Prerequisites:** Grok G0 host/readiness proof + HF1 + CAP-M1.

**Mission:** reuse the Claude-compatible source projection where current runtime proves it; add Grok-specific projection only for real incompatibility.

#### CAP-Z1 — ZCode/GLM parity vertical

**Prerequisites:** approved ZCode execution surface/worker realm + HF1 + CAP-M1.

**Mission:** prove immutable plugin/skill staging, environment isolation and runtime reload behavior under the same canonical capability identity.

#### CAP-P1 — full plugin-generation parity

**Prerequisite:** BSC-F2 implementation accepted and at least two provider-native skill verticals proven.

**Mission:** allow one exact attested `mastermind-operator` plugin generation in a read-only rich profile, including exact skill inventory and separately governed MCP references; no ambient plugins.

#### CAP-B1X — cross-provider browser capability parity

**Prerequisites:** Worker Browser B1 installed-path proof + HF1 provider adapter on a second provider.

**Mission:** the same `operator.browser.local-review.v1` resource/profile is usable by a second provider without browser lifecycle duplication.

#### CAP-H1 — multi-host parity proof

**Prerequisites:** MH1 accepted + at least two READY host-local worker realms.

**Mission:** the same capability profile/bundle generation can execute on a second host with host-local credentials and identical attestation semantics; no shared writable plugin cache or credential copy.

### 12.3 Why waves are not collapsed

A single PR that simultaneously adds registry schema, provider-neutral harness, four provider adapters, plugin install, browser egress and multi-host routing would be impossible to review against authority boundaries and impossible to production-prove coherently.

Each wave above creates one independently testable capability.

---

## 13. Acceptance tests and production proof

### 13.1 CAP-S1 acceptance

A real rich operator Attempt must prove:

- exact protected skill source generation;
- exact expected `skill_content_digest` in sealed `CapabilityManifest`;
- exact observed content digest before work;
- changed one-byte skill source refuses old profile/generation;
- same skill name with different content refuses;
- missing skill refuses;
- unexpected custom skill refuses in exact profile;
- no credential bytes in receipt/event/model-visible output;
- no work turn before launch ALLOW;
- normal stop/process cleanup under OHF law.

### 13.2 Cross-provider parity acceptance

At least Codex + one non-Codex provider must execute the same bounded read-only commission under:

- same semantic execution profile;
- same canonical skill/bundle generation;
- equivalent required MCP/resource identity where applicable;
- provider-native materialization receipts;
- exact observed capability identity;
- no ambient extension influence;
- provider-neutral Executive result handling.

Provider-native session IDs/layouts may differ. Company authority and capability semantics may not.

### 13.3 Browser acceptance

Browser parity is not accepted because a screenshot file exists. It requires:

- real local devserver resource;
- exact browser profile/resource attestation;
- structured snapshot use;
- image-visible discriminating fixture consumed correctly by the model;
- console/network evidence;
- external egress falsifier;
- exact artifact receipt;
- no unexpected tracked workspace mutation;
- full cleanup proof.

### 13.4 Multi-host acceptance

A second host proof must show:

- canonical Executive Attempt remains on the control plane;
- selected opaque host/Worker realm was eligible before transport;
- capability bundle staged from exact source without credential copy;
- exact same requested/observed bundle generation semantics;
- remote timeout/effect uncertainty does not trigger alternate-host retry;
- GUI resource collision is refused deterministically.

### 13.5 Green CI is not acceptance

Unit/integration CI proves code-level invariants only. Production acceptance requires real provider/runtime input through the real installed path to a visible machine/user capability.

---

## 14. Security and trust boundaries

1. **Extension content is code/instruction trust.** Review it as such.
2. **Skill text never grants authority.** Provider frontmatter such as `allowed-tools` is advisory/provider-specific unless independently enforced; Executive policy is canonical.
3. **No secrets in Git plugin/skill source.**
4. **No inherited environment assumption.** Provider plugin runtimes that can read inherited env require an explicit sanitized process environment.
5. **No dynamic marketplace trust.** A mutable marketplace listing/version string is not source identity.
6. **No symlink-to-moving-source production identity.** Exact source bytes/digests must be stable for the Attempt.
7. **No model-controlled package install/update.**
8. **No provider-native subagent laundering.** Native children remain inside the parent Attempt capability ceiling unless separately represented as Executive organizational work.
9. **No browser privilege laundering.** Browser capability does not widen source write/network/credential authority.
10. **No plugin privilege laundering.** Installing `mastermind-operator` does not make a session a Mastermind Worker or bind it to a Job.
11. **No automatic provider/host failover after ambiguous modification.**
12. **Revocation is first-class.** Revoked bundle/app generations must become ineligible before new Attempts; existing live Attempt handling follows the accepted capability/Attempt-boundary law.

---

## 15. Rejected alternatives

### 15.1 “Agent OS should own worker plugins because workers are agents” — rejected

Agent OS owns organizational knowledge, not runtime execution state. Putting installed extensions, provider sessions or browser seats there would create a third control plane.

### 15.2 “Create one generic Mastermind super-MCP for every worker” — rejected

It would collapse unrelated authority realms, enlarge blast radius, weaken tool-schema review and duplicate existing typed owners. MCP capabilities stay narrow and independently governed.

### 15.3 “Just copy the same `.claude-plugin` directory everywhere” — rejected as proof

Compatibility is useful source leverage, not attestation. Every provider adapter must prove its own loader precedence, reload semantics and observed effective capabilities.

### 15.4 “If the skill name matches, the skill is good enough” — rejected

Company procedure is executable behavior. Same-name/different-content drift must not pass an exact profile.

### 15.5 “Let the worker install what it needs” — rejected

That makes capability/authority mutable after routing and gives unreviewed external content execution trust.

### 15.6 “Give all agents arbitrary desktop/browser access” — rejected

Browser/computer-use is an explicit resource with network, identity and GUI concurrency consequences. Make it broadly routable when eligible, not ambient.

### 15.7 “Use tmux as the session/worker manager” — rejected

Tmux may keep a process alive. It is not company lifecycle, identity, retry, result or authority truth.

### 15.8 “Build provider-specific brokers first and unify later” — rejected

HF1 exists specifically to prevent `grok_broker`, `glm_broker`, `claude_broker` divergence.

---

## 16. Current primary-source provider evidence

Current official documentation observed during this freeze supports the convergence direction:

- OpenAI: `https://developers.openai.com/codex/build-plugins` and `https://developers.openai.com/codex/build-skills` — current Codex plugin/skill surfaces; plugins can package skills and MCP and are shared with supported ChatGPT plugin distribution.
- Anthropic: `https://code.claude.com/docs/en/plugins` — Claude Code plugin architecture for reusable skills/agents/hooks/MCP.
- xAI: `https://docs.x.ai/build/features/skills-plugins-marketplaces` — Grok Build skills/plugins/MCP/marketplaces and current Claude Code compatibility statement.
- ZCode: `https://zcode.z.ai/en/docs/plugin` and `https://zcode.z.ai/en/docs/skill` — plugin/skill/MCP packaging, Claude-compatible manifest fallback and external-agent skill import.

Provider documentation is evidence, not execution proof. Every implementation wave re-pins current docs plus exact installed runtime behavior.

---

## 17. Architecture freeze / no-rebuild law

The following are frozen unless Sol records a new explicit architecture ruling based on evidence:

1. Executive OS remains the only Job/Attempt/Worker/Event lifecycle.
2. Agent OS remains knowledge, not worker runtime.
3. `ExecutionCapabilityRegistry` remains the capability grant/source-generation owner.
4. BSC-F2 owns installed plugin/app generation attestation; this program consumes, not duplicates, it.
5. OHF/HF1 remains the common worker harness contract.
6. Provider adapters own only provider-native materialization, start/resume/observe/cancel/reconcile mechanics.
7. Custom company skills require content identity, not name-only attestation, for exact profiles.
8. Provider-native package formats may differ while semantic capability identities stay common.
9. Dynamic model-controlled capability installation is forbidden for production work.
10. Browser Resource Fabric remains the browser/devserver owner.
11. MH1/Capacity remains the host/resource placement owner.
12. GUI/computer-use is an explicit capacity/resource realm, never ambient desktop authority.
13. Chairman browser/provider credentials are never copied to workers.
14. Effect-unknown modification blocks provider/host reassignment until canonical reconciliation.
15. Tmux remains a substrate, never a lifecycle or capability authority.

---

## 18. Exact next action

This carrier must remain records-only.

The next implementation action for this program is **not** to start a new provider broker or install plugins on hosts. It is:

1. preserve the active dependency chains already underway;
2. accept/protect BSC-F2's exact installed-bundle/source-generation contract in the existing registry;
3. reach the accepted HF1 seam through the current Capacity/Router dependency chain;
4. then commission **CAP-S1**, the narrow exact custom-skill content-attestation vertical on Codex;
5. after CAP-S1 proof, implement provider-neutral materialization and one non-Codex parity vertical;
6. separately complete real Worker Browser B1 installed-path proof before widening browser network/resource authority.

No current carrier should claim that cross-provider operator capability parity, browser-for-all-workers, arbitrary public browsing, multi-host routing, plugin installation, or production Worker readiness is complete because this architecture file exists.
