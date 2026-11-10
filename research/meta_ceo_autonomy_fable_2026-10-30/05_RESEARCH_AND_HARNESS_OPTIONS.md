# Research synthesis and harness options

**Question:** Which engineering patterns and already available implementations most directly improve Mastermind's original autonomous-organization outcome without replacing its accepted owners? Public research informs design; it is not evidence that a Mastermind path is installed or authorized.

Research was current to October 30/31, 2026. Only first-party engineering, official specifications/documentation and original repositories are used for technical claims below. No provider was contacted, no plan purchased and no new donor installed in this research. The market price or live entitlement of any candidate remains unverified.

## 1. What current primary research suggests

### A. Separate generation from outcome evaluation; do not mandate a particular agent hierarchy

Anthropic's March 24, 2026 [long-running application harness report](https://www.anthropic.com/research/harness-design-long-running-apps) describes planner/generator/evaluator separation, concrete evaluation criteria and structured session handoffs. It reports self-evaluation leniency and model-dependent long-context behavior.

**Application to Mastermind (our inference):** Keep independent original-intent and real-artifact review; give Fable concrete taste/usability criteria instead of a vague “make it excellent.” Reuse existing review and continuity owners. Do not require three agents for every task or fixed context resets; verify whether the selected model/harness benefits. This is a reported engineering approach, not proof that every model or task needs the same structure.

### B. Context should be curated and expandable, not encyclopedic

Anthropic's September 29, 2025 [context-engineering article](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents) distinguishes prompt design from the ongoing selection of relevant context and recommends guidance between brittle hardcoding and vagueness.

**Application:** Supply a small entry brief plus exact domain/source pointers, not every source in every worker prompt. Keep a compact mission/effects/accepted-work frontier and expand for real questions. This directly supports the user's request for a prepared but non-constrictive Fable plan. Fewer tokens are not inherently better; sufficient relevant context and correct consumer behavior are the test.

### C. Evaluate the actual environment outcome and the harness-model combination

Anthropic's January 9, 2026 [agent-evaluation guidance](https://www.anthropic.com/research/demystifying-evals-for-ai-agents) distinguishes task, trial, grader, transcript and final environment outcome, and emphasizes that an agent evaluation measures the harness together with the model.

**Application:** A worker's “done” message cannot replace source/runtime/consumer evidence. Use deterministic assertions for exact effects and independent calibrated judgment for interpretation and product quality. Compare candidate harnesses under normalized and realistic contexts, with repeated trials where useful. Preserve held-out cases and the existing Agent Eval owner rather than creating another leaderboard.

### D. Stable interfaces can outlive a model or harness implementation

Anthropic's April 8, 2026 [Managed Agents engineering report](https://www.anthropic.com/research/managed-agents) describes separating session history, harness and execution environment and notes that scaffolding useful for one model may become unnecessary for another.

**Application:** Treat the selected interaction harness as replaceable behind existing Executive, Agent OS and resource interfaces. Recover from durable owner evidence, not an irreplaceable local chat. This does **not** recommend purchasing Managed Agents, moving included-plan principal cognition to a metered API, or adding its session service alongside Mastermind's owners. Replacement of execution machinery remains subject to actual effect reconciliation.

### E. Make the environment and evidence legible to agents

OpenAI's February 11, 2026 [harness-engineering account](https://openai.com/index/harness-engineering/) describes repository-based knowledge, agent-readable UI/observability and explicit architecture constraints in an agent-first development environment.

**Application:** Give workers reproducible, scoped test/review paths and exact source maps; expose the real product's observable behavior rather than requiring the Chairman to relay logs. Preserve Mastermind's existing independent-review and release rules instead of importing another team's merge philosophy. The report's throughput estimates are not performance forecasts for this fleet.

### F. Thin orchestration is useful for routing, not a substitute for strategic judgment

Meta's October 19, 2026 [thin-orchestrator engineering report](https://engineering.fb.com/2026/10/19/ml-applications/thin-orchestrator-ai-agent-architecture/) separates deterministic pipeline routing/reliability checks from specialist reasoning in a specific configuration-onboarding system.

**Application:** Keep deterministic admission/routing with existing owners and give domain operators bounded context. Avoid making the primary principal ingest every domain schema and raw return. However, Mastermind's strategic/product decisions remain ambiguous and require judgment; this report does not justify turning the Meta-CEO into a fixed pipeline or removing Fable's creative responsibility. Reported Meta results are not imported as Mastermind benchmarks.

### G. Authorization belongs at the receiving boundary

The official [MCP authorization security considerations, 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations) require resource/audience binding, appropriate token validation, secure communication, PKCE and exact redirect protections; token passthrough is forbidden.

