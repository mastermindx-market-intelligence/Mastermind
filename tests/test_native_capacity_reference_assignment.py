"""Bounded C1 tests for the inert finite-reference preparation function.

Scope: the pure ``prepare_finite_reference_stanza`` constructor in
``ops.executive_os.finite_reference_assignment`` and the canonical
``validate_native_subscription_capacity_enrollment`` validator.

Every host/principal/custody coordinate below is an explicit synthetic
fixture value and randomness is replaced by an explicitly installed
deterministic ``secrets.token_hex`` fake, so the tests are fully
self-contained: no real identity, credential, store, host discovery,
network call or publication effect is involved. These tests prove nothing
about root publication or custody authority: the existing fixed
root-config publisher owns those, and they are explicitly outside this
pure function.
"""
from __future__ import annotations

import copy
import re
import secrets

import pytest

import ops.executive_os.finite_reference_assignment as finite_reference_assignment
from ops.executive_os.capacity_source_contract import (
    CapacitySourceContractError,
    validate_native_subscription_capacity_enrollment,
)
from ops.executive_os.finite_reference_assignment import (
    FiniteReferenceError,
    prepare_finite_reference_stanza,
)

ENROLLMENT_SCHEMA = "mastermind.native_subscription_capacity_enrollment/v1"
BROKER_SCHEMA = "mastermind.executive_worker_broker_config/v5"
WORKER_ID = "minimax-finite-01"
WORKER_USER = "_mastermind_minimax"
WORKER_UID = 470
WORKER_GID = 470
CONTROL_UID = 450
CONTROL_GID = 450
PROVIDER_HOME = (
    "/private/var/db/mastermind-executive/workers/"
    "minimax-finite-01/provider-home"
)
HARNESS_BINDING = "minimax-token-plan.claude-code-anthropic"
CANONICAL_FIELDS = {
    "schema_version", "host_ref", "os_principal_ref", "config_custody_ref",
    "enrollment_state", "registration_source",
}
REF_PREFIXES = {
    "host_ref": "host",
    "os_principal_ref": "principal",
    "config_custody_ref": "custody",
}
GENERATION_LIMIT = 2 ** 63

_DELETE = object()


def _hex64(digit: int) -> str:
    """Synthetic lowercase hex payload: one nibble repeated to 64 chars."""
    return f"{digit & 0xF:x}" * 64


def _ref(prefix: str, digit: int) -> str:
    return f"{prefix}-{_hex64(digit)}"


def _amend(mapping: dict, **overrides) -> dict:
    amended = dict(mapping)
    for key, value in overrides.items():
        if value is _DELETE:
            amended.pop(key, None)
        else:
            amended[key] = value
    return amended


def _registration_source(**overrides) -> dict:
    return _amend(
        {
            "release_commit": "a" * 40,
            "previous_release_commit": "b" * 40,
            "material_source_digest": _hex64(12),
            "export_sha256": _hex64(13),
        },
        **overrides,
    )


def _enrollment(state: str = "unenrolled") -> dict:
    return {
        "schema_version": ENROLLMENT_SCHEMA,
        "host_ref": _ref("host", 1),
        "os_principal_ref": _ref("principal", 2),
        "config_custody_ref": _ref("custody", 3),
        "enrollment_state": state,
        "registration_source": _registration_source(),
    }


_NO_ENROLLMENT = object()


def _previous_worker(enrollment: object = _NO_ENROLLMENT, generation: int = 1) -> dict:
    return {
        "schema_version": BROKER_SCHEMA,
        "worker_id": WORKER_ID,
        "worker_user": WORKER_USER,
        "worker_uid": WORKER_UID,
        "worker_gid": WORKER_GID,
        "control_uid": CONTROL_UID,
        "control_gid": CONTROL_GID,
        "provider_home": PROVIDER_HOME,
        "harness_binding_id": HARNESS_BINDING,
        "subscription_realm_enrollment": {
            "generation": generation,
            "binding_id": HARNESS_BINDING,
        },
        "native_capacity_enrollment": (
            _enrollment() if enrollment is _NO_ENROLLMENT else enrollment
        ),
    }


