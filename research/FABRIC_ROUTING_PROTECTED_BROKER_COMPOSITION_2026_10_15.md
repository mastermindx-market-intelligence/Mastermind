# Routing integration with the protected native broker

Same operation `fabric-routing-deep-audit-20261013-c2-001`, PR #1443 and branch.
Compatible procedure pin remains `76576d8680bb70cdb9e1cfe7016aefec0fb3286f`.

## Material source change and repair

The source owner #1391 has merged as `e1cacf9eb310cbdf25a3a22defedb7b086c6c179`.
Its accepted native broker patch adds `native_binding` after the existing
`operator_child_id` argument of `_try_acquire`. Our original priority candidate
also added an optional parameter at that seam and forwarded it positionally.
The original patch cannot simply be applied to the new signature. If a manual
merge preserves the native parameter first but leaves our positional call, the
logical work class is passed as native binding rather than scheduling metadata.

The new `protected_composition/logical_priority_after_native.patch` is the
broker-only priority amendment for the protected-native postimage. It preserves
the native parameter's position and forwards `job_class` by keyword. The native
admission caller still supplies its original binding by keyword, and its older
positional parameter meaning also remains intact. This is not an instruction to
install the old historical snapshot or to edit #1391's branch.

Eight focused patch-call/signature tests pass, versus six failures/two passes on
the original positional variant. The prior original logical-priority patch and
its 49-pass/one-failure native evidence remain frozen. Do not add this alternative
broker patch on top of that old broker patch; use it after the accepted native
patch instead. Launcher wiring remains the original logical/request-ID changes
and needs its own current-source/override compatibility qualification.

## Complete-source integration test

`tests/test_native_fabric_protected_broker_composition.py` composes against the
complete original broker fixture published by #1391, not a reconstructed method
excerpt. Four exact Git blobs are reused as test data; their original paths,
commit pins and SHA256 checks are retained. The #1391 native postimage is checked
before layering the neighboring #1365 expiry candidate, new priority amendment,
sibling priority, request-demand/wiring and normalized-account candidates.

The fixture uses temporary SQLite and synthetic configurations only. Tests cover
ordinary scheduling metadata versus native binding, request-local sibling
retention, normalized account selection, host-compatible subsets, original
native binding rejection, ordinary release/heartbeat refusal for native rows,
uncertain native capacity retention and shared capacity limits. Source AST checks
preserve native schema/GC/release/heartbeat and original-root accounting bodies.
The native helper is unchanged. No supported provider/authenticated native action
is exposed by this test.

At publication, the eight argument-binding checks and Python syntax are locally
verified. The complete-source tests require hosted execution using the exact
reused blobs; no passing result is claimed in advance. This new integration check
does not clear the original denied native fixture or host actions, prove actual
installation, qualify all providers, or serve as independent review.

## Remaining acceptance

Read the exact hosted result and repair any real composition defect on this same
source branch. Preserve #1365/#1441 and current native source/install custody.
Do not overwrite the stale M2 workspace. Full current-host generation, accepted
review, broker/launcher overrides, protected release, installation and useful
original-parent execution/return remain required. The broader head-of-line,
effective scoring and quality-confidence findings remain open until qualified.
