# What this package verifies

## Confirmed handoff-selector counterexample

Run:

```bash
python3 verification/handoff-selector-reproduce.py
```

`handoff-selector-fixture.json` contains the pinned source's date regex, citation helpers, association comprehension and ranking function, extracted through Python AST, plus the association-relevant frontmatter excerpts of two exact canonical October 19 records. It preserves the original file hashes, source line locations and Macro pin. It contains no credentials or live runtime state. The finite regression fixture is not a replacement canonical record store.

The audit first ran this logic extracted directly from the full pinned source and actual records. This portable reproduction executes the same selected fragments without importing the Agent OS module or CLI. Both records associate correctly. Both filename date captures are empty because the regex requires the date at the end. Lexical rank selects the earlier S3-installed handoff and drops the later acceptance-failed handoff. `correct: false` is the **expected confirmation of the current defect**, not a successful product test.

The current workstream separately retains the acceptance failure, and newer October 20/21 checkpoints supersede both handoffs as the runtime frontier. Neither fact removes the selector defect. A fix needs owner-approved chronology/tie semantics, focused regression proof and a real isolated full-compiler consumer test. This audit did not modify the canonical compiler.

## Brief compilation and document checks

`brief-compilation.json` records the actual seven successful Craft compilations: six Opus domain briefs and one bounded backend example. Compiler/input/output hashes identify authoring bytes; they are not installation, admission, capability or completion receipts. Every authored runtime binding remains null until a real existing owner issues it.

`validate-package.py` checks the package's structural claims: complete expected files, unique planning IDs, valid dependencies, acyclic graph, root/domain coverage, unresolved runtime bindings, source-ID closure, brief input/output hashes, the specific reproduced counterexample, and document references. `package-checks.json` records the actual result. These checks do not prove production behavior or the truth of owner reports.

`adversarial-review.md` records a separate reasoning review of the execution plan. Any repaired findings are documented in `review-resolution.md`; independent review of this plan does not substitute for future independent review of its implementations.

## Scope of testing

No large implementation suite was rerun, no worker was admitted, no readiness canary was consumed, no external message was sent and no production service was changed by this audit. Existing test counts in the domain memos remain attributed to their named original revisions. Current Executive state reading and Studio discovery failed before useful host state; Fabric capability discovery succeeded but worker admission/start remained unprobed.


## Canonical continuity proposal

`canonical-continuity-check.json` records the actual path-scoped validation of Macro draft PR9988. The current unmodified Agent OS validator ran in an isolated fixture with its actual registry and three transitive workstream dependencies. One proposed existing-workstream append passed with zero errors/warnings; every prior workstream byte and all frontmatter were preserved. The published candidate was read back exactly. This is not whole-repository validation, hosted CI, a merged canonical update, a source-custody transfer or runtime proof.