def _install_entropy(monkeypatch, fake):
    """Replace the module's ``secrets.token_hex`` with ``fake(n)``.

    Returns the list of requested bit sizes so tests can assert the exact
    number of entropy calls. Also patches a module-level ``token_hex`` if a
    future revision switches to ``from secrets import token_hex``.
    """
    calls = []

    def recorder(n):
        calls.append(n)
        return fake(n)

    monkeypatch.setattr(secrets, "token_hex", recorder)
    if hasattr(finite_reference_assignment, "token_hex"):
        monkeypatch.setattr(finite_reference_assignment, "token_hex", recorder)
    return calls


def _rotating_fake(*digits):
    payload = [_hex64(digit) for digit in digits]

    def fake(_n):
        return payload.pop(0)

    return fake


def _forbid_entropy(monkeypatch):
    def forbidden(_n):
        raise AssertionError(
            "secrets.token_hex must not be consulted on this path"
        )

    return _install_entropy(monkeypatch, forbidden)


def _assert_ref_shape(value, prefix: str) -> None:
    assert type(value) is str
    assert re.fullmatch(prefix + r"-[0-9a-f]{64}", value)


class TestCanonicalValidatorContract:
    """The canonical validator the preparation function delegates to."""

    def test_contract_error_is_a_value_error(self):
        # The preparation function wraps validator failures by catching
        # ValueError, so this subclass relationship is load-bearing.
        assert issubclass(CapacitySourceContractError, ValueError)

    @pytest.mark.parametrize("state", ["unenrolled", "enrolled"])
    def test_validator_accepts_well_formed_stanza_and_copies_source(self, state):
        stanza = _enrollment(state)
        validated = validate_native_subscription_capacity_enrollment(stanza)
        assert validated == stanza
        assert validated is not stanza
        assert validated["registration_source"] is not stanza["registration_source"]

    def test_validator_copy_is_independent(self):
        stanza = _enrollment()
        validated = validate_native_subscription_capacity_enrollment(stanza)
        validated["registration_source"]["release_commit"] = "f" * 40
        validated["host_ref"] = _ref("host", 15)
        assert stanza["registration_source"]["release_commit"] == "a" * 40
        assert stanza["host_ref"] == _ref("host", 1)

    @pytest.mark.parametrize(
        "value", [None, [], "stanza", 7, ("host", "principal"), {1, 2}]
    )
    def test_validator_rejects_non_mapping_values(self, value):
        with pytest.raises(CapacitySourceContractError):
            validate_native_subscription_capacity_enrollment(value)

    @pytest.mark.parametrize(
        "mutation",
        [
            pytest.param(lambda e: e.pop("host_ref"), id="missing-field"),
            pytest.param(lambda e: e.update(unexpected="x"), id="extra-field"),
            pytest.param(
                lambda e: e.update(schema_version=ENROLLMENT_SCHEMA.replace("v1", "v2")),
                id="wrong-schema-version",
            ),
            pytest.param(lambda e: e.update(enrollment_state="pending"), id="unknown-state"),
            pytest.param(lambda e: e.update(enrollment_state=None), id="none-state"),
            pytest.param(
                lambda e: e.update(host_ref=_ref("principal", 4)), id="swapped-prefix"
            ),
            pytest.param(lambda e: e.update(host_ref=_ref("host", 1)[:-1]), id="short-host"),
            pytest.param(
                lambda e: e.update(host_ref=_ref("host", 1).upper()), id="uppercase-host"
            ),
            pytest.param(
                lambda e: e.update(config_custody_ref=7), id="nonstring-custody"
            ),
            pytest.param(
                lambda e: e.update(
                    registration_source=_registration_source(
                        release_commit="a" * 40, previous_release_commit="a" * 40
                    )
                ),
                id="identical-commits",
            ),
            pytest.param(
                lambda e: e.update(registration_source=None), id="nonmapping-source"
            ),
        ],
    )
    def test_validator_rejects_malformed_stanzas(self, mutation):
        stanza = _enrollment()
        mutation(stanza)
        with pytest.raises(CapacitySourceContractError):
            validate_native_subscription_capacity_enrollment(stanza)


