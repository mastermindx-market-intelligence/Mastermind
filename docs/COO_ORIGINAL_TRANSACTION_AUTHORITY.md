# COO authority at the original write transaction

This source change repairs a reached selected-child claim failure. It changes
neither admission ownership nor the installed principal grants. Runtime still
owns the original claim, Attempt, completion, and explicit API-requester receipt.

## Observed defect

The authenticated joint API path reached a genuine current-C Mission, qualified
the installed COO source, and selected an actually admitted child. Its canonical
claim then held `BEGIN IMMEDIATE` while calling the final authority guard. That
guard opened another public Mission observation. The service namespace owner
attempted its own `BEGIN IMMEDIATE`, on a different connection, and refused after
its existing maximum 250 ms reservation budget. The Mission became PARTIAL in
that guard and immediately returned to CURRENT after the writer rolled back.

The original operation had no claim Event or Attempt. Its result was
`REFUSED / EXECUTIVE_SELECTED_CHILD_CLAIM_REFUSED`; the correction must not turn
that refusal into a retry, extend its timeout, or treat preflight Mission data
as authority for commit. The original diagnostic is retained separately at
`/tmp/estate-joint-service-refusal-diagnostic-20261110-c4`; its JUnit SHA-256 is
`7bd84bdc8ceeb881cd0b20aec257a720f61ed505e634e8db1888f87b35982b65`.

## Original-owner composition

| Owner | Change | Preserved boundary |
| --- | --- | --- |
| Runtime claim and requester ACK | Issue a private synchronous guard scope for the original root, command, exact owned writer and thread. | Original command replay, source grants, child/parent/plan selection, lease, completion, and receipt transactions remain canonical. |
| Runtime connection factory | Install an inert VM-budget handler only when constructing a fresh COO-guarded write connection. | A borrowed reader cannot install, replace, or remove SQLite handlers. Ordinary transactions retain their existing open path. |
| Service namespace custody | Recover the actual nominal request capability from the existing installed bounded-runtime factory and revalidate its original seals, flock, and marker. | No second reservation, new service, alternative database, or caller assertion supplies custody. |
| Workspace | Reacquire current Control Room source and validity before and after a bounded root read through the original writer. | No cached Mission substitutes for source or permission authority. |
| Mission and COO mandate | Reuse the canonical root join, currentness conjunction, typed result, posture, owed-turn, effect-gate, and decision predicates. | Generic public Mission CURRENT still requires its genuine closed SAME observation. |

The live scope exists only while one original synchronous guard runs. Its root
and command are read-only properties. It rejects another store, a foreign or
unowned connection, another thread, an expired scope, or an unqualified VM-budget
owner. It does not expose a public connection, SQL API, receipt, generation, or
read observation. Any namespace first used by the guard is retained only until
that guard exits and is checked again at that exit; a different namespace cannot
replace it. The scope is invalidated and discarded in all exit paths.

The original Runtime connection supplies both guard reads. The first sees the
preclaim child. The second sees the transaction's own newly allocated Attempt
and changed Job, before COMMIT. Comparing either to a cached preflight root
snapshot would reject this legitimate owned change. The current implementation
reproves the source and semantic conditions each time, while the existing
same-transaction selection validator still checks the actual child, immediate
parent, original root, current admitted plan, step, repair round, ordinal and
deterministic command.

## Evidence and budget semantics

The private Workspace authority state is labeled `LIVE_TRANSACTION`. That state
does not satisfy the public Mission CURRENT/SAME validator and is never returned
through a public read route. The private Fabric material also retains UNKNOWN
public read-generation evidence. Its actual authority comes from the live
Runtime scope and independently revalidated source owners.

The bounded material loader is the existing Runtime loader and root selector:
17 Jobs, 20 Attempts per Job, 340 Attempts total, 256 statements, 512 rows,
8 MiB per raw cell, 32 MiB of raw material, and 200,000 SQLite VM steps. Creation
evidence is charged to that same selection. Immutable root creation provenance
must prove the selected workstream through the canonical Fabric validator.

Every retained SELECT cursor is explicitly closed before the guard returns.
The writer remains owned by its original transaction. A failed cursor close
refuses the guard and lets that transaction roll back and perform its own
physical cleanup. No public closed-read receipt is manufactured. The VM handler
is deactivated before cursor teardown and before any subsequent lifecycle SQL,
rollback or COMMIT; only the original fresh-connection owner removes it.

The read's Control Room bracket requires the same owner, instance, publication,
document and proof identities, plus separately current validity at both ends.
Elapsed validity budgets remain real clock samples. Actual source/grant facts
and the nominal `PrincipalFact` / `AuthorityFact` checks remain part of the
original receiving and effect guards.

## Acknowledgment remains narrower than admission

The explicit API-requester acknowledgment needs the current authenticated
principal, original work/root association, matching catalogue/action and exact
original completed result. It is not a fresh child admission and does not gain
the `DECIDE_CONTINUE` or COO-owed-turn requirement. Runtime still joins its
original claim provenance and canonical result on the same writer, then appends
at most the existing digest-bound consumption Event. Parent-native consumption,
review approval, product acceptance and a fresh provider turn remain separate.

## Qualification and remaining delivery

Focused source tests exercise actual Runtime and SQLite, actual service
namespace custody, a genuine current-C publication and its installed source
grant. The real provider remains inert. They cover successful claim and explicit
ACK, visibility of the transaction's own Attempt, public closed-read behavior,
wrong thread/store/connection, scope expiry, cancellation, VM/raw-byte ceilings,
cursor cleanup, namespace release, and source revocation before commit.

The same test run includes the incumbent Mission Workspace, COO mandate/host and
requester-return regressions. The immutable qualification manifest records the
exact source postimages, dependency patch hashes, commands, result log and JUnit
digest. The next consumer proof is the existing signed MCP/App/Unix Control
joint API suite on the exact composed M2 source tree; installation and grant
activation remain separate from this source qualification.

This increment preserves the single-Executive-resource requester contract.
It does not grant current-DATA effect access from an absent Workspace companion,
attribute a T3 or Paperclip native origin, or alter the independent current-DATA
project readiness and original-input witness work.
