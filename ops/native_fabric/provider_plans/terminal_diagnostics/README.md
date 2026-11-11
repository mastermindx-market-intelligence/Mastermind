# Native-plan terminal qualification diagnostics

This is a fixed-parent SOURCE COMPONENT. It does not change a selected generation,
any existing provider profile, the current 119 cohort, routing, consent, admission,
or the disposition of an existing operation. The descriptor binds the exact
`ef27796c...` worker parent, forward patch and resulting worker digest. Integration
must verify those three hashes and explicitly bind the resulting member through
the existing composer, preserving every other member. No whole-cohort output or
arbitrary parent/path override is supplied here.

The existing native-plan controller already returns 76 and retains UNKNOWN when
terminal qualification fails. Previously every exception at that boundary lost
its predicate. This patch adds closed source-owned reason codes and a best-effort,
write-new `.local-terminal-diagnostic.json` for FUTURE executions. The controller
still returns 76. It does not publish a terminal ledger row, release custody,
accept a result, execute another provider command, or permit replay.

An optional anchor is captured from the request and launch bytes already checked
by `original_request`. It binds their hashes, the source hash and a hash of the
original identity. The ordinary default return from `original_request` stays the
same. Before and after writing, the controller rejoins those original frames and
source. Missing, changed, foreign or inaccessible facts withhold even the public
`diagnostic=retained` acknowledgement. The existing provider/process/physical/quota
qualification predicates and return conditions are unchanged; only their explicit
ValueError subclass carries the closed reason. Arbitrary exception messages,
objects and lookalike ValueErrors cannot become reason codes.

The retained frame has an opaque binding digest, source digest, closed reason,
`EFFECT_UNKNOWN`, `NOT_RECONCILED`, and false terminal/replay flags. It contains no
root, parent, account, model, lease/process identity, file path, output, packet or
exception text. A late post-write drift may leave that historical UNKNOWN frame;
it never receives a retained acknowledgement or currentness/terminal authority.
No reader, reconciliation CLI or backfill is added. A future legitimate owner read
would have to authenticate and rejoin the original facts; the frame alone cannot
settle an operation. A diagnostic failure cannot weaken UNKNOWN or create success.

The actual original `mmos-reader-root-contract-tests-01a1a4bf-20261108-v1` remains
EFFECT_UNKNOWN under its original owner. Outer 76 does not identify its inner
return code or swallowed predicate. No original run store, result, process, lease,
provider or host was read or changed for this source work.

Focused tests reconstruct the exact patch, execute the genuine old and new
controllers with the same inert original, and show old reason loss versus the new
bounded witness while both return 76. They cover unchanged terminal predicates,
physical/process/quota/cross-root failures, malformed receipts, source/request
withdrawal, privacy, unknown exceptions, write failure, post-write drift, once-only
capture, and the pre-existing qualified success branch. SQLite use is confined to
a disposable test database, and the subprocess/provider boundary is inert.
