from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest

from control_plane.executive_coo_policy import (
    CooCyclePolicy,
    CooCyclePolicyError,
    EXPECTED_POLICY_SHA256_BY_VERSION,
    load_pinned_coo_cycle_policy,
)


BASELINE_V1_PAYLOAD = {
    "schema_version": 1,
    "max_fan_out_per_parent": 8,
    "max_depth": 1,
    "max_repair_rounds": 2,
    "max_review_attempts_per_job": 2,
    "max_children_total": 16,
    "max_attempts_per_orchestration_job": 2,
    "review_job_attempt_limit": 1,
    "allowed_child_cost_classes": ["default", "small"],
}
BASELINE_V1_SHA256 = (
    "6cc80806fb0aa48a10f45f8d6483c3718d70c841aef671f501374f8b4ac4ed60"
)
CURRENT_POLICY_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "authority_map.yml"
)
CURRENT_V2_SOURCE = CURRENT_POLICY_PATH.read_bytes()
CURRENT_V2_SOURCE_SHA256 = hashlib.sha256(CURRENT_V2_SOURCE).hexdigest()
V1_SOURCE = b"""coo_cycle_policy:
  schema_version: 1
  max_fan_out_per_parent: 8
  max_depth: 1
  max_repair_rounds: 2
  max_review_attempts_per_job: 2
  max_children_total: 16
  max_attempts_per_orchestration_job: 2
  review_job_attempt_limit: 1
  allowed_child_cost_classes: [default, small]
"""
V2_SOURCE = b"""coo_cycle_policy:
  schema_version: 2
  max_fan_out_per_parent: 8
  max_depth: 2
  max_repair_rounds: 2
  max_review_attempts_per_job: 2
  max_children_total: 16
  max_attempts_per_orchestration_job: 2
  review_job_attempt_limit: 1
  max_provider_work_units_per_root: 32
  reserved_domain_consumption_units: 1
  allowed_child_cost_classes: [default, small]
"""


def _write_policy(tmp_path: Path, source: bytes) -> Path:
    path = tmp_path / "authority_map.yml"
    path.write_bytes(source)
    return path


def _pinned(
    version: int,
    source: bytes,
    tmp_path: Path,
    *,
    policy_sha256: str | None = None,
):
    return load_pinned_coo_cycle_policy(
        version,
        policy_sha256=(
            EXPECTED_POLICY_SHA256_BY_VERSION[version]
            if policy_sha256 is None
            else policy_sha256
        ),
        path=_write_policy(tmp_path, source),
    )


def _modified(source: bytes, old: bytes, new: bytes) -> bytes:
    assert source.count(old) == 1
    return source.replace(old, new)


def test_load_accepts_exact_current_v2() -> None:
    policy = CooCyclePolicy.load()

    assert policy.schema_version == 2
    assert policy.max_depth == 2
    assert policy.max_provider_work_units_per_root == 32
    assert policy.reserved_domain_consumption_units == 1
    assert policy.max_fan_out_per_parent == 8
    assert policy.max_children_total == 16
    assert policy.policy_sha256 == EXPECTED_POLICY_SHA256_BY_VERSION[2]
    assert policy.source_sha256 == hashlib.sha256(
        CURRENT_POLICY_PATH.read_bytes()
    ).hexdigest()


def test_load_refuses_v1_source_as_current() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = _write_policy(Path(directory), V1_SOURCE)
        with pytest.raises(CooCyclePolicyError, match="closed-key drift"):
            CooCyclePolicy.load(path)


def test_load_only_accepts_closed_exact_v2(tmp_path: Path) -> None:
    # Any drift / non-V2 schema_version refuses; V1 source misses new V2 keys.
    widened = _modified(V2_SOURCE, b"  max_depth: 2\n", b"  max_depth: 3\n")
    legacy_only = V1_SOURCE
    for source in (widened, legacy_only):
        with pytest.raises(CooCyclePolicyError):
            CooCyclePolicy.load(_write_policy(tmp_path, source))