**Application:** Preserve existing role-correct scopes, issuer/resource validation and exact owner policy. A local proxy or a model-selected role must not broaden permission. Qualify the actual client/receiver exchange, including negative audience, role and redirect cases. This is particularly relevant to the held Claude COO adapter and candidate Steward/harness integration.

### H. An agent tool server adds security questions beyond OAuth syntax

The official [MCP security best-practices document](https://modelcontextprotocol.io/docs/2026-07-28/tutorials/security/security_best_practices) treats confused-deputy behavior, token misuse, SSRF, session misuse and local-server risks.

**Application:** Test destination/source constraints, hostile tool output, correct session association and actual least-privilege execution. Do not treat a valid OAuth token as permission for every repository, browser profile, recipient or external disclosure. These tests supplement existing Mastermind security contracts; they do not authorize a new gateway or broad red-team activity against live systems.

### I. Durable replay needs recorded history, not optimistic resubmission

[Temporal's workflow execution documentation](https://docs.temporal.io/workflow-execution) explains recovery by checking replayed commands against recorded event history.

**Application:** Use this as a comparison principle for the **existing** Executive recovery/effect machinery. A lost answer must reconcile the original command and effect, not be “fixed” by a second request. Do not install Temporal, introduce a new queue or claim exactly-once external effects based on this analogy. The actual Mastermind contracts and external API behavior decide what is safely replayable.

### J. Observability references themselves can drift

The old [OpenTelemetry GenAI agent-span page](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/) now redirects readers to the dedicated [GenAI semantic-conventions repository](https://github.com/open-telemetry/semantic-conventions-genai). The new repository covers GenAI clients, MCP and provider-specific conventions.

**Application:** Pin an actually adopted convention before implementing trace fields. Reuse owner operation/result identifiers, redact sensitive content and distinguish selected from observed model identity. Do not make a trace collector the lifecycle owner or invent unsupported semantic attributes from an obsolete page. Specific new attribute contracts were not audited in this research.

## 2. Harness comparison: evidence, not marketing

### DeepSeek Harness

**Original source inspected:** [README at the pilot pin](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/README.md), [safety notice](https://github.com/deepseek-ai/deepseek-harness/blob/687f282e8625c6b8d11ff58211a90524be2e4317/SAFETY.md). The README describes a Cordis/plugin architecture and developer preview with breaking changes. Its safety notice says the software is not security-audited or production-ready and should not be the sole isolation control.

**Mastermind evidence:** #1717 full-app pilot; #1790 real provider-free governed MCP tests on another exact pin; #1845 startup probe qualified against a synthetic child, not the real donor; #1876 isolated developer-seat launcher; original ACP/Runtime integration remains separate.

**Best-fit hypothesis:** Flexible interaction/AgentLoop foundation and extension seams, with existing significant Mastermind integration investment.

**Decision risks:** Multiple donor pins, ignored build/dependency closure, preview churn, actual isolation, native model/tool identity and original-parent return. A private DSH_HOME and tool-free persona are not a sandbox.

**Next discriminator:** Same real Office mission under a pinned full dependency closure and actual receiving tool grants. Preserve its source investment even if another harness wins the resident Secretary role.

### Hermes Agent

**Original sources:** [official documentation](https://hermes-agent.nousresearch.com/docs); [pinned MIT license](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/LICENSE). The current official documentation advertises memory, skills, messaging, scheduling, MCP and subagents. Those are upstream features, not accepted Mastermind capabilities or automatic permission to enable overlapping systems.

**Mastermind evidence:** #1865 reports an actual isolated provider-free CLI/backend startup and role-registry checks; #1869/#1871-#1875 and later hardening build the reader, inert delegation, runtime/model/Secretary integration; #1880/#1881 qualify disabled native MCP and clarify-only registry; #1883 introduces native scoped BYOK; #1884 binds shadow Wake to typed owner attention; #1885 repairs secret-value aliases.

**Best-fit hypothesis:** Credible persistent headless Secretary/Meta-CEO interaction candidate with useful existing role and runtime work. It is no longer merely a pattern reference.

**Decision risks:** Upstream memory/cron/subagent features overlap canonical owners; actual model/tool admission and parent consumption remain unproven; source-only/private prerequisites and release checks remain. Clarify-only startup is intentionally much narrower than an autonomous organization.

**Next discriminator:** Qualified role -> incumbent Steward read -> original Executive/Fabric admission -> actual worker/ruling/review/parent return. Keep native overlapping schedulers/delegation inert unless the existing authority explicitly supplies the correct integration.

### Rakazo

**Original sources:** [pinned README](https://github.com/elie222/rakazo/blob/c5e66e010ee3f3166d2ad216f928a75a0b9a2218/README.md), [Apache-2.0 license](https://github.com/elie222/rakazo/blob/c5e66e010ee3f3166d2ad216f928a75a0b9a2218/LICENSE), and [official product explanation](https://rakazo.com/about/). The inspected source describes persistent bots, browser/shell use, memory/routines, PostgreSQL/Prisma, Better Auth and Graphile Worker.

**Mastermind evidence:** #1852 source qualification and #1860 topology/preparation; no accepted full live company journey.

**Best-fit hypothesis:** Strong product/computer-interaction comparator and selective donor where licensed components genuinely help.

**Decision risks:** Wholesale runtime adoption would bring independent authentication, database and job machinery. A visually complete app is not necessarily the cheapest integration with Mastermind's owners.

**Next discriminator:** Compare the user journey and operator effort against the smaller incumbent-compatible options. Prefer bounded lawful reuse where it wins; do not run a second company lifecycle alongside Executive.

### Existing Office and Grok Secretary

These are the baseline, not disposable obstacles. The Office already has the company-specific source/selection contracts, and Grok Secretary has incumbent responsibilities. Source records report limitations on one observed gateway path; that is not proof every Grok bot or host is unusable. A replacement needs actual evidence, current custody reconciliation and rollback, not a better marketing feature list.

## 3. Decision matrix for Fable

This is a **qualitative choice rubric**, not fabricated performance scoring. Populate observations through the actual comparison; unknown stays unknown.

| Criterion | Why it matters | Strong evidence |
|---|---|---|
| Original Chairman journey | Avoids another disconnected assistant | Same intent, ordinary ruling, real accepted result and original-parent return |
| Existing-owner compatibility | Avoids control-plane duplication and integration debt | Receiving owners remain authoritative; no alternate task/memory/auth queue |
| Real tool isolation | Protects company data and effects | Actual registry/process/network/env/receiver tests, not prompt assurances |
| Recovery and responsiveness | Keeps one useful office across long projects | Foreground answer while child works; interrupted original operation recovered |
| Product comprehension | Makes current work and decisions understandable | User can explain status/limitation/next action from the actual Office |
| Native requirements | Preserves R2 rather than substituting a simpler product | Exact eligible native Project/mode/context and parent consumption |
| Total completion economics | Captures coordination and review, not only token price | Measured whole-cycle usage, backlog, repair and Chairman burden |
| Maintainability and provenance | Avoids brittle unreviewed donor code | Exact donor/dependency pins, licenses, small adapters, source tests and release evidence |
| Operational reliability | Distinguishes demo from useful organization | Installed campaign with actual failures, recovery and workload coverage |

**Provisional recommendation:** Keep DSH and Hermes as serious, bounded alternatives; use the existing Office/canonical interfaces as the stable product anchor. Hermes deserves a stronger candidacy than the old plan allowed; DSH should not be discarded before the actual comparison. Rakazo is most immediately useful as a product comparator. This is a recommendation, not an accepted harness election.

A role split can be valid—for example, one harness for a resident headless role and another for a specialized developer interaction—only if it reduces total complexity and still has one company authority. Multiple harnesses are not inherently better; compare the cost of shared identity, recovery, tools and release maintenance.

## 4. Other donor material: preserve provenance and avoid renewed archaeology

The existing [October 24 donor assessment](https://github.com/mastermindx-market-intelligence/Mastermind/blob/dc0016ec6f27a5e45014917adb3c8a4043ff46ab/research/META_CEO_OPEN_SOURCE_HARNESS_DONOR_ASSESSMENT_2026-10-24.md) already inspected OpenMausBot, OpenGrokBot, Rome, Open Dots and OpenDot. Reuse its exact pins and caveats rather than rerunning a broad GitHub search.

OpenMausBot's OSS versus restricted enterprise boundaries and third-party assets require file-level license care. OpenDot had no verified redistribution license at the inspected root; do not treat it as a code donor until that changes through actual evidence. Material described as retained proprietary Grok Bot code/assets is not a lawful implementation donor. Publicly documented product behavior can inspire an original implementation; it does not authorize copying proprietary internals.

This research independently refreshed the most decision-relevant DSH/Hermes/Rakazo sources and licenses. It did not independently re-audit every file/license in every secondary donor.

## 5. Research questions now worth answering—and questions to stop spending on

High-value next questions: Which actual candidate completes the same owner-bound journey? What is the smallest missing admission/return adapter? Does the primary remain responsive? Does a real interruption recover the original effect? Which context pack produces correct intent with less rediscovery? Is the observed blocker code, release, credentials/consent, provider capacity, or missing consumer proof?

Low-value repetition: another general survey of agent frameworks; counting stars; generic model rankings; reading complete transcripts; creating new universal context schemas; comparing list prices without actual entitlements; rebuilding a feature that is already merged; or asking whether a harness has “memory” without testing how it respects Agent OS.

Stop a research branch when its decision is sufficiently supported or the exact remaining evidence is unavailable and independent useful delivery is ready. Continue difficult research when a feasible discriminating test could materially change the design. The purpose is better execution, not a larger bibliography.