class TestInitialGeneration:
    """Fresh generation-1 publication: three synthetic, distinct coordinates."""

    def test_fresh_generation_one_draws_three_entropy_values(self, monkeypatch):
        calls = _install_entropy(monkeypatch, _rotating_fake(4, 5, 6))
        result = prepare_finite_reference_stanza(
            registration_source=_registration_source(), realm_generation=1
        )
        assert calls == [32, 32, 32]
        assert result["host_ref"] == _ref("host", 4)
        assert result["os_principal_ref"] == _ref("principal", 5)
        assert result["config_custody_ref"] == _ref("custody", 6)

    def test_fresh_references_are_well_formed_and_distinct(self, monkeypatch):
        _install_entropy(monkeypatch, _rotating_fake(4, 5, 6))
        result = prepare_finite_reference_stanza(
            registration_source=_registration_source(), realm_generation=1
        )
        assert set(result) == CANONICAL_FIELDS
        assert result["schema_version"] == ENROLLMENT_SCHEMA
        assert result["enrollment_state"] == "unenrolled"
        for key, prefix in REF_PREFIXES.items():
            _assert_ref_shape(result[key], prefix)
        assert len({result[key].split("-", 1)[1] for key in REF_PREFIXES}) == 3
        assert validate_native_subscription_capacity_enrollment(result) == result

    def test_existing_host_coordinate_is_reused_with_only_two_entropy_calls(
        self, monkeypatch
    ):
        existing = _ref("host", 9)
        calls = _install_entropy(monkeypatch, _rotating_fake(5, 6))
        result = prepare_finite_reference_stanza(
            registration_source=_registration_source(),
            realm_generation=1,
            existing_host_ref=existing,
        )
        assert calls == [32, 32]
        assert result["host_ref"] == existing
        assert result["os_principal_ref"] == _ref("principal", 5)
        assert result["config_custody_ref"] == _ref("custody", 6)
        assert result["enrollment_state"] == "unenrolled"

    @pytest.mark.parametrize(
        "existing",
        [
            pytest.param(_ref("principal", 1), id="principal-prefix"),
            pytest.param(_ref("custody", 1), id="custody-prefix"),
            pytest.param(_ref("host", 1)[:-1], id="63-hex"),
            pytest.param(_ref("host", 1) + "0", id="65-hex"),
            pytest.param("host-" + "g" * 64, id="non-hex"),
            pytest.param(_ref("host", 1).upper(), id="uppercase"),
            pytest.param("host", id="no-suffix"),
            pytest.param("host--" + _hex64(1), id="double-dash"),
            pytest.param("", id="empty"),
            pytest.param(7, id="int"),
            pytest.param(b"host-" + b"a" * 64, id="bytes"),
        ],
    )
    def test_malformed_existing_host_coordinate_refuses(self, monkeypatch, existing):
        _install_entropy(monkeypatch, _rotating_fake(4, 5, 6))
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=1,
                existing_host_ref=existing,
            )

    @pytest.mark.parametrize(
        "generation", [2, 3, GENERATION_LIMIT - 1, 0, -1, -GENERATION_LIMIT, GENERATION_LIMIT]
    )
    def test_initial_branch_only_admits_generation_one(self, monkeypatch, generation):
        _install_entropy(monkeypatch, _rotating_fake(4, 5, 6))
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(), realm_generation=generation
            )

    @pytest.mark.parametrize(
        "generation", [True, False, 1.0, "1", None, 1 + 0j]
    )
    def test_non_integer_initial_generation_refuses(self, monkeypatch, generation):
        _install_entropy(monkeypatch, _rotating_fake(4, 5, 6))
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(), realm_generation=generation
            )


