# Operator Continuity — Claude Authentication Compatibility Amendment

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Status:** **ARCHITECTURE AMENDMENT / RECORDS ONLY.** This narrows the Chairman-approved Operator Continuity architecture after current-source reconciliation. It creates no provider login, credential, Worker, Attempt, route or production capability.  
**Operation key:** `operator-continuity-realm-rebinding-20260827-sol-001`  
**Protected Mastermind / Skillpack basis:** `af43f356f4f7f34cb3514d1d1099b50444af8487`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1.  
**Parent architecture:** `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`  
**Higher-specificity predecessor reconciled:** `research/MASTERMIND_EXECUTIVE_CLAUDE_V1_PROVIDER_SOURCE_LAW_2026-08-26.md` and `docs/superpowers/plans/2026-08-27-hybrid-workforce-pf1-claude-worker.md`.

## 1. Collision found

The approved Operator Continuity design listed several possible mechanisms that could eventually isolate the five paid Claude subscriptions, including a host-local long-lived subscription-token mechanism. Current Claude V1 provider source law is more specific for the first production Claude vertical: it freezes native subscription login under a dedicated worker OS principal, with Claude-owned macOS Keychain storage, and explicitly rejects `CLAUDE_CODE_OAUTH_TOKEN` / `claude setup-token` as the default local worker auth path.

The first OCR-1 implementation plan drafted before this reconciliation proposed injecting existing `CLAUDE_CODE_OAUTH_TOKEN_N` values into probe subprocesses. That would widen provider-secret authority and contradict the accepted PF1 security boundary.

## 2. Ruling

**The stricter existing Claude V1 auth law remains controlling for PF1 and for the first Operator Continuity production proof.**

For the first production-real pool:

```text
one Claude realm
= one opaque Executive/Capacity realm label
+ one exact host_ref
+ one dedicated OS principal / native Keychain realm
+ one exact Claude Code binary/profile
+ native claude.ai subscription login performed through a Chairman/admin ceremony
+ secret-free proof that the selected credential source is that native subscription login
```

Distinct physical hosts naturally provide distinct host/principal realms. Multiple Claude realms on one Mac require distinct OS principals / Keychain realms or another provider-supported isolation mechanism that is separately reviewed and accepted.

### 2.1 Token path status

`CLAUDE_CODE_OAUTH_TOKEN` remains a **researched provider-supported mechanism, not an accepted production realm mechanism under this freeze**.

The Chairman's approval of the broader continuity architecture does not, by itself, supersede the existing provider secret law or authorize token generation/injection. If native OS-principal/host isolation later proves insufficient for the required pool, Sol may propose a separate explicit provider-source-law amendment with its own secret-boundary design and Chairman/admin gate. Until then:

- do not run `claude setup-token`;
- do not read `CLAUDE_CODE_OAUTH_TOKEN_N` values from Macro for Executive worker use;
- do not inject a subscription token into an OCR/PF1 subprocess;
- do not create a token broker, credential mapper or synchronization service;
- do not reinterpret Macro's existing OAuth pool as Executive worker login authority.

Macro's existing `claude_code_oauth_N` capability slots remain valid for the provider lanes that already own them. This amendment changes no current Macro provider behavior.

### 2.2 Native login must win Claude Code authentication precedence

Current first-party Claude Code documentation makes `/login` subscription OAuth the lowest normal credential in a broader precedence chain. Higher-precedence sources include Claude apps gateway/provider selection, cloud-provider modes, `ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_API_KEY`, `apiKeyHelper`, `CLAUDE_CODE_OAUTH_TOKEN`, and Anthropic profile/federation credentials. Therefore a dedicated macOS Keychain realm is not sufficient proof if the actual worker environment/configuration silently selects another source.

For V1 Executive Claude realms, the accepted worker environment must fail closed on any ambient higher-precedence source capable of moving execution off the intended native subscription. At minimum current-source review must cover/refuse or explicitly neutralize through the **same production worker composition**:

```text
CLAUDE_CODE_USE_BEDROCK
CLAUDE_CODE_USE_VERTEX
CLAUDE_CODE_USE_FOUNDRY
ANTHROPIC_AUTH_TOKEN
ANTHROPIC_API_KEY
CLAUDE_CODE_OAUTH_TOKEN
ANTHROPIC_PROFILE
ANTHROPIC_FEDERATION_RULE_ID / ANTHROPIC_ORGANIZATION_ID and related federation inputs
apiKeyHelper / active Anthropic profile configuration
a Claude apps gateway session or other provider selection
```

