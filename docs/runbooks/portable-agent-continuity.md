# Portable agent continuity — bounded operating runbook

Status: **candidate source capability; production HOLD**. Parent: existing Operator Continuity & Realm Rebinding / WS:EXECUTIVE-CAPACITY-FABRIC. This runbook creates no admission, credential, source lease, new lifecycle, or automatic recovery service.

## Select the recovery path

**Native recovery:** use the existing provider adapter and Operator Harness only when the same accepted realm/session and current native-resume predicates permit it. The owner must establish the exact old process is dead, its writer is released, the lease and generation are current, and effects are reconciled. A disconnected browser stream or failed tool response is not death or effect clearance. Preserve the existing Attempt only where current Harness law allows it.

**Portable continuation:** a provider/account/realm change requires the existing Executive lifecycle to establish a new Attempt under the same logical Job, after reconciling its predecessor. Model Router / Capacity Fabric select only eligible destinations. Launch a fresh native session through the accepted adapter. This patch does not select, claim, launch, requeue, or authorize any destination.

**Fresh Web conversation:** recover a compact verified checkpoint and current AgentOS references in one successor. Manual handoff is distinct from automated browser creation/binding/wake; a capsule does not provide browser authority. No automatic Web succession is accepted by this patch.

## PREPARE and ACK at the trusted seam

The attempt-bound `ExecutiveOperatorHarnessPort` exposes `prepare_operator_continuation(attempt_id, draft)` and `acknowledge_operator_continuation(attempt_id, ack)`. These are internal Runtime methods, not newly published external tools. The port supplies its existing lease token and fence; no model supplies an authoritative timestamp, capsule identity, provider-account grant, or replacement lease.

1. Compile current source material through the accepted source-builder owner. PR #656 is still a held integration dependency; its missing/malformed Git-identity refusal tests are currently red. Do not feed an arbitrary model-authored mapping to production as a substitute.
2. PREPARE rechecks source/target identity, grant, current admitted binding, exact checkpoint-derived material and predecessor process/writer evidence in one existing SQLite transaction. Missing predecessor process evidence, unreleased writer/process state and operation `EFFECT_UNKNOWN` refuse. This conservative candidate does not interpret an unrelated later observation as reconciliation.
3. The Executive clock finalizes one immutable capsule. Command identity is `operator-continuation:prepare:<target-attempt-id>`. `OPERATOR_CONTINUATION_PREPARED` stores the full bounded capsule plus semantic digest and exact epoch/provider-session binding in the existing Events table. There is no capsule file, cache, queue or second database.
4. Same-semantic replay returns the same bytes and identity. A different draft, provider session, epoch, capsule, command owner or event identity conflicts. External source movement never silently edits an existing capsule.
5. Deliver exactly that prepared capsule through the already-admitted continuation-bearing turn. Lost delivery response requires reconciliation of that original operation; it is not permission to dispatch again or prepare a replacement. This patch adds neither delivery nor an uncertain-effect reconciliation writer.
6. After exact consumption evidence, ACK binds the target Attempt, capsule digest and current provider session. `operator-continuation:ack:<target-attempt-id>` creates one `OPERATOR_CONTINUATION_ACKNOWLEDGED` Event. It does not complete the Job, acknowledge Wake, or certify that a useful result was returned.
7. Demonstrate useful successor work and its return through the original Job/dialogue. Acceptance is owed until this real path is observed.

For V1 automatic quota rollover, an empty Git diff does not make a write-capable Attempt non-modifying. The existing canonical `NON_MODIFYING_ATTEMPT` rule remains unchanged. Arbitrary write-capable migration is not authorized.

## Honest context loading

AgentOS organizational memory, task-local checkpoint context, provider-native state and runtime authority are separate. Retrieved summaries never grant permissions. Use source revisions and immutable artifact references; omit secrets, credentials, raw provider transcripts and unnecessary personal information.

The pinned Macro compiler at `cdbcd143dcfa419ab0637bc11dd4c80368143e2e` returned `context_bundle.v1` for `EXECUTIVE-CAPACITY-FABRIC` on 2026-10-09T03:16:29Z. It reported 18,363 estimated tokens against an 8,000-token request, 43 budget omissions, and missing active-builds/P0-grounding inputs. Its always-included workstream context dominates the result. This is a successful but degraded compilation, not an 8,000-token capsule or proven cold-successor journey. Do not silently truncate mandatory constraints or claim absent decisions/handoffs were loaded.

