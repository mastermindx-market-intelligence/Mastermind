# Native Codex Fabric: bounded worker direct-message isolation

**Date:** 2026-10-18. **Status:** source-only candidate; not installed, not a live worker.

## Grounded failure evidence

The Chairman's attached SESSION_RESET.md (2026-10-17) audited 21 Codex chats
and three ChatGPT reference conversations. One Chrome Plugin Codex turn lasted
approximately 3.3 hours with 40 cross-chat sends, 63 peer waits and 259
commands. Multiple orchestrators drifted into repeat check-ins/heartbeat
wakes, while native subagents were disabled by the old attended config.
The reset fixed the attended native app by enabling at most two spawned
children, disabling direct peer messages, denying four Codex app tools
(send_message_to_thread, create_thread, fork_thread, handoff_thread), and
instructing sessions against cross-carrier bypass and spam. It did NOT claim
already-running in-flight tool catalogs were retroactively removed.

Read-only M2 current configuration confirms the attended user's
features.multi_agent_v2.disable_direct_message=true and exactly these
four tools in the bundled Codex app-tools plugin disabled_tools list.
Those protection settings are NOT automatically inherited by a Fabric
worker using the pre-existing Macro native_remote.command() execution
mode with --ignore-user-config.

## Narrow existing-launcher modification

The installed non-Git Macro Fabric
ext/native_remote.py (SHA-256
a111878452f2d7ba6ad97af53055d77ed9de13d783653029e5f20311902ff051)
already used --ignore-user-config and features.multi_agent=false,
and it preserves a remote host/lease/provider model preflight. The only
proposed change is additional explicit config flags on an already
lease-validated codex-native worker launch:

- features.multi_agent_v2.enabled=false
- features.multi_agent_v2.disable_direct_message=true
- agents.enabled=false

The preceding features.multi_agent=false remains. The worker's default
approved Studio MCP projection, model, sandbox and original Native
process/lease controller remain untouched. These flags intentionally
prevent the ordinary bounded *worker* from creating an autonomous native
chat web; a parent wishing to orchestrate should use the existing
governed Fabric/executive delegation and exact receiver/lineage contract.
The CLI flags are not claimed to retroactively affect attended Codex
App conversations or any already-running worker.

The installed macOS Codex CLI 0.159.3 successfully accepted these
non-provider-read -c overrides in codex features list, which
reported multi_agent=false and multi_agent_v2=false. No model turn.

## Provider-free proof and boundaries

RED-first: two requested Astra/Sol worker command tests both failed on
the byte-exact current installed source, which lacked the flags.

GREEN: nine scratch-source tests validated direct-message disable and
model restrictions, existing preflight continuation, and rejection of
injected CODEX_/OPENAI_/ANTHROPIC_ overrides, plus immutable manifest
and patch scope. The digest-sealed replay checker verified exact
installed preimage SHA, patch digest, compiled postimage SHA, replayed
the tests in a disposable scratch directory and verified the installed
kit remained unchanged. In hosted GitHub CI without the non-Git kit,
the seven provider-specific tests skip and two manifest/scope tests
run; the exact-installed-source replay proof is M2-specific.

This does NOT establish host enrollment, six worker launches, runtime
App Server tool catalog or live denial of unrelated MCP messaging;
the legacy M2 Fabric broker still advertises a single
codex-native/default slot. Account qualification, broker atomic
claim/START, original-parent result acceptance, and independent source
review are outstanding. No credential material, installed source,
model turn, reset redemption, native session messages, or broker state
was modified by this source candidate.

**Release gates:** reviewer approval and hosted CI; drift-guarded
installer by the incumbent source owner; exact CLI effective config
check on enrolled execution host; one admitted bounded worker with
recipient-scoped output and accepted return; failure/rollback proof.
Do not use this patch to bypass any platform installation refusal.
