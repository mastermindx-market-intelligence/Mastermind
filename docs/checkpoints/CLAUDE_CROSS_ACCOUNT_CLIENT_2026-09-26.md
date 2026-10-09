# Claude cross-account communication — 2026-09-26

MISSION_COMPLETE: false
FINALIZATION_CLASSIFICATION: CHECKPOINTED_CONTINUATION
Capability: BUILT_NOT_PROVEN / SOURCE + HOST ADAPTER / not cut over.
Operation: `claude-cross-account-client-20260926-sol-001`.
Parent: `agent-interconnect-mailbox-20260924-sol-001`, Mastermind #600.
Protected source/procedure: `763ec8f920177fdf48b18df1b8e37b61ab482ef0`.
Skillpack: mastermind.sol_skillpack.v1 / 1.0.1 / bootstrap 1.
Current Chairman commission: enable communication among four Claude macOS accounts.

## Reconciled architecture

Anthropic's supported same-machine carrier is now the preferred direct path:
`ListAgents` discovers peers and `SendMessage` sends bounded messages. Desktop's
session-management UI is app-local, but Claude Code native peer registration is
per-user rather than project identity. The Mastermind Company consultation facet
remains the governed semantic/durable layer for admitted peer identity, Wake,
reply/consumption, and cross-responsibility questions; it is not a second transport.

Current active profile labels are Claude 2, 3, 5 and 6. These labels are host
profile aliases, not account identifiers. Claude 2 is running Desktop 2.7032.0 /
Code 2.1.280 without a SendMessage deny. Claude 3/5/6 are running Desktop
1.46388.4 / Code 2.1.260 with `--disallowedTools SendMessage`. This is the
observed cross-app blocker; project membership is not the primary blocker.

## Source and host adapter delta
#1004 continues to extend the existing #962 plugin with native-first communication
guidance and Company peers/ask/read/reply workflows. No plugin manifest, OAuth
client, connector, hook, listener, registry, mailbox, scheduler, or lifecycle
owner is duplicated.

New `scripts/claude_cross_app_runtime.py` is a guarded entry adapter only. It has
a closed profile set for Claude 2/3/5/6, reuses the known modern Mastermind Claude
runtime, preserves each existing Parall `--user-data-dir`, emits secret-safe
status, refuses unsupported profiles, refuses a missing modern runtime, and refuses
launch while that profile already has any matching process. It never terminates,
logs in, edits profile data, copies tokens, patches a live process, or writes sockets.

The observed Parall shortcut metadata confirms each account is isolated by its own
profile root. Claude 2 already runs the modern runtime against its existing profile,
proving that runtime/profile separation is viable on this host. Existing Claude
3/5/6 sessions remain untouched.

## Verification

TDD for the native-carrier correction: 2 expected failures before the skill and
qualification source were updated; then 27/27 passed.
TDD for the guarded launcher: initial import/collection RED because the module did
not exist; after implementation 12/12 passed.

Live safe-status probe using the new adapter:
- claude-2: running, SendMessage denied=false, launch refused while open.
- claude-3: running, SendMessage denied=true, launch refused while open.
- claude-5: running, SendMessage denied=true, launch refused while open.
- claude-6: running, SendMessage denied=true, launch refused while open.

Synthetic integrated tree on current protected master + #962 exact head + #1001
exact head + current #1004 workspace: **259 passed, 4 skipped**, exit 0. Skips are
the pre-existing MCP SDK cases because this host Python lacks `mcp`. This proves
source composition only, not native delivery.

The earlier repository-wide pytest attempt still stops during collection on missing
`jwt`; no full-suite green claim. Actual four-account directed messaging matrix
remains NOT_RUN and no live account message was sent in this continuation.

Two additional read-only diagnostics (profile config scan and socket/process
mapping) were refused before dispatch by the platform. They were not retried or
moved to another carrier; their facts remain unknown.

## Preserved gates / DO_NOT_REDO

#1001 targeted-carrier source remains draft; #962 plugin and #955 role-correct
transport/enrollment remain separate owners. Preserve #955's COO authority hold and
do not retry #633's unresolved DCR operation. Do not take over the dirty sibling
`claude-cross-app-dialogue-20260926-sol-001` writer or its untracked snapshot work.
Do not patch Parall wrapper binaries/plists while their profiles are running.
Do not terminate Claude 3/5/6 merely to obtain a test window.

## Exact continuation

Publish the current #1004 source head and invalidate the older head's CI as release
evidence. When any old Claude 3/5/6 profile is deliberately closed, use the guarded
adapter to launch that same isolated profile on the modern runtime, then prove
`ListAgents` visibility and one harmless correlated `SendMessage` round trip.
Only after the native carrier is proven profile-by-profile should the 12 directed
pair matrix be executed. Mastermind Company consultation integration then adds
admitted Wake/reply/consumption evidence where required.

Resume surface: Extra High for source integration and native host proof.