def test_public_pinned_loads_accept_both_exact_sources() -> None:
    with tempfile.TemporaryDirectory() as directory:
        v1 = _pinned(1, V1_SOURCE, Path(directory))
        nested = Path(directory) / "nested"
        nested.mkdir()
        v2 = _pinned(2, V2_SOURCE, nested)

        assert v1.to_dict() == BASELINE_V1_PAYLOAD
        assert v1.policy_sha256 == BASELINE_V1_SHA256
        assert v1.source_sha256 == hashlib.sha256(V1_SOURCE).hexdigest()
        assert v1.max_provider_work_units_per_root is None
        assert v1.reserved_domain_consumption_units is None
        assert v2.schema_version == 2
        assert v2.max_provider_work_units_per_root == 32
        assert v2.reserved_domain_consumption_units == 1
        assert v2.source_sha256 == hashlib.sha256(V2_SOURCE).hexdigest()


def test_v1_pin_against_current_v2_source_yields_historical_payload(
    tmp_path: Path,
) -> None:
    """Pinning V1 against the current V2 source still emits the historical V1
    payload + canonical digest, with the new V2-only attributes None and absent
    from to_dict(), while source_sha256 reflects the V2 bytes actually read."""

    policy = _pinned(1, CURRENT_V2_SOURCE, tmp_path)

    assert policy.to_dict() == BASELINE_V1_PAYLOAD
    assert policy.policy_sha256 == BASELINE_V1_SHA256
    assert policy.max_provider_work_units_per_root is None
    assert policy.reserved_domain_consumption_units is None
    assert "max_provider_work_units_per_root" not in policy.to_dict()
    assert "reserved_domain_consumption_units" not in policy.to_dict()
    assert policy.source_sha256 == CURRENT_V2_SOURCE_SHA256


def test_v1_pin_rejects_malformed_v2_source_corruption(tmp_path: Path) -> None:
    """Selecting the old pin must not mask source corruption: missing V2
    fields, unknown fields, or duplicate keys still refuse through the
    V1 pinned-loader."""

    missing_new_field = _modified(
        V2_SOURCE, b"  max_provider_work_units_per_root: 32\n", b""
    )
    missing_other_new_field = _modified(
        V2_SOURCE, b"  reserved_domain_consumption_units: 1\n", b""
    )
    unknown_field = _modified(
        V2_SOURCE,
        b"  review_job_attempt_limit: 1\n",
        b"  review_job_attempt_limit: 1\n  unknown_policy_field: 1\n",
    )
    duplicate = _modified(
        V2_SOURCE, b"  max_depth: 2\n", b"  max_depth: 2\n  max_depth: 2\n"
    )
    for source in (missing_new_field, missing_other_new_field, unknown_field, duplicate):
        with pytest.raises(CooCyclePolicyError):
            _pinned(1, source, tmp_path)


def test_duplicate_coo_cycle_policy_mapping_refuses(tmp_path: Path) -> None:
    doubled = V2_SOURCE + b"\ncoo_cycle_policy:\n  schema_version: 2\n"
    with pytest.raises(CooCyclePolicyError):
        CooCyclePolicy.load(_write_policy(tmp_path, doubled))
    with pytest.raises(CooCyclePolicyError):
        _pinned(2, doubled, tmp_path)


def test_v2_pin_requires_v2_source_and_exact_digest(tmp_path: Path) -> None:
    # V1 source against a V2 pin already refuses with CooCyclePolicyError;
    # assert the semantic refusal rather than a brittle error substring.
    with pytest.raises(CooCyclePolicyError):
        _pinned(2, V1_SOURCE, tmp_path)
    with pytest.raises(CooCyclePolicyError, match="digest is not exact"):
        _pinned(2, V2_SOURCE, tmp_path, policy_sha256="0" * 64)


def test_v1_pin_requires_v1_or_v2_source_and_exact_digest() -> None:
    widened = _modified(V1_SOURCE, b"max_depth: 1", b"max_depth: 3")
    with tempfile.TemporaryDirectory() as directory:
        with pytest.raises(CooCyclePolicyError, match="values are not exact"):
            _pinned(1, widened, Path(directory))
        with pytest.raises(CooCyclePolicyError, match="digest is not exact"):
            _pinned(1, V1_SOURCE, Path(directory), policy_sha256="f" * 64)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("schema_version: 2", "schema_version: 3"),
        ("max_depth: 2", "max_depth: 3"),
        ("max_fan_out_per_parent: 8", "max_fan_out_per_parent: 9"),
        ("max_children_total: 16", "max_children_total: 17"),
        ("max_provider_work_units_per_root: 32", "max_provider_work_units_per_root: 33"),
        ("reserved_domain_consumption_units: 1", "reserved_domain_consumption_units: 2"),
    ],
)
def test_load_and_v2_pin_reject_widened_values(tmp_path: Path, old: str, new: str) -> None:
    source = _modified(V2_SOURCE, old.encode(), new.encode())
    with pytest.raises(CooCyclePolicyError):
        CooCyclePolicy.load(_write_policy(tmp_path, source))
    with pytest.raises(CooCyclePolicyError):
        _pinned(2, source, tmp_path)