The preflight must then verify the provider-reported selected auth method through `claude auth status` (JSON by default in current first-party CLI docs). For the first accepted subscription realm:

```text
logged in = true
selected auth method = claudeai/native subscription login
selected provider = Anthropic first-party subscription path where the installed-version wire exposes it safely
```

Exact JSON field names are attested against the installed reviewed Claude version; unknown or changed fields fail closed rather than being guessed. Provider email, organization/account IDs and other PII from the JSON response are discarded before receipt construction.

A worker preflight must not obtain a passing result by unsetting an ambient source that the real later worker process would retain. The preflight and provider process must share the same reviewed production environment-composition law. If actual runtime composition would select a different credential source, the realm is not `WORKER_CONTEXT_AUTH_READY`.

First-party source reconciled during review: `https://code.claude.com/docs/en/authentication` and `https://code.claude.com/docs/en/cli-usage` as observed 2026-08-27. These URLs are evidence only; checked-in Mastermind source law remains authoritative until a fresh action-time provider review supersedes it.

## 3. Realm identity for V1

Provider account PII is not required to become durable Executive identity.

The existing Operator Harness already distinguishes:

```text
AuthRealmRequirement.SLOT_BOUND_V1
AuthRealmRequirement.VERIFIED_PROVIDER_ACCOUNT
```

The first pool may use `SLOT_BOUND_V1` when the installed provider cannot expose a non-secret stable account identifier. Realm distinction is established by exact execution-principal/auth-home separation plus **native selected-login readiness**, not by persisting email/account identifiers.

A V1 realm proof therefore requires:

- unique opaque realm/account label assigned by trusted provisioning;
- exact host identity;
- exact OS principal identity;
- distinct provider credential realm by construction (separate user Keychain or separate host principal);
- `claude auth status` success under that principal;
- proof that the selected auth method/provider is the native subscription path rather than a higher-precedence ambient source;
- exact binary/version/profile evidence;
- Chairman/admin confirmation that the intended subscription was used for the native login when provider-reported account identity is unavailable;
- no credential/account PII in GitHub, Agent OS, Slack, Executive events or model prompts.

`provider_reported` identity may strengthen this later, but unknown provider account identity is not converted into a fabricated value.

## 4. macOS config-directory ruling

`CLAUDE_CONFIG_DIR` is not accepted as the credential-isolation boundary on macOS. Current first-party documentation says Claude Code credentials are stored in the encrypted macOS Keychain, and `CLAUDE_CONFIG_DIR` relocates the credentials file on Linux/Windows rather than defining a separate macOS Keychain credential. An upstream issue also reports cross-config credential collision on macOS. The issue is a falsifier, not canonical provider truth, but the first-party Keychain behavior alone is sufficient to reject “five config dirs under one OS user” as proof of five independent credential realms.

A real installed-host test may prove additional isolation behavior, but absence of collision in one run does not grant a config directory authority over Keychain identity.

## 5. OCR-1 plan supersession

The earlier plan:

```text
docs/superpowers/plans/2026-08-27-operator-continuity-ocr1-claude-realm-isolation.md
```

is **SUPERSEDED BEFORE IMPLEMENTATION** by:

```text
docs/superpowers/plans/2026-08-27-operator-continuity-ocr1-native-realm-isolation-v2.md
```

and the single-preflight path/schema correction in:

```text
docs/superpowers/specs/2026-08-27-operator-continuity-claude-preflight-owner-amendment.md
```

Specifically superseded/rejected from the first plan or later stale plan wording:

- resolving token values from `CLAUDE_CODE_OAUTH_TOKEN_N`;
- setting `CLAUDE_CODE_OAUTH_TOKEN` in probe subprocesses;
- pairwise provider-account comparison that requires handling raw provider account identity;
- treating token-backed process environments as an accepted V1 realm;
- treating any successful Claude authentication method as equivalent to the required native subscription login;
- creating a second `claude-native-realm-preflight.py` beside the PF1-reserved Claude worker preflight.

The original plan remains historical evidence only and must not be commissioned.

## 6. Compatibility with the approved continuity outcome

This amendment does not reduce the five-subscription objective. It changes the first admitted mechanism from “any isolated credential mechanism” to “native provider login in distinct trusted OS-principal/host realms with exact selected-auth proof.” The five-account pool may span multiple Macs; the later MH1 architecture already expects host-local credentials and one canonical Executive Runtime.

If the actual host estate cannot support five native isolated realms, or the real worker context cannot prove native subscription auth wins credential precedence, record that falsifier and return to Sol. Do not silently weaken the security boundary to make the pool count look complete.
