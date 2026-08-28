# Task 2 implementer report

Append exact RED/GREEN evidence and the final immutable commit identity for each fix round here.

## Task 2 fix round 2 — Finding A RED

Tests were added before production changes for the three canonical heterogeneous
producer surfaces. Exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'retained_topology_accepts_exact_per_row_producer_metadata or retained_rollback_accepts_exact_moved_artifact_metadata or retained_legacy_accepts_each_canonical_producer_metadata'
```

Result: exit 1; `FFF [100%]` (3 selected failures). Each faithful
root-owned producer fixture failed because the retained graph had no exact
per-object policy derivation: `_topology_object_security_policy`,
`_rollback_object_security_policy`, and `_legacy_object_security_policy` were
absent. The fixtures encode config/attestation `root:<row worker_gid> 0440`,
plist `root:wheel 0644`, moved-artifact metadata, rollback receipt
`root:wheel 0400`, and the two distinct legacy group identities. Their paired
negative cases exchange two otherwise admitted GIDs, so an unbound UID/GID/mode
union cannot satisfy GREEN.

## Task 2 fix round 2 — Finding B RED

Timeout behavior was injected before production normalization at launchctl
`print-disabled`, each of the five fixed label `print` calls, `dscl`,
`dsmemberutil`, `dseditgroup`, `id -G`, the source-repair CLI boundary, and a
precommit preserved-invariant gate. Exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'preserved_native_command_timeout or source_repair_cli_normalizes_subprocess_timeout or precommit_subprocess_timeout or postcommit_subprocess_timeout'
```

Result: exit 1; 12 failed and 1 passed. All ten command-stage cases leaked raw
`subprocess.TimeoutExpired`; the CLI case also leaked the raw exception with
argv rather than returning exit 65 with a closed reason; and the precommit case
escaped raw instead of entering authorized recovery. The postcommit replay
already became `SourceRepairIncomplete(POST_COMMIT_RECONCILIATION_REQUIRED)`,
which is the frozen same-carrier behavior and remained as a positive guard.

## Task 2 fix round 2 — Finding C RED

Every guard admission failure stage was injected before the ownership-order
repair, together with a close-failure continuation guard. Exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'owns_every_guard_before_each_admission_failure or closes_after_one_close_refuses'
```

Result: exit 1; `F...... [100%]` (1 failed, 6 passed). The first guard
`fstat` case opened descriptor 11 but observed no close (`[] != [11]`), proving
the descriptor was not owned before the first fallible audit. The ancestor,
xattr, ACL, relation-observation, later-open, and close-refusal cases already
preserved one-close/close-all behavior and remain as positive regression guards.

## Task 2 fix round 2 — Finding D RED

The role-policy directory regression overlaid a stable zero link count through
both descriptor and parent-relative observations before production changes.
Exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'repository_role_directory_refuses_stable_zero_link_count or repository_role_directory_freezes_each_admitted_positive_link_count'
```

Result: exit 1; `F. [100%]` (1 failed, 1 passed). A role directory with
`st_nlink == 0` was admitted without raising `SOURCE_METADATA_INVALID`; the
paired positive-count test confirmed the existing exact temporal snapshot law.

## Task 2 fix round 2 — focused GREEN

Finding A exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'retained_topology_accepts_exact_per_row_producer_metadata or retained_rollback_accepts_exact_moved_artifact_metadata or retained_legacy_accepts_each_canonical_producer_metadata_and_rejects_union'
```

Result: exit 0; `... [100%]` (3 passed).

Finding B exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'preserved_native_command_timeout or source_repair_cli_normalizes_subprocess_timeout or precommit_subprocess_timeout or postcommit_subprocess_timeout'
```

Result: exit 0; `............. [100%]` (13 passed).

Finding C exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'owns_every_guard_before_each_admission_failure or closes_after_one_close_refuses'
```

Result: exit 0; `....... [100%]` (7 passed).

Finding D exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'repository_role_directory_refuses_stable_zero_link_count or repository_role_directory_freezes_each_admitted_positive_link_count'
```

