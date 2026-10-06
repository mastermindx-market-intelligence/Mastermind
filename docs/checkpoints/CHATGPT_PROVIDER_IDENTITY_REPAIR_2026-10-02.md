# ChatGPT provider identity repair

Existing operation: `grok-chatgpt-provider-identity-20261002-sol-001`.
Existing PR: #1134; branch `sol/web-grok-chatgpt-provider-identity-20261002-sol-001`.
Parent mission: #1141 / #1143 exact-session interconnect. MISSION_COMPLETE: false.
Protected procedure pin: `bce27c289fc3802f34ca4a1ecad21d40f147b85c`.

## Custody and scope

The installed Studio mmx-workspace launcher reused the original web workspace,
base `ba5e8ed0a5d03efabeca745725da5c0c442d3b11`, candidate parent
`a23b40cfd907ba518006c122232ce3e52acbf4a0`, and original lock.
No committable preexisting dirt, cwd holder, index lock, merge or rebase was observed.
Ignored caches explain the CLI's PRESERVED_DIRTY label; they were preserved.
Only provider_identity.py, its test file and this checkpoint are changed.

## Behavioral repair

- A latestTurnId log observation may corroborate an already native-bound marker
  user. It cannot assign a missing native turn ID to that user. Missing causal
  identity refuses with provider_turn_join_native_id_unproven; the caller's
  original evidence remains EFFECT_UNKNOWN. An exact ordered reply may inherit
  the user-bound ID; conflicting native reply identity refuses.
- Native observation clocks use the existing turn clock validator and snapshot
  age/skew policy. Non-finite, unrepresentable, stale and future evidence refuses.
- Only exact info/logger/event envelopes are parsed. Required field and method
  values are exact; duplicate/conflicting fields and quoted field injection refuse.
  Outputs remain bounded and content-free.

## Verification

The unchanged owning identity/turn baseline passed before repair. Added regressions
reproduced 24 failures before the source change. The repaired identity and turn
suites pass 166 tests on Python 3.12, bytecode and pytest cache writes disabled.
git diff --check passes. These are source tests, not a native-provider journey.

## Acceptance boundary

Independent review of the new immutable head and hosted checks remain owed.
The stacked #1131 parent and #1136 resource remain separate candidates/owners.
A real native producer must attest the marker user's causal native ID; marker
text plus conversation recency is deliberately insufficient. No such new producer
is installed or claimed here. No GUI send, provider, credential, service, runtime,
summon, merge or deployment effect occurred.

Do not replay #1112's held source comparison or #991's uncertain canary.
Next: independently review this exact source delta, qualify the existing stack,
and only then pursue the permitted native producer/resource proof.
