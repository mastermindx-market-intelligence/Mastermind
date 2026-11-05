# Product completion and composite-scope source successor

This is a frozen successor inside the existing restoration package. It preserves
the November 3 PT [product-completion correction](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1842#issuecomment-6622345759).
It is source data, not an installer, hook, task registry or scheduler. The original
package and its historical qualification remain unchanged.

The patch corrects three related boundaries:

- Local task progress cannot close, drop or reopen a canonical wave. Export keeps
  unfinished acceptance and original Goal/Success criteria visible; CLI and resume
  use the same existing selector and recovery presentation.
- Existing workstreams can be associated additively, retaining original records,
  task evidence, distinct wave identities and idempotence. This adds no authority.
- Task import, ambiguous wave selection and proposed-wave next actions preserve
  `(workstream, wave)` identity. Ambiguous references fail before charter-data writes.

`manifest.json` binds every predecessor, successor and test source. The mmtask and
charterlib predecessors are the existing package's `../payload/` bytes; only the
previously untracked schema predecessor is retained here. The zero-context patch
requires those exact bytes, zero fuzz, and final hash verification. It must never
be applied to an unqualified live target or with guessed/fuzzy/reverse recovery.

To reconstruct, create a new empty disposable directory. Copy the three manifest
preimages into it as `mmtask`, `charterlib.py` and `SCHEMA.md`, verify their SHA-256
values, then run `patch --batch --fuzz=0 -p1 -i <absolute-path>/completion.patch`
from that directory. Verify all three resulting SHA-256 values against the
manifest before using any result. This exact reconstruction was performed and
matched all three reviewed source files. No live helper or charter was written.

Tests are retained as `.py.source` so normal repository discovery does not execute
them. Their fixtures are synthetic and disposable. For the 42 targeted tests,
copy them into the reconstructed directory without the `.source` suffix, retain
the sibling source filenames, and run:

```sh
python3 -m unittest -v test_completion_semantics.py test_composite.py test_wave_identity.py
```

Python and PyYAML must already be available; this package installs no dependencies.
Semantic/export unit tests isolate behavior with stubs. They do not replace the
separately retained real Agent OS validator and four-workstream import evidence.
The manifest distinguishes the 35 original compatibility passes, combined 29 plus
6 fixture-corrected passes, and 4 affected passes after the identity correction.
It does not claim a new full compatibility run or product acceptance.

Any separately authorized installation must reconcile the current writer, exact
target preimages/modes and unresolved effects, retain backups, and read back the
installed bytes. Install the compatible mmtask before the charterlib that invokes
it. A mismatched target is not permission to overwrite it. Source-only completion
remains source-only; native continuation uptake, original-owner action, scheduled
recovery and complete product journeys require their own observed evidence.

Known consumers are the existing `codex-session.sh` launch/resume path through
`charterlib.py`, and Operations' `mmtask next --explain` recovery. This package does
not claim universal Codex Desktop or ChatGPT Project installation or fresh loading.
