# O4: installed Web-observation owner wiring

Date: 2026-11-06 (America/Vancouver).
Operation: `chatgpt-web-observation-owner-20261106-c2`.
Source base: `615146aac6a1b0c0933bc9b815517a2fd285ed4a`.
Existing programme: WS:CHAIRMAN-CONTROL-ROOM / SC1, not a new workstream.
Parent master plan: [v1.2 source](https://github.com/mastermindx-market-intelligence/Mastermind/blob/0545e8a374e45a31f93505fe198f7a18ee5de1b6/docs/superpowers/plans/2026-11-06-chatgpt-session-observability.md).
Prior implementation: #2174 source-merged; #2179 O5 consumer in its original protected queue.

## Decision

Close the actual installed source route, not just provide unbound callbacks:
signed public MCP -> existing private Session Bridge/CeoIngress -> independently
authorized original profile-local C2 census -> existing bounded public projection.

The public MCP process must never directly impersonate a browser profile owner.
Its dedicated UID is 458; the standard Control template is UID450, while a
desktop browser ordinarily belongs to another user. Configuration does not
manufacture that physical channel. This source slice stays absent/default-off
and must fail dark unless the actual Control process is already the authorized
profile owner for the configured original C2 binding. Do not change HOME,
borrow another identity, relax a socket, add a broker, open a new port or use
SSH/browser fallback to bridge the mismatch.

## Bounded task tree

| Leaf | Existing owner | Acceptance |
|---|---|---|
| O4A | Sealed Executive MCP installation | Closed optional source/permission block; exact policy/issuer/resource/subject/client; one explicitly selected profile; no grants by default; explicit generation plus file-instance readback |
| O4B | Existing private Session Bridge | One closed READ-only census operation; no caller-selected source, socket, path, grant or credential; pre/post independent authority checks |
| O4C | Original profile-local C2 owner | Resolve the existing navigation binding, independently verify the granted adapter and actual process UID, retain original nonce/deadline/receipt checks; no changes to #836-owned client/extension/protocol |
| O4D | Current network/Control constructors | Consume the real permission/private-read adapters; actual signed HTTP -> private handler -> C2/native synthetic fixture proof; default inventory unchanged; no live activation |

Freeze source coordinates, authentication policy and transport credentials for
the installed process. Only the same owner's permission projection may rotate.
Include an explicit owner generation and the sealed file-instance identity in
the ephemeral scope revision so a revoke/regrant or atomic file replacement
cannot silently revive an in-flight old read. Missing/changed/unavailable owner
state refuses; no caches, retries or alternate sources.

Only a single profile-local source is in this vertical. #546's broader fleet
collector/cache is not implemented or replaced. The observation remains normal
open ChatGPT tabs in one explicitly enrolled profile, not all account history,
transcripts, hidden reasoning, registered targets or permission to control them.

## Source and writer fences

- Do not modify #836's Web-Sol client, protocol, native host, extension or Wake
  continuation paths, and do not repeat a historical browser refusal.
- #2178 owns `integrations/executive_mcp/installed.py` and the adopted Agent OS
  receiver. Do not wire `session_continuity_read` through a filesystem bypass.
- #2172 owns the disabled Hermes Executive/Paper MCP consumer. Do not widen its
  fixed allowlist or change installed role settings.
- #2109 owns `control_plane/executive_service.py`; its existing nominal
  SessionBridgeIngressOwner dispatch already suffices and needs no edit.
- #2134/#1966 are source-merged; their earlier runtime-specific holds are not a
  blanket source-work prohibition. Their installation claims remain separate.

## Verification and completion boundary

Use synthetic owner records, temporary sockets/profiles and genuine protocol/
authentication handlers. Assert no source access before permission, no network
process browser read, UID mismatch refusal, exact source join, stale/changed
navigation binding, no foreign account inference, expiry/revocation, same-policy
different-client refusal, strict closed arguments and bounded receipts.
Prove old private tools and default V3 inventory remain unchanged.

Main retains the source/authority seam and acceptance judgment. A native
read-only architectural critique informed the boundary; it is neither an
implementation worker nor formal approval. No current Fabric START or live
profile enrollment is claimed.

After source and required CI are qualified, release through the existing
protected controller. Actual Meta-CEO/Secretary role grants and a qualified
profile-owner channel remain separately evidenced installed acceptance. Do not
declare live session visibility or complete account control from source tests.

## Implementation and installed-state checkpoint

The source route is implemented on the declared branch, including the actual network and
Control factory compositions. The former C2/native owner is consumed unchanged. The new
[installation contract](../../hermes/CHATGPT_SESSION_OBSERVATION_INSTALL.md) records the
exact optional fields, physical-owner requirement, budgets, rollback and unproven live gates.

Red-first: all three new seam tests failed at the base because the private READ operation,
permission owner and installed composition did not exist. The current dedicated candidate
has 91 new owner/transport cases. Its signed HTTP proof traverses the actual Control factory,
private CeoIngress socket, Python C2 client/native host and Node collector using synthetic
browser APIs, then revokes the real test installation after collection to prove withholding.

A read-only architectural critique found a late-start cancellation flaw in the first candidate:
preflight could consume the carrier budget before starting a fresh native window. The repair
captures one monotonic deadline before thread dispatch, passes a request-local cancellation
fence, clamps the native expiry to the remaining original budget and refuses late release.
Stalled-preflight, spent-budget and cancellation-before-native regressions now pass. This
critique is not a formal GitHub approval and did not mutate or access a live browser.

Read-only installed check: the existing M2 root-owned Executive MCP configuration is at
`b4a5a8925c6c1412dac67ba296cf65ee81c4d4c8`, service UID458, `web_ceo_v3`, with Workspace
configured and no `session_web_observation` block. It was not changed. Publishing this
candidate therefore cannot be described as live visibility or role enrollment.

Current leadership-consumer PR #2179 remains in its original protected queue (entry
`MQE_lQDOTotz3c8AAAABNdX48M4ABAiKzgPMVzw`, last read AWAITING_CHECKS at position5).
Macro #10817's controller-integrated head `82b9654f590ee7a9db034fa34cd62cc1733f073d` has
SUCCESS for CI42336448189 and fences42336448378; its original controller effect is preserved.
These are timestamped phase observations, not standing future-state claims.

