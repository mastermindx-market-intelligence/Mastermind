# Executive OS Phase 1G — Provider Evidence Register

**Status:** dated external evidence for the Agent Fabric design  
**Evidence date:** 2026-08-15  
**Rule:** provider limits, model names, plan terms, supported tools, and pricing are volatile. This file records the evidence used to form the current design; runtime policy must use fresh configured/observed state rather than treating these values as permanent constants.

---

## 0. Evidence classes

- **Official product documentation:** provider-controlled documentation or pricing page.
- **Operator premise:** current Mastermind-owned account topology supplied by Chairman Chris; not a claim about public plan mechanics.
- **Architecture inference:** a conservative design decision derived from the evidence, explicitly identified as such.

No credential, account email, OAuth state, or API key belongs in this register.

---

## 1. OpenAI / ChatGPT / Codex

### Official evidence

Source: OpenAI Help Center, “Using Codex with your ChatGPT plan”  
`https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan`

Current documentation states that Codex, ChatGPT Work, ChatGPT for Excel, and Workspace Agents draw from the same agentic usage/credit pool **when they are available on the same plan**. Consumption varies with task size, complexity, model, execution location, codebase size, and session length.

Source: OpenAI Help Center, “ChatGPT agent”  
`https://help.openai.com/en/articles/11752874-chatgpt-agent`

Current documentation separately describes ChatGPT agent availability and plan limits.

### Operator premise

Chris reports that Mastermind currently has:

- one ChatGPT Business account intended for Workspace Agents / the executive surface;
- multiple separate accounts specifically for Codex execution;
- those Codex accounts use the operator-described “20× Max” plans;
- usage on the dedicated Codex accounts does not consume the current Business account’s pool.

The repository deliberately records no account count, login identity, or credential.

### Architecture implication

- Register the Business account as `capacity_domain=executive_workspace`, `worker_claimable=false`.
- Register each dedicated Codex account as an independent `provider_account`, pool, provider home, and worker slot.
- A limit/auth failure on one Codex account must not update another Codex account or the Business account.
- Exact-model/different-Codex-account is the first implementation failover preference.

The independence between separate accounts is an operator-supplied topology fact, not inferred from the same-plan sharing statement.

---

## 2. xAI / SuperGrok / Grok Build

### Official evidence

Source: xAI documentation, “FAQ — Grok Website / Apps”  
`https://docs.x.ai/grok/faq`

Current documentation states that paid SuperGrok users receive one shared weekly pool across Grok products, with usage broken down by product such as API, Build, Chat, Imagine, and Voice. The reset date/time is displayed in Settings → Usage.

Source: xAI documentation, “Grok Build — Headless & Scripting”  
`https://docs.x.ai/build/cli/headless-scripting`

Current documentation supports:

- headless prompts;
- named/resumable sessions;
- `plain`, `json`, and `streaming-json` output;
- explicit working directory;
- ACP over JSON-RPC with `grok agent stdio`.

Source: xAI documentation, “Grok Build overview”  
`https://docs.x.ai/build/overview`

Grok Build is officially described as usable interactively, headlessly, or through ACP.

### Architecture implication

- Grok Build is a separate provider/account pool from Cursor.
- The SuperGrok pool can be consumed by non-Build Grok activity, so Build-session estimates alone cannot establish exact remaining capacity.
- Prefer ACP or streaming JSON to tmux pane parsing.
- Persist provider session IDs and use provider-reported weekly usage/reset evidence where available.

---

## 3. Cursor Ultra

### Official evidence

Source: Cursor pricing  
`https://cursor.com/pricing`

Current pricing describes Ultra as 20× Pro Agent limits, with generous limits for Grok and Composer, frontier-model access, skills/hooks/MCP, and cloud agents.

Source: Cursor, “Increased usage for agents”  
`https://cursor.com/blog/increased-agent-usage`

Cursor documents a first-party models pool and API-priced model usage as separate usage categories.

Source: Cursor documentation, “Using CLI”  
`https://docs.cursor.com/en/cli/using`

The CLI supports:

- non-interactive print mode;
- JSON output;
- resuming by thread/session ID;
- project `AGENTS.md` and `CLAUDE.md` rules;
- full write access in non-interactive mode.

Source: Cursor, “Grok 4.5”  
`https://cursor.com/grok-4-5`

Cursor currently describes its Grok model as part of Cursor’s first-party model pool.

### Architecture implication

- Cursor is represented independently from xAI/SuperGrok.
- Separate Cursor pool categories are created only when the account/dashboard or official product surface can distinguish them reliably.
- Use CLI structured output and resumable IDs before tmux.
- Start with conservative concurrency and calibrate from actual account telemetry.

---

## 4. Z.AI / GLM Coding Plan

### Official evidence

Source: Z.AI Coding Plan overview  
`https://docs.z.ai/devpack/overview`

Current documentation states:

- usage is governed by both rolling five-hour and weekly limits;
- estimated Max limits are approximately 1,600 prompts per five-hour window and 8,000 prompts per week;
- one prompt is estimated to invoke the model 15–20 times;
- supported tools share the subscription quota;
- Claude Code model environment variables can map to GLM models.

Source: Z.AI usage policy  
`https://docs.z.ai/devpack/usage-policy`

Current policy states:

- the subscription is for individual subscriber use;
- benefits are limited to officially supported tools/products;
- unsupported or SDK-based access may trigger throttling, suspension, or other restrictions;
- concurrency may vary dynamically.

Source: Z.AI supported-tool integration  
`https://docs.z.ai/devpack/tool/others`

Current documentation lists supported coding/agent tool environments, including Claude Code.

