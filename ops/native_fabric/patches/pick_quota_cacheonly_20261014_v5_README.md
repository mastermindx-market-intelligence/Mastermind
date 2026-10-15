# Fabric V5 - nonblocking quota advice rebased to current live M2 router

Status: BUILT_NOT_PROVEN / SOURCE ONLY / NOT INSTALLED. Source/host authority is
the existing Mastermind support publisher and broker, never this patch.

## Machine capability
Advisory MiniMax/GLM ranking uses only fresh, complete cache observations.
No provider HTTP quota refresh or GLM window-file write occurs during picker
selection. The explicit refresh readers and atomic account/host admission are
unchanged. Unknown account state cannot make ALL GLM accounts appear exhausted,
and future/stale quota dates never claim provider-authoritative urgency.
The current live M2 GLM model-to-host account join, Grok/Cursor alias rules,
reviewer restrictions, MiniMax catch-up rules, and broker gate are preserved.

## Preimages and diff
Existing source preimages must be checked before any proposed installation.
Core live preimages (SHA256):
* pick.py: 3120d99aa3bc4c9224b61ab3d593c284dcc11f4a2df0e657f401125b2651f188
* quota_remote.py: a1dab11da10264836e6271955b375b8e6508c23f23d0444c99d96464deb70f2b
* pool_ledger.py: 85d40296487f1f040ef3597b8110966e36a9b6ebee781e05a5e6172b8610d78e
Only these three incumbent code files, five fixture/test files and four new
adversarial test modules are changed/added in the patch. Provider keys,
accounts.yaml, live lease state and host registry are NOT bundled or altered.

## Verification
M2 Python3.14 core: 227 passed in v5-combined2.log.
M2 Python3.14 additional placement, host and MiniMax window: 104 passed
in v5-scoped-expanded.log (331 distinct qualified tests). No test exclusion
in either scoped suite. Additional exploratory historical tests have baseline
fixture/import/capacity incompatibilities and are not claimed as green.
A retained earlier picker call took 76.10s before cache-only changes; the
source test simulates blocked remote quota to prove picker independence.
No actual installed-path latency improvement is claimed.

## CI identity-scan compatibility
The two unrelated synthetic cache ages that previously resembled peer UIDs
are represented as FRESH_S-based expressions, preserving test semantics.
The identity-protection scanner must remain enabled, with a real CI receipt.

## Unfinished production requirements
Draft for independently reviewed source integration only. Source-writer
custody, exact preimage, current protected baseline, full support-generation
closure, reviewer approval, publisher permission and actual worker execution
must be proven separately. Current M2 controller host caps are conservative
and currently differ from the installed remote static registries; this patch
does not touch physical host limits or free disk admission.
The separate V8 Ubuntu elastic physical max installation is HELD_PLATFORM_REFUSAL
under original effect fabric-ubuntu-elastic-max-20261010-web-003. This source
proposal never retries or broadens that denied release.


## October 15 reset-window correction (source-only)
Current V5 source patch now incorporates the reset-window semantic correction
from independent routing PR #1443 at the existing `ext/quota_remote.py`
`_advisory_fresh_states` boundary. A recently observed, provider-authoritative
quota row with a present expired/equal/malformed `reset_at` is UNKNOWN, not a
continuing PARKED or asserted OK allowance after reset. Missing reset metadata
retains the original compatibility contract. This changes advisory ranking
only; hard provider account admission, explicit refreshes and live ledger/
broker are unchanged.

Exact evidence: previous V5 patch Git blob
`fb853e50690f1c1bf538aa1500f100a5198677dd`, revised patch Git blob
`d34b6b15bf7ab074d911d3d05128e2cbf1f74100`, deterministic revised
patch SHA-256 `6b368b720ded00ce6dddcbd02195163777ead91c2644cf82b0c2c4c68ef4cd52`.
The isolated exact quota preimage `a1dab11da10264836e6271955b375b8e6508c23f23d0444c99d96464deb70f2b`
replays with `patch --fuzz=0` through prior V5 postimage
`42f3a5f9b4d820ab5fafd9b739944a685dab4ebe254fb9c190f9ab75129ebfab`
to the independent #1443 tested reset-aware postimage
`06a10fecbc60ed30d43bcfd933d2aea0dbf234f32c16f8a2c65ce2da95648e8c`.
Eight additional isolated AST/case checks passed; #1443's independent
25-case original test suite is existing supporting evidence, not a claimed
new CI result on this PR's complete source package. Stage receipt:
`~/.mastermind/agent-evidence/fabric-advisory-reset-v5-20261015/integration-receipt.json`.

**Release hold remains.** At 2026-10-15 10:35 UTC, M2 installed
`ext/pick.py` was `0f5cbc32504680e09055b77cffdea81adea734388b7b061fcf77d017b7715cb2`,
not this V5's pinned `3120d99aa3bc4c9224b61ab3d593c284dcc11f4a2df0e657f401125b2651f188`.
The installed quota reader and pool ledger still matched original preimages.
**Never overlay the full V5 patch on a drifting picker**; the complete
current-live picker + quota + ledger composition, source-writer custody,
full compatibility suite, hosted CI on exact head, independent review,
support-generation publication, placement and worker acceptance remain
unproven. The earlier 331-pass suites and sealed archive qualify the
previous V5 patch, not an installed reset-aware release. Current protected
`master` has already corrected the unrelated Research Read CI test; the
previous red #1441 run is not a new pass. This PR stays DRAFT and uninstalled.

No Ubuntu capacity configuration, CPU cutoff, workers, provider quota,
lease, host profile or other V8 physical install was touched. The original
elastic V8 effect remains HELD_PLATFORM_REFUSAL / DO_NOT_RETRY.
