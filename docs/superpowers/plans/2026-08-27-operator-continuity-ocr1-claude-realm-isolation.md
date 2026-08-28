# OCR-1 Claude Realm Isolation Falsifier — SUPERSEDED / DO NOT IMPLEMENT

**Status:** `SUPERSEDED_BEFORE_IMPLEMENTATION`  
**Operation key:** `operator-continuity-realm-rebinding-20260827-sol-001`  
**Superseded by:** `docs/superpowers/plans/2026-08-27-operator-continuity-ocr1-native-realm-isolation-v2.md`  
**Controlling amendment:** `docs/superpowers/specs/2026-08-27-operator-continuity-claude-auth-compatibility-amendment.md`

This file is a tombstone for the first OCR-1 planning draft. **Do not commission or implement it.**

The initial draft explored using Macro `CLAUDE_CODE_OAUTH_TOKEN_N` pool values as Executive Claude worker credentials. Current-source reconciliation found that this conflicts with the more specific accepted Claude V1 provider source law, which freezes the first Executive Claude production path around native Claude subscription login under a dedicated worker OS principal / Claude-owned macOS Keychain realm.

The following ideas from the historical draft are explicitly rejected for the first production pool:

- reading Macro `CLAUDE_CODE_OAUTH_TOKEN_N` values for Executive worker execution;
- injecting `CLAUDE_CODE_OAUTH_TOKEN` into OCR/PF1 provider subprocesses;
- running `claude setup-token` as part of OCR-1;
- treating five `CLAUDE_CONFIG_DIR` directories under one macOS user as five independent credential realms;
- persisting provider account identity/PII merely to prove realm distinction;
- creating a token broker, credential mapper or synchronization service.

The accepted OCR-1 V2 instead defines one Claude realm as an opaque Executive/Capacity realm label bound to an exact host + OS principal + native provider authentication realm and proves readiness with secret-free installed-host evidence. `AuthRealmRequirement.SLOT_BOUND_V1` remains valid when the provider cannot expose a safe stable account identifier.

Git history preserves the superseded draft for archaeology. Current implementation must use the V2 plan and controlling auth compatibility amendment only.
