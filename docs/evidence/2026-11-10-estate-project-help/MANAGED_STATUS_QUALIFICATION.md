# Managed-session canonical status repair — source qualification

## Source and observed failure

Repository: `mastermindx-market-intelligence/Mastermind`; exact base `95762fc3700598a7be1a12b8c6c1995753071eed`. CI run `42796811883`, attempt 1, shard 5 job `129774519669` failed `test_real_retained_runtime_source_and_typed_proxy_compose_without_a_send_target`: the actual retained reader returned `UNAVAILABLE` instead of `MATERIALIZED_OBSERVATION`.

The unchanged positive test reproduces the failure alone. A bounded exception trace through the actual reader/composer identifies `OperatorMaterializationReceiptError: materialization receipt fields do not match the closed schema`. Both original broker reads complete; the fixture provider remains at one original begin-turn and zero stops. No provider execution is performed by this READ.

The typed remote adapter has already decoded the broker receipt. The reached managed reader then uses generic dataclass serialization, reintroducing optional fields as null. The original receipt owner deliberately omits both planner fields for v1 and the observed contract for v3, retaining historical canonical bytes and digests. The composer correctly refuses the expanded shape.

## Correction and preserved owners

Add `OperatorMaterializationStatusObservation.to_dict`, delegating its nested receipt to the existing version-aware `OperatorMaterializationReceipt.to_dict`. Use that canonical method at the actual `ExistingManagedProjectSessionSource.read` call. The strict receipt decoder, generic `operator_harness_wire.to_wire`, permissions, currentness brackets, Runtime, broker and provider lifecycle remain unchanged.

The new focused tests cover v1, v2 and v3 under both positive broker statuses, byte/digest preservation, v1/v3 omitted-field versus explicit-null rejection (each omitted field independently), and both negative statuses. These tests intentionally confirm generic expansion remains invalid for historical schemas.

## Qualification

`managed-final.log`: **93 passed, 2 dependency deprecation warnings, 3.97s**, actual pytest exit 0 on Python 3.12. No conftest substitutions or decoder patches.

Command, from the exact source snapshot:

```sh
PYTHONPATH=/workspace/scratch/dfef37b7f33a/estate-return-qualification/.qualification-deps:.:tests python -m pytest --noconftest -c /dev/null tests/test_workspace_managed_project_session_source.py tests/test_operator_materialization_status_wire.py tests/test_workspace_project_session.py tests/test_workspace_project_session_read.py::test_session_permission_refusal_keeps_plain_integer_http_status_before_source_read tests/test_operator_materialization_receipt.py -q -x --tb=short
```

This includes the real retained-reader positive with two broker status reads, original same-owner/currentness and foreign-root negatives, closed DTO and source/profile mismatch tests, permission refusal before source access, and the original receipt canonical/digest/persistence refusal suite. No source grant or send target is created.

The original signed Workspace HTTP/Unix-control test was attempted, after 27 passing source cases. It stops at actual `ExecutiveControlService.start` because this cloud environment denies `socket(AF_UNIX, SOCK_STREAM)` with `PermissionError: [Errno 1] Operation not permitted`. This is **not qualified socket/HTTP evidence** and is not an application test pass. `managed-affected.log` preserves the exact stack. No alternate socket implementation or approval bypass was attempted. Parent owns the planned unchanged `tests/test_workspace_project_session_read.py` run on M2 when its existing host reservation permits.

The three-file full-index patch was applied with `git apply --check --index`, then actually applied to exact recorded preimages in isolated scratch. All three replay bytes match their manifest postimages; `git diff --cached --check` passes. The original source test files and generic decoder/serializer are unchanged.

## Delivery boundary

Reviewable source increment only. No GitHub publication, installed service, provider, worker, profile, credential, grant or host mutation occurred here. Parent owns composition and canonical source publication. Installed production behavior and the actual socket path remain unclaimed until their respective proofs.
