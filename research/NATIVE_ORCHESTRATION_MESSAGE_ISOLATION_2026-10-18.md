# Native worker communication isolation: compiler parity repair

Status: SOURCE_ONLY / BUILT_NOT_PROVEN. No account, provider, service or runtime
was changed. This is a restrictive compiler repair, not a new messaging plane.
Base: e77631490e5bddca7d40c8cf039ae7763ce17b99.
Operation: orchestration-message-isolation-20261018-sol-001.

## Findings and repaired source
An attended-account communication restriction does not automatically survive
materialization of an isolated worker profile. The existing Codex native-helper
profile enabled multi_agent_v2 without disabling native direct messaging.
Its expected config/read projection and launch overrides now BOTH include
`disable_direct_message=true`. Spawning and automatic original-parent child
results remain enabled, the depth-one and one-helper ceilings are unchanged,
and no model/effort/permission/source ownership is widened. The existing
no-helper V3 projection's pinned digest is unchanged.

The finite one-parent Claude worker compiler already limits its tool set, but
outbound tool restriction does not itself reject native incoming peer messages.
Its closed --settings now includes `crossSessionInbound: refuse` and explicit
SendMessage/ListAgents denies. Its descriptor refuses a missing/widened inbound
setting or removed peer-tool deny. No attended Fable/Opus programme, native user
configuration or cross-project owner is reconfigured by this source patch.

## Vendor evidence
- OpenAI openai/codex commit 7b44ac1661433ae3a6f375fde873fa7123c935fe:
  codex-rs/features/src/feature_configs.rs and core/src/tools/spec_plan.rs
  define disable_direct_message and retain spawning/automatic child results.
- Claude Code documentation: https://code.claude.com/docs/en/cross-session-messaging
  documents recipient-side refuse separately from SendMessage/ListAgents tool
  permission. Native messaging is therefore not inherently isolated by model.

## Qualification actually performed
RED-first: three Codex profile tests failed on the protected predecessor.
RED-first: all seven Claude finite message-isolation tests failed on the
protected predecessor. After these source changes, 73 focused tests passed
with zero failures/errors/skips, covering both new suites, existing capability
profiles and the existing finite Claude launch preparation contract. Python
compilation and git diff --check passed. No real provider binary or worker was
launched; no live messaging was sent merely to prove a negative.

## Compatibility and release boundary
The Codex helper expected effective-config digest changes intentionally. The
finite Claude permission digest also changes because it includes these closed
settings. Old effective-policy/readiness receipts cannot attest the new policy.
Use the existing exact-binary/config/permission qualification and release owner,
not another attestation registry or additional human-approval form. An older CLI
that ignores or rejects a setting is unqualified; source tests do not prove
that any installed binary enforces these fields.

Keep independent source/security review, exact-head CI, current-source
integration and real exact-parent return qualification separate. Source-only
Sol-6.1 candidate PR 1266 must compose this same restriction if adopted; legacy
model aliases, reservations and provider-account admission remain unchanged.
The existing programme owner and all original uncertain operations retain their
identity. Do not revive retired coordinators or add periodic model-driven polls.

## Broader audit: existing owners, not replacement services
The existing consultation contract already restricts one peer, no forwarding,
no broadcast and a correlated answer. The wake router already ignores ordinary
heartbeat/quota events. The installed session bridge has exact target and
current-binding checks, but its target projection must also be evaluated against
the caller's actual project assignment; globally authenticated CEO access is
not automatically project-worker authority. This is a composition question,
not a demonstrated exploit or evidence that this bridge caused an incident.

Next consumer proof: the original native adapter materializes the closed
profile; supported config/read or effective policy confirms it; a legitimate
child completes and its actual parent consumes the result; no unrelated native
peer channel is exposed. Larger autonomous workflow promotion additionally
requires useful delivery, independent review, bounded repair and real product
acceptance through the existing Executive/Fabric lifecycle.

## Exact-head hosted W6B fixture compatibility repair — October 17 evening

Hosted PR CI run 39086979983 at original semantic head
\`cb1a1ef45a9b1e5e2cd942eca87945b4195e5ddd\` finished FAILURE:
pytest shard 0 failed exactly three \`tests/test_w6b_native_round_trip.py\`
cases. The checked-in W6B test fake projected \`multi_agent_v2\`
without the newly required \`disable_direct_message=true\` field, so
its expected security digest disagreed with the legitimately tightened
generated capability profile (\`89612a1... != c48a700...\`). After
repairing only the fixture's expected projection, two execution cases
also correctly refused \`REFUSE_CONFIG_DRIFT\`, because the fake
App Server's test-local sealed-config wrapper did not echo the new bit.

The candidate repair updates ONLY \`tests/test_w6b_native_round_trip.py\`:
a single \`disable_direct_message=true\` in the constant, and a
strictly test-local native-helper \`config/read\` echo for that field.
It does not modify the shared fake App Server implementation,
production native-helper configuration, session messaging permission,
default profile, auth, credential, Runtime, or Fabric.

This is an observed test-fixture convergence, **not weakening isolation**.
The original hosted failure is retained as RED evidence and cannot be
claimed green by review or repair alone. New focused M2 suite
\`tests/test_w6b_native_round_trip.py\` + three native capability/message
isolation suites **51/51 PASS**, Python compile and \`git diff --check\`
PASS. Exact successor head/CI follows publication; require fresh
hosted shard 0 plus all required checks and independent current-head
review. The actual on-host native App Server readback at Codex CLI
0.159.3 independently reported \`disable_direct_message=true\` and
verified private process-group cleanup; no provider turn or real
worker return was started. Preserve Fable original programme ownership,
unresolved CODEX-01/other effects, and live deny lists.
