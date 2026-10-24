# Open-source Grok Bot / OpenAI Dots-style harness donor assessment

**As of:** 2026-10-24. **Scope:** First-pass source/README/license review; NOT an executed benchmark, security certification, license opinion, or reproduction of private xAI/OpenAI software. **Parent operation:** \`meta-ceo-open-harness-convergence-20261024-sol-001\`. **Mastermind protected review base:** \`e00e97b81a5d41cb8a570ad080316279a0f3853f\`; Skillpack \`mastermind.sol_skillpack.v1\`, v1.0.1/bootstrap-major 1.

## Executive finding

**Reuse DeepSeek Harness (DSH) as the default *candidate* full-application foundation because Mastermind already has an explicitly preferred full-DSH adoption pilot, PR #1717, and mature existing ACP/Worker/Fabric integration predecessors.** Rakazo is the strongest product-level challenger to benchmark against DSH before a durable app-shell selection. Inspect and selectively import the **licensed, separable** OpenMausBot provider-driver/event-stream patterns. Use Hermes Agent and Rome for *patterns* in skill evolution, routines, interfaces and learning, and OpenGrokBot for per-teammate container UX/proof ideas. Do not instantiate a new Executive OS, lifecycle, queue, company memory or capacity router merely because a donor provides one.

No candidate is demonstrably a source-equivalent clone of the private Grok Bot/Dots internals. Most are independent recreations of externally visible behaviors. **'Open source' must be established by the actual license and provenance, not a repository name.** A retained proprietary Grok Bot asset collection is not an approved code donor.

## Candidate matrix

| Candidate / source pin (2026-10-24) | License / maturity from inspected public files | Validated from inspected source/docs | Proposed use | Primary reason not to wholesale adopt |
| --- | --- | --- | --- | --- |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness/tree/22ddee3792402c3e70ec5f86a63c3e3e895a2f60) | MIT; vendor developer-preview, warns of breaking changes | Plugin-first Cordis system, native chat/session/web app, local install; [Mastermind PR #1717](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1717) already pilots the full app | **Default incumbent shell/AgentLoop**, extension point via governed Cordis plugin | Preview API churn; live signed-in Mastermind journey and ACP/WorkerResult still unproven |
| [Rakazo](https://github.com/elie222/rakazo/tree/c5e66e010ee3f3166d2ad216f928a75a0b9a2218) | Apache-2.0; self-declared beta | Persistent bots, routines/memory, shared/team or isolated computers, delegation, browser/terminal, connectors; full web/Electron/mobile; Postgres/Graphile Worker/API | **Best whole-product comparator**; inspect UI/session/computer isolation and portable components | Full Rakazo runtime would add its own job scheduler/DB/auth and collide with existing Mastermind owners; must compare integration burden vs DSH |
| [OpenMausBot](https://github.com/milind-soni/OpenMausBot/tree/9f58c7838ff9ef3855e3f83d8f03cc39542b1f5b) | Apache-2.0 for OSS core, BUT \`enterprise/\` has a separate restricted production license; cross-licensed third-party components | Source inspected: \`server/contracts.ts\` defines typed provider errors and runtime events; \`CONTRIBUTING.md\` documents fake-CLI driver contract, event-based tests and API smoke; app/server and local/cloud computer options | Driver SPI, provider error classes, event fan-in, contract tests; optional UI/desktop reference | Avoid transplanting server-owned agent instances, private event ledger or proprietary \`enterprise/\`; first audit provenance of ported code and third-party assets |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent/tree/4dcef215cfe41bd2d02c2d1dad6e257a18101216) | MIT; maintained multi-channel agent | README documents persistent memory, learned Skills, scheduled delivery, parallel subagents and multiple tool backends | Reference implementation for bounded skills/learning, memory retrieval and multi-channel UX; optional standalone *noncanonical* worker | Its scheduler/memory/subagent lifecycle overlaps Mastermind canonical owners |
| [OpenGrokBot](https://github.com/wolfqing/OpenGrokBot/tree/e26183cf8923b5db5b177903b21172f8924c5904) | MIT; independent early-stage implementation | Docker computer per bot, approvals, webhook/routine instructions; \`docs/always-on.md\` details launchd/systemd and tunnel modes | Per-worker computer UX and operational threat model, local single-host service design | A second gateway, bot database, webhook queue and credential store must not supersede Mastermind |
| [Open Dots](https://github.com/Anil-matcha/open-dots) | MIT claimed in README; explicit early prototype | Owner-auth local app, governed action gateway, optional Docker/Playwright computer, audit events | Narrow action-gateway and approval tests | No built-in durable memory or schedule engine; README admits hostile-site isolation and production multi-user limitations |
| [Rome](https://github.com/rome-os/rome/tree/55cfac3eb4155b4826f3078f9aa9a820258b41f3) | MIT; app/runtime and compounding skills ecosystem | Typed Actions, Skills, Hooks, workflows/apps with source-controlled reuse | Patterns for capability packages and reusable app-like outputs through existing Mastermind Skill/Craft authorities | Wholesale Rome runtime would duplicate orchestration, memory and result storage |
| [OpenDot](https://github.com/itumor/opendot/tree/e0b050de0cc80a8d24325bf38ba99283b16059da) | Very small DSH-based prototype; **no LICENSE found** at inspected root | README proposes inbox-only wake events, schedules, goals, memory, operator rules as Cordis plugins | **Behavioral/reference inspiration only**; reimplement lawfully if valuable | No verified redistribution license, tiny maturity/evidence, no autonomous production proof |
| [brok-pot-harness](https://github.com/river-li/brok-pot-harness/tree/ead2cf14dbf86ef30e17724e7e71b9b0566530a3) | NO single umbrella license; README says it adapts retained Grok Bot release code and assets | Claims partial desktop/integration coverage and upstream code retention | **NOT A CODE DONOR**; at most study publicly documented feature list, without copying proprietary internals | Retained upstream code/assets and unclear rights; do not import, redistribute or build Mastermind from it |

**Source inspection performed:** repository metadata, public README, root license where available, selected OpenMausBot contract / licensing, Rakazo self-host docs, OpenGrokBot always-on docs, GitHub Mastermind live/open PR metadata. Candidate pins are evidence anchors, **not** qualified hashes of a locally built artifact. No donor was cloned, dependency-installed, started, fuzzed or security-audited in this session.

## What the research actually establishes

### Grok Bot-style capabilities already exist in open projects
Rakazo describes real persistent Bots, delegated tasks, remembered routines, owned private computers and a mobile shell; OpenMausBot supplies a typed driver protocol with server-side event fan-in and approval handling; OpenGrokBot shows a small always-on gateway plus container per teammate. These are **provider-published capability claims** until our own reproduction. They disprove the assumption that a from-scratch product app is necessary.

### Dots-style capabilities already exist but no source-equivalent replica is verified
OpenDot proposes schedules, event-triggered wakeups and remembered goals on DSH but is too small and unlicensed for code reuse. Open Dots is explicitly a prototype without durable routines. Hermes Agent offers more mature documented memory, cron and self-improving skill mechanics; Rome has composable Actions and Apps. Adopt validated *behavior and interfaces*, not a vendor's proprietary hidden design.

### A true Grok Bot transcript reverse-engineering effort exists
The [txcript reverse-engineered Grok Bot transcript format](https://docs.rs/crate/txcript/latest/source/docs/formats/grok-bot.md) records observed JSONL / sqlite-like on-box formats. This is useful for designing **import/export interoperability tests for a user-owned transcript**, not proof that the private Grok Bot agent harness source is freely licensed. Do not rely on undocumented formats for core Mastermind storage or provider-side access.

## Proposed donor selection and code provenance policy

**Provisional integration choices:**
1. **DSH app + Cordis plugins** for native interaction and model/tool loop, continuing the same #1717 adoption lineage. Its native sessions remain *subordinate provider execution state*.
2. **Rakazo** as the alternative entire-app candidate. Time-box a reproducible, isolated startup and owner-contract compatibility spike; if materially better, record the decision and coordinate with #1717's incumbent rather than silently forking another app shell.
3. **OpenMausBot OSS driver SPI** as a candidate for *selective licensed code reuse* only after independently validating provenance, Apache notices, compatible dependency tree, and a testable isolation boundary. Recreating a tiny boundary against existing worker v1 may be cheaper than copying a server.
4. **Hermes/Rome/OpenGrokBot** as design patterns or optional subordinate tools. Do not enable their autonomous scheduling/credentialing as a second Mastermind company authority.
5. **OpenDot and brok-pot-harness** excluded from code import under current evidence.

**OSS compliance gate for every imported directory:** exact source SHA + file path; actual root and per-directory licenses + copyright notices + third-party SBOM; no retained unreleased proprietary assets; patch origin; static/security inspection; specific functional tests; installed-artifact provenance; no ambient accounts/secrets. MIT and Apache-2.0 commonly coexist with correct notices, but separate dependencies still require checking.

## Qualification experiment, not a popularity contest

1. **Functional acceptance** — one natural-language intent becomes one grounded Meta-CEO plan, admitted bounded worker execution and original-parent-consumed result; no hallucinated running status.
2. **Long-horizon autonomy** — 24-hour then 7-day event-driven run with routine wake, cold restart, parallel children, rejection, refusal and a missed-return recovery; no duplicate actions.
3. **Tool/computer isolation** — hostile external page injection, cross-bot credentials, identity revocation, blocked writes, human approval, auth change and exact operation-key replay.
4. **Provider routing** — same exact GLM model on qualified harnesses, then same harness against GLM-5.3 / Flash and Grok reference, preserving quota, context/cache attribution and tool parity; avoid assuming native consumer modes equal direct API modes.
5. **Quality/cost** — accepted tasks per 1k model calls and per dollar, p50/p95 latency, intervention count, false refusals, retry/effect defects and operator satisfaction. Do not infer 'outmatches Grok Bot/Dot' from a feature matrix.
6. **Maintainability** — reproducible source pin, CI, notices, upgrade/diff process, observability, signed builds and portability across Mac/VPS/Linux.

Research agenda and implementation DAG: [companion masterplan](../docs/superpowers/plans/2026-10-24-meta-ceo-open-harness-convergence-masterplan.md) (path present on this candidate branch after publication).

## Current Mastermind owner boundaries

Protect and reuse the current [R2 Meta-CEO master plan](mastermind_meta_ceo_master_plan_r2_2026-10-12.md), [implementation contract](../docs/superpowers/specs/2026-10-12-meta-ceo-office-r2-implementation.md), [#1717 DSH pilot](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1717), [#687 harness convergence](https://github.com/mastermindx-market-intelligence/Mastermind/pull/687), [#1790 governed DSH MCP tests](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1790), and [#188 Grok Secretary](https://github.com/mastermindx-market-intelligence/Mastermind/pull/188). Sources describe different degrees of implementation; none alone proves a production Meta-CEO.

**Decision grade:** DSH = recommended incumbent for a proof; Rakazo = highest-priority challenger; OpenMausBot = specialist driver donor; all choices **provisional** pending reproducible integrated tests and original-owner acceptance.
