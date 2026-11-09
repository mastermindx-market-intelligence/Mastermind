# FABRIC R28 gen22 picker-only interim — source provenance and release gate

Status: SOURCE_ONLY_NOT_PUBLISHED_NOT_SELECTED. This is an input to the incumbent native_generation.py publisher; it creates no competing publisher, queue, watcher or installed adapter.

## Exact identities

- Protected merged R28 source: master fbb0c69818edeb4217cdc1b2f353df2f00cd70fc (#1797); reviewed picker SHA256 4008caca8c6a0e2145e7cb90965740ce24445e3300a8e3693d7a96130df236df.
- Sealed installed M2 gen22 baseline: ac9acf0daf5a438934f3862afa02039734aa100812d4e040eda5966388817c3b; baseline picker SHA256 9bbb96c8da84e38bbd802fdd373a0e8ba386395abc5a80bc8628b49d5afd8174.
- Exact fused F1+R28 two-hunk picker: 4311200ae485ffd19b2560434e46c0c01899fbb58f0793c198292dba6004503b.
- Candidate descriptor: 854dd5456c005f6385daecb6e93658025d59f94e496dd5f9374d7896d06eed87; NOT published or selected.
- Native source manifest: 95 members / exactly 94 unchanged from verified immutable gen22; manifest SHA256 158d5feaa7372bec25c588675f0073b30cce95570717a6a4a812b6a6886f3328.

## Source-law boundary

Baseline preservation derives from the incumbent previously sealed selected generation, not a blind reimport of current protected master. The new judgment-routing hunks come from the exact protected merged #1797 Git object. A blind reimport of protected 95 would revert the selected F1 fabric_task, host_pull and pool images. This new release requires independent source review and protected merge before it becomes an approved publication input.

## Source-only staging and existing publisher

From a repo checkout containing the pinned protected source, run from ops/native_fabric/quota_continuity/rollout:

    python3 -m unittest -v test_r28_interim_gen22.py
    python3 r28_interim_gen22.py --store /Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/native-code-releases --output /private/tmp/FRESH-EXTERNAL-SOURCE-STAGE

The stage helper checks gen22 CURRENT, uses the existing native_generation.verify for source authenticity, checks protected Git source, enforces two unique hunks, SHA-checks each of the 95 staged files, and produces native-code-stage/, native-manifest.json and STAGE_RECEIPT.json OUTSIDE the installed kit. It never calls publish, select, changes launcher pins, restarts launchd, leases workers, reads credentials or attempts provider admission.

After genuine non-author approval, green head and protected merge-group CI, original-publisher ownership/preimage and Studio consumer-pin gates, the incumbent native_generation.py publish may consume the already sealed native-code-stage and native-manifest.json with existing --source/--stable-ext/--manifest flags; CAS selection may then use --expect ac9acf0... only after fresh CURRENT reconciliation. The source-only PR does not itself authorize these effects. Failing preimages require new source review, not forced select.

## Proof completed before PR

- 12 hermetic unit tests green: manifest completeness, protected Git review anchor, two-hunk uniqueness and positive/negative derivation, 94-member preservation, membership drift, unreviewed provenance, unsafe stage destinations.
- Actual M2 stage succeeded with 95 sealed files; readback picker 4311200a... and manifest 158d5fea...; selected CURRENT remained seq22/ac9acf0d.
- Original native_generation.publish and verify succeeded in an isolated disposable fake kit with no CURRENT selected; no production native release publication or selection occurred.
- Studio launcher has 10 pre-existing pin mismatches; any changed ingress needs the incumbent consumer publication owner. Draft #1836 97-member collector and H1 #1847 100-member union remain separate approval gates.
- The original refused MANUAL_ROUTE_UNAVAILABLE worker call has retry_allowed=false: do not replay; after verified install and qualification use a genuinely NEW run ID for review.

## Independent reviewer request

Review exact source provenance, protected two-hunk anchoring, 94-member immutable preservation, complete 95 hash manifest and descriptor, fail-closed path/identity checks, and no production effects. Return an actual formal GitHub APPROVE or REQUEST_CHANGES; a comment or passing CI alone is not release approval.
