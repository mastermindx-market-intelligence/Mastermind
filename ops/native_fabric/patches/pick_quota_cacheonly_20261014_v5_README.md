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
