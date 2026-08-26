# Mastermind-X Executive Claude V1 Subscription Programmatic-Use Amendment

**Date:** 2026-08-26  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Status:** SOURCE-LAW AMENDMENT / RESEARCH ONLY. No Claude worker, credential, service, provider route, Job, Attempt, Worker, or runtime is armed by this record.  
**Protected Mastermind basis:** `5f9eca71ad21355b56da2a3c68fa5b61b3f4204a`  
**Amends:** `research/MASTERMIND_EXECUTIVE_CLAUDE_V1_PROVIDER_SOURCE_LAW_2026-08-26.md`  
**Precedence:** this amendment controls the V1 subscription/programmatic-use boundary if the sibling source-law text is broader.

## 1. Current first-party policy facts

Fresh 2026-08-26 review of Anthropic's current first-party policy/product pages establishes two facts that must be read together:

1. Anthropic Consumer Terms of Service, effective 2025-10-08, prohibit automated or non-human access except when the user accesses via an Anthropic API key **or Anthropic otherwise explicitly permits it**. The same terms prohibit sharing Account login information, Anthropic API keys, Account credentials, or making the Account available to another person.
2. Anthropic's current Help Center page **Use the Claude Agent SDK with your Claude plan**, dated 2026-06-16, explicitly addresses Claude Agent SDK, `claude -p`, and third-party app usage with Claude subscriptions. Its June 15 update says the announced usage change is paused and, for now, those programmatic surfaces continue drawing from the user's subscription usage limits; the separate announced monthly Agent SDK credit is not currently available.

The preserved lower section of that Help Center page describes a planned pricing/credit regime that Anthropic says is paused. It is historical context, not current billing authority.

## 2. V1 ruling

The first Claude V1 proof may treat **the exact first-party-documented subscription programmatic surfaces**—specifically local Claude Code `claude -p` / the documented Agent SDK subscription-auth path—as `PROVISIONALLY_ELIGIBLE_BY_PROVIDER_DOCUMENTATION`, subject to current account/plan availability and a fresh policy recheck immediately before host authentication and production proof.

This is intentionally narrower than saying “automation with a Claude subscription is generally allowed.” It does **not** authorize:

- browser scraping or reverse-engineered subscription access;
- credential sharing between workers, people, services, hosts, or accounts;
- turning one user's subscription login into a shared organization-wide credential;
- arbitrary third-party bots outside Anthropic's explicitly documented programmatic surfaces;
- provider-native background/cloud/Managed-Agent orchestration already held by the sibling source law;
- shared production automation at scale merely because one bounded `claude -p` Executive child can be proven;
- evasion of usage limits, rate limits, plan controls, or provider safeguards.

## 3. Principal and credential consequence

For the subscription-backed V1 candidate:

```text
one authorized human-owned Anthropic account
    -> one native account-owner login ceremony
    -> one dedicated local worker OS principal / Keychain boundary
    -> Claude Code internally consumes that principal's credential
    -> no other worker or service receives the credential value
```

The isolated OS principal is an execution boundary, **not a new Anthropic account owner** and not permission to share the account with another person. HF1 must prove that the local worker process operates as the Chairman-authorized automation for the same account owner rather than exposing the Account login or credential to another human/model/principal.

No raw login credential, OAuth token, session token, API key, or Keychain value may appear in argv, GitHub, Agent OS, Linear, Slack, Executive receipts, model prompts, logs, temp files, or test fixtures.

If the required worker embodiment cannot satisfy the current Consumer Terms without making the Account available to another person/account holder, stop. Do not copy credentials to make the architecture fit.

## 4. Commercial/API boundary

Anthropic API-key access is governed by separate Commercial Terms. It remains a legitimate later transport option but is **not** interchangeable with the subscription-backed Claude Code proof:

- API-key eligibility/billing does not follow from a Pro login;
- a Console/API key must not be introduced merely to bypass a subscription-policy ambiguity without a current Sol/Chairman commercial/authority ruling;
- conversely, if current provider policy or the intended production scale requires API-key/Commercial use, the V1 Claude implementation must stop and return that as a transport/commercial gate rather than forcing subscription credentials into a shared production service.

The old preserved Help Center paragraph about “production automation at scale” belongs to the paused pre-June-15 rollout text and therefore is not treated as a current standalone billing rule. It is still a useful warning that scale can change the correct commercial transport, so HF1 must recheck the live page and applicable terms at action time.

## 5. Action-time acceptance gate

Immediately before the first Claude host-auth/readiness ceremony, Sol/HF1 must re-read current first-party Anthropic terms and the current subscription Agent SDK/`claude -p` page and record a non-secret receipt containing at least:

- document/page titles;
- current effective/published dates where supplied;
- exact transport being used (`claude -p` or current accepted equivalent);
- account/plan surface as safely reported by the installed client/provider;
- classification: `SUBSCRIPTION_PROGRAMMATIC_USE_ACCEPTED` or a fail-closed reason;
- whether an API-key/Commercial transport is now required instead.

No cached 2026-08-26 webpage text is sufficient production authority if Anthropic changes the terms or product guidance before the host proof.

## 6. Stop/falsifier conditions

Stop the subscription-backed Claude V1 carrier and return to Sol if any of these becomes true:

1. Anthropic removes or narrows the explicit subscription programmatic-use documentation relevant to the chosen transport;
2. current terms no longer contain an applicable explicit-permission path for the chosen subscription transport;
3. the actual account/plan does not expose the documented programmatic surface;
4. the worker would require credential sharing or making the Account available to another person;
5. the intended production topology is classified by current Anthropic policy as requiring API-key/Commercial access;
6. the actual host/client silently switches from subscription auth to an API key or another billing surface;
7. the provider requires a legal/commercial/account-owner ceremony not already authorized by current Chairman intent.

This is a provider-policy/transport falsifier, not permission to create another queue, lifecycle, credential broker, account pool, or fallback transport.

## 7. First-party sources reviewed 2026-08-26

- Anthropic Consumer Terms of Service, effective 2025-10-08: https://www.anthropic.com/legal/consumer-terms
- Anthropic Help Center, **Use the Claude Agent SDK with your Claude plan**, dated 2026-06-16: https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan

## 8. Exact continuation

This amendment does not release Claude implementation. The dependency order remains:

```text
CF2-I accepted
    -> RF1 provider-neutral suitability tiers frozen
    -> HF1 common Operator Harness boundary frozen/implemented
    -> revalidate current Anthropic policy/product guidance
    -> one Claude implementation carrier released
    -> native account-owner login/readiness ceremony
    -> one real Claude Executive child Job + independent review + production proof
```

A successful standalone `claude -p` call, a subscription login, or a provider Help Center page is not by itself `PROVEN_LIVE`.