class TestRetainedGeneration:
    """Predecessor supplied: all three coordinates retained, zero entropy."""

    def test_same_generation_retains_all_three_references_without_entropy(
        self, monkeypatch
    ):
        calls = _forbid_entropy(monkeypatch)
        prior = _enrollment(state="enrolled")
        worker = _previous_worker(enrollment=prior, generation=3)
        result = prepare_finite_reference_stanza(
            registration_source=_registration_source(),
            realm_generation=3,
            previous_worker=worker,
        )
        assert calls == []
        for key in REF_PREFIXES:
            assert result[key] == prior[key]
        assert result["enrollment_state"] == "unenrolled"
        assert result["schema_version"] == ENROLLMENT_SCHEMA
        assert validate_native_subscription_capacity_enrollment(result) == result

    def test_next_generation_retains_references_without_entropy(self, monkeypatch):
        calls = _forbid_entropy(monkeypatch)
        prior = _enrollment()
        worker = _previous_worker(enrollment=prior, generation=3)
        result = prepare_finite_reference_stanza(
            registration_source=_registration_source(),
            realm_generation=4,
            previous_worker=worker,
        )
        assert calls == []
        assert result["host_ref"] == prior["host_ref"]
        assert result["os_principal_ref"] == prior["os_principal_ref"]
        assert result["config_custody_ref"] == prior["config_custody_ref"]

    def test_enrolled_predecessor_yields_unenrolled_stanza_without_entropy(
        self, monkeypatch
    ):
        calls = _forbid_entropy(monkeypatch)
        prior = _enrollment(state="enrolled")
        assert prior["enrollment_state"] == "enrolled"
        result = prepare_finite_reference_stanza(
            registration_source=_registration_source(),
            realm_generation=1,
            previous_worker=_previous_worker(enrollment=prior, generation=1),
        )
        assert calls == []
        assert result["enrollment_state"] == "unenrolled"
        assert result is not prior

    def test_matching_existing_host_coordinate_accepted_without_entropy(
        self, monkeypatch
    ):
        calls = _forbid_entropy(monkeypatch)
        prior = _enrollment()
        result = prepare_finite_reference_stanza(
            registration_source=_registration_source(),
            realm_generation=2,
            previous_worker=_previous_worker(enrollment=prior, generation=1),
            existing_host_ref=prior["host_ref"],
        )
        assert calls == []
        assert result["host_ref"] == prior["host_ref"]
        assert result["os_principal_ref"] == prior["os_principal_ref"]
        assert result["config_custody_ref"] == prior["config_custody_ref"]

    @pytest.mark.parametrize(
        "foreign",
        [
            pytest.param(_ref("host", 15), id="different-well-formed-coordinate"),
            pytest.param(_ref("principal", 1), id="wrong-prefix"),
            pytest.param("host-" + "g" * 64, id="malformed"),
            pytest.param(7, id="non-string"),
        ],
    )
    def test_mismatched_existing_host_coordinate_refuses(self, monkeypatch, foreign):
        _forbid_entropy(monkeypatch)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=2,
                previous_worker=_previous_worker(generation=1),
                existing_host_ref=foreign,
            )

    def test_retained_stanza_carries_the_caller_registration_source(self, monkeypatch):
        _forbid_entropy(monkeypatch)
        worker = _previous_worker(enrollment=_enrollment(), generation=1)
        source = _registration_source(release_commit="e" * 40)
        result = prepare_finite_reference_stanza(
            registration_source=source,
            realm_generation=2,
            previous_worker=worker,
        )
        assert result["registration_source"] == source
        assert (
            result["registration_source"]
            != worker["native_capacity_enrollment"]["registration_source"]
        )

    def test_generation_one_with_predecessor_takes_the_retained_path(
        self, monkeypatch
    ):
        calls = _forbid_entropy(monkeypatch)
        prior = _enrollment()
        result = prepare_finite_reference_stanza(
            registration_source=_registration_source(),
            realm_generation=1,
            previous_worker=_previous_worker(enrollment=prior, generation=1),
        )
        assert calls == []
        assert result["host_ref"] == prior["host_ref"]


