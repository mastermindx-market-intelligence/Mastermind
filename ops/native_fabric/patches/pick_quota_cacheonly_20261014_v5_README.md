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


### October 15 10:44 UTC — newer-picker isolated full integration

The newer installed M2 picker `0f5cbc32504680e09055b77cffdea81adea734388b7b061fcf77d017b7715cb2`
is **not** byte-identical to V5's original pin, but the existing four
V5 picker hunks apply with `patch --fuzz=0` and produce
`dbdd1ada7e4933acf36f6c2e7b32b0c546126c30e6603f32f3784b0daf98fb1e`.
A fresh `difflib.unified_diff` against the latest live picker yields a
**byte-identical 40-line picker section** (SHA-256
`fc631a26b9e00af51245468ac82c3d0811914a4cf29ae2f57b0a64861ace5b0c`),
so no redundant rebase commit is warranted. The complete reset-corrected
12-file V5 patch applied with zero fuzz to isolated exact current copies of
picker, quota, ledger and five original tests; all four new tests were created.
All staged Python compiled. The three source postimage SHA-256s:
picker `dbdd1ada7e4933acf36f6c2e7b32b0c546126c30e6603f32f3784b0daf98fb1e`;
quota `06a10fecbc60ed30d43bcfd933d2aea0dbf234f32c16f8a2c65ce2da95648e8c`;
ledger `07970a0859557dcaa77b9133c1f7edc4a363fd1281f82cc8f5141304a1fd811c`.

An initial hermetic test attempt could not import the staged dependency
`test_placement_view` and, once importable, lacked the staged
`orch/fabric/pools.yaml`; those were **fixture construction failures**, not
V5 routing regressions. After adding only current policy/host snapshots to
the isolated stage and the original sibling test search path, all **269
relevant staged routing tests PASSED** in 6.41 seconds (one unrelated pytest
garbage-collection warning regarding a different private browser fixture).
Exact logs: `~/.mastermind/agent-evidence/fabric-advisory-reset-v5-20261015/full-current-v5-scoped-tests-v3.log`,
with staged 12-source application receipt `full-current-stage-receipt.json`.
This supersedes the prior untested newer-picker *composition* assumption,
not the hard production preimage/source-owner/review/CI gate. The other 104
original V5 scoped regressions have not been claimed rerun by this phase.
There were **no live router/provider/broker/host/lease changes**.

**Still DRAFT / NOT INSTALLED:** Preserve current source independently,
approve exact updated live-source preimage and full qualified support bundle,
obtain full CI and independent review, and prove an original routed accepted
worker/result before production acceptance. The denied V8 installation
remains untouched.


### October 15 10:48 UTC — additional physical-admission compatibility

In the same isolated full-current-source stage, nine original host,
placement, Intel/AMD physical-temperature and remote selection test modules
were exercised against the revised V5 source. The first pass had exactly
one **test-fixture missing-file** issue: the stage omitted the current original
`remote_sub.sh`. A byte-identical copy of installed reviewed launcher
SHA-256 `fdb50974e37852c8024135ddf4bf021e6c6a67d1a0418cd5675cc24dc4ad5a17`
was added *to the isolated test stage only*. Rerunning the nine affected
modules gave **114 passed, zero failed** in 1.75 seconds. Combined with
the separate 269-pass router suite, this is **383 passing cases across two
non-overlapping suites** on the revised full-source candidate, in addition
to eight isolated reset-age/expiry checks. One unrelated pytest old-browser
temporary-cleanup warning does not change those results. Log:
`~/.mastermind/agent-evidence/fabric-advisory-reset-v5-20261015/full-current-v5-host-policy-extra-v2.log`.

These tests do **not** imply current hosted CI success, real provider latency,
qualified runtime support publication, deployment or CPU-heavy concurrency
acceptance. V5 remains DRAFT, original M2 production code unchanged.