def test_rejects_malformed_scalar_types(tmp_path: Path) -> None:
    for old, new in [
        (b"max_depth: 2", b"max_depth: true"),
        (b"max_depth: 2", b"max_depth: 2.5"),
        (b"max_depth: 2", b'max_depth: "2"'),
        (b"max_depth: 2", b"max_depth: -1"),
        (b"max_depth: 2", b"max_depth:"),
    ]:
        source = _modified(V2_SOURCE, old, new)
        with pytest.raises(CooCyclePolicyError):
            CooCyclePolicy.load(_write_policy(tmp_path, source))
        with pytest.raises(CooCyclePolicyError):
            _pinned(2, source, tmp_path)


def test_rejects_unknown_missing_duplicate_and_block_drift(tmp_path: Path) -> None:
    unknown = _modified(
        V2_SOURCE,
        b"  review_job_attempt_limit: 1\n",
        b"  review_job_attempt_limit: 1\n  unknown_policy_field: 1\n",
    )
    missing = _modified(V2_SOURCE, b"  max_depth: 2\n", b"")
    duplicate = _modified(V2_SOURCE, b"  max_depth: 2\n", b"  max_depth: 2\n  max_depth: 2\n")
    no_block = V2_SOURCE.replace(b"coo_cycle_policy:", b"other_policy:")
    for source in (unknown, missing, duplicate, no_block):
        path = _write_policy(tmp_path, source)
        with pytest.raises(CooCyclePolicyError):
            CooCyclePolicy.load(path)
        with pytest.raises(CooCyclePolicyError):
            _pinned(2, source, tmp_path)


def test_legacy_reserved_methods_are_unchanged(tmp_path: Path) -> None:
    v1 = _pinned(1, V1_SOURCE, tmp_path)
    v2 = CooCyclePolicy.load()

    for policy in (v1, v2):
        assert policy.reserved_step_slots(review_required=False) == 1
        assert policy.reserved_step_slots(review_required=True) == 9
        # (False,) totals 1 + 1 = 2 — within max_children_total=16.
        assert policy.reserved_children_total((False,)) == 2
        # (False, True) totals 1 + 1 + 9 = 11 — within max_children_total=16.
        assert policy.reserved_children_total((False, True)) == 11
        # (False, True, True) totals 1 + 1 + 9 + 9 = 20 — exceeds the 16 cap.
        with pytest.raises(CooCyclePolicyError, match="plan capacity"):
            policy.reserved_children_total((False, True, True))


def test_pinned_loader_rejects_unsupported_requested_version(tmp_path: Path) -> None:
    path = _write_policy(tmp_path, V2_SOURCE)
    for bad in (True, 0, 3, "1"):
        with pytest.raises(CooCyclePolicyError, match="unsupported pinned"):
            load_pinned_coo_cycle_policy(
                bad,  # type: ignore[arg-type]
                policy_sha256=EXPECTED_POLICY_SHA256_BY_VERSION[1],
                path=path,
            )


def test_pinned_loader_rejects_malformed_and_mismatched_digest(tmp_path: Path) -> None:
    path = _write_policy(tmp_path, V1_SOURCE)
    with pytest.raises(CooCyclePolicyError, match="digest is malformed"):
        load_pinned_coo_cycle_policy(
            1, policy_sha256="not-a-real-digest", path=path
        )
    with pytest.raises(CooCyclePolicyError, match="digest is malformed"):
        load_pinned_coo_cycle_policy(1, policy_sha256=42, path=path)  # type: ignore[arg-type]
    with pytest.raises(CooCyclePolicyError, match="digest is not exact"):
        load_pinned_coo_cycle_policy(
            1, policy_sha256="0" * 64, path=path
        )
    with pytest.raises(CooCyclePolicyError, match="digest is not exact"):
        load_pinned_coo_cycle_policy(
            2,
            policy_sha256=EXPECTED_POLICY_SHA256_BY_VERSION[1],
            path=_write_policy(tmp_path, V2_SOURCE),
        )