class TestGenerationTransitions:
    """Same-or-next admission; rollback, skip and overflow are refused."""

    def test_rollback_generation_refuses(self, monkeypatch):
        _forbid_entropy(monkeypatch)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=2,
                previous_worker=_previous_worker(generation=3),
            )

    def test_skipped_generation_refuses(self, monkeypatch):
        _forbid_entropy(monkeypatch)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=3,
                previous_worker=_previous_worker(generation=1),
            )

    def test_distant_generation_refuses(self, monkeypatch):
        _forbid_entropy(monkeypatch)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=10,
                previous_worker=_previous_worker(generation=1),
            )

    def test_missing_predecessor_at_generation_two_refuses(self, monkeypatch):
        _forbid_entropy(monkeypatch)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(), realm_generation=2
            )

    def test_next_generation_at_upper_boundary_is_accepted(self, monkeypatch):
        _forbid_entropy(monkeypatch)
        result = prepare_finite_reference_stanza(
            registration_source=_registration_source(),
            realm_generation=GENERATION_LIMIT - 1,
            previous_worker=_previous_worker(generation=GENERATION_LIMIT - 2),
        )
        assert result["enrollment_state"] == "unenrolled"

    def test_generation_overflow_refuses(self, monkeypatch):
        _forbid_entropy(monkeypatch)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=GENERATION_LIMIT,
                previous_worker=_previous_worker(generation=GENERATION_LIMIT - 1),
            )

    def test_boolean_generation_refuses_even_when_numerically_equal(self, monkeypatch):
        _forbid_entropy(monkeypatch)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=True,
                previous_worker=_previous_worker(generation=1),
            )

    @pytest.mark.parametrize("generation", ["2", 2.0, None])
    def test_non_integer_realm_generation_refuses_on_retained_path(
        self, monkeypatch, generation
    ):
        _forbid_entropy(monkeypatch)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=generation,
                previous_worker=_previous_worker(generation=1),
            )


class TestPredecessorQualification:
    """The fixed predecessor record must match the broker config exactly."""

    _FOREIGN = {
        "schema_version": BROKER_SCHEMA.replace("v5", "v4"),
        "worker_id": "minimax-finite-02",
        "worker_user": "_mastermind_other",
        "worker_uid": 471,
        "worker_gid": "470",
        "control_uid": 451,
        "control_gid": 450.0,
        "provider_home": PROVIDER_HOME.replace("minimax-finite-01", "minimax-finite-02"),
        "harness_binding_id": "other-plan.claude-code-anthropic",
    }

    @pytest.mark.parametrize("worker", [[], "worker", 470, (), True])
    def test_non_mapping_predecessor_refuses(self, monkeypatch, worker):
        _forbid_entropy(monkeypatch)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=1,
                previous_worker=worker,
            )

    def test_empty_predecessor_mapping_refuses(self, monkeypatch):
        _forbid_entropy(monkeypatch)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=1,
                previous_worker={},
            )

    @pytest.mark.parametrize("field", sorted(_FOREIGN))
    def test_foreign_predecessor_field_refuses(self, monkeypatch, field):
        _forbid_entropy(monkeypatch)
        worker = _previous_worker()
        worker[field] = self._FOREIGN[field]
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=1,
                previous_worker=worker,
            )

    @pytest.mark.parametrize(
        "field",
        [
            "schema_version",
            "worker_id",
            "worker_user",
            "worker_uid",
            "worker_gid",
            "control_uid",
            "control_gid",
            "provider_home",
            "harness_binding_id",
        ],
    )
    def test_missing_predecessor_field_refuses(self, monkeypatch, field):
        _forbid_entropy(monkeypatch)
        worker = _previous_worker()
        del worker[field]
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=1,
                previous_worker=worker,
            )

    @pytest.mark.parametrize(
        "field,value",
        [
            ("worker_uid", True),
            ("worker_uid", 470.0),
            ("worker_gid", False),
            ("control_uid", "450"),
        ],
    )
    def test_wrongly_typed_identity_field_refuses(self, monkeypatch, field, value):
        _forbid_entropy(monkeypatch)
        worker = _previous_worker()
        worker[field] = value
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=1,
                previous_worker=worker,
            )

    @pytest.mark.parametrize(
        "realm_block",
        [
            pytest.param(None, id="none"),
            pytest.param([], id="list"),
            pytest.param("generation", id="string"),
            pytest.param({}, id="empty"),
            pytest.param({"generation": 1}, id="missing-binding"),
            pytest.param({"binding_id": HARNESS_BINDING}, id="missing-generation"),
            pytest.param(
                {"generation": 1, "binding_id": HARNESS_BINDING, "extra": True},
                id="extra-key",
            ),
            pytest.param({"generation": 1, "binding_id": "other-binding"}, id="foreign-binding"),
            pytest.param({"generation": "1", "binding_id": HARNESS_BINDING}, id="string-generation"),
            pytest.param({"generation": True, "binding_id": HARNESS_BINDING}, id="bool-generation"),
            pytest.param({"generation": 0, "binding_id": HARNESS_BINDING}, id="zero-generation"),
            pytest.param({"generation": -5, "binding_id": HARNESS_BINDING}, id="negative-generation"),
            pytest.param(
                {"generation": GENERATION_LIMIT, "binding_id": HARNESS_BINDING},
                id="overflow-generation",
            ),
        ],
    )
    def test_malformed_subscription_realm_enrollment_refuses(
        self, monkeypatch, realm_block
    ):
        _forbid_entropy(monkeypatch)
        worker = _previous_worker(generation=1)
        worker["subscription_realm_enrollment"] = realm_block
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=1,
                previous_worker=worker,
            )