Result: exit 0; `.. [100%]` (2 passed).

Consolidated exact new selector:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'retained_topology_accepts_exact_per_row_producer_metadata or retained_rollback_accepts_exact_moved_artifact_metadata or retained_legacy_accepts_each_canonical_producer_metadata_and_rejects_union or preserved_native_command_timeout or source_repair_cli_normalizes_subprocess_timeout or precommit_subprocess_timeout or postcommit_subprocess_timeout or owns_every_guard_before_each_admission_failure or closes_after_one_close_refuses or repository_role_directory_refuses_stable_zero_link_count or repository_role_directory_freezes_each_admitted_positive_link_count'
```

Result: exit 0; `......................... [100%]` (25 passed).

Prior 47-case review selector:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'recovery or crash'
```

Result: exit 0; `............................................... [100%]`
(47 passed).

Legacy-v1 compatibility selector:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'recovery_v1'
```

Result: exit 0; `..... [100%]` (5 passed).

## Task 2 fix round 2 — Finding A self-review type RED

The pre-commit self-review identified that the exact per-object tuple did not
yet bind object type. A descriptor/parent-relative stable overlay made a
directory present the exact config UID/GID/mode. Exact command:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'exact_topology_policy_refuses_directory_substitution'
```

Result: exit 1; `F [100%]` (1 failed). The substituted directory was admitted
instead of raising `SOURCE_METADATA_INVALID`.

## Task 2 fix round 2 — final proof on final code

The exact per-object policy now binds object type as well as UID/GID/mode.
The self-review regression command above returned exit 0; `. [100%]` (1
passed). The complete Finding A selector returned exit 0; `.... [100%]` (4
passed).

Final consolidated new selector:

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'retained_topology_accepts_exact_per_row_producer_metadata or exact_topology_policy_refuses_directory_substitution or retained_rollback_accepts_exact_moved_artifact_metadata or retained_legacy_accepts_each_canonical_producer_metadata_and_rejects_union or preserved_native_command_timeout or source_repair_cli_normalizes_subprocess_timeout or precommit_subprocess_timeout or postcommit_subprocess_timeout or owns_every_guard_before_each_admission_failure or closes_after_one_close_refuses or repository_role_directory_refuses_stable_zero_link_count or repository_role_directory_freezes_each_admitted_positive_link_count'
```

Result: exit 0; 26 passed.

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'recovery or crash'
```

Result: exit 0; 47 passed.

```text
python3 -m pytest -q tests/test_capacity_host_artifacts.py -k 'recovery_v1'
```

Result: exit 0; 5 passed.

```text
/usr/bin/time -p python3 -m pytest -q -x tests/test_capacity_host_artifacts.py -k 'preserved or source_repair'
```

Result: exit 0; 67 passed; `real 78.78`, `user 33.08`, `sys 35.59`.

```text
/usr/bin/time -p python3 -m pytest -q tests/test_capacity_host_artifacts.py
```

Result: exit 0; all 351 collected cases reached `[100%]`; `real 1167.21`,
`user 492.10`, `sys 512.08`. The final run remains within the prior bounded
full-module profile (`real 1148.81` for 298 cases) while adding 53 cases.

```text
python3 -m pytest --collect-only -q tests/test_capacity_host_artifacts.py
```

Result: exit 0; `tests/test_capacity_host_artifacts.py: 351`.

```text
/usr/bin/python3 -m py_compile ops/executive_os/capacity_host_artifacts.py tests/test_capacity_host_artifacts.py
```

Result: exit 0; no output.

```text
git diff --check
```

Result: exit 0; no output.

Final protected master re-pin:
`b901dee0272a99b8a1d60385848b99b7273e8261`.

The bounded review repair changes only the Task 2 implementation, its behavior
tests, and this task's progress/report evidence. Task 3, native/provider/Slack,
OAuth, services, routing, publication, PR, merge, push, deployment, and installed
payload execution remained held.
