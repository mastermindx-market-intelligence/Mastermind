# Task 5 final safety-fix report

## Frozen identity and authority

- Exact parent: `1822db356eab71c46067953f321846851a9ff2cc`
- Branch: `codex/cf2-h0-source-closure-20260827`
- Protected Skillpack source: `origin/master` at
  `8affa1c0403f4400825371bea0257f360a4814f2`
- Skillpack schema/version: `mastermind.sol_skillpack.v1` / `1.0.0`
- Bootstrap compatibility: project `bootstrap_major = 1` satisfies Skillpack
  `minimum_bootstrap_major = 1`
- Controller authority: all five blockers in `task-5-final-review-findings.md` are mandatory.

No provider home, credential, OAuth, service, socket, worker, routing, native root action, P0,
push, PR, merge, or hosted action was used during this task-local fix.

## TDD RED evidence

The first discriminating run was executed before production edits:

```text
python3 -m pytest -q \
  tests/test_capacity_host_artifacts.py::test_closed_tree_digest_uses_exact_canonical_rows_and_descriptor_reads \
  tests/test_capacity_host_artifacts.py::test_closed_tree_digest_refuses_nonzero_mocked_fstat_flags \
  tests/test_capacity_host_artifacts.py::test_closed_tree_digest_refuses_native_harmless_user_flag \
  tests/test_capacity_host_artifacts.py::test_source_repair_parent_graph_refuses_untrusted_intermediate_metadata \
  tests/test_capacity_host_artifacts.py::test_source_repair_parent_graph_detects_synchronized_system_root_swap \
  tests/test_capacity_host_artifacts.py::test_inert_release_manifest_verifier_never_executes_installed_payload \
  tests/test_capacity_host_artifacts.py::test_privileged_git_environment_is_closed_to_ambient_execution_and_network \
  tests/test_executive_capacity_source_closure_repair.py::test_native_ceremony_materializes_one_digest_bound_root_created_carrier \
  tests/test_executive_capacity_source_closure_repair.py::test_root_carrier_wrapper_uses_no_git_and_requires_descriptor_verification \
  tests/test_executive_launchd_config.py::test_root_scripts_are_syntax_valid_and_service_control_is_fixed_scope

11 failed, 1 skipped
```

The failures discriminated the missing `flags` rows/refusal, intermediate symlink and parent-mode
acceptance, missing retained-parent revalidation, absent inert-release verifier, incomplete Git
environment, old operator-checkout ceremony, privileged Git in the Bash carrier, and tracked mode
`100644`. The native harmless-user-flag test also failed on Darwin before the repair. The one skip
was an unavailable xattr fixture in that initial version; the final Darwin test uses the native
`xattr` tool and runs deterministically.

## Implemented repair

1. The nonprivileged ceremony now emits one SHA-256-bound exact-protected-ref Git bundle as inert
   data. The trusted inline root shell runs under `env -i`, copies without preserving metadata into
   a new root-created `0700` namespace, authenticates the copied bundle, creates a private bare
   repository, and writes only three exact reviewed Git blobs plus the commit stamp into new
   root-owned inodes. Each blob is re-bound with `hash-object --no-filters`; the executable carrier
   is descriptor-verified before launch. A pre-opened operator write descriptor cannot mutate the
   root-created carrier.
2. Every privileged Git surface has fixed `HOME`, `PATH`, `LANG`, and `LC_ALL`; ignores system,
   global, and local config; disables hooks, fsmonitor, attributes, replacement refs, external
   diff/textconv, prompts, lazy fetch, and optional locks; and allows only local file transport.
   The root Bash carrier itself invokes no Git. No network protocol is available as root.
3. The installed e4 release is never executed or imported. The reviewed repair carrier walks the
   release and v1 manifest as inert descriptor-relative data, validates exact commit/tree/schema,
   content, inventory, metadata, symlink confinement, and pre/post state, and refuses a replaced
   `release_manifest.py` sentinel without launching it.
4. The fixed system root is traversed from `/` component-by-component with `openat`/`dir_fd` and
   `O_NOFOLLOW`. System root, capacity-source, generation, staging, archive, and lock parents remain
   open, are validated for exact security metadata and same-device law, and have descriptor and
   pathname relations revalidated. Installed source and preserved runtime/generation/archive/
   topology/rollback evidence use retained views across semantic verification. Intermediate
   symlink, parent mode, ACL, xattr, flag, and synchronized-swap regressions fail closed.
5. The frozen allowed BSD flag value is zero. It is now part of descriptor/snapshot states and
   closed-tree semantic rows and is checked on roots, parents, directories, files, locks, intents,
   receipts, source, generation, archive, runtime, release, topology, rollback, and carrier
   objects. Both deterministic mocked-`fstat` and native Darwin harmless-user-flag regressions pass.
6. `ops/executive_os/repair-capacity-source-closure.sh` is tracked as `100755`.

The existing single lock, intent, receipt, archive, source-repair identity axis, and frozen
e4 topology/preparer/release axis remain canonical. No new lifecycle or state store was added.
The v1 behavior and public v2 schemas are unchanged; the flags field strengthens only the internal
closed-tree semantic row law required by the adjudicated finding.

## GREEN evidence

Final discriminating regressions:

```text
................                                                         [100%]
```

This 16-case selection covers canonical flag rows, mocked and native flags, five intermediate
parent drifts, synchronized root swap, inert installed-release sentinel, exact closed Git env,
malicious include/fsmonitor/diff/textconv non-execution, pre-opened operator FD isolation, root
carrier/runbook law, Bash no-Git descriptor verification, and executable Git mode.

CI plan:

```text
discovered=315 excluded=0 running=315
```

Exact six-file Task 5 matrix:

```text
........................................................................ [ 20%]
........................................................................ [ 40%]
........................................................................ [ 60%]
........................................................................ [ 80%]
....................................................................     [100%]
```

The expanded matrix collected 356 cases and completed without failure (356 passed). A disposable
nonprivileged Apple-Git proof of the documented closed
bundle/init/verify/unbundle/rev-parse path emitted:

```text
UNPRIVILEGED_INERT_BUNDLE_BOOTSTRAP_PASS 1822db356eab71c46067953f321846851a9ff2cc
```

Apple `/usr/bin/python3` isolated compilation, Bash syntax, `git diff --check`, exact parent/path/
mode checks, final commit identity, and clean-status evidence are recorded in the controller
handoff after the report-containing commit, because a commit cannot contain its own SHA.

## Changed paths

- `.superpowers/sdd/2026-08-27-executive-capacity-cf2-h0-source-closure-repair/task-5-final-fix-report.md`
- `docs/superpowers/plans/2026-08-27-executive-capacity-cf2-h0-source-closure-repair.md`
- `docs/superpowers/specs/2026-08-27-executive-capacity-cf2-h0-source-closure-repair-design.md`
- `ops/executive_os/HOST_PREREQUISITES.md`
- `ops/executive_os/capacity_host_artifacts.py`
- `ops/executive_os/repair-capacity-source-closure.sh`
- `tests/test_capacity_host_artifacts.py`
- `tests/test_executive_capacity_source_closure_repair.py`

## Residual and boundary

The controller-parked closure-sized object-inventory memory concern remains Minor and unchanged.
This result is task-local implementation evidence only. It is not hosted-CI proof, merged,
installed, live, two-pass native verify-only proof, or CF2-P0 acceptance.
