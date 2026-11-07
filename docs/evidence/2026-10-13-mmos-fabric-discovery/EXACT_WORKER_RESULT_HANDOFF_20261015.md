# Mastermind OS Fabric — exact indexed worker return navigation

**Source state:** developed in the existing Draft/Hold Fabric Discovery PR #1426, based on `411535d60843274bf3cbf58ea55c116fd477befc`. This is an app-side consumer extension, not a new backend, issuer permission, worker controller or production release.

## Capability

The Meta-CEO Mission inspector can now expose **Inspect indexed result** for a selected worker only when all of these source facts are simultaneously true: the supplied Mission is a CURRENT v3 owner observation, the root is resolved and unique, the selected ChildCard belongs to a qualified, displayed root-associated row, the selected latest Attempt explicitly has a returned result, the Mission result-reference index is SAME/AVAILABLE or SAME/PARTIAL under its owner snapshot, and exactly one sealed result index entry matches that job, attempt and available role.

The UI constructs the existing five-field `ResultSelection` exclusively from that exact index entry; it does not guess URLs, result names, digests, or use a direct M2 machine credential. On an explicit click, the current App owner checks that the authenticated `MissionHost`, its generation, the actual signed-in acquisition principal, selected project/workstream, current Office source, Mission v3 observation digest/generation and exact result index entry still match. Only then does it open `Projects → Overview` using the **existing** `pickResult`/`readResult` source and its original authorization, cancellation and response decoders. No source content is read before the explicit click.

Latest returned and current attempts stay distinct. The index labels returned references **UNVALIDATED**; content availability is not product acceptance. An exact reference without a mounted result reader is labelled differently from a genuinely missing reference, preserving source missingness. Root conflicts, unassociated/off-cap workers, stale source/owner observations, unmatched attempts/roles and duplicate pointers cannot construct the action. English and zh-CN copy is supplied by the existing UI theme/locale.

## Verification status

Red-first negative fixtures were added for the missing feature and adjusted to the existing strict source contracts. Focused helper, inspector, Office and full App-route tests pass. The App-route negative cases demonstrate that a host generation change or loss of acquisition permission **between display and click** produces zero result reads. No legacy fallback reader is invoked. Frozen source proof: 1,513 tests passed, one skipped, zero failed in 67 app files. TypeScript and Vite production build passed, with existing large chunk and Tauri mixed-import warnings. These are source tests, not live authenticated app or production browser acceptance.

## Remaining product gates

Direct attended M2 run discovery still requires the existing OS/Executive principal-to-original-run membership source and pre/post permission stamps. The C3 gateway/tunnel's machine-owner access is not an OS end-user grant. #1426 remains Draft/Hold with protected CI, independent review and production browser proof obligations. Fleet Health #1425 and Mission after-cap repair #1435 retain their independent source owners; do not overwrite their pending composition. The prior platform refusal on protected-base source update, backend shared-contract changes, reviewer dispatch and browser qualification is preserved. No reader installation, token, provider worker, automatic merge or deployment is claimed.