class TestPriorEnrollmentQualification:
    """The predecessor's capacity enrollment must clear the canonical validator."""

    _PRIOR_MUTATIONS = {
        "missing-host-ref": lambda e: e.pop("host_ref"),
        "extra-field": lambda e: e.update(unexpected="x"),
        "wrong-schema": lambda e: e.update(schema_version=ENROLLMENT_SCHEMA.replace("v1", "v2")),
        "unknown-state": lambda e: e.update(enrollment_state="pending"),
        "missing-state": lambda e: e.pop("enrollment_state"),
        "foreign-principal-prefix": lambda e: e.update(os_principal_ref=_ref("host", 2)),
        "short-custody": lambda e: e.update(config_custody_ref=_ref("custody", 3)[:-1]),
        "uppercase-host": lambda e: e.update(host_ref=_ref("host", 1).upper()),
        "nonstring-host": lambda e: e.update(host_ref=7),
        "nonmapping-source": lambda e: e.update(registration_source=None),
        "identical-commits": lambda e: e.update(
            registration_source=_registration_source(
                release_commit="a" * 40, previous_release_commit="a" * 40
            )
        ),
        "short-digest": lambda e: e.update(
            registration_source=_registration_source(material_source_digest="c" * 63)
        ),
    }

    def test_absent_prior_enrollment_refuses(self, monkeypatch):
        _forbid_entropy(monkeypatch)
        worker = _previous_worker(generation=1)
        del worker["native_capacity_enrollment"]
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=1,
                previous_worker=worker,
            )

    @pytest.mark.parametrize("prior", [None, [], "stanza", 7])
    def test_non_mapping_prior_enrollment_refuses(self, monkeypatch, prior):
        _forbid_entropy(monkeypatch)
        worker = _previous_worker(enrollment=prior, generation=1)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=1,
                previous_worker=worker,
            )

    @pytest.mark.parametrize("mutation_id", sorted(_PRIOR_MUTATIONS))
    def test_prior_enrollment_failing_canonical_validation_refuses(
        self, monkeypatch, mutation_id
    ):
        _forbid_entropy(monkeypatch)
        prior = _enrollment(state="enrolled")
        self._PRIOR_MUTATIONS[mutation_id](prior)
        worker = _previous_worker(enrollment=prior, generation=1)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=1,
                previous_worker=worker,
            )

    @pytest.mark.parametrize(
        "overrides",
        [
            pytest.param(
                {"os_principal_ref": _ref("principal", 1)}, id="host-equals-principal"
            ),
            pytest.param(
                {"config_custody_ref": _ref("custody", 1)}, id="host-equals-custody"
            ),
            pytest.param(
                {
                    "os_principal_ref": _ref("principal", 1),
                    "config_custody_ref": _ref("custody", 1),
                },
                id="all-three-aliased",
            ),
        ],
    )
    def test_prior_with_colliding_reference_suffixes_refuses(
        self, monkeypatch, overrides
    ):
        # Each coordinate is individually well formed and the stanza clears the
        # canonical validator, but the entropy-aliasing guard must still refuse.
        _forbid_entropy(monkeypatch)
        prior = _amend(_enrollment("enrolled"), **overrides)
        assert (
            validate_native_subscription_capacity_enrollment(prior) is not None
        )
        worker = _previous_worker(enrollment=prior, generation=1)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=1,
                previous_worker=worker,
            )