Source: Z.AI Claude Code integration  
`https://docs.z.ai/devpack/tool/claude`

Current documentation shows the supported Anthropic-compatible endpoint/configuration for Claude Code.

Source: Z.AI GLM usage-query plugin  
`https://docs.z.ai/devpack/extension/usage-query-plugin`

Z.AI provides an official Claude Code plugin that queries current Coding Plan quota and usage statistics.

### Architecture implication

- Use an officially supported client path; do not build an unsupported direct Coding Plan SDK.
- Model five-hour, weekly, and any MCP/monthly limits as separate horizons.
- Treat advertised prompt counts as estimates, not exact static constants.
- Begin with one dedicated subscriber/worker slot and conservative concurrency.
- Normalize the official usage-query result into non-secret `CapacityObservation` data.

---

## 5. Alibaba Cloud Token Plan — Team Edition

### Official evidence

Source: Alibaba Cloud Model Studio, “Token Plan (Team Edition) overview”  
`https://www.alibabacloud.com/help/en/model-studio/token-plan-overview`

Current documentation states:

- Team Edition is monthly and billed in Credits;
- multiple Qwen and third-party models consume the plan’s Credits pool;
- seats are assigned to individual members with dedicated keys;
- Standard, Pro, and Max seats have different monthly Credit quotas;
- optional shared usage packs are separate pools used after seat quota;
- console/management surfaces report usage percentage, reset time, per-member and per-model consumption;
- the service is currently Singapore-region/Global deployment.

The same page’s usage policy states that Team Edition is for interactive use with compatible AI programming/agent tools and must not be used for automated scripts or application backends. Keys are assigned-member-only and may not be shared.

Source: Alibaba Cloud Token Plan FAQ  
`https://www.alibabacloud.com/help/en/model-studio/token-plan-faq`

Current FAQ states:

- Team, Individual/Coding, and pay-as-you-go credentials/quotas are not interchangeable;
- compatible tools may share one member key/quota;
- Team Plan remains restricted to interactive compatible-tool use rather than automated scripts/application backends.

Source: Alibaba Cloud Team FAQ  
`https://www.alibabacloud.com/help/en/model-studio/token-plan-team-faq`

Current documentation states that Team seat quotas reset monthly and do not use five-hour or seven-day windows.

### Architecture implication

- Represent each assigned seat and any shared pack as separate pools/horizons.
- Never share a member key across people or accounts.
- Register Team Edition as `operator_assisted` until Alibaba confirms the intended unattended local orchestrator flow in writing or a separately reviewed interpretation changes the mode.
- A pay-as-you-go/API Qwen entitlement is a separate account/pool and may be used for autonomous canaries when lawful.

---

## 6. Qwen Code

### Official evidence

Source: Qwen Code overview  
`https://qwenlm.github.io/qwen-code-docs/en/`

Qwen Code is officially described as terminal-based, composable, scriptable, and able to edit files/run commands.

Source: Qwen Code, “Headless Mode”  
`https://qwenlm.github.io/qwen-code-docs/en/users/features/headless/`

Current documentation supports:

- command-line/stdin prompts;
- structured text/JSON output and stream-oriented operation;
- consistent exit codes;
- project-scoped resumable sessions;
- unattended scripting/automation use at the tool level.

Source: Qwen Code, “Subagents”  
`https://qwenlm.github.io/qwen-code-docs/en/users/features/sub-agents/`

Current documentation states:

- named and forked subagents have separate behavior/context modes;
- forked results are not automatically fed back into the parent conversation;
- forks share the parent working directory and concurrent file modifications may conflict.

Source: Qwen Code worktree documentation  
`https://qwenlm.github.io/qwen-code-docs/en/users/features/worktree/`

Current documentation also describes optional subagent worktree isolation, with provider-owned ephemeral worktree behavior and limitations.

### Architecture implication

- Qwen Code structured headless operation is technically suitable for an adapter.
- Entitlement terms remain a separate gate: tool capability does not override Alibaba Team Plan restrictions.
- Provider-native subagents may be used for bounded/read-oriented fan-out, but Executive child Jobs remain the default for concurrent writing, review, lifecycle, and cross-provider routing.
- Executive OS owns the canonical worktree and handoff contract even if a provider tool supports internal worktrees.

---

## 7. Anthropic / Claude Code

### Official evidence

Source: Anthropic Claude Code CLI reference  
`https://docs.anthropic.com/en/docs/claude-code/cli-usage`

Current documentation supports:

- non-interactive print mode;
- text, JSON, and stream-JSON output;
- allowed/disallowed tool controls;
- bounded maximum turns;
- model selection;
- permission modes;
- resume/continue by session.

Source: Anthropic Claude Code SDK documentation  
`https://docs.anthropic.com/en/docs/claude-code/sdk`

The SDK/CLI provides typed streamed messages, result metadata, session IDs, turn/cost information, and programmatic tool/permission configuration.

### Architecture implication

- Prefer structured CLI/SDK events rather than terminal scraping.
- Keep leader/worker account capacity and provider homes independent.
- Generalize existing Claude key-rotor evidence into the common capacity observation model; do not let the old rotor become a second placement authority.
- Protect Claude frontier capacity with explicit reserve policy.

---

## 8. Evidence update law

Before a provider adapter or live routing policy is armed, its implementation PR must:

1. re-check every load-bearing official source above;
2. record the exact observation date;
3. update changed plan terms, model aliases, supported tools, quotas, or compliance modes;
4. add a regression/acceptance test for any changed architecture implication;
5. refuse live arming when authoritative evidence is missing or contradictory.

This register is orientation and provenance. Installed configuration plus fresh capacity observations govern runtime eligibility.