# Experiential Max funding contract correction

## Problem

Experiential documents two different benefits:

- A promotional `:free` qualifier applies only when that organization has the
  corresponding free-tier grant.
- Models included on Pro, Max or Ultra use plain model IDs. Max includes
  7,000 credits per day. Usage beyond the allowance pauses unless
  **Continue on credits** is enabled.

The previous plan integration inferred promotional qualifiers from plain
catalog entries. Neither that inference nor an observed wallet establishes
Max included-funding enforcement.

Primary contracts:

- https://platform.experientiallabs.ai/llms.txt
- https://platform.experientiallabs.ai/docs/billing
- https://platform.experientiallabs.ai/docs/account-api
- https://platform.experientiallabs.ai/docs/errors

## Changed behavior

The existing plan policy maps the seven included models to their exact plain
IDs and original protocols. The two explicitly selected paid Flash Uncensored
models retain their existing prepaid-wallet admission and DeepSeek preference.
An included or refused request never falls through into that paid lane.

The current public account reader has no authoritative Max entitlement or
continuation-control readback. It therefore supplies no included-funding proof.
Included admission fails before dispatch, and AUTO excludes that candidate
before selecting an ordinary eligible route. The existing gateway independently
refuses included requests before RPM reservation or upstream transmission.
No environment flag, catalog entry, configured allowance or caller-supplied
Boolean can enable the included lane.

The pure funding predicate defines the facts an actual provider-account reader
must establish: the same organization, an active Max entitlement, all seven
included models, provider-enforced stopping with continuation disabled,
continued availability of independently requested paid Uncensored models,
and a fresh observation. Remaining included credits stay unknown.

HTTP 401 and 403 now have different terminal classifications. The transport
retains only a closed set of provider error codes, types and parameters, the
HTTP status and an existing shape-validated request handle. Arbitrary error
messages and response bodies do not enter exception text or terminal metadata.
The original provider outcome records this evidence. No error is retried,
and no historical outcome is rewritten.

## Validation and remaining acceptance

Focused tests cover the funding predicate, default gateway refusal before
upstream effects, exact model/protocol mappings, automatic-selection exclusion,
single-send error handling and bounded error redaction. Positive included
transport tests use explicitly identified fixture-only account evidence;
they do not establish production entitlement.

The native composer preserves the complete selected 116-file predecessor and
updates only source-owned dependencies through the existing publisher.

Production included-lane acceptance remains pending an authenticated provider
account/control readback. A successful plain-ID response, wallet balance or
green unit test cannot substitute for that funding evidence.

The focused six-module suite passed all 161 cases. A supplemental broader run
reported 493 passed, one skipped, and 19 historical overlay fixture failures
(five failures plus fourteen setup errors). Every failure was the old release
tree content-CAS mismatch: that fixture still binds a 75-file predecessor while
the current protected base contains 78 files. The on-disk tree and the unchanged
base commit's Git blobs have identical digests, establishing that this mismatch
predates this change. The current 116-file composer and local pipeline tests
passed. The historical release seal was not changed.

## Concurrent fixed-parent source qualifications

The remote-placement and maintenance-guard qualifications bind sequence 37.
Their tests now reconstruct that exact parent from the existing verified
predecessor fixture and an exact frozen copy of its protected profile. They
do not infer their parent from the latest default composer output. Original
parent/profile, patch, postimage and unchanged-payload assertions remain intact.
The sidecar source profiles and publication authority are unchanged.

After integrating the concurrent protected changes, all 197 focused tests passed,
including the fixed-parent router, maintenance-guard and sparse Git qualifications.
Their original hash and behavioral assertions remain enforced.


## CI composition repair

Required CI exposed the paired application test's explicit gateway Git-blob pin.
The pin now identifies the corrected gateway bytes, and the paired test executes
that actual source against CI's exact Macro owner commit. All 46 inference
composition cases passed, followed by eight buffered-delivery, five native-text,
and 24 translation composition cases. Browser qualification remains with the
required hosted job; no local browser result is claimed here.

The historical overlay fixture failures above are also resolved. A test-only
75-member map was derived from the original protected release and verified
against its unchanged content seal. Every original member remains byte-identical
in current source; the three later auxiliary files are outside that old release.
Tests now reconstruct the exact sealed parent before invoking the unchanged
production composer. All 53 historical bridge cases passed, including the
existing tampered-tree and moved-head refusals. No release manifest, production
CAS gate or runtime payload changed in this repair.
