# H1 + original host-pull collector: 100-member reviewable source composition

**State:** SOURCE-ONLY integration, not release, not selected, not installed, not a
provider/host qualification receipt. This is a *stacked* code-review input into
the original #1836 collector source; it is not a new native publisher, daemon,
readiness database, event queue, broker, or replacement for the H1/collector PRs.

## Pinned donors and protected law

- Protected law/parent: Mastermind protected `master@bb85b429f2ffffd38408080ce4df7d6378c34100` and compatible Sol Skillpack v1.0.1/bootstrap1.
- Original collector donor #1836:
  `9fb836d078f0c2167950a76598119802fb5fc0b9` — 97 native files,
  Draft, historical `CHANGES_REQUESTED`; the single native publisher,
  original launchd label, lock/CAS/rollback/EFFECT_UNKNOWN, fixed SSH
  stdin-spool/key guard, F1 strict-manual and R28 picker are preserved.
- Original H1 donor #1847:
  `0b0722d763a3a8185279abe693755891269d564a` — 98 native files,
  Draft, latest CI 40273452798 passed; formal independent APPROVED
  #5647947534 for *test-platform source only*, not live host qualification.
- Original accepted shared-hunk/manifest custody:
  `https://github.com/mastermindx-market-intelligence/Mastermind/pull/1836#issuecomment-6392825457`.
- M2 selected remains independent seq23
  `854dd5456c005f6385daecb6e93658025d59f94e496dd5f9374d7896d06eed87`
  (95 files); no selector or launchd command is issued by this PR.

## Exact 100-member closure

The new source stage is generated solely through the incumbent
`ops/native_fabric/quota_continuity/rollout/build_review_stage.py` and
canonical `native-source-inventory.json`, with explicit source paths and each
file's SHA256. The branch adds three H1-only members
`ext/paid_initializer.py`, `ext/paid_initializer_nested_data.py`, and
`ext/paid_initializer_token_data.py`, preserving the #1836-only
`ext/host_pull_daemon.sh` and `ext/host_pull_launchd.plist.template`.
The five conflicts are resolved as follows:

| Member | Rule |
| --- | --- |
| `ext/fabric_task.py` | Keep #1836's accepted F1+R28 postimage |
| `ext/pick.py` | Keep R28 fused SHA256 `4311200ae485ffd19b2560434e46c0c01899fbb58f0793c198292dba6004503b` |
| `pool` | Keep F1 source SHA256 `12602edd2f0bf3a5a789eb2b77043a1973bbed533ff35d307357e00be1531679` |
| `ext/paid_host_qualification.py` | Adopt exact H1 approved immutable source component SHA256 `e4cb143b13324bd5ce4d96af5396054b3c63e1b82c831edae4516f37e495a1b0` |
| `ext/host_pull.sh` | Preserve #1836 authenticated stdin-spooled fleet telemetry, H1 strict direct paid-qualification transport, and this reviewed finite mode join |

The three initializer file SHA256s are
`a0d8095c1e32f25449bfb27de062565956c118d3fffbcec2bf6cbed681c7b2ae`,
`47c476deedd42231206d528b656664c8b590414ea905ee2fe91571a90454d073`,
and `7a3e5d2642df12c48769490c6cb86301bad1843088bf2dae48181c7a307e2dfe`.
All 100 hashes must match actual source bytes. The old historical
`native_install.py` immutable 95-member/`UPGRADE_MANIFEST` epoch **is not**
modified or made to admit 100 files.

## One-collector finite qualification modes

The original `com.mastermind.host-pull` label, original publisher lock,
selector CAS and failure fencing remain the only runtime/service owners.
Its fixed plist ProgramArguments remain `lockf -t 0 <lock> /bin/bash
<verified-host_pull.sh>`, with **one additional literal closed suffix**
`--qualification-mode <off|physical-only|qualified-readiness>`, never arbitrary
caller executable/argv, second daemon, anonymous provider, or host override.
Installer render substitutes and SHA-verifies a single immutable template
and the same exact mode controls expected `launchctl/ps` argv. Unknown,
missing and duplicate modes refuse. Default `off` retains normal fleet
telemetry exactly; physical-only retains the existing normal whole-fleet
pass **plus a detached** bounded physical Ubuntu0 subpass using the existing
fixed read-only diagnostic transport, never writing account/provider
readiness from this subpass.

`qualified-readiness` is a deliberately **closed but held** literal mode.
The original `--paid-qualification ubuntu0` is an at-most-once DATA probe;
there is no accepted fresh per-pass canonical H1 parent/boot/source/host/
account/credential join for a recurring LaunchAgent yet. The parser and
original publisher **refuse rc78 before any remote/collector/selector effect**
if this mode is selected, rather than promoting a single-use <=60-second
token to recurring readiness. Its real source context/admission and
production proof are still owed; this PR does NOT claim qualification is
live or that it should be installed with this held mode.