class TestRegistrationSourceContract:
    """Registration material is validated and copied, never mutated."""

    _SOURCE_MUTATIONS = {
        "empty-mapping": lambda s: s.clear(),
        "missing-export": lambda s: s.pop("export_sha256"),
        "extra-field": lambda s: s.update(note="x"),
        "short-commit": lambda s: s.update(release_commit="a" * 39),
        "long-commit": lambda s: s.update(release_commit="a" * 41),
        "non-hex-commit": lambda s: s.update(release_commit="g" * 40),
        "nonstring-commit": lambda s: s.update(release_commit=123),
        "identical-commits": lambda s: s.update(previous_release_commit="a" * 40),
        "short-previous": lambda s: s.update(previous_release_commit="b" * 39),
        "short-digest": lambda s: s.update(material_source_digest="c" * 63),
        "long-digest": lambda s: s.update(material_source_digest="c" * 65),
        "uppercase-digest": lambda s: s.update(material_source_digest="C" * 64),
        "empty-digest": lambda s: s.update(material_source_digest=""),
        "nonstring-export": lambda s: s.update(export_sha256=None),
    }

    @pytest.mark.parametrize("mutation_id", sorted(_SOURCE_MUTATIONS))
    def test_malformed_registration_source_refuses_on_initial_path(
        self, monkeypatch, mutation_id
    ):
        _install_entropy(monkeypatch, _rotating_fake(4, 5, 6))
        source = _registration_source()
        self._SOURCE_MUTATIONS[mutation_id](source)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=source, realm_generation=1
            )

    def test_malformed_registration_source_refuses_on_retained_path(self, monkeypatch):
        _forbid_entropy(monkeypatch)
        source = _registration_source(
            release_commit="a" * 40, previous_release_commit="a" * 40
        )
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=source,
                realm_generation=2,
                previous_worker=_previous_worker(generation=1),
            )

    @pytest.mark.parametrize("source", [None, "release", [], 7, tuple()])
    def test_non_mapping_registration_source_refuses(self, monkeypatch, source):
        _install_entropy(monkeypatch, _rotating_fake(4, 5, 6))
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=source, realm_generation=1
            )

    def test_returned_registration_source_is_an_independent_copy(self, monkeypatch):
        _install_entropy(monkeypatch, _rotating_fake(4, 5, 6))
        source = _registration_source()
        result = prepare_finite_reference_stanza(
            registration_source=source, realm_generation=1
        )
        assert result["registration_source"] == source
        assert result["registration_source"] is not source
        result["registration_source"]["release_commit"] = "f" * 40
        result["registration_source"]["material_source_digest"] = "f" * 64
        assert source["release_commit"] == "a" * 40
        assert source["material_source_digest"] == _hex64(12)


