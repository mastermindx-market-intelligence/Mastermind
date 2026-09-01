# Mastermind-X Executive Claude V1 Provider Retry Amendment

**Date:** 2026-08-26  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** SOURCE-LAW AMENDMENT / RESEARCH ONLY. This file arms no Claude worker, credential, provider route, service, Job, Attempt, Worker, or runtime.  
**Protected Mastermind basis:** `5f9eca71ad21355b56da2a3c68fa5b61b3f4204a`  
**Amends:** `research/MASTERMIND_EXECUTIVE_CLAUDE_V1_PROVIDER_SOURCE_LAW_2026-08-26.md`  
**Precedence:** for Claude V1 retry and structured-output retry semantics, this amendment controls if the sibling source-law text is less explicit.

## 1. Discovery

Fresh first-party Anthropic review on 2026-08-26 found a provider behavior that must be fenced before the first Claude Executive vertical:

- Claude Code automatically retries transient API failures by default, up to **10 retries** with exponential backoff. Current first-party docs list server errors, overloaded responses, request timeouts, temporary 429 throttles, and dropped connections as retryable.
- `CLAUDE_CODE_MAX_RETRIES` controls that retry count and can be lowered for scripted use.
- Claude Code's non-interactive structured-output path also has a separate `MAX_STRUCTURED_OUTPUT_RETRIES` setting; current first-party environment-variable documentation states its default is **5** when a model response fails the `--json-schema` validation.
- In streaming/non-interactive output Claude Code can emit `system/api_retry` events with the retry attempt, maximum and delay. That event is evidence that a provider retry occurred; it is not an Executive Attempt.

The original V1 source-law intent already forbids a Claude-specific retry plane, but leaving provider defaults intact would violate that intent in practice.

## 2. V1 ruling

For the **first accepted Claude V1 foreground child Job**, the Operator Harness must explicitly launch Claude Code with the semantic equivalent of:

```text
CLAUDE_CODE_MAX_RETRIES=0
MAX_STRUCTURED_OUTPUT_RETRIES=0
```

These are **behavior controls, not credentials**. They must be injected by the reviewed harness into the child process environment after the harness has stripped/controlled credential-bearing ambient variables. They must not be accepted from untrusted job text, repository instructions, model output, `CLAUDE.md`, plugins, hooks, MCP servers or user shell aliases.

The exact implementation belongs to HF1 after current-version host verification; this research record freezes the required behavior, not a shell command.

### 2.1 Consequences

1. A transient API/network/rate-limit/server failure is surfaced by the Claude child process to the existing Executive Attempt/reconcile path rather than retried by Claude Code.
2. A structured-output schema miss is surfaced as a provider/result failure rather than causing hidden model regeneration inside the same Attempt.
3. No availability `--fallback-model` chain is configured; model unavailability returns to Executive as already frozen by the sibling source law.
4. `switchModelsOnFlag=false` remains the fail-closed category-switch posture for non-interactive work where the installed version supports it.
5. The first V1 vertical must not use background sessions, daemon restart/rescheduling, cloud sessions, Remote Control, Managed Agents rescheduling, or provider-native multiagent retries as substitute recovery.
6. Executive OS remains the sole authority that decides whether a later attempt is lawful after an observable provider failure.

## 3. Receipt and falsifier law

The later HF1/Claude production receipt must bind the effective retry fence to the invocation-policy fingerprint and prove it on the exact installed Claude Code version.

At minimum the proof must establish:

- exact Claude Code version;
- effective `CLAUDE_CODE_MAX_RETRIES=0` and `MAX_STRUCTURED_OUTPUT_RETRIES=0` at the child-process boundary without exposing credentials or unrelated environment values;
- one deterministic retryable-failure falsifier or equivalent controlled test showing the provider process does not perform a hidden retry;
- structured-output invalid-result test showing no hidden schema-regeneration loop;
- no `system/api_retry` event in the accepted production canary; if one occurs despite the zero fence, classify the attempt as non-conforming and stop rather than accepting the result;
- no second Executive Attempt is created by provider code itself.

If the exact installed Claude Code version does not honor a zero value for either retry control, or if another unavoidable hidden retry path is discovered, **HF1 must stop and return the falsifier to Sol**. Do not approximate the retry count and do not accept a provider retry plane merely because it is built into the client.

## 4. Why this is not a new retry plane

This amendment removes provider retry authority; it does not add a Mastermind retry component. No new queue, table, daemon, counter store, session registry or retry scheduler is introduced.

Transport failure remains evidence on the existing Attempt. Existing Executive effect-unknown and retry/reconcile law decides what happens next. For a modifying child Job, real worktree/Git effects are reconciled before any subsequent attempt, exactly as required by the sibling source law and one-carrier law.

## 5. First-party sources reviewed 2026-08-26

- Claude Code error reference — Automatic retries: https://code.claude.com/docs/en/errors
- Claude Code environment variables — `CLAUDE_CODE_MAX_RETRIES`, `MAX_STRUCTURED_OUTPUT_RETRIES`: https://code.claude.com/docs/en/env-vars
- Claude Code programmatic/headless use — `system/api_retry` event: https://code.claude.com/docs/en/headless
- Claude Code CLI reference — foreground `-p`, structured output, `--max-turns`, `--no-session-persistence`, `--safe-mode`, `--no-chrome`, tool fences and `--fallback-model`: https://code.claude.com/docs/en/cli-reference

## 6. Exact continuation

This amendment does **not** release Claude implementation. The accepted Autonomy V1 order remains:

```text
CF2-I accepted
    -> RF1 provider-neutral suitability tiers frozen
    -> HF1 common Operator Harness boundary frozen/implemented
    -> one Claude implementation carrier released
    -> native worker-principal login/readiness ceremony
    -> real Claude Executive child Job + independent review + production proof
```

When that dependency gate opens, HF1 must consume this retry amendment together with the sibling Claude V1 source law. A standalone `claude -p` smoke test remains insufficient for `PROVEN_LIVE`.