Bundle SHA-256: `26840ad9e6cd45ca36dcd73219fcf7b1a3640de7a5909e9716742d68f6398696`; source-records digest: `sha256:b11ce527e32220071b42918136c931d09b9edbd7d02a58c7541bbfb2f10a0350`. Retain these receipts and source refs, not the complete bundle in a second store. The compact Web frontier should stay near the current Session Reliability target of 12 KiB / 1,500 words where applicable.

## Provider capability and proof matrix

These rows distinguish inspected source capability, existing carrier-reported evidence and actual acceptance in this operation. They are not an eligibility registry and must not drive routing.

| Path / provider | Native resume source | Portable capsule / required tools | Cross-realm eligibility | Acceptance here |
|---|---|---|---|---|
| OpenAI Codex | Existing `codex_operator_adapter` and Harness path; targeted regression tests included | Candidate PREPARE/ACK uses current admitted OHF binding; exact source compiler, lease, tools and destination admission remain required | Must be independently admitted by current owners | Hermetic target admission and seeded predecessor-history tests only; no installed native or cross-provider canary |
| Claude / Fable | Existing `claude_operator_adapter` and native supervisor source | Same bounded capsule contract is provider-neutral, but inspected RuntimeBinding reasoning-surface mapping lacks Claude; qualified binding/adapter integration is not established | Not inferred from a subscription label or old worker slot | Native installed recovery and two-realm continuation NOT PROVEN here |
| GLM / MiniMax through existing local Fabric | Macro #8535 reports context/compaction wrapper hardening; this is evidence, not a new native-resume acceptance | Must use qualified adapter/tool envelope and current Executive admission; compaction does not replace a durable handoff | Existing owners only; not granted by this runbook | Latest qualified wrapper terminal receipt and native compaction firing remain unproven in that carrier |
| Grok through existing local Fabric | #8535 reports prior direct-dispatch test evidence and sampled Grok use of a support digest | No inspected complete portable continuation journey | Independently qualified route required | Dispatch evidence does not prove capsule consumption, native resume or Job-preserving succession |
| Astra/Sol Web | Native hidden/session state is not portable by this patch | Compact verified checkpoint plus AgentOS; separately admitted browser/session-target path for automation | Manual and automatic succession are different capabilities | No fresh-Web useful-action canary or automatic browser succession performed |

Macro #8535 was inspected at head `45d6d6038fab0c6ee0372f980594afd782e31663`, open draft. Its code-support digest is reported as `a811c5a16d7795a97c9bb639c7c4efb69c98ccf4676b11edbe9932e105be0de2`. Reported installation checks on two hosts do not establish fleet-wide adoption or latest GLM/MiniMax execution. Preserve its incumbent custody and safety holds.

## Installed-runtime canary: required evidence, not fabricated examples

Use the existing production release/admission owners after source integration, exact-head CI and independent review. Record actual values for: protected release and installed source SHAs; original Job, predecessor Attempt, successor Attempt; selected versus served model; provider/account realm identity and exact native session; source workspace revision; predecessor liveness/writer/effect reconciliation; lease/fence/generation; capsule semantic and content digests; PREPARE Event; exact first delivery receipt; ACK Event; useful tool action/result; parent/dialogue return and acceptance. Missing values mean NOT PROVEN. Do not populate this ledger with synthetic fixture IDs.

Run positive native-resume, cold recovery, non-modifying two-realm rollover, replay and successor-result-return canaries through admitted paths. Run adverse tests for unknown effects/liveness/writers, wrong account/workspace/tools, stale lease/binding, duplicate successors, changed/tampered/oversized context, lost delivery and login/quota failure. Require zero forbidden duplicate effects, not just an expected exception string.

## Release boundary and next owner actions

This source candidate must remain draft/held until the source-builder regression is repaired under #656 custody, the public two-Attempt lifecycle-to-delivery chain is integrated, required exact-head hosted CI passes and independent review returns. Installation, runtime selection, provider availability and production canaries are separately owed.

The observed installed Executive source differs from protected master. At 2026-10-09T03:09:45Z its read interface reported `ceo_submit_armed: false`; no submission, dispatch, provider session, or production configuration change was attempted here. The existing release/admission owner must supply a qualified execution path, not a workaround that bypasses that setting. A GitHub review request is not a started worker or completed review.