class TestEntropyRobustness:
    """A broken randomness source must fail loudly, never alias coordinates."""

    def test_entropy_provider_failure_propagates(self, monkeypatch):
        def broken(_n):
            raise RuntimeError("synthetic entropy outage")

        _install_entropy(monkeypatch, broken)
        with pytest.raises(RuntimeError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(), realm_generation=1
            )

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param("", id="empty"),
            pytest.param("a" * 63, id="short"),
            pytest.param("a" * 65, id="long"),
            pytest.param("a" * 32, id="half-length"),
        ],
    )
    def test_entropy_wrong_shape_refuses(self, monkeypatch, payload):
        _install_entropy(monkeypatch, lambda _n, payload=payload: payload)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(), realm_generation=1
            )

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param("g" * 64, id="non-hex"),
            pytest.param("A" * 64, id="uppercase"),
            pytest.param("0x" + "a" * 62, id="prefixed"),
        ],
    )
    def test_entropy_non_hex_payload_refuses(self, monkeypatch, payload):
        _install_entropy(monkeypatch, lambda _n, payload=payload: payload)
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(), realm_generation=1
            )

    @pytest.mark.parametrize(
        "payload",
        [pytest.param(32, id="int"), pytest.param(b"a" * 64, id="bytes"),
         pytest.param(None, id="none"), pytest.param(object(), id="object")],
    )
    def test_entropy_wrong_type_raises_without_producing_a_stanza(
        self, monkeypatch, payload
    ):
        # A type-broken entropy source may surface as TypeError (string
        # concatenation) or be refused as a ValueError; either way no stanza
        # may be produced.
        _install_entropy(monkeypatch, lambda _n, payload=payload: payload)
        with pytest.raises((TypeError, ValueError)):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(), realm_generation=1
            )

    def test_constant_entropy_aliased_across_all_three_refs_refuses(
        self, monkeypatch
    ):
        _install_entropy(monkeypatch, lambda _n: _hex64(4))
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(), realm_generation=1
            )

    def test_partial_entropy_aliasing_refuses(self, monkeypatch):
        # host and custody receive the same payload while principal differs.
        payloads = iter([_hex64(4), _hex64(5), _hex64(4)])
        _install_entropy(monkeypatch, lambda _n: next(payloads))
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(), realm_generation=1
            )

    def test_entropy_colliding_with_the_admitted_host_refuses(self, monkeypatch):
        existing = _ref("host", 4)
        _install_entropy(monkeypatch, lambda _n: _hex64(4))
        with pytest.raises(FiniteReferenceError):
            prepare_finite_reference_stanza(
                registration_source=_registration_source(),
                realm_generation=1,
                existing_host_ref=existing,
            )


class TestPurityAndCopySemantics:
    """No input mutation; outputs share no mutable state with inputs."""

    def test_initial_call_does_not_mutate_registration_source(self, monkeypatch):
        _install_entropy(monkeypatch, _rotating_fake(4, 5, 6))
        source = _registration_source()
        snapshot = copy.deepcopy(source)
        result = prepare_finite_reference_stanza(
            registration_source=source, realm_generation=1
        )
        assert source == snapshot
        assert result["registration_source"] == snapshot

    def test_retained_call_does_not_mutate_predecessor_or_source(self, monkeypatch):
        _forbid_entropy(monkeypatch)
        worker = _previous_worker(enrollment=_enrollment(state="enrolled"), generation=1)
        worker_snapshot = copy.deepcopy(worker)
        source = _registration_source()
        source_snapshot = copy.deepcopy(source)
        result = prepare_finite_reference_stanza(
            registration_source=source,
            realm_generation=2,
            previous_worker=worker,
        )
        assert worker == worker_snapshot
        assert source == source_snapshot
        prior = worker["native_capacity_enrollment"]
        assert prior["enrollment_state"] == "enrolled"
        assert result["enrollment_state"] == "unenrolled"
        assert result is not prior
        assert result["registration_source"] is not source
        # Mutating the returned stanza must not reach the predecessor record
        # or the caller's registration material.
        result["host_ref"] = _ref("host", 15)
        result["registration_source"]["release_commit"] = "e" * 40
        assert worker == worker_snapshot
        assert source == source_snapshot

    def test_repeated_calls_are_independent(self, monkeypatch):
        state = {"counter": 0}

        def sequenced(_n):
            state["counter"] += 1
            return f"{state['counter']:064x}"

        calls = _install_entropy(monkeypatch, sequenced)
        first = prepare_finite_reference_stanza(
            registration_source=_registration_source(), realm_generation=1
        )
        second = prepare_finite_reference_stanza(
            registration_source=_registration_source(), realm_generation=1
        )
        assert calls == [32] * 6
        assert first["host_ref"] != second["host_ref"]
        assert first["os_principal_ref"] != second["os_principal_ref"]
        assert first["config_custody_ref"] != second["config_custody_ref"]
        assert first["registration_source"] is not second["registration_source"]


class TestInterfaceContract:
    def test_arguments_are_keyword_only(self):
        with pytest.raises(TypeError):
            prepare_finite_reference_stanza(_registration_source(), 1)