## Acceptance / failure discriminators

- Rebuild from committed source in a new disposable external staging root;
  compare exact manifest and inventory bytes and hash every staged file.
- Run existing host-pull lifecycle, publisher, rollback, proof and H1 fixed-
  qualifier tests; preserve old 95-member historical importer refusal.
- Source-only mode tests: physical-only once in a scratch tree with a fake
  `perl` transport and fake backend; no host, network, state, credential,
  provider or launchd effect. Unknown/duplicate/qualified modes must refuse;
  no new `state/hosts/*.json` or PID file.
- Require current exact-head hosted CI and genuinely separate nonauthor
  GitHub review. Prior #1847/#1836 source approvals are component evidence,
  NOT a 100-member changed-risk review or a release permit.
- Do not make either original PR Ready, dismiss its review, merge, publish
  or select any native source until protected source/queue/admission, final
  qualified-context semantics, Studio consumer pins, original publisher
  preimages, physical host telemetry, and real non-Qwen worker proof all pass.

**Release classification:** source candidate can become independently reviewed
and CI green. `QUALIFIED_READINESS_LIVE` remains held until the existing
canonical H1 parent actually supplies a fresh authenticated per-pass
commitment, not a JSON file or claimed token.

## Hosted CI 40282712904 reconciliation — 100/95 source law remains distinct

All three pytest shards and required fan-in failed on initial integration
commit `04441f8cfacba075e8224a50d35317b654fcc496`.
Shard0: native-security current-stage SHA was still fixed to old 97-stage
`4897f593...` instead of new 100-stage `238d60fb...`.
Shard1: historical paired-upgrade source test removed only the old collector's
two later members, overlooking the three later H1 initializer members, so
the reverse-composed historical 95 manifest could not match the immutable
original importer; macro-result publication tests also pinned the prior
97-file *current* stage. The repair removes all five only in the disposable
historical fixture and updates the current-stage count independently.
Shard2: the previously approved H1 diagnostics plugin
`scripts/ci_pytest_timing.py` was unintentionally omitted from this
integration donor, despite tests importing its allowlisted, privacy-safe
failure annotations. Restored exact #1847 donor bytes SHA256
`2d7d726c3a99dfc6d90d964a6c0643ec071d7ddd86470ef8c3614173fc6dc972`.
H1 native extension fixture now checks exactly five new member names and
exactly five changed member hashes, comparing retained 95 preimage with
current 100 source rather than erroneously demanding the earlier 98.
No production native_install, legacy `UPGRADE_MANIFEST`, ACL, token,
reviewer admission, or live publisher is changed.
The historical paired-upgrade fixture also restores its original
`paid_host_qualification.py` bytes (SHA256 `d2f5be14...`) from the
already retained and digest-checked f608 H1 preinitializer fixture, only
inside the disposable stage. This source-only inverse retains the original
95-member `native_install.UPGRADE_MANIFEST` and does not change the live
or current 100-member qualified-host implementation.

## Hidden real Linux Macro publisher child source assertion (discriminating)

A subsequent exact-head Ubuntu0 targeted macro publication test reached
the sealed 100-file source successfully, then its fresh child process
refused on its own stale `CHILD` `RELEASE.json` count==97 assertion.
The same module had a 97 count in its generation-B fixture used for
source-switch/continued result-retention proof. Both are now asserted
as exactly 100; only source/test fixture counts and prose changed. The
original binary-alias/retained-result/second-generation scenario remains
mandatory, not removed, skipped or relabeled green. No publisher, reader,
account, identity or selected-generation implementation was changed.

## Subsequent correction — physical reachability versus optional readiness (2026-10-26)

A later read-only #1836/#1879 source census established that the single legacy
shell used the optional readiness tail's exit status to mark all physical
telemetry unreachable. The existing parser also rejected transport-zero with
nonzero optional readiness. The corrected **source candidate**, not a native
rollout, returns physical-stage status, validates complete ordered framing,
and withholds every provider/account readiness field on an optional failure.
Missing physical fields, malformed/incomplete stages, or nonzero transport
remain non-reachable. No second transport, collector, publisher, credential,
selector or recurring H1 producer is introduced; qualified-readiness remains
rc78 before remote/state effects. These source changes require new exact-head
hosted CI and fresh nonauthor review before any source admission.

Updated 100-member manifest SHA256: `50a7ff3e78e8022d0d86af8bc3622cc0d607e2be976b8758d8c44a91c2508a45`.
Updated source inventory SHA256: `e76374948a190bdcea5fe6f33b6499a603fdbbd986d7264807d790e5a49cfd4a`.
Historical earlier hashes in this note describe earlier immutable commits.
