# Successor of an unstarted migration preparation

This finite maintenance mode handles one completed, sealed sixteen-origin v5-to-v7 preparation whose migration executor remains correct, while a different sealed release is required for subsequent installation and acceptance. It neither reruns migration nor replaces the original preparation. It grants no live action permission.

The original selected release, original v5 prestate, migration executor P, and new reader/acceptance release R have separate identities. All four actual migration receipts must identify P. The new running source must independently prove R. Existing INITIAL and historical APIs retain their original semantics.

## Eligibility and preparation

Use the normal Root maintenance CLI from the actual sealed R release with the existing prepare action, predecessor, successor R, root Job and terminal-carry arguments, and these two exclusive selectors:

```
--supersede-unstarted-migration-preparation-sha P
--superseded-migration-preparation-descriptor-sha256 D
```

D is the canonical digest of the genuine issued P descriptor. P must be an intact, unstarted `supersede_unstarted_preproof_v5_to_v7` preparation with exactly its eight expected files and the closed sixteen-origin spent-ctime material. No recursive prepared-successor parent is accepted. The target R must differ from P, the original selected release and the predecessor, and be absent. Existing private preparation residues refuse; they are retained for reconciliation.

The qualified Root config must still be byte-for-byte the original source-control preimage sealed by P, with its original selected release. Require disarmed control, closed worker harness, actual stopped Control/Worker/Relay predicates, and the existing canonical service lock. This does not require every host service absent; MCP may remain running under the incumbent stopped-readside contract. Source qualification is not service or controller settlement.

The owner revalidates the complete original selected/deeper lineage, terminal/root/grant/quota bindings, selected v5 full content including sequence and migration timestamps, current v7 INITIAL physical and semantic evidence, exact preservation inventory and canary, and both release seals. The new helper `open_prepared_successor_v5_to_v7_evidence` performs current INITIAL checks, never a historical fallback. Its returned material remains identical to P's original sixteen-origin material.

The new closed descriptor adds only `superseded_unstarted_migration_preparation_sha` and `superseded_migration_preparation_descriptor_sha256` to the existing migration descriptor. Every prior field except schema and successor is preserved. All six sealed payload files are copied as exact bytes; only the new descriptor and preparing marker differ. The original P bundle and all migration origins remain unchanged. No PASS is credited to P.

The new candidate is private until full final requalification, retained FD/name/namespace checks, source seal checks, and normal atomic rename. Failure retains the private candidate; it is not automatically deleted or retried. These checks operate under exclusive administrative Root custody and do not constitute a global lock against a competing Root writer.

## Selection, admission and proof

After separately qualified normal installation and config selection of R, the existing acceptance entry uses R's new descriptor and expected digest. Normal installation/selection is not performed by this mode. Admission holds the canonical service lock through strict INITIAL checks and publication of the exclusive run marker, then releases it before Service startup. Both sources and the unchanged, unstarted P preparation are rechecked at that boundary.

The new R run owns its actual proof Jobs, backup/restore evidence, PASS summary and carry. Existing v7 preservation, genuine restore-receipt checks and running-Service-safe historical validation remain in force. Finish and future carry retain the migration executor P and original sixteen origins; they do not require live raw database bytes to remain equal to the initial C67 database while heartbeat/WAL activity occurs. P receives no run marker, summary or carry from R's run.

## Offline qualification and limits

`tests/test_executive_prepared_migration_successor.py` exercises actual Root issuance, Control continuation, ordinary v6-to-v7 migration, the sixteen-origin helper, P preparation, distinct R preparation/admission, real Runtime proof and backup/restore producers, finish during a held Service lock and WAL heartbeat, and future carry after unrelated work. It also checks both old INITIAL forms still refuse this two-release case, immutable parent/origin bytes, initial and late refusal cases, and absence of a new run marker after late admission drift.

Fixtures use disposable databases and explicitly inherited host-principal/native-ACL/ancestor/source-seal/sensor and accepted-ancestor/assignment inputs. These seams do not establish live host eligibility or actual installed source identity. Local interpreter/SQLite versions are recorded in the source return; the live binary hash and exact patch/SQLite fidelity remain separate facts. No fixture result authorizes descriptor issuance, configuration, migration, service startup, readiness, credentials or canary use.
