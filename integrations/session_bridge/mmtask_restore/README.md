# Frozen mmtask source and offline restoration rehearsal

This package preserves the exact Portfolio handoff for [the November 2 continuity correction](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1842#issuecomment-6588972253). It is source data plus an explicit disposable rehearsal. Importing or checking out the package does not install a helper, invoke a hook, read a live charter, create a scheduler, or change a registry.

The manifest binds the original helper and test preimages, approved helper and test postimages, unchanged `charterlib.py`, and the exact combined patch. Original byte contents and executable modes are retained. The accepted test files end in `.py.source` so repository test discovery cannot execute their historical live-home defaults. The rehearsal copies the accepted test bytes to their original filename only inside a fresh temporary directory.

## Provenance and dependency boundary

Bounded inspection found no tracked `mmtask`, `charterlib`, or `gwcap/bin` source or installation owner in protected Mastermind `04ca04c703855183924c7a0e048ac8b5b1b7e261` under `AGENTS.md`, `docs/`, `scripts/`, and `integrations/`, or the corresponding cited Macro `b03edd4902a5582ed59773ec12ff2c2fa37aadf7` manual/script paths. Filename inspection of the installed Mastermind support directory did not find a mmtask installer. This is the scope of the search, not a claim that no other historical copy exists. `~/gwcap` is not a Git source repository. Local repair fragments establish local editing history only, not protected publication or installation ownership.

The supplied helper imports standard Python modules and dynamically imports `scripts/agentos.py` from its explicit Macro mirror. Export validation uses that mirror's Agent OS schemas and validator. PyYAML is required for import/export. `charterlib.py` is retained as an unchanged, explicitly supplied companion; the helper does not import it. This package does not appoint a second Agent OS or task database.

The owner reported 35 passing tests on M2 using a private historical fixture. That reported result is separate from this package's rehearsal. The committed fixture is wholly synthetic: invented task text, notes, evidence and identities, preserving the null binding, ordered legacy statuses, alias, dependencies, and lossless-preservation assertions. No original private fixture content is included. The frozen test's historical prose about a real fixture is unchanged; here the adjacent fixture is the explicitly approved synthetic substitute. Its exact digest and the independent rehearsal result are in the manifest and `qualification.json`.

## Reproduce without a live helper or charter

Requirements: Python 3.12 or newer, PyYAML, Git, and `patch` supporting `--fuzz=0`. No dependency installation is performed by the package. Qualification records the observed Python/PyYAML versions.

From this directory:

```sh
python3 rehearse.py --verify-only
python3 rehearse.py \
  --macro-repo /path/to/readable/macro-clone \
  --result /path/to/new/rehearsal-result.json
```

The result path must not exist. The script checks all bound source bytes and modes first, reconstructs both postimages from the exact preimages with zero fuzz in a private staging tree, and verifies the reconstructed bytes against the bound payloads. It archives only tracked `agentos/` and `scripts/` from exact Macro commit `b03edd4902a5582ed59773ec12ff2c2fa37aadf7`. A missing commit fails; it never fetches or pulls. That archive becomes a disposable mirror without `.git`. The unchanged supplied tests run with explicit `MMTASK_UNDER_TEST`, `MM_AGENTOS_MIRROR`, private `HOME` and `TMPDIR`, and no inherited charter/session variables. Test subprocesses only edit disposable charters. The archive digest, synthetic fixture digest, exact versions, test exit/output, and isolation are recorded in the new result file. Temporary homes and test copies are removed after the run.

## Offline recovery recipe

Recover this package from its reviewed protected commit and run the verification/rehearsal above. An absent or changed manifest member must be reconciled from that immutable source, never substituted from an installed file. To prepare an offline recovery candidate, create a **new empty staging directory**, copy `payload/mmtask` and `payload/charterlib.py` into it with their manifest modes, and verify their hashes again. Keep the staging directory separate from every real `gwcap/bin` or charter path.

Before any separately authorized promotion, read and hash the intended target and its mode. The helper's only qualified predecessor here is SHA-256 `9567ecad658e50b149a14f4c0cd0c7b42d15ad546b0508e2153619f14d0eb336`, mode `0755`; the accepted postimage is `711ba4f46c80e518d99167877738db9e92182b78bf7b4e3052bcfee79316d54a`, mode `0755`. A target already matching the postimage needs no replacement. An absent target, a symlink, a different predecessor, modified bytes, changed mode, active writer, or unresolved effect is **unqualified**: preserve it and the staged candidate, and reconcile its own source/custody before any write. Do not apply this patch to a guessed target, use fuzzy/reverse patching, or overwrite a modified file. This source package deliberately performs no promotion, installation, rollback, real-target overwrite, or hook change. Those effects need their own assigned owner and actual gates.

Source qualification does not prove a fresh native session selected an unfinished product task or that the original owner performed useful work. Those consumer and installed-behavior proofs remain with the existing integration and portfolio owners.

The exact supplied patch includes eight whitespace-bearing context lines, and both frozen test-source copies retain the same original trailing-space line. These ten `git diff --check` findings are bound input data, not authored normalization changes. They remain unchanged to preserve the approved hashes; this package does not relax repository whitespace attributes or checks. Authored package files pass the whitespace check.