Next installed acceptance remains O4/O7: qualify the original profile-owning process/channel;
adopt the merged candidate through the existing sealed installation owner; independently
grant the actual Meta-CEO/Secretary principals; prove both role reads on two explicitly
enrolled sessions. No role name, old account memory or navigation binding can substitute for
those grants. The current working GLM leadership services and OMH memory owner stay intact.

### Final local proof for this source candidate

After the deadline/cancellation repair, the exact focused regression invocation below
returned **416 passed, 15 subtests passed, 0 skipped in 38.82 seconds** on the existing
native Python3.12 test environment. Of those, 91 are the new owner/installed transport cases.
The temporary test dependency directory is an already-prepared fixture dependency location,
not a runtime installation or credential source.

```sh
PYTHONPATH='/tmp/mmx-session-observe-testdeps.0NflAu:.' \
  /Users/chriswong/.venvs/mastermind-workbench-action-c1/bin/python \
  -m pytest -o addopts='' -q \
  tests/test_session_web_observation_installed.py \
  tests/test_session_web_observation_installed_asgi.py \
  tests/test_session_web_observation.py tests/test_session_web_observation_asgi.py \
  tests/test_session_bridge_installed.py tests/test_executive_mcp_entry.py \
  tests/test_executive_mcp_session_entry.py tests/test_executive_mcp_session_install_profile.py \
  tests/test_executive_mcp_web_ceo_v3.py \
  tests/test_executive_mcp_installed_fabric_composition.py \
  tests/test_web_sol_native_census.py tests/test_web_sol_fleet_transport.py \
  tests/test_c1_ceo_ingress_composition.py --tb=short
```

The original baseline's three missing-seam failures are distinct from two test-harness
iterations: the new ASGI fixture initially supplied a float clock to an authenticator that
requires integer epoch seconds. Correcting the fixture to the incumbent clock contract
made the full signed/native path pass; production authentication was not weakened.
Hosted exact-head CI, protected release and installed-role acceptance remain separate
receipts, to be recorded on the source PR rather than inferred from this local result